"""The task that hands an email to a mail server, and what it does when that fails.

**Sending moved off the request path, and this is where the part that replaced it
is tested.** ``test_mail`` and ``test_dispatch`` cover the composing half -- the
right server, the right sender, a truthful row. What is new is the half that runs
in a worker: whether a refused message is tried again, whether it is tried again
for the *right* refusals, and whether the row settles honestly at the end either
way.

Three things are worth defending here, and none of them is visible when it
breaks.

**A permanent refusal must not be retried.** ``550 no such user`` is a final
answer. Retried, it is five entries in somebody's abuse log and -- if the
refusal is per-recipient and one attempt does land -- five copies of the same
sign-in code. Nothing about that shows up in the row, which reads ``failed``
either way.

**A transient refusal must be retried, and must settle when the retries run
out.** The failure the platform will actually meet is a provider that is briefly
slow, and retrying is the whole reason a queue is worth its cost. But a row that
was retried and then abandoned has to end on ``failed`` rather than sitting on
``queued`` waiting for an attempt nobody is going to make -- ``queued`` is the
signal that no worker is consuming the queue, and a row that lies about that
hides an outage.

**A redelivered task must not send twice.** ``acks_late`` is off for this task
precisely to prevent that, but the guard in ``mail.deliver`` is what covers a
task published twice, and a duplicate sign-in code is indistinguishable from a
correct one at the mailbox.

**Retries are pinned off by the test runner**, so every test here that wants
them says so with ``override_settings``. ``f2c/test_runner.py`` explains why the
default is zero: run eagerly, retries are immediate and a test that patched the
backend to fail would hand over six times before reaching its assertion.
"""
import smtplib
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings

from app.core.storefronts.mail import transient
from app.core.storefronts.models import EmailDispatch, Storefront
from app.core.storefronts.tasks import (
    DELIVER_EMAIL,
    _countdown,
    deliver_email,
)
from f2c.testing import make_account

SENDERS = {
    'club': 'no-reply@club.example.co.za',
    'market': 'no-reply@market.example.co.za',
}


def smtp_error(code, message=b'nope'):
    """An ``SMTPResponseException`` carrying a server's own verdict."""
    return smtplib.SMTPResponseException(code, message)


class TransientClassificationTests(TestCase):
    """Which failures are worth a second attempt. See ``mail.transient``.

    A pure function over exceptions, so it needs no database and no mail server
    -- which is the point of it being a function at all rather than a branch
    inside the task.
    """

    def test_a_4xx_response_is_transient(self):
        """SMTP's own "try later". A full mailbox is the common one."""
        self.assertTrue(transient(smtp_error(452, b'insufficient storage')))

    def test_a_5xx_response_is_permanent(self):
        """The refusal this whole function exists to stop retrying."""
        self.assertFalse(transient(smtp_error(550, b'no such user')))

    def test_a_bad_password_is_permanent(self):
        """``535`` is 5xx and credentials do not fix themselves. Retrying a
        rejected login five times a message is how an account gets locked."""
        self.assertFalse(
            transient(smtplib.SMTPAuthenticationError(535, b'auth failed'))
        )

    def test_a_refusal_with_no_code_is_transient(self):
        """``SMTPConnectError`` and friends arrive with a zero, because no server
        got far enough to judge the message. That is transport, not a verdict --
        and reading a falsy code as "not 4xx" would make the archetypal retryable
        failure permanent."""
        self.assertTrue(transient(smtplib.SMTPConnectError(0, b'')))

    def test_a_dropped_connection_is_transient(self):
        self.assertTrue(transient(smtplib.SMTPServerDisconnected('closed')))

    def test_a_socket_failure_is_transient(self):
        self.assertTrue(transient(ConnectionRefusedError('refused')))
        self.assertTrue(transient(TimeoutError('timed out')))

    def test_recipients_refused_with_4xx_is_transient(self):
        self.assertTrue(
            transient(
                smtplib.SMTPRecipientsRefused(
                    {'member@example.com': (450, b'try later')}
                )
            )
        )

    def test_recipients_refused_with_5xx_is_permanent(self):
        self.assertFalse(
            transient(
                smtplib.SMTPRecipientsRefused(
                    {'member@example.com': (550, b'no such user')}
                )
            )
        )

    def test_a_rate_limited_http_backend_is_transient(self):
        """For the ESP backend that is not configured yet. Anymail raises with a
        ``status_code``, and treating ``429`` as a bounce would turn a rate limit
        into permanent send failures at exactly the moment volume is highest."""

        class ApiError(Exception):
            status_code = 429

        self.assertTrue(transient(ApiError()))

    def test_a_rejected_http_request_is_permanent(self):
        class ApiError(Exception):
            status_code = 422

        self.assertFalse(transient(ApiError()))

    def test_a_programming_error_is_not_retried(self):
        """A ``TypeError`` from a template is a bug, and a bug retried five times
        is the same bug with a longer log."""
        self.assertFalse(transient(TypeError('body is not a string')))
        self.assertFalse(transient(ValueError('no address')))


class BackoffTests(TestCase):
    def test_it_doubles_from_the_base(self):
        self.assertEqual(30, _countdown(0, 30, 600))
        self.assertEqual(60, _countdown(1, 30, 600))
        self.assertEqual(120, _countdown(2, 30, 600))

    def test_it_is_capped(self):
        """Uncapped, the fifth retry of a doubling sequence is far past the
        window in which a sign-in code is any use to the member waiting."""
        self.assertEqual(600, _countdown(10, 30, 600))


@override_settings(STOREFRONT_FROM_EMAIL=SENDERS)
class DeliverEmailTaskTests(TestCase):
    """The task against a row, called directly rather than through a send.

    Direct because the subject is the task: what it does with a row that is
    missing, already sent, or refused. ``test_dispatch`` covers the path from a
    caller through to a delivered message.
    """

    def setUp(self):
        self.member = make_account('member@example.com')
        mail.outbox.clear()

    def queue(self, **overrides):
        options = {
            'kind': EmailDispatch.Kind.LOGIN_CODE,
            'storefront': Storefront.CLUB,
            'recipient': self.member,
            'subject': 'Your sign-in code',
            'body': 'Your code is 123456',
            'trigger': EmailDispatch.Trigger.MEMBER,
        }
        options.update(overrides)
        return EmailDispatch.objects.queue(**options)

    def test_the_task_name_is_the_one_the_route_matches(self):
        """**The route is keyed on this string and a mismatch does not raise.**

        ``CELERY_TASK_ROUTES`` maps ``storefronts.deliver_email`` onto the
        ``mail`` queue. A task registered under any other name would silently
        land on the default queue instead -- behind the nightly purges, which is
        the arrangement the two queues exist to prevent -- and every test here
        would still pass, because eager execution never consults a queue.
        """
        self.assertEqual('storefronts.deliver_email', DELIVER_EMAIL)
        self.assertEqual(DELIVER_EMAIL, deliver_email.name)

    def test_it_sends_the_message_the_row_carries(self):
        dispatch = self.queue()

        deliver_email(str(dispatch.pk))

        self.assertEqual(1, len(mail.outbox))
        message = mail.outbox[0]
        self.assertEqual(['member@example.com'], message.to)
        self.assertEqual('Your sign-in code', message.subject)
        self.assertIn('123456', message.body)
        self.assertEqual('club', message.sent_using)

    def test_a_successful_send_settles_the_row_and_erases_the_text(self):
        dispatch = self.queue()

        deliver_email(str(dispatch.pk))

        dispatch.refresh_from_db()
        self.assertEqual(EmailDispatch.SendStatus.SENT, dispatch.send_status)
        self.assertIsNotNone(dispatch.sent_at)
        self.assertEqual('', dispatch.body)
        self.assertEqual(1, dispatch.attempts)

    def test_a_row_that_no_longer_exists_is_not_an_error(self):
        """The retention purge deletes send records nightly, so a task that
        outlived its own row is an ordinary consequence of the window rather than
        a fault. Retrying would only rediscover that the row is gone."""
        missing = '01900000-0000-7000-8000-000000000000'

        self.assertIsNone(deliver_email(missing))
        self.assertEqual(0, len(mail.outbox))

    def test_a_row_already_sent_is_not_sent_again(self):
        """**A duplicate sign-in code is indistinguishable from a correct one.**

        ``acks_late`` is off for this task so a killed worker cannot cause this,
        but a task published twice still can, and the guard is what covers it.
        """
        dispatch = self.queue()
        deliver_email(str(dispatch.pk))
        self.assertEqual(1, len(mail.outbox))

        with self.assertLogs('app.core.storefronts.mail', level='WARNING'):
            deliver_email(str(dispatch.pk))

        self.assertEqual(1, len(mail.outbox))

    def test_a_permanent_refusal_fails_the_row_without_retrying(self):
        """**The assertion the retry policy exists for.**

        Retries are on for this test, so a retry would be observable as a second
        hand-over. There must not be one: the server has given a final answer.
        """
        dispatch = self.queue()

        with override_settings(EMAIL_SEND_MAX_RETRIES=5):
            with patch(
                'django.core.mail.EmailMessage.send',
                side_effect=smtp_error(550, b'no such user'),
            ) as send:
                with self.assertLogs(
                    'app.core.storefronts.tasks', level='ERROR'
                ):
                    deliver_email(str(dispatch.pk))

        self.assertEqual(1, send.call_count)
        dispatch.refresh_from_db()
        self.assertEqual(EmailDispatch.SendStatus.FAILED, dispatch.send_status)
        self.assertEqual(1, dispatch.attempts)
        self.assertEqual('', dispatch.body)

    def test_the_last_attempt_fails_the_row_rather_than_leaving_it_queued(self):
        """A row abandoned on ``queued`` would hide the one outage nothing else
        reports.

        ``pending()`` is what says "no worker is consuming the mail queue".
        Retried-and-given-up rows sitting in it would make that query useless,
        and an operator watching ``failed()`` would see nothing at all.
        """
        dispatch = self.queue()

        with patch(
            'django.core.mail.EmailMessage.send',
            side_effect=smtplib.SMTPServerDisconnected('closed'),
        ):
            with self.assertLogs('app.core.storefronts.tasks', level='ERROR'):
                # Retries are off under the test runner, so this first attempt is
                # also the final one -- which is the state being asserted.
                deliver_email(str(dispatch.pk))

        dispatch.refresh_from_db()
        self.assertEqual(EmailDispatch.SendStatus.FAILED, dispatch.send_status)
        self.assertIn('closed', dispatch.send_error)
        self.assertEqual('', dispatch.body)

    def test_a_transient_refusal_with_retries_left_keeps_the_row_sendable(self):
        """**Retried, so the row must stay ``queued`` and must keep its body.**

        The status matters because ``failed`` is terminal by contract -- it is
        what ``failed()`` reports to an operator -- and a message still queued
        for another attempt is not a failure yet. The body matters more
        prosaically: the next attempt has nothing to send without it.

        ``self.retry`` is patched rather than the countdown waited out. What is
        under test is the state the row is left in and the fact that a retry was
        asked for at all; Celery's own scheduling is Celery's.
        """
        dispatch = self.queue()
        retry = RuntimeError('retry scheduled')

        with override_settings(EMAIL_SEND_MAX_RETRIES=5):
            with patch(
                'django.core.mail.EmailMessage.send',
                side_effect=smtplib.SMTPServerDisconnected('closed'),
            ):
                with patch.object(
                    deliver_email, 'retry', side_effect=retry
                ) as asked:
                    with self.assertRaises(RuntimeError):
                        deliver_email(str(dispatch.pk))

        self.assertEqual(1, asked.call_count)
        self.assertEqual(30, asked.call_args.kwargs['countdown'])

        dispatch.refresh_from_db()
        self.assertEqual(EmailDispatch.SendStatus.QUEUED, dispatch.send_status)
        self.assertEqual('Your code is 123456', dispatch.body)
        self.assertIn('closed', dispatch.send_error)
        self.assertEqual(1, dispatch.attempts)

    def test_attempts_accumulate_across_retries(self):
        """``send_error`` holds only the most recent failure, so without this
        column "refused once then accepted" and "refused four times then
        accepted" are the same row -- a blip and a provider worth looking at."""
        dispatch = self.queue()

        with override_settings(EMAIL_SEND_MAX_RETRIES=5):
            with patch(
                'django.core.mail.EmailMessage.send',
                side_effect=smtplib.SMTPServerDisconnected('closed'),
            ):
                with patch.object(
                    deliver_email, 'retry', side_effect=RuntimeError('retry')
                ):
                    for _ in range(3):
                        with self.assertRaises(RuntimeError):
                            deliver_email(str(dispatch.pk))

        dispatch.refresh_from_db()
        self.assertEqual(3, dispatch.attempts)
        self.assertEqual(EmailDispatch.SendStatus.QUEUED, dispatch.send_status)

    def test_an_account_erased_before_the_send_fails_the_row(self):
        """**A failure mode the queue created, and it was a bug before this test.**

        Composing and sending used to be one statement, so there was no window
        in which an account could lose its address in between. There is now, and
        POPIA erasure is exactly what happens in it.

        The row has to settle. Left on ``queued`` it would sit in ``pending()``
        forever -- the query that means "no worker is consuming the mail queue",
        which is the one outage nothing else on this platform reports. One
        un-sendable message must not be able to look like that. Not retried
        either: waiting does not restore an erased address.
        """
        dispatch = self.queue()
        self.member.email = None
        self.member.save(update_fields=['email'])

        with self.assertLogs('app.core.storefronts.mail', level='WARNING'):
            deliver_email(str(dispatch.pk))

        dispatch.refresh_from_db()
        self.assertEqual(EmailDispatch.SendStatus.FAILED, dispatch.send_status)
        self.assertEqual(0, len(mail.outbox))
        self.assertEqual(0, EmailDispatch.objects.pending().count())
        # The code does not outlive the account it was addressed to.
        self.assertEqual('', dispatch.body)

    def test_the_market_sends_as_the_market_from_a_row(self):
        """The storefront survives the trip through the queue. A code that left
        by the store's provider under the club's name is indistinguishable from a
        phishing attempt -- ``mail`` -- and the worker is now where that is
        decided."""
        dispatch = self.queue(storefront=Storefront.MARKET)

        deliver_email(str(dispatch.pk))

        message = mail.outbox[0]
        self.assertEqual('market', message.sent_using)
        self.assertEqual(SENDERS['market'], message.from_email)
