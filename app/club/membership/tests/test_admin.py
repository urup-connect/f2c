"""Tests for the club membership admin.

The page is new: before C27 none of what is on it was its own record. Three
things here are worth a test rather than a look, and they are the three that
would fail silently.

The **nickname clash** is the first. The uniqueness rule lives on
``nickname_key``, not on ``nickname``, so a form that compared the text it was
given would agree with the index for most inputs and disagree at exactly the
margins the key exists to settle -- and the disagreement renders as an
``IntegrityError`` page rather than a message. The admin form calls the
register's own check, and the tests below pin that it reaches the index.

The **session flush** is the second. Suspending through the action ends every
live session; suspending by moving the dropdown is a different code path, and a
membership left Suspended with a working browser is not a visible failure. It
is the one thing ``save_model`` exists for.

The third is **who the actions refuse**. They delegate to
``administration.suspend_member`` and ``reinstate_member`` so the rules cannot
drift, and the point of the delegation is lost if a refusal is swallowed instead
of reported -- so the tests assert on the message, not only on the record.
"""
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.models import Session
from django.test import RequestFactory, TestCase

from app.club.membership.admin import ClubMembershipAdmin, ClubMembershipAdminForm
from app.club.membership.models import ClubMembership, MembershipStatus
from app.core.accounts.models import User, UserStatus
from f2c.testing import (
    make_account,
    make_administrator,
    make_member,
    make_producer,
    make_sharing_placeholder,
)


def request_for(user, path='/admin/membership/clubmembership/'):
    """A request the admin can attach messages to.

    ``message_user`` writes through the messages framework, which needs a
    storage backend on the request -- the middleware normally puts it there and
    ``RequestFactory`` does not run middleware.
    """
    request = RequestFactory().post(path)
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


def messages_on(request):
    return [str(message) for message in request._messages]


class NicknameClashTests(TestCase):
    """The unique index reached as a form error rather than a 500."""

    def setUp(self):
        self.taken = make_member('taken@example.com', nickname='Thabo')
        self.other = make_member('other@example.com', nickname='Naledi')

    def form_for(self, membership, nickname):
        return ClubMembershipAdminForm(
            instance=membership,
            data={
                'user': membership.user_id,
                'status': membership.status,
                'nickname': nickname,
            },
        )

    def test_a_nickname_another_member_wears_is_refused_on_the_field(self):
        form = self.form_for(self.other.club_membership, 'Thabo')

        self.assertFalse(form.is_valid())
        self.assertIn('nickname', form.errors)

    def test_the_comparison_is_case_insensitive_like_the_index(self):
        """``nickname_key`` is ``LOWER(nickname)``, so ``THABO`` is taken too.

        The case that a hand-written equality check would let through and the
        database would then refuse with a 500.
        """
        form = self.form_for(self.other.club_membership, 'THABO')

        self.assertFalse(form.is_valid())
        self.assertIn('nickname', form.errors)

    def test_a_member_may_keep_their_own_nickname(self):
        """The clash check excludes the row being edited.

        Without it, saving the page without touching the nickname would refuse
        the member their own name.
        """
        form = self.form_for(self.taken.club_membership, 'Thabo')

        self.assertTrue(form.is_valid(), form.errors)

    def test_a_blank_nickname_is_allowed_and_does_not_collide(self):
        """Blank is not taken. ``nickname_key`` is null, and nulls are distinct.

        A produce-market customer who later joined the club has a name and no
        pseudonym, so any number of memberships may hold none.
        """
        self.other.club_membership.nickname = ''
        self.other.club_membership.save()

        form = self.form_for(self.taken.club_membership, '')

        self.assertTrue(form.is_valid(), form.errors)
        membership = form.save()
        self.assertEqual(membership.nickname, '')
        self.assertIsNone(membership.nickname_key)

    def test_a_reserved_nickname_keeps_its_own_wording(self):
        """Not folded into "already taken" -- they are different facts.

        An administrator is the one person who can act on the difference, so
        the sentence ``validate_nickname`` raised has to survive the form.
        """
        form = self.form_for(self.other.club_membership, 'x')

        self.assertFalse(form.is_valid())
        self.assertNotIn(
            'Another member already wears that nickname.',
            form.errors['nickname'],
        )


class _SubmittedForm:
    """The two attributes ``save_model`` reads off a bound admin form.

    A stand-in rather than a real ``ClubMembershipAdminForm``, because what is
    under test is what ``save_model`` does with ``changed_data`` and
    ``initial`` -- building a genuine bound form to reach it would test the
    form's own validation a second time and obscure which state is being
    described.
    """

    def __init__(self, changed, was_status):
        self.changed_data = changed
        self.initial = {'status': was_status}


class StatusEditTests(TestCase):
    """``save_model``: a membership edited out of Active loses its sessions.

    The action route flushes sessions inside ``suspend_member``. The form route
    is a different code path, and a membership left Suspended with a live
    browser is not a visible failure -- which is why it is asserted rather than
    looked at.
    """

    def setUp(self):
        self.admin = ClubMembershipAdmin(ClubMembership, AdminSite())
        self.operator = make_administrator('operator@example.com', is_staff=True)
        self.member = make_member('member@example.com', nickname='Thabo')

    def test_moving_a_membership_out_of_active_ends_its_sessions(self):
        self.client.force_login(self.member)
        self.assertEqual(Session.objects.count(), 1)

        membership = self.member.club_membership
        membership.status = MembershipStatus.SUSPENDED
        self.admin.save_model(
            request_for(self.operator),
            membership,
            _SubmittedForm(['status'], MembershipStatus.ACTIVE),
            change=True,
        )

        self.assertEqual(
            ClubMembership.objects.get(user=self.member).status,
            MembershipStatus.SUSPENDED,
        )
        self.assertEqual(Session.objects.count(), 0)

    def test_an_edit_that_leaves_the_membership_active_keeps_the_session(self):
        """The flush is scoped to losing the club, not to any save at all.

        An administrator correcting a nickname must not sign the member out.
        """
        self.client.force_login(self.member)

        membership = self.member.club_membership
        membership.nickname = 'Thabo-Renamed'
        self.admin.save_model(
            request_for(self.operator),
            membership,
            _SubmittedForm(['nickname'], MembershipStatus.ACTIVE),
            change=True,
        )

        self.assertEqual(
            ClubMembership.objects.get(user=self.member).nickname,
            'Thabo-Renamed',
        )
        self.assertEqual(Session.objects.count(), 1)

    def test_the_account_is_left_alone_when_the_membership_is_suspended(self):
        """C27's whole point: a club matter must not close the market.

        ``User.deactivate`` would have done exactly that on the old model,
        because ``is_active`` was derived from the one status column.
        """
        membership = self.member.club_membership
        membership.status = MembershipStatus.SUSPENDED
        self.admin.save_model(
            request_for(self.operator),
            membership,
            _SubmittedForm(['status'], MembershipStatus.ACTIVE),
            change=True,
        )

        account = User.objects.get(pk=self.member.pk)
        self.assertTrue(account.is_active)
        self.assertEqual(account.status, UserStatus.ACTIVE)


class ActionTests(TestCase):
    """The two actions delegate, and report what the service refused."""

    def setUp(self):
        self.admin = ClubMembershipAdmin(ClubMembership, AdminSite())
        self.operator = make_administrator('operator@example.com', is_staff=True)
        self.member = make_member('member@example.com', nickname='Thabo')

    def run_action(self, name, queryset, actor=None):
        request = request_for(actor or self.operator)
        getattr(self.admin, name)(request, queryset)
        return messages_on(request)

    def selection(self, *users):
        return ClubMembership.objects.filter(user__in=users)

    def test_suspend_moves_the_membership_and_not_the_account(self):
        """The account still signs in — it may have a market to shop on."""
        self.run_action('suspend_memberships', self.selection(self.member))

        self.member.refresh_from_db()
        self.assertEqual(
            self.member.club_membership.status, MembershipStatus.SUSPENDED
        )
        self.assertTrue(self.member.is_active)

    def test_reinstate_returns_a_suspended_membership_to_active(self):
        self.run_action('suspend_memberships', self.selection(self.member))
        self.run_action('reinstate_memberships', self.selection(self.member))

        self.member.refresh_from_db()
        self.assertEqual(
            self.member.club_membership.status, MembershipStatus.ACTIVE
        )

    def test_a_placeholder_is_refused_by_name_rather_than_counted(self):
        """C6: a placeholder's record belongs to the producer that made it.

        Reported with the sentence the service raised, because "1 skipped" is
        not something an administrator can act on.
        """
        producer = make_producer('Kloof Farm')
        placeholder = make_sharing_placeholder('Sharer', producer=producer)

        messages = self.run_action(
            'suspend_memberships', self.selection(placeholder)
        )

        self.assertEqual(
            ClubMembership.objects.get(user=placeholder).status,
            MembershipStatus.SHARING,
        )
        self.assertTrue(any('Sharer' in message for message in messages))

    def test_reinstating_an_unpaid_membership_is_refused(self):
        """Only a suspended membership is a block the club placed on somebody.

        Activating a pending-payment one here would hand them the club for
        free, which is what the payment screen is for.
        """
        unpaid = make_member(
            'unpaid@example.com',
            nickname='Unpaid',
            status=MembershipStatus.PENDING_PAYMENT,
        )

        messages = self.run_action(
            'reinstate_memberships', self.selection(unpaid)
        )

        self.assertEqual(
            ClubMembership.objects.get(user=unpaid).status,
            MembershipStatus.PENDING_PAYMENT,
        )
        self.assertTrue(messages)

    def test_a_caller_without_the_permission_is_told_so_and_nothing_moves(self):
        """``PermissionDenied`` reported on the page rather than as a 403.

        Staff status opens this admin site; it grants no platform permission at
        all — C29 — so an operator with no club appointment reaches here.
        """
        plain_staff = make_account('plain@example.com', is_staff=True)

        messages = self.run_action(
            'suspend_memberships', self.selection(self.member), actor=plain_staff
        )

        self.assertEqual(
            ClubMembership.objects.get(user=self.member).status,
            MembershipStatus.ACTIVE,
        )
        self.assertTrue(messages)

    def test_an_anonymous_caller_is_refused(self):
        messages = self.run_action(
            'suspend_memberships',
            self.selection(self.member),
            actor=AnonymousUser(),
        )

        self.assertEqual(
            ClubMembership.objects.get(user=self.member).status,
            MembershipStatus.ACTIVE,
        )
        self.assertTrue(messages)
