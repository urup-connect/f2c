"""Tests for the record that an email was sent, and for what it refuses to claim.

Two things are being defended here, and only one of them is ordinary.

The ordinary one is that a send leaves a truthful row: the right member, the
right kind, a status that matches what the mail server did, and a timestamp
beside it.

The other is **what the row does not say.** ``delivery_status`` and
``read_status`` stay at "not reported" and "not tracked" on every send this
deployment makes, because SMTP does not report delivery and no open beacon is
embedded. A future change that starts defaulting either of those to something
more definite -- a ``delivered`` on a successful hand-over, say, because the two
look alike from the inside -- would make the log assert something nothing knows,
and it is precisely the sort of change that looks like an improvement in a diff.
The assertions below are what would fail.
"""
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from app.core.storefronts.mail import send_storefront_email
from app.core.storefronts.models import EmailDispatch, Storefront
from f2c.testing import make_account

SENDERS = {
    'club': 'no-reply@club.example.co.za',
    'market': 'no-reply@market.example.co.za',
}


@override_settings(STOREFRONT_FROM_EMAIL=SENDERS)
class RecordingASendTests(TestCase):
    def setUp(self):
        self.member = make_account('member@example.com')
        self.operator = make_account('operator@example.com')
        mail.outbox.clear()

    def send(self, **overrides):
        options = {
            'storefront': Storefront.CLUB,
            'kind': EmailDispatch.Kind.LOGIN_CODE,
            'recipient': self.member,
            'subject': 'Your sign-in code',
            'body': 'Body',
        }
        options.update(overrides)
        send_storefront_email(**options)
        return EmailDispatch.objects.get()

    def test_a_send_leaves_exactly_one_row(self):
        self.send()

        self.assertEqual(1, EmailDispatch.objects.count())

    def test_it_records_who_it_went_to_and_what_it_was(self):
        dispatch = self.send()

        self.assertEqual(self.member, dispatch.recipient)
        self.assertEqual(EmailDispatch.Kind.LOGIN_CODE, dispatch.kind)
        self.assertEqual(Storefront.CLUB, dispatch.storefront)
        self.assertEqual('Your sign-in code', dispatch.subject)

    def test_a_successful_send_is_sent_with_a_timestamp(self):
        dispatch = self.send()

        self.assertEqual(EmailDispatch.SendStatus.SENT, dispatch.send_status)
        self.assertIsNotNone(dispatch.sent_at)
        self.assertEqual('', dispatch.send_error)

    def test_delivery_is_not_claimed_by_a_successful_send(self):
        """**The assertion this module exists for.** A mail server accepting a
        message is not the message arriving, and the log must not blur them."""
        dispatch = self.send()

        self.assertEqual(
            EmailDispatch.DeliveryStatus.UNKNOWN, dispatch.delivery_status
        )
        self.assertIsNone(dispatch.delivered_at)

    def test_reading_is_recorded_as_untracked_rather_than_as_unread(self):
        """"Not tracked" and "not read" are different answers to a support
        question, and only the first one is true here."""
        dispatch = self.send()

        self.assertEqual(
            EmailDispatch.ReadStatus.NOT_TRACKED, dispatch.read_status
        )
        self.assertIsNone(dispatch.read_at)

    def test_no_provider_message_id_is_invented(self):
        """SMTP issues none, and a made-up one would match a stranger's webhook."""
        self.assertEqual('', self.send().provider_message_id)

    def test_the_body_is_not_stored(self):
        """A sign-in code lives in the body. Nothing here should be able to read
        it back out of the database."""
        dispatch = self.send(body='Your code is 123456')

        self.assertNotIn('123456', dispatch.subject)
        self.assertFalse(
            any(
                '123456' in str(value)
                for value in dispatch.__dict__.values()
            )
        )

    def test_the_recipients_address_is_not_stored_on_the_row(self):
        """The account is the address -- see ``EmailDispatch``. This is what
        makes erasure de-identify the send history without a scrub step."""
        dispatch = self.send()

        self.assertNotIn(
            'email', {field.name for field in dispatch._meta.fields}
        )
        self.assertFalse(
            any(
                'member@example.com' in str(value)
                for value in dispatch.__dict__.values()
            )
        )

    def test_an_overlong_subject_is_truncated_rather_than_raising(self):
        """A subject is descriptive, not load-bearing. Losing the tail of one is
        better than losing the send, and better than a 500 on a sign-in."""
        dispatch = self.send(subject='x' * 400)

        self.assertEqual(255, len(dispatch.subject))
        self.assertEqual(1, len(mail.outbox))


@override_settings(STOREFRONT_FROM_EMAIL=SENDERS)
class ProvenanceTests(TestCase):
    def setUp(self):
        self.member = make_account('member@example.com')
        self.operator = make_account('operator@example.com')
        mail.outbox.clear()

    def send(self, **overrides):
        options = {
            'storefront': Storefront.CLUB,
            'kind': EmailDispatch.Kind.MEMBERSHIP_SUSPENDED,
            'recipient': self.member,
            'subject': 'Subject',
            'body': 'Body',
        }
        options.update(overrides)
        send_storefront_email(**options)
        return EmailDispatch.objects.get()

    def test_a_send_with_nothing_said_about_it_is_the_platforms_own(self):
        """The default, and the right one: a caller that names no cause is a
        scheduled job or an internal flow."""
        dispatch = self.send()

        self.assertEqual(EmailDispatch.Trigger.SYSTEM, dispatch.trigger)
        self.assertIsNone(dispatch.triggered_by)

    def test_an_operators_send_names_the_operator(self):
        dispatch = self.send(
            trigger=EmailDispatch.Trigger.OPERATOR, triggered_by=self.operator
        )

        self.assertEqual(EmailDispatch.Trigger.OPERATOR, dispatch.trigger)
        self.assertEqual(self.operator, dispatch.triggered_by)

    def test_a_members_request_can_name_nobody_and_still_say_so(self):
        """A sign-in code is requested by somebody who is not signed in. The
        trigger is what keeps that blank from reading as a system send."""
        dispatch = self.send(
            kind=EmailDispatch.Kind.LOGIN_CODE,
            trigger=EmailDispatch.Trigger.MEMBER,
        )

        self.assertEqual(EmailDispatch.Trigger.MEMBER, dispatch.trigger)
        self.assertIsNone(dispatch.triggered_by)

    def test_erasing_the_operator_keeps_the_record_of_the_send(self):
        """``SET_NULL``: losing the operator must not lose the fact that the
        member was written to. The same call ``StorefrontStaff`` makes."""
        dispatch = self.send(
            trigger=EmailDispatch.Trigger.OPERATOR, triggered_by=self.operator
        )
        self.operator.delete()

        dispatch.refresh_from_db()
        self.assertIsNone(dispatch.triggered_by)
        self.assertEqual(EmailDispatch.Trigger.OPERATOR, dispatch.trigger)


@override_settings(STOREFRONT_FROM_EMAIL=SENDERS)
class FailureTests(TestCase):
    def setUp(self):
        self.member = make_account('member@example.com')
        mail.outbox.clear()

    def send(self):
        send_storefront_email(
            storefront=Storefront.CLUB,
            kind=EmailDispatch.Kind.LOGIN_CODE,
            recipient=self.member,
            subject='Subject',
            body='Body',
        )

    def test_a_refused_send_is_recorded_as_failed_with_the_reason(self):
        """The row outlives the exception, which is the point: a 503 tells the
        member to try again and tells an operator nothing."""
        with patch(
            'django.core.mail.EmailMessage.send',
            side_effect=OSError('mail server is not answering'),
        ):
            with self.assertRaises(OSError):
                self.send()

        dispatch = EmailDispatch.objects.get()
        self.assertEqual(EmailDispatch.SendStatus.FAILED, dispatch.send_status)
        self.assertIn('not answering', dispatch.send_error)
        self.assertIsNone(dispatch.sent_at)

    def test_the_exception_still_reaches_the_caller(self):
        """Logging a failure is not handling it. ``otp`` answers 503 off this."""
        with patch(
            'django.core.mail.EmailMessage.send', side_effect=OSError('nope')
        ):
            with self.assertRaises(OSError):
                self.send()

    def test_a_backend_that_sends_nothing_quietly_is_recorded_as_failed(self):
        """``send()`` returning 0 without raising -- ``fail_silently``, or a
        backend with the same habit. Nothing went out, so the row must not
        say it did."""
        with patch('django.core.mail.EmailMessage.send', return_value=0):
            self.send()

        dispatch = EmailDispatch.objects.get()
        self.assertEqual(EmailDispatch.SendStatus.FAILED, dispatch.send_status)
        self.assertIsNone(dispatch.sent_at)

    def test_a_row_that_cannot_be_updated_does_not_undo_a_send(self):
        """The asymmetry in ``send_storefront_email``. The message is already
        with the mail server; raising here would invite a second one."""
        with patch.object(
            EmailDispatch, 'mark_sent', side_effect=OSError('database gone')
        ):
            with self.assertLogs('app.core.storefronts.mail', level='ERROR'):
                self.send()

        self.assertEqual(1, len(mail.outbox))


class ProviderEventTests(TestCase):
    """The half of the loop no provider is wired up to close yet.

    Built now because the schema and the handler are the part that needs
    deciding; a provider is configuration. These tests are what a webhook
    handler will be written against.
    """

    def setUp(self):
        self.member = make_account('member@example.com')
        self.dispatch = EmailDispatch.objects.create(
            kind=EmailDispatch.Kind.PAYMENT_LINK,
            storefront=Storefront.CLUB,
            recipient=self.member,
            subject='Subject',
            trigger=EmailDispatch.Trigger.MEMBER,
            send_status=EmailDispatch.SendStatus.SENT,
            sent_at=timezone.now(),
            provider_message_id='abc-123',
        )

    def test_a_delivery_event_closes_the_second_stage(self):
        EmailDispatch.apply_provider_event('abc-123', 'delivered')

        self.dispatch.refresh_from_db()
        self.assertEqual(
            EmailDispatch.DeliveryStatus.DELIVERED, self.dispatch.delivery_status
        )
        self.assertIsNotNone(self.dispatch.delivered_at)

    def test_a_bounce_records_what_the_provider_said(self):
        EmailDispatch.apply_provider_event(
            'abc-123', 'bounced', detail='550 mailbox unavailable'
        )

        self.dispatch.refresh_from_db()
        self.assertEqual(
            EmailDispatch.DeliveryStatus.BOUNCED, self.dispatch.delivery_status
        )
        self.assertIn('550', self.dispatch.delivery_detail)

    def test_an_open_event_closes_the_third_stage(self):
        EmailDispatch.apply_provider_event('abc-123', 'opened')

        self.dispatch.refresh_from_db()
        self.assertEqual(
            EmailDispatch.ReadStatus.READ, self.dispatch.read_status
        )
        self.assertIsNotNone(self.dispatch.read_at)

    def test_an_unknown_event_is_ignored_rather_than_raised_on(self):
        """A webhook that 500s on an event it does not recognise is retried by
        the provider forever."""
        self.assertIsNone(
            EmailDispatch.apply_provider_event('abc-123', 'clicked')
        )

    def test_an_unknown_message_id_is_ignored(self):
        self.assertIsNone(
            EmailDispatch.apply_provider_event('not-a-message', 'delivered')
        )

    def test_a_blank_message_id_matches_nothing(self):
        """Every row on an SMTP deployment has a blank id. A webhook quoting one
        must not be answered by the oldest untracked send."""
        EmailDispatch.objects.filter(pk=self.dispatch.pk).update(
            provider_message_id=''
        )

        self.assertIsNone(EmailDispatch.apply_provider_event('', 'delivered'))
        self.assertIsNone(EmailDispatch.apply_provider_event(None, 'delivered'))


class QuerySetTests(TestCase):
    def setUp(self):
        self.member = make_account('member@example.com')
        self.other = make_account('other@example.com')

    def make(self, **overrides):
        options = {
            'kind': EmailDispatch.Kind.LOGIN_CODE,
            'storefront': Storefront.CLUB,
            'recipient': self.member,
            'subject': 'Subject',
            'trigger': EmailDispatch.Trigger.MEMBER,
            'send_status': EmailDispatch.SendStatus.SENT,
            'sent_at': timezone.now(),
        }
        options.update(overrides)
        return EmailDispatch.objects.create(**options)

    def test_for_recipient_answers_the_support_question(self):
        mine = self.make()
        self.make(recipient=self.other)

        self.assertEqual(
            [mine], list(EmailDispatch.objects.for_recipient(self.member))
        )

    def test_failed_finds_what_never_left(self):
        broken = self.make(
            send_status=EmailDispatch.SendStatus.FAILED, sent_at=None
        )
        self.make()

        self.assertEqual([broken], list(EmailDispatch.objects.failed()))

    def test_unconfirmed_is_every_sent_row_until_a_provider_reports(self):
        sent = self.make()
        self.make(
            delivery_status=EmailDispatch.DeliveryStatus.DELIVERED,
            delivered_at=timezone.now(),
        )

        self.assertEqual([sent], list(EmailDispatch.objects.unconfirmed()))

    def test_queued_before_ages_a_failed_send_too(self):
        """Keyed on ``queued_at``, so a row that never got past ``queued`` is
        still purgeable. Keying on ``sent_at`` would keep failures forever."""
        old = self.make(
            send_status=EmailDispatch.SendStatus.QUEUED, sent_at=None
        )
        EmailDispatch.objects.filter(pk=old.pk).update(
            queued_at=timezone.now() - timedelta(days=400)
        )
        self.make()

        cutoff = timezone.now() - timedelta(days=365)
        self.assertEqual(
            [old.pk],
            list(
                EmailDispatch.objects.queued_before(cutoff).values_list(
                    'pk', flat=True
                )
            ),
        )


class PurgeCommandTests(TestCase):
    """The retention schedule. POPIA's retention principle, made to actually run.

    A policy nobody executes is a policy nobody has, which is why this is a
    command on a timer rather than a paragraph in a document.
    """

    def setUp(self):
        self.member = make_account('member@example.com')

    def make(self, *, age_days):
        dispatch = EmailDispatch.objects.create(
            kind=EmailDispatch.Kind.LOGIN_CODE,
            storefront=Storefront.CLUB,
            recipient=self.member,
            subject='Subject',
            trigger=EmailDispatch.Trigger.MEMBER,
            send_status=EmailDispatch.SendStatus.SENT,
            sent_at=timezone.now(),
        )
        # `queued_at` is `auto_now_add`, so ageing a row means going round the
        # model. The alternative is freezing the clock, which is a heavier
        # dependency than one `.update()`.
        EmailDispatch.objects.filter(pk=dispatch.pk).update(
            queued_at=timezone.now() - timedelta(days=age_days)
        )
        return dispatch

    def run_command(self, *args):
        output = StringIO()
        call_command('purge_email_dispatches', *args, stdout=output)
        return output.getvalue()

    @override_settings(EMAIL_DISPATCH_RETENTION_DAYS=365)
    def test_it_deletes_past_the_window_and_keeps_inside_it(self):
        old = self.make(age_days=400)
        recent = self.make(age_days=30)

        self.run_command()

        surviving = set(EmailDispatch.objects.values_list('pk', flat=True))
        self.assertEqual({recent.pk}, surviving)
        self.assertNotIn(old.pk, surviving)

    @override_settings(EMAIL_DISPATCH_RETENTION_DAYS=365)
    def test_a_dry_run_reports_and_deletes_nothing(self):
        self.make(age_days=400)

        output = self.run_command('--dry-run')

        self.assertIn('1 send record', output)
        self.assertEqual(1, EmailDispatch.objects.count())

    def test_days_overrides_the_configured_window(self):
        self.make(age_days=30)

        self.run_command('--days', '7')

        self.assertEqual(0, EmailDispatch.objects.count())

    @override_settings(EMAIL_DISPATCH_RETENTION_DAYS=0)
    def test_zero_keeps_everything_and_says_so(self):
        """A deployment that has decided to keep the lot should hear that its
        schedule ran and deliberately did nothing, not read a silent success."""
        self.make(age_days=4000)

        output = self.run_command()

        self.assertIn('Nothing was deleted', output)
        self.assertEqual(1, EmailDispatch.objects.count())

    def test_a_negative_window_is_refused(self):
        with self.assertRaises(CommandError):
            self.run_command('--days', '-1')

    @override_settings(EMAIL_DISPATCH_RETENTION_DAYS=365)
    def test_running_twice_is_safe(self):
        self.make(age_days=400)

        self.run_command()
        self.run_command()

        self.assertEqual(0, EmailDispatch.objects.count())


class ConstraintTests(TestCase):
    """The rules the database keeps when the model layer is walked past.

    None of these rows come from a form, so ``choices`` protects nothing here,
    and a queryset ``.update()`` goes straight through the model. What is being
    defended is a specific silent failure: a status written without its
    timestamp reads as a definite answer that happened at no particular time,
    and every report over the log drops the row without saying so.

    On MySQL below 8.0.16 every assertion in this class is decoration --
    ``common.checks`` is what refuses such a database.
    """

    def setUp(self):
        self.member = make_account('member@example.com')

    def make(self, **overrides):
        options = {
            'kind': EmailDispatch.Kind.LOGIN_CODE,
            'storefront': Storefront.CLUB,
            'recipient': self.member,
            'subject': 'Subject',
            'trigger': EmailDispatch.Trigger.MEMBER,
        }
        options.update(overrides)
        return EmailDispatch.objects.create(**options)

    def test_an_unrecognised_kind_is_refused(self):
        """An email nothing can name is one no report will ever count."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make(kind='newsletter')

    def test_an_unrecognised_storefront_is_refused(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make(storefront='greengrocer')

    def test_a_send_cannot_be_marked_sent_at_no_time(self):
        dispatch = self.make()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EmailDispatch.objects.filter(pk=dispatch.pk).update(
                    send_status=EmailDispatch.SendStatus.SENT, sent_at=None
                )

    def test_a_delivery_outcome_cannot_be_reported_at_no_time(self):
        dispatch = self.make()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EmailDispatch.objects.filter(pk=dispatch.pk).update(
                    delivery_status=EmailDispatch.DeliveryStatus.DELIVERED,
                    delivered_at=None,
                )

    def test_a_bounce_needs_a_timestamp_too(self):
        """The timestamp is the delivery *stage*, not only its happy path. A
        bounce with no time on it cannot be put in order against anything."""
        dispatch = self.make()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EmailDispatch.objects.filter(pk=dispatch.pk).update(
                    delivery_status=EmailDispatch.DeliveryStatus.BOUNCED,
                    delivered_at=None,
                )

    def test_an_open_cannot_be_recorded_at_no_time(self):
        dispatch = self.make()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                EmailDispatch.objects.filter(pk=dispatch.pk).update(
                    read_status=EmailDispatch.ReadStatus.READ, read_at=None
                )

    def test_not_tracked_and_not_reported_need_no_timestamps(self):
        """The default state of every row on this deployment, and it has to be
        constructible -- otherwise the constraints above would forbid the truth."""
        dispatch = self.make()

        self.assertEqual(
            EmailDispatch.DeliveryStatus.UNKNOWN, dispatch.delivery_status
        )
        self.assertEqual(
            EmailDispatch.ReadStatus.NOT_TRACKED, dispatch.read_status
        )
        self.assertIsNone(dispatch.delivered_at)
        self.assertIsNone(dispatch.read_at)
