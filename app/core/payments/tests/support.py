"""Scaffolding for the payment tests.

Three things here rather than in the tests.

``PAYFAST`` is a fixed sandbox configuration, applied with ``override_settings``
by every test case below. Without it the suite would read whatever is in the
developer's ``.env`` -- so a test would pass or fail depending on the amount
somebody happened to have configured, which is the most misleading way for a
test about an *amount mismatch* to be green.

``notification`` builds a correctly signed Payfast notification as an **ordered
list of pairs**, because that is the only form the signature verifies over. A
helper that returned a dict would let every test in this suite pass while the
production code failed on the wire, which is precisely the bug this integration
is most likely to have.

``PaymentsTestCase`` gives every test a member at ``Pending payment`` with a
subscription open against them, because that is the only state a payment can
arrive into. It reaches through the real registration path rather than building
rows by hand: a subscription created directly would not prove that registration
opens one.
"""
from decimal import Decimal

from django.test import TestCase, override_settings

from app.club.membership.models import MembershipStatus
from app.club.membership import services as membership_services
from app.club.membership.tests.support import ADULT_ID, RegistrationTestCase
from app.core.payments import gateway
from app.core.payments.models import Subscription

#: The configuration every test in this app runs against. Payfast's published
#: sandbox merchant, a round amount, and monthly billing -- so a cycle is 31
#: days and the arithmetic in the assertions is readable.
PAYFAST = gateway.sandbox_settings(amount=Decimal('150.00'))

#: An address the tests declare to be Payfast's. Nothing resolves it; every
#: caller that needs the source check to pass injects this through
#: ``addresses=``, which is why no test in this suite touches DNS.
PAYFAST_IP = '197.97.145.144'

#: One monthly cycle, from ``gateway.CYCLE_DAYS``. Named so a test asserting a
#: paid-up date says *why* it is that date.
MONTHLY_DAYS = gateway.CYCLE_DAYS[gateway.FREQUENCIES['monthly']]


def notification(subscription, *, status='COMPLETE', payment_id='PF-1', amount=None,
                 token='sub-token-1', config=PAYFAST, extra=(), sign=True):
    """A signed Payfast notification, as an ordered list of pairs.

    ``extra`` is appended before signing, which is how a test proves that a
    field this application does not read is still signed over -- Payfast adds
    fields, and a verifier that ignored unknown ones would break the day it did.

    ``sign=False`` returns the same body with a signature that does not verify,
    for the tests that need a forgery rather than a mistake.
    """
    gross = subscription.amount if amount is None else Decimal(str(amount))
    pairs = [
        ('m_payment_id', str(subscription.pk)),
        ('pf_payment_id', payment_id),
        ('payment_status', status),
        ('item_name', config.item_name),
        ('amount_gross', f'{gross:.2f}'),
        ('amount_fee', '-5.25'),
        ('amount_net', f'{gross - Decimal("5.25"):.2f}'),
        ('merchant_id', config.merchant_id),
        ('token', token),
    ]
    pairs.extend(extra)
    signature = (
        gateway.notification_signature(pairs, config.passphrase)
        if sign
        else '0' * 32
    )
    return pairs + [('signature', signature)]


@override_settings(PAYFAST=PAYFAST)
class PaymentsTestCase(RegistrationTestCase):
    """A registered member at Pending payment, with a subscription open.

    Built through ``register_member`` rather than by creating rows, so every
    test here also holds registration to opening exactly one subscription.
    """

    def setUp(self):
        super().setUp()
        submission = self.submission()
        self.registration = membership_services.register_member(
            first_name=submission['first_name'],
            last_name=submission['last_name'],
            nickname=submission['nickname'],
            email=submission['email'],
            mobile=submission['mobile'],
            id_number=ADULT_ID,
            consents=self.consents(),
        )
        self.member = self.registration.user
        self.subscription = Subscription.objects.get(user=self.member)

    def reload(self):
        """The subscription and the member as the database now holds them.

        Both, together, and always: every rule in this app is about the pair.
        Asserting on a stale in-memory member is how a test about activation
        passes without anything having been activated.
        """
        self.subscription.refresh_from_db()
        self.member.refresh_from_db()
        return self.subscription, self.member

    def assertStillPendingPayment(self):
        """Nothing has been activated.

        **Asserts on the membership, not the account.** Before C27 an unpaid
        member's *account* was blocked, so this checked `is_active` — and would
        now pass trivially, because the account is Active from the moment it
        exists and it is the membership that is outstanding. Checking the
        account here would be an assertion that can no longer fail.
        """
        self.member.refresh_from_db()
        self.member.club_membership.refresh_from_db()
        self.assertEqual(
            self.member.club_membership.status, MembershipStatus.PENDING_PAYMENT
        )
        # The account signs in throughout; that is the point of the split.
        self.assertTrue(self.member.is_active)


@override_settings(PAYFAST=PAYFAST)
class GatewayTestCase(TestCase):
    """For the tests that need no database. Kept apart so it is obvious which
    of these rules are pure -- which is nearly all of them."""
