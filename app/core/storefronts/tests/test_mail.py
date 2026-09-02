"""Tests for which server an email leaves by, and as whom.

The failure this module exists to catch does not look like a failure. Route a
storefront's mail through another storefront's server and the send *succeeds* --
the message arrives, correctly formatted, with a plausible signature. What is
wrong is only visible in the headers: the wrong provider, the wrong domain, and
a member being asked to trust a one-time code that came from neither. So the
assertions here are about the alias and the ``From`` header rather than about
whether anything was sent.

``sent_using`` is stamped on the outbox copy by Django's locmem backend, which
the test runner substitutes for every configured alias. It is the only way to
see, after the fact, which mailer a message actually went through.
"""
from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings

from app.core.storefronts.mail import (
    brand_for,
    from_email_for,
    mailer_for,
    send_storefront_email,
)
from app.core.storefronts.models import EmailDispatch, Storefront
from f2c.testing import make_account

SENDERS = {
    'club': 'no-reply@club.example.co.za',
    'market': 'no-reply@market.example.co.za',
}


class MailerForTests(SimpleTestCase):
    def test_each_storefront_gets_its_own_alias(self):
        self.assertEqual(mailer_for(Storefront.CLUB), 'club')
        self.assertEqual(mailer_for(Storefront.MARKET), 'market')

    def test_the_alias_is_the_storefront_code(self):
        """Not a lookup table. If that ever stops being true, so does this."""
        for storefront in Storefront.values:
            with self.subTest(storefront=storefront):
                self.assertEqual(mailer_for(storefront), storefront)

    @override_settings(DEFAULT_STOREFRONT='market')
    def test_no_storefront_falls_back_to_the_configured_default(self):
        """A shell, a cron job, a test: nothing to resolve, and it must not raise."""
        self.assertEqual(mailer_for(), 'market')
        self.assertEqual(mailer_for(None), 'market')

    @override_settings(DEFAULT_STOREFRONT='market')
    def test_an_unrecognised_storefront_falls_back_rather_than_raising(self):
        """Sign-in must not fail on a mapping error. `checks` is what catches it."""
        self.assertEqual(mailer_for('greengrocer'), 'market')

    @override_settings(DEFAULT_STOREFRONT='nonsense')
    def test_a_nonsense_default_falls_back_to_the_club(self):
        self.assertEqual(mailer_for(), Storefront.CLUB)


class FromEmailTests(SimpleTestCase):
    @override_settings(STOREFRONT_FROM_EMAIL=SENDERS)
    def test_each_storefront_sends_as_its_own_address(self):
        self.assertEqual(from_email_for(Storefront.CLUB), SENDERS['club'])
        self.assertEqual(from_email_for(Storefront.MARKET), SENDERS['market'])

    @override_settings(
        STOREFRONT_FROM_EMAIL={'club': SENDERS['club']},
        DEFAULT_FROM_EMAIL='fallback@example.co.za',
        DEFAULT_STOREFRONT='club',
    )
    def test_a_storefront_with_no_address_falls_back_to_the_default(self):
        """Only reachable in local development -- settings refuses a blank one."""
        self.assertEqual(from_email_for(Storefront.MARKET), 'fallback@example.co.za')

    @override_settings(
        STOREFRONT_FROM_EMAIL={}, DEFAULT_FROM_EMAIL='fallback@example.co.za'
    )
    def test_an_empty_mapping_falls_back_rather_than_raising(self):
        self.assertEqual(from_email_for(Storefront.CLUB), 'fallback@example.co.za')


class BrandTests(SimpleTestCase):
    def test_the_name_comes_from_the_storefront_labels(self):
        """One source, so the subject line and the admin cannot disagree."""
        self.assertEqual(brand_for(Storefront.CLUB), Storefront.CLUB.label)
        self.assertEqual(brand_for(Storefront.MARKET), Storefront.MARKET.label)
        self.assertEqual(brand_for(Storefront.CLUB), 'Cultivators Collective')

    @override_settings(DEFAULT_STOREFRONT='market')
    def test_no_storefront_uses_the_default_storefronts_name(self):
        self.assertEqual(brand_for(), Storefront.MARKET.label)


@override_settings(STOREFRONT_FROM_EMAIL=SENDERS)
class SendStorefrontEmailTests(TestCase):
    """``TestCase`` rather than ``SimpleTestCase``, and that is not incidental.

    Sending now writes an ``EmailDispatch`` row, so there is no database-free
    path through this function any more. That is the design -- the log is
    complete because there is no way to send without writing to it -- and this
    class needing a database is the first place it shows.
    """

    def setUp(self):
        super().setUp()
        self.member = make_account('someone@example.com')
        mail.outbox.clear()

    def send(self, storefront):
        """Queue a send and let the commit it is waiting on happen.

        ``captureOnCommitCallbacks`` because the send is published from
        ``transaction.on_commit`` and a ``TestCase`` never commits --
        ``f2c.testing.flush_commit_hooks`` explains why that is worth a
        line in every test that wants an email rather than being hidden
        in a base class.
        """
        with self.captureOnCommitCallbacks(execute=True):
            send_storefront_email(
                storefront=storefront,
                kind=EmailDispatch.Kind.LOGIN_CODE,
                recipient=self.member,
                subject='Subject',
                body='Body',
            )
        return mail.outbox[-1]

    def test_club_mail_leaves_by_the_club_server_as_the_club(self):
        message = self.send(Storefront.CLUB)

        self.assertEqual(message.sent_using, 'club')
        self.assertEqual(message.from_email, SENDERS['club'])

    def test_market_mail_leaves_by_the_market_server_as_the_market(self):
        message = self.send(Storefront.MARKET)

        self.assertEqual(message.sent_using, 'market')
        self.assertEqual(message.from_email, SENDERS['market'])

    def test_the_two_storefronts_never_share_a_server_or_a_sender(self):
        """The whole point, asserted as one thing rather than two."""
        club = self.send(Storefront.CLUB)
        market = self.send(Storefront.MARKET)

        self.assertNotEqual(club.sent_using, market.sent_using)
        self.assertNotEqual(club.from_email, market.from_email)

    def test_the_address_comes_off_the_account(self):
        """Not from the caller, so a caller cannot log one member and write to
        another. See ``send_storefront_email``."""
        message = self.send(Storefront.CLUB)

        self.assertEqual([self.member.email], message.to)

    def test_an_account_with_no_address_is_refused_before_anything_is_sent(self):
        """A programming error, not a runtime condition: the callers ask whether
        there is anybody to write to before they get here."""
        self.member.email = None
        self.member.save(update_fields=['email'])

        with self.assertRaises(ValueError):
            self.send(Storefront.CLUB)

        self.assertEqual(0, len(mail.outbox))
        self.assertEqual(0, EmailDispatch.objects.count())
