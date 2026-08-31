"""The rules behind the administrator's membership register.

Six things are tested here that no endpoint test would reach, because each is a
rule the router never sees: who may read the register at all, what an erased
record refuses, what a sharing member refuses, that an administrator cannot
suspend themselves, that reinstatement only lifts a suspension, and that reading
an identity number writes its own evidence first.

The API tests beside this file cover the translation into status codes. Nothing
is asserted twice.
"""
from datetime import date
from unittest.mock import patch

from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from app.core.accounts.models import IdentityNumberDisclosure, User, UserStatus
from f2c.testing import make_cultivator
from app.core.payments.models import SubscriptionStatus

from .. import administration
from .support import ADULT_ID, RegisterTestCase
from app.club.membership.models import MembershipStatus


class Authorisation(RegisterTestCase):
    """``platform.disable_user``, asked on reads as well as writes."""

    def test_a_member_may_not_read_the_register(self):
        with self.assertRaises(PermissionDenied):
            administration.register(self.member)

    def test_a_cultivator_may_not_read_the_register(self):
        # A cultivator manages the sharing members they registered, through a
        # permission of their own. That is not this register.
        with self.assertRaises(PermissionDenied):
            administration.register(self.grower)

    def test_an_administrator_may(self):
        self.assertIn(self.member, administration.register(self.admin))

    def test_a_suspended_administrator_may_not(self):
        # `permissions_for` empties the set for an account that cannot sign in,
        # so the role alone is not the answer -- which is the whole reason this
        # module asks `has_perm` rather than comparing `role`.
        self.admin.deactivate(UserStatus.SUSPENDED)
        with self.assertRaises(PermissionDenied):
            administration.register(self.admin)

    def test_an_anonymous_caller_may_not(self):
        with self.assertRaises(PermissionDenied):
            administration.register(None)

    def test_a_member_may_not_write(self):
        with self.assertRaises(PermissionDenied):
            administration.update_member(self.member, self.member, first_name='X')

    def test_a_member_may_not_read_an_identity_number(self):
        with self.assertRaises(PermissionDenied):
            administration.disclose_id_number(
                self.member, self.member, reason='Because I would like to.'
            )


class TheRegister(RegisterTestCase):
    """What the list returns, and what each filter narrows it to."""

    def test_newest_first(self):
        # The order that makes `joined_within` the whole of the recent sign-ups
        # view rather than a second endpoint.
        old = self.joined(self.account('old@example.com', 'Older'), days_ago=90)
        new = self.account('new@example.com', 'Newer')

        listed = list(administration.register(self.admin))
        self.assertLess(listed.index(new), listed.index(old))

    def test_status_narrows(self):
        """On the **membership's** standing, not the account's.

        An unpaid member signs in perfectly well since C27, so filtering on the
        account status would report every one of them as Active — which is the
        opposite of what this column is for.
        """
        suspended = self.account('gone@example.com', 'Gone')
        administration.suspend_member(self.admin, suspended)

        listed = administration.register(
            self.admin, status=MembershipStatus.SUSPENDED
        )
        self.assertEqual([suspended], list(listed))

    def test_role_narrows(self):
        """A join now, not a column — C28.

        The fixture is a member **who also grows**, which is the case the
        filter is asked about. `self.grower` is appointed to a producer and
        holds no membership, so he is correctly absent from the club's register
        altogether: see `test_the_register_lists_members_only`.
        """
        grower_member = self.account('both@example.com', 'BothHats')
        make_cultivator('both@example.com', account=grower_member)

        listed = administration.register(self.admin, role='cultivator')
        self.assertEqual([grower_member], list(listed))

    def test_the_register_lists_members_only(self):
        """An account with no membership is not on the club's register.

        A produce-market customer never joined, owes the club nothing, and a
        club administrator has no business reading their record. Before the two
        storefronts every account was a member and this filter had nothing to
        exclude — so `self.admin` and `self.grower`, who hold no membership,
        are absent.
        """
        listed = list(administration.register(self.admin))

        self.assertIn(self.member, listed)
        self.assertNotIn(self.admin, listed)
        self.assertNotIn(self.grower, listed)

    def test_an_unrecognised_role_narrows_to_nothing(self):
        """Rather than being ignored.

        A filter that silently returns the unfiltered list is the failure where
        an administrator believes they are looking at cultivators and is looking
        at everybody.
        """
        self.assertEqual(
            [], list(administration.register(self.admin, role='overlord'))
        )

    def test_a_blank_filter_is_no_filter(self):
        # A `select` reset to "any" submits an empty string, so blank and absent
        # have to mean the same thing on both sides of the wire.
        self.assertEqual(
            list(administration.register(self.admin)),
            list(administration.register(self.admin, status='', role='', search='')),
        )

    def test_search_covers_the_four_columns_a_person_is_recognised_by(self):
        target = self.account(
            'zanele@example.com', 'Zaza', first_name='Zanele', last_name='Khumalo'
        )

        for term in ('Zanele', 'Khumalo', 'Zaza', 'zanele@example.com'):
            with self.subTest(term=term):
                self.assertIn(
                    target, administration.register(self.admin, search=term)
                )

    def test_search_finds_an_exact_identity_number(self):
        # The one search a club actually performs, and the only thing an
        # encrypted column can answer: exact match through the blind index.
        holder = self.account('holder@example.com', 'Holder')
        holder.id_number = ADULT_ID
        holder.save()

        self.assertIn(holder, administration.register(self.admin, search=ADULT_ID))

    def test_a_short_digit_string_is_not_tried_against_the_index(self):
        # Below the floor the term is a name, not a document. Asserted because
        # the alternative -- a three-digit prefix search -- is exactly the
        # browsing the blind index exists to prevent, and it would fail silently.
        holder = self.account('holder@example.com', 'Holder')
        holder.id_number = ADULT_ID
        holder.save()

        self.assertNotIn(
            holder, administration.register(self.admin, search=ADULT_ID[:4])
        )

    def test_joined_within_is_the_recent_signups_view(self):
        recent = self.account('recent@example.com', 'Recent')
        self.joined(self.account('ancient@example.com', 'Ancient'), days_ago=120)

        listed = list(administration.register(self.admin, joined_within=30))
        self.assertIn(recent, listed)
        self.assertEqual(
            [], [row for row in listed if row.club_nickname == 'Ancient']
        )

    def test_zero_days_is_unfiltered(self):
        self.joined(self.account('ancient@example.com', 'Ancient'), days_ago=120)

        self.assertEqual(
            len(list(administration.register(self.admin))),
            len(list(administration.register(self.admin, joined_within=0))),
        )


class TheStanding(RegisterTestCase):
    """The subscription the register reports beside each member."""

    def test_the_live_subscription_is_attached(self):
        self.subscribe(self.member, paid_until=date(2027, 1, 31))

        row = administration.register(self.admin).get(pk=self.member.pk)
        self.assertEqual(
            [SubscriptionStatus.ACTIVE], [s.status for s in row.live_subscriptions]
        )

    def test_a_cancelled_subscription_is_not_live(self):
        # `Subscription.objects.live()` is PENDING or ACTIVE. A cancelled
        # arrangement is history, and the register asks what is in force.
        self.subscribe(self.member, status=SubscriptionStatus.CANCELLED)

        row = administration.register(self.admin).get(pk=self.member.pk)
        self.assertEqual([], row.live_subscriptions)


class Editing(RegisterTestCase):
    """The five columns, and the two records that refuse every write."""

    def test_the_five_fields_are_written(self):
        administration.update_member(
            self.admin,
            self.member,
            first_name='Thabo',
            last_name='Mahlangu',
            nickname='Tebza',
            email='NEW@Example.COM',
            mobile='082 123 4567',
        )
        self.member.refresh_from_db()

        self.assertEqual('Mahlangu', self.member.last_name)
        self.assertEqual('Tebza', self.member.club_nickname)
        # Lower-cased whole, by `User.save`. Asserted here because the
        # uniqueness check above it compares against the stored form.
        self.assertEqual('new@example.com', self.member.email)
        self.assertEqual('+27821234567', self.member.mobile)

    def test_a_field_outside_the_allow_list_is_a_ValueError_not_a_refusal(self):
        # Loud, and never in a response body: a field reaching the service that
        # is not writable is a schema that has drifted, not something a caller
        # did.
        with self.assertRaises(ValueError):
            administration.update_member(self.admin, self.member, role='admin')

    def test_every_refusal_comes_back_at_once(self):
        # An administrator who mistyped two fields is told both, rather than
        # told the first and then the second on the next attempt.
        other = self.account('taken@example.com', 'Taken')

        with self.assertRaises(ValidationError) as refused:
            administration.update_member(
                self.admin,
                self.member,
                first_name='Thabo',
                last_name='Mahlangu',
                nickname=other.club_nickname,
                email=other.email,
                mobile='082 123 4567',
            )

        self.assertEqual(
            {'email', 'nickname'}, set(refused.exception.message_dict)
        )

    def test_a_refused_write_changes_nothing(self):
        other = self.account('taken@example.com', 'Taken')

        with self.assertRaises(ValidationError):
            administration.update_member(
                self.admin,
                self.member,
                first_name='Changed',
                last_name='Changed',
                nickname='Fresh',
                email=other.email,
                mobile='082 123 4567',
            )
        self.member.refresh_from_db()

        self.assertEqual('Given', self.member.first_name)

    def test_a_member_may_keep_their_own_address(self):
        # The exclusion that makes an edit that changes one field possible at
        # all: without `exclude_pk` the member's own row is the duplicate.
        administration.update_member(
            self.admin,
            self.member,
            first_name='Thabo',
            last_name='Ncube',
            nickname=self.member.club_nickname,
            email=self.member.email,
            mobile='082 123 4567',
        )
        self.member.refresh_from_db()

        self.assertEqual('Ncube', self.member.last_name)

    def test_a_nickname_may_be_cleared(self):
        # Blank is not the same as taken. `nickname_key` goes null, which is what
        # lets any number of accounts hold none under a unique index.
        administration.update_member(
            self.admin,
            self.member,
            first_name='Thabo',
            last_name='Ncube',
            nickname='',
            email=self.member.email,
            mobile='082 123 4567',
        )
        self.member.refresh_from_db()

        self.assertEqual('', self.member.club_nickname)
        self.assertIsNone(self.member.club_membership.nickname_key)

    def test_a_mobile_already_on_file_is_refused_however_it_is_typed(self):
        # Normalised before the query: a number typed as `082 …` has to find a
        # row holding `+2782…`, or the uniqueness check is decorative.
        holder = self.account('holder@example.com', 'Holder', mobile='+27821234567')
        self.assertTrue(holder.pk)

        with self.assertRaises(ValidationError) as refused:
            administration.update_member(
                self.admin,
                self.member,
                first_name='Thabo',
                last_name='Ncube',
                nickname='Thabo',
                email=self.member.email,
                mobile='082 123 4567',
            )

        self.assertIn('mobile', refused.exception.message_dict)

    def test_an_erased_record_refuses_every_write(self):
        self.member.soft_delete()

        with self.assertRaises(ValidationError) as refused:
            administration.update_member(
                self.admin,
                self.member,
                first_name='Back',
                last_name='Again',
                nickname='Back',
                email='back@example.com',
                mobile='082 123 4567',
            )

        # A non-field refusal: nothing is wrong with the submission, the record
        # is out of bounds. That is what the endpoint puts in `detail` rather
        # than marking up against an input nobody can correct.
        self.assertEqual('erased', refused.exception.code)

    def test_a_sharing_member_refuses_every_write(self):
        # C14 has not decided whether an administrator may touch one. Refusing
        # is the answer that does not pre-empt the decision.
        held = self.sharing_member()

        with self.assertRaises(ValidationError):
            administration.update_member(
                self.admin,
                held,
                first_name='Sipho',
                last_name='Ndlovu',
                nickname='Held',
                email='sipho@example.com',
                mobile='082 123 4567',
            )


class Suspending(RegisterTestCase):
    """The disable half of ``platform.disable_user``."""

    def test_it_suspends_the_membership_and_leaves_the_account(self):
        """**The membership, not the account.**

        Locking the account would sign them out of the produce market too, over
        a club matter they may have nothing to do with — the same call
        `payments.lapse_overdue` makes. Platform-wide removal is
        `platform.revoke_access`, in the Django admin.
        """
        administration.suspend_member(self.admin, self.member)
        self.member.refresh_from_db()
        self.member.club_membership.refresh_from_db()

        self.assertEqual(
            MembershipStatus.SUSPENDED, self.member.club_membership.status
        )
        self.assertTrue(self.member.is_active)

    def test_it_takes_the_club_away(self):
        """The suspension has to mean something, and this is what it means."""
        administration.suspend_member(self.admin, self.member)

        self.assertFalse(
            User.objects.with_platform_roles()
            .get(pk=self.member.pk)
            .has_perm('platform.purchase_plants')
        )

    def test_it_ends_the_live_sessions(self):
        # Without this an already signed-in browser keeps working until its
        # cookie expires, which makes a suspension advisory.
        self.client.force_login(self.member)
        self.assertTrue(self.client.session.session_key)

        administration.suspend_member(self.admin, self.member)

        self.assertEqual(0, self.member.flush_sessions())

    def test_it_is_idempotent(self):
        administration.suspend_member(self.admin, self.member)
        administration.suspend_member(self.admin, self.member)
        self.member.refresh_from_db()

        self.assertEqual(UserStatus.SUSPENDED, self.member.club_membership.status)

    def test_an_administrator_may_not_suspend_themselves(self):
        # Not paternalism: suspension signs the caller out on the way, and they
        # cannot sign back in to undo it.
        with self.assertRaises(ValidationError) as refused:
            administration.suspend_member(self.admin, self.admin)

        self.assertEqual('self_suspension', refused.exception.code)

    def test_a_sharing_member_cannot_be_suspended(self):
        with self.assertRaises(ValidationError):
            administration.suspend_member(self.admin, self.sharing_member())

    def test_an_erased_account_cannot_be_suspended(self):
        self.member.soft_delete()

        with self.assertRaises(ValidationError):
            administration.suspend_member(self.admin, self.member)

    def test_it_emails_the_member_that_the_hold_is_on(self):
        """**The screen will not say why; this does.**

        A suspended member can still sign in — the account stays Active — and
        the club layout sends them to `/blocked`, which names their standing and
        nothing else. The reason and the invitation to challenge it belong in the
        mailbox, which only its owner reads. C-decision: emailed, not shown.
        """
        mail.outbox.clear()

        with self.captureOnCommitCallbacks(execute=True):
            administration.suspend_member(self.admin, self.member)

        self.assertEqual(1, len(mail.outbox))
        sent = mail.outbox[0]
        self.assertEqual([self.member.email], sent.to)
        self.assertIn('on hold', sent.subject)

    def test_the_email_does_not_say_why(self):
        """A reason an administrator recorded is not in the member's mailbox
        either. What the email offers is a way to ask, not an account of the
        club's reasoning — which nothing in this codebase stores anyway."""
        mail.outbox.clear()

        with self.captureOnCommitCallbacks(execute=True):
            administration.suspend_member(self.admin, self.member)

        body = mail.outbox[0].body.lower()
        for word in ('breach', 'misconduct', 'violation', 'complaint', 'fraud'):
            self.assertNotIn(word, body)

    def test_it_emails_nothing_until_the_transaction_commits(self):
        """A suspension that rolls back tells nobody it happened."""
        mail.outbox.clear()

        with self.captureOnCommitCallbacks(execute=False):
            administration.suspend_member(self.admin, self.member)

        self.assertEqual(0, len(mail.outbox))

    def test_suspending_twice_emails_once(self):
        """The idempotent early return sits above the send, so a second call is
        genuinely a no-op rather than a second letter."""
        mail.outbox.clear()

        with self.captureOnCommitCallbacks(execute=True):
            administration.suspend_member(self.admin, self.member)
            administration.suspend_member(self.admin, self.member)

        self.assertEqual(1, len(mail.outbox))

    def test_a_mail_failure_does_not_undo_the_suspension(self):
        """**The one place this project sends with the failure swallowed.**

        The suspension is committed by the time the send runs. Raising would
        report failure to an administrator whose action in fact succeeded, and
        invite them to repeat it. The block stands and the log carries the line.
        """
        mail.outbox.clear()

        with patch(
            'app.core.accounts.notifications.send_storefront_email',
            side_effect=OSError('mail server unreachable'),
        ):
            with self.assertLogs('app.core.accounts.notifications', level='ERROR'):
                with self.captureOnCommitCallbacks(execute=True):
                    administration.suspend_member(self.admin, self.member)

        self.member.club_membership.refresh_from_db()
        self.assertEqual(
            MembershipStatus.SUSPENDED, self.member.club_membership.status
        )


class Reinstating(RegisterTestCase):
    """Lifting a suspension, and refusing to invent a status."""

    def test_it_returns_a_suspended_account_to_active(self):
        administration.suspend_member(self.admin, self.member)

        administration.reinstate_member(self.admin, self.member)
        self.member.refresh_from_db()

        self.assertEqual(UserStatus.ACTIVE, self.member.club_membership.status)
        self.assertTrue(self.member.is_active)

    def test_it_is_idempotent_for_an_active_account(self):
        administration.reinstate_member(self.admin, self.member)
        self.member.refresh_from_db()

        self.assertEqual(UserStatus.ACTIVE, self.member.club_membership.status)

    def test_an_unpaid_membership_is_refused_rather_than_activated(self):
        # Nothing records where an account sat before a suspension, so this
        # cannot restore it -- and Pending payment is not a block the club
        # placed, it is a payment `app.core.payments` owns.
        waiting = self.account(
            'waiting@example.com', 'Waiting'
        )
        waiting.club_membership.status = MembershipStatus.PENDING_PAYMENT
        waiting.club_membership.save(update_fields=['status', 'updated_at'])

        with self.assertRaises(ValidationError) as refused:
            administration.reinstate_member(self.admin, waiting)

        self.assertEqual('not_suspended', refused.exception.code)
        waiting.refresh_from_db()
        self.assertEqual(MembershipStatus.PENDING_PAYMENT, waiting.club_membership.status)

    def test_an_erased_account_is_refused_before_activate_raises(self):
        # `User.activate` raises ValueError for one, which would be a 500.
        # `_editable` gets there first with something the endpoint can answer.
        self.member.soft_delete()

        with self.assertRaises(ValidationError):
            administration.reinstate_member(self.admin, self.member)


class DisclosingAnIdentityNumber(RegisterTestCase):
    """Reading the number in full, and the row that pays for it."""

    def setUp(self):
        super().setUp()
        self.member.id_number = ADULT_ID
        self.member.save()

    def test_it_returns_the_number_and_records_the_read(self):
        number, disclosure = administration.disclose_id_number(
            self.admin, self.member, reason='Verifying against the document on file.'
        )

        self.assertEqual(ADULT_ID, number)
        self.assertEqual(self.member, disclosure.member)
        self.assertEqual(self.admin, disclosure.read_by)
        self.assertEqual(
            'Verifying against the document on file.', disclosure.reason
        )

    def test_the_record_is_the_only_route(self):
        administration.disclose_id_number(
            self.admin, self.member, reason='Verifying against the document.'
        )
        administration.disclose_id_number(
            self.admin, self.member, reason='Asked again by the auditor.'
        )

        self.assertEqual(
            2, IdentityNumberDisclosure.objects.filter(member=self.member).count()
        )

    def test_a_blank_reason_is_refused_and_writes_nothing(self):
        with self.assertRaises(ValidationError) as refused:
            administration.disclose_id_number(self.admin, self.member, reason='')

        self.assertIn('reason', refused.exception.message_dict)
        self.assertFalse(IdentityNumberDisclosure.objects.exists())

    def test_a_reason_too_short_to_review_is_refused(self):
        # A disclosure whose reason is "x" is a disclosure nobody can review,
        # which is the same as no disclosure at all.
        with self.assertRaises(ValidationError):
            administration.disclose_id_number(self.admin, self.member, reason='ok')

        self.assertFalse(IdentityNumberDisclosure.objects.exists())

    def test_a_member_with_no_number_on_file_is_refused(self):
        # Writing a disclosure for a read that returned nothing would put a row
        # in an evidence table describing something that did not happen.
        bare = self.account('bare@example.com', 'Bare')

        with self.assertRaises(ValidationError) as refused:
            administration.disclose_id_number(
                self.admin, bare, reason='Checking whether one is on file.'
            )

        self.assertEqual('absent', refused.exception.code)
        self.assertFalse(IdentityNumberDisclosure.objects.exists())

    def test_an_erased_member_has_no_number_left_to_read(self):
        # `soft_delete` blanks the ciphertext, so this falls through to the
        # "nothing on file" refusal rather than needing a rule of its own.
        self.member.soft_delete()

        with self.assertRaises(ValidationError):
            administration.disclose_id_number(
                self.admin, self.member, reason='Looking for the erased document.'
            )


class TheDisclosureRecord(RegisterTestCase):
    """The two deletion rules on ``accounts.IdentityNumberDisclosure``."""

    def setUp(self):
        super().setUp()
        self.member.id_number = ADULT_ID
        self.member.save()
        administration.disclose_id_number(
            self.admin, self.member, reason='Verifying against the document.'
        )

    def test_deleting_the_auditor_keeps_the_disclosure(self):
        # SET_NULL: deleting the auditor's account must not erase the fact that
        # a disclosure happened, only who made it.
        self.admin.delete()

        disclosure = IdentityNumberDisclosure.objects.get()
        self.assertIsNone(disclosure.read_by_id)
        self.assertEqual(self.member, disclosure.member)
        self.assertLessEqual(disclosure.created_at, timezone.now())

    def test_erasing_the_member_keeps_the_disclosure(self):
        # `soft_delete` is the POPIA route and it keeps the row, so the evidence
        # that staff read a number survives the erasure of the number itself.
        self.member.soft_delete()

        self.assertEqual(1, IdentityNumberDisclosure.objects.count())

    def test_deleting_the_member_outright_takes_it(self):
        # CASCADE, matching `payments.Subscription.user` and
        # `documents.DocumentConsent.user`: a disclosure against an account that
        # no longer exists names nobody. Reachable only by a real deletion,
        # which is superusers only.
        self.member.delete()

        self.assertFalse(IdentityNumberDisclosure.objects.exists())
