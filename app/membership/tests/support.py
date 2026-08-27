"""Scaffolding for the registration tests.

Two things here rather than in the tests themselves.

``sa_id_for`` builds a structurally valid RSA ID number for a given date of
birth, check digit included. The suite needs several -- one per member, one
under age, one for the duplicate case -- and hard-coding them would mean a test
about *being under age* that actually fails on a check digit, which is the most
misleading way for a test to be green or red.

``RegistrationTestCase`` inherits the club-document scaffolding, because a
registration cannot happen without a published revision of every required
document. That is the point of ``DocumentsNotReady``, and it means every test
here has to publish three of them first.
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from app.accounts.models import UserStatus
from app.accounts.roles import UserRole
from app.common.validators import luhn_is_valid
from app.documents.tests.support import DocumentsTestCase
from app.payments.models import Subscription, SubscriptionStatus

#: The slugs migration 0002 seeds, in form order.
REQUIRED_DOCUMENTS = ('club-rules', 'annexures', 'constitution')


def sa_id_for(born, sequence='5009', citizenship='0'):
    """A well-formed RSA ID number encoding ``born``.

    ``YYMMDD SSSS C A Z``: date of birth, the sequence, the citizenship digit,
    the legacy digit, and a Luhn check digit computed here so the result passes
    ``validate_sa_id_number``.
    """
    body = f'{born:%y%m%d}{sequence}{citizenship}8'
    for candidate in '0123456789':
        if luhn_is_valid(body + candidate):
            return body + candidate
    raise AssertionError(f'No check digit completes {body}')


#: A member comfortably over eighteen, and a second identity for the tests that
#: need two people.
ADULT_BORN = date(1990, 3, 15)
ADULT_ID = sa_id_for(ADULT_BORN)
SECOND_ADULT_ID = sa_id_for(date(1985, 7, 2), sequence='5123')


class RegistrationTestCase(DocumentsTestCase):
    """A published revision of all three documents, and a valid submission."""

    def setUp(self):
        super().setUp()
        self.revisions = {
            slug: self.published(document=self.document(slug=slug), label='1')
            for slug in REQUIRED_DOCUMENTS
        }

    def consents(self, **overrides):
        """The three agreements, at the revisions actually in force."""
        submitted = [
            {'document': slug, 'version': self.revisions[slug].label}
            for slug in REQUIRED_DOCUMENTS
        ]
        for entry in submitted:
            if entry['document'] in overrides:
                entry['version'] = overrides[entry['document']]
        return submitted

    def submission(self, **overrides):
        """A submission every rule accepts, before ``overrides`` are applied."""
        payload = {
            'first_name': 'Thandiwe',
            'last_name': 'Mokoena',
            'nickname': 'Grower',
            'email': 'thandiwe@example.com',
            'mobile': '082 123 4567',
            'id_number': ADULT_ID,
            'consents': self.consents(),
        }
        payload.update(overrides)
        return payload

    def supersede(self, slug, label='2'):
        """Publish a newer revision of ``slug``, making the form's one stale.

        The file has to differ: ``publish`` refuses a byte-identical re-upload,
        because accepting one would ask every member to agree again to a
        document that did not change.

        ``effective_from`` is left as ``publish`` stamps it. ``published()``
        breaks a tie on the primary key, so this revision is the one in force
        even if both stamps land in the same microsecond.
        """
        return self.published(
            document=self.document(slug=slug),
            label=label,
            content=b'%PDF-1.7\na later revision\n%%EOF\n',
        )


User = get_user_model()


class RegisterTestCase(TestCase):
    """Accounts for the administrator's register, and nothing to do with documents.

    Deliberately **not** a ``RegistrationTestCase``. Nothing under
    ``/api/members/{id}`` publishes or reads a club document, and inheriting
    three published revisions into every one of these tests would make each of
    them slower and none of them clearer -- the two halves of ``/api/members``
    share a URL and no fixtures.

    Four accounts that differ in exactly one way each, following
    ``strains.tests.support``: building them by hand in every test case is how
    two of them end up differing in two ways. Active throughout, because
    ``permissions_for`` empties the set for an account that cannot sign in, so a
    Pending administrator would be refused for the wrong reason and a test
    asserting 403 would pass without testing anything about the role.
    """

    def setUp(self):
        self.admin = self.account('registrar@example.com', 'Registrar', UserRole.ADMIN)
        self.cultivator = self.account('grower@example.com', 'Kloof', UserRole.CULTIVATOR)
        self.member = self.account('thabo@example.com', 'Thabo', UserRole.MEMBER)

    def account(self, email, nickname, role=UserRole.MEMBER, **overrides):
        """An account holding ``role``, Active unless told otherwise."""
        return User.objects.create_user(
            email=email,
            nickname=nickname,
            role=role,
            status=overrides.pop('status', UserStatus.ACTIVE),
            first_name=overrides.pop('first_name', 'Given'),
            last_name=overrides.pop('last_name', 'Family'),
            **overrides,
        )

    def sharing_member(self, nickname='Held', **overrides):
        """A stock-holding identity: no address, and a cultivator's attestation.

        Written through the model rather than through
        ``accounts.services.register_sharing_member``, because these tests are
        about what the register refuses to do to one, not about how one comes to
        exist. The four columns ``sharing_member_is_complete`` requires are all
        set, so the row is one the database accepts.
        """
        person = User(
            nickname=nickname,
            first_name=overrides.pop('first_name', 'Sipho'),
            last_name=overrides.pop('last_name', 'Ndlovu'),
            role=UserRole.SHARING_MEMBER,
            status=UserStatus.SHARING,
            registered_by=overrides.pop('registered_by', self.cultivator),
            sharing_consent_attested_by=self.cultivator,
            sharing_consent_attested_at=timezone.now(),
            **overrides,
        )
        person.id_number = SECOND_ADULT_ID
        person.set_unusable_password()
        person.save()
        return person

    def subscribe(self, member, status=SubscriptionStatus.ACTIVE, **overrides):
        """A subscription against ``member``, live by default.

        The columns are set here rather than through
        ``payments.services.open_subscription``, because these tests care what
        the register *reports* about a standing and not how one is opened --
        and ``open_subscription`` always writes ``PENDING``, which is only one
        of the four states the register has to show.

        ``gateway_token`` is set for an Active row and left blank otherwise,
        because ``active_subscription_is_paid_up`` says an active subscription
        is one Payfast has taken money against: it has a token and a paid-up
        date. A fixture that ignored that would be a fixture the database
        refuses.
        """
        active = status == SubscriptionStatus.ACTIVE
        return Subscription.objects.create(
            user=member,
            status=status,
            amount=overrides.pop('amount', '150.00'),
            frequency=overrides.pop('frequency', 3),
            checkout_expires_at=timezone.now() + timedelta(days=1),
            gateway_token=overrides.pop(
                'gateway_token', 'pf-token' if active else ''
            ),
            paid_until=overrides.pop(
                'paid_until', date(2026, 12, 31) if active else None
            ),
            **overrides,
        )

    def joined(self, member, days_ago):
        """Backdate ``created_at``, which is ``auto_now_add`` and cannot be set.

        A queryset ``update`` rather than a save: ``auto_now_add`` writes the
        column on insert and ignores it on every write afterwards, so the only
        way to test the *joined within* filter at all is to go round the model.
        The row is re-read so the instance and the database agree.
        """
        User.objects.filter(pk=member.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )
        member.refresh_from_db()
        return member

    def edit(self, **overrides):
        """A complete, acceptable ``MemberIn`` body.

        Every field present, because the endpoint is a replace and a test that
        sent a subset would be testing a shape the screen never produces.
        """
        return {
            'first_name': 'Thabo',
            'last_name': 'Mahlangu',
            'nickname': 'Thabo',
            'email': 'thabo@example.com',
            'mobile': '082 123 4567',
        } | overrides
