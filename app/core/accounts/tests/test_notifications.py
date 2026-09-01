"""The emails that tell somebody they cannot get in.

These are the private half of a deliberately uninformative sign-in. The
endpoints answer a blocked account exactly as they answer a stranger -- because
saying otherwise would confirm to anybody typing addresses that one belongs to a
member of a cannabis club -- so the explanation has to reach the mailbox instead,
and these tests are about what does and does not travel with it.
"""
from unittest.mock import patch

from django.core import mail
from django.test import TestCase

from app.core.accounts import notifications
from app.core.accounts.models import UserStatus
from app.core.storefronts.models import EmailDispatch, Storefront
from f2c.testing import make_account, make_member, make_sharing_placeholder


class SuspensionEmailTests(TestCase):
    def setUp(self):
        self.member = make_member('grower@example.com', 'Grower')
        mail.outbox.clear()

    def send(self):
        with self.captureOnCommitCallbacks(execute=True):
            return notifications.email_membership_suspended(self.member)

    def test_it_reaches_the_member(self):
        self.assertTrue(self.send())

        self.assertEqual(1, len(mail.outbox))
        self.assertEqual(['grower@example.com'], mail.outbox[0].to)

    def test_it_is_club_branded_whatever_triggered_it(self):
        """Named outright rather than resolved from a request.

        A club membership is the club's alone. The host an administrator happened
        to be signed in to says nothing about which storefront the suspension
        belongs to -- the same call `payments._send_checkout_link` makes.
        """
        self.send()

        self.assertIn(Storefront.CLUB.label, mail.outbox[0].subject)

    def test_it_says_the_member_area_is_closed_and_not_the_platform(self):
        """A club suspension leaves the produce market open, so the wording must
        not claim otherwise. The account is still Active."""
        self.send()

        self.assertNotIn('both', mail.outbox[0].body.lower())
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_active)

    def test_it_offers_a_way_to_ask(self):
        # The whole point of sending anything. A block nobody can question is a
        # block nobody can correct.
        self.assertTrue(self.send())

        self.assertIn('reply to this email', mail.outbox[0].body.lower())

    def test_nothing_is_sent_before_the_commit(self):
        with self.captureOnCommitCallbacks(execute=False):
            notifications.email_membership_suspended(self.member)

        self.assertEqual(0, len(mail.outbox))

    def test_a_placeholder_is_not_written_to(self):
        """A sharing member has no address and is not a person -- C6. Reachable,
        because an administrator can suspend the identity."""
        placeholder = make_sharing_placeholder()

        with self.captureOnCommitCallbacks(execute=True):
            self.assertFalse(notifications.email_membership_suspended(placeholder))

        self.assertEqual(0, len(mail.outbox))

    def test_an_erased_account_is_not_written_to(self):
        """POPIA erasure removes the address, so there is nowhere to write."""
        self.member.soft_delete()

        with self.captureOnCommitCallbacks(execute=True):
            self.assertFalse(notifications.email_membership_suspended(self.member))

        self.assertEqual(0, len(mail.outbox))

    def test_a_mail_failure_is_logged_and_swallowed(self):
        """See `_deliver`. The caller's change is already committed, and failing
        it after the fact would report a suspension that did not happen."""
        with patch(
            'app.core.accounts.notifications.send_storefront_email',
            side_effect=OSError('unreachable'),
        ):
            with self.assertLogs('app.core.accounts.notifications', level='ERROR') as logs:
                with self.captureOnCommitCallbacks(execute=True):
                    notifications.email_membership_suspended(self.member)

        self.assertIn('Somebody should tell them', logs.output[0])


class RevocationEmailTests(TestCase):
    def setUp(self):
        self.account = make_account('customer@example.com')
        mail.outbox.clear()

    def test_it_reaches_the_account(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(notifications.email_access_revoked(self.account))

        self.assertEqual(['customer@example.com'], mail.outbox[0].to)

    def test_it_says_both_sites_because_it_means_both(self):
        """The difference from a club suspension, and the reason there are two
        templates rather than one with a flag: this block does stop somebody
        signing in to the produce market."""
        with self.captureOnCommitCallbacks(execute=True):
            notifications.email_access_revoked(self.account)

        self.assertIn('either of our sites', mail.outbox[0].body)

    def test_the_letterhead_can_be_named(self):
        """A produce customer barred from the market should not receive a
        cannabis club's letterhead."""
        with self.captureOnCommitCallbacks(execute=True):
            notifications.email_access_revoked(
                self.account, storefront=Storefront.MARKET
            )

        self.assertIn(Storefront.MARKET.label, mail.outbox[0].subject)

    def test_it_is_the_only_channel_there_is(self):
        """Documents why this send is not optional.

        A revoked account is filtered out by `active_by_email`, so every sign-in
        route answers it as it answers a stranger and no screen can ever explain
        the block. If this email does not go, nothing tells them.
        """
        self.account.deactivate(UserStatus.SUSPENDED)

        from app.core.accounts.models import User

        self.assertIsNone(
            User.objects.active_by_email('customer@example.com').first()
        )


class SendRecordTests(TestCase):
    """The send log, from the caller's end rather than the mail layer's.

    ``storefronts.tests.test_dispatch`` asserts that a send writes a truthful
    row. What is asserted here is that these two callers hand it the right facts
    -- which is where the wiring can silently be wrong: a suspension notice
    recorded as the platform's own doing, or attributed to nobody, still sends
    perfectly well and reads correctly in the member's mailbox.
    """

    def setUp(self):
        self.member = make_member('member@example.com', 'Thabo')
        self.operator = make_account('operator@example.com')
        mail.outbox.clear()

    def test_a_suspension_notice_is_recorded_against_the_member(self):
        with self.captureOnCommitCallbacks(execute=True):
            notifications.email_membership_suspended(self.member, by=self.operator)

        dispatch = EmailDispatch.objects.get()
        self.assertEqual(self.member, dispatch.recipient)
        self.assertEqual(
            EmailDispatch.Kind.MEMBERSHIP_SUSPENDED, dispatch.kind
        )
        self.assertEqual(Storefront.CLUB, dispatch.storefront)
        self.assertEqual(EmailDispatch.SendStatus.SENT, dispatch.send_status)

    def test_it_names_the_operator_who_caused_it(self):
        """The question the log is here to answer about an administrator's
        action: not only whether the member was told, but by whose doing."""
        with self.captureOnCommitCallbacks(execute=True):
            notifications.email_membership_suspended(self.member, by=self.operator)

        dispatch = EmailDispatch.objects.get()
        self.assertEqual(EmailDispatch.Trigger.OPERATOR, dispatch.trigger)
        self.assertEqual(self.operator, dispatch.triggered_by)

    def test_an_unattributed_suspension_is_still_an_operators(self):
        """``by`` is optional. An admin path that does not pass it records an
        operator with no name -- not a send the platform decided on."""
        with self.captureOnCommitCallbacks(execute=True):
            notifications.email_membership_suspended(self.member)

        dispatch = EmailDispatch.objects.get()
        self.assertEqual(EmailDispatch.Trigger.OPERATOR, dispatch.trigger)
        self.assertIsNone(dispatch.triggered_by)

    def test_a_revocation_is_recorded_as_its_own_kind(self):
        """Two blocks, two kinds. Reporting on "who have we barred?" must not
        have to read subject lines to tell them apart."""
        account = make_account('customer@example.com')

        with self.captureOnCommitCallbacks(execute=True):
            notifications.email_access_revoked(account, by=self.operator)

        dispatch = EmailDispatch.objects.get()
        self.assertEqual(EmailDispatch.Kind.ACCESS_REVOKED, dispatch.kind)
        self.assertEqual(account, dispatch.recipient)

    def test_a_member_with_no_address_leaves_no_row(self):
        """The caller declines to send at all, so there is nothing to record.
        A dispatch row for a message that was never attempted would be worse
        than the silence -- see ``_addressee``."""
        self.member.soft_delete()

        with self.captureOnCommitCallbacks(execute=True):
            notifications.email_membership_suspended(self.member)

        self.assertEqual(0, EmailDispatch.objects.count())

    def test_a_mail_failure_is_still_recorded(self):
        """The send is swallowed here -- see ``_deliver`` -- which is exactly why
        the row matters: without it a suspension notice that never left is
        invisible outside the application log."""
        with patch(
            'django.core.mail.EmailMessage.send', side_effect=OSError('unreachable')
        ):
            with self.assertLogs('app.core.accounts.notifications', level='ERROR'):
                with self.captureOnCommitCallbacks(execute=True):
                    notifications.email_membership_suspended(self.member)

        dispatch = EmailDispatch.objects.get()
        self.assertEqual(EmailDispatch.SendStatus.FAILED, dispatch.send_status)
        self.assertIn('unreachable', dispatch.send_error)
