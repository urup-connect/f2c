"""Belonging to the club: the row that used to be four columns on ``User``.

``ClubMembership`` is one person's membership of Cultivators Collective. Before
the split it was ``User.status``, ``User.nickname``, ``User.nickname_key`` and
the four sharing-member columns, all on the account itself, because the club was
the whole platform.

**It is not any more.** ``design/verticals.md`` section 5 has the argument in
full; the short form is that ``is_active`` was derived from ``status`` under a
check constraint and ``PENDING_PAYMENT`` is not ``ACTIVE``, so on the old model
somebody buying carrots on the produce market could not sign in at all. Identity
and membership are different facts and now sit in different tables. C27.

**There is no ``club`` foreign key, and that is not an omission.** There is one
club. This app *is* the club's, which is what scopes the table -- a `Club` table
holding a single row would buy a join on every query and answer no question.
The market's equivalent is that a customer has no row here at all: an account
and nothing else is what buying produce requires.

Three things deliberately stayed on ``User``: the identity number, the date of
birth and its verification stamp. Club membership is what *requires* them, but
identity verification is plausibly platform-level -- paying a farmer out asks
the same question -- and moving two encrypted columns and a blind index is a
migration with a real failure mode and no upside. What moved is the requirement,
enforced in ``services`` when a membership is activated, not the columns. C27.
"""
import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from app.core.common.validators import nickname_key

__all__ = ['ClubMembership', 'MembershipStatus']


class MembershipStatus(models.TextChoices):
    """Where a membership sits in its lifecycle.

    These are the four values that used to live on ``User.status`` and describe
    the club rather than the account. ``PENDING`` is registered but not
    verified, ``PENDING_PAYMENT`` is on file and not paid for, ``SUSPENDED`` is
    a block that can be lifted, and ``LAPSED`` is where ``lapse_memberships``
    leaves an unpaid one.

    ``SHARING`` is the one value that is not a stage in a lifecycle: a
    **placeholder** a cultivator creates so that flowering stock can sit in the
    swap zone. **C6 is decided** -- a sharing member is not a person -- and the
    attestation machinery that assumed otherwise is gone rather than carried
    forward. What a placeholder needs beyond a label and the cultivator who
    made it is deferred to the swap zone, where the mechanics are defined.

    Note what is **not** here. ``INACTIVE`` was the old erasure landing state and
    belongs to the account, not the membership: erasure is a fact about a person
    and ``User.status`` still carries it.
    """

    PENDING = 'pending', 'Pending verification'
    PENDING_PAYMENT = 'pending_payment', 'Pending payment'
    ACTIVE = 'active', 'Active'
    SUSPENDED = 'suspended', 'Suspended'
    LAPSED = 'lapsed', 'Lapsed'
    SHARING = 'sharing', 'Sharing member (no sign-in)'


class ClubMembershipQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=MembershipStatus.ACTIVE)

    def by_nickname(self, value):
        """Memberships wearing this nickname, compared case-insensitively.

        A plain equality against the derived key rather than an annotated
        ``Lower('nickname')``, for the reason the old ``UserManager.by_nickname``
        gave: the annotation could use no index, and the two disagreed at the
        margin because the key trims the ends and ``Lower`` does not.
        """
        key = nickname_key(value)
        if not key:
            return self.none()
        return self.filter(nickname_key=key)

    def nickname_is_taken(self, value, *, exclude_pk=None):
        candidates = self.by_nickname(value)
        if exclude_pk is not None:
            candidates = candidates.exclude(pk=exclude_pk)
        return candidates.exists()


class ClubMembership(models.Model):
    """One person's membership of the club."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)

    # CASCADE, unlike almost every other foreign key here. A membership without
    # the person is not a record of anything, and the person's row is the one
    # that survives erasure -- `User.soft_delete` keeps the row precisely so
    # that what they grew and what they paid still points somewhere. Hard-
    # deleting a User is a development act, and this should follow it.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='club_membership',
    )

    status = models.CharField(
        max_length=16,
        choices=MembershipStatus.choices,
        default=MembershipStatus.PENDING,
        db_index=True,
    )

    # What the club shows. Members of a collective know each other by this far
    # more often than by a legal name, and it is a property of belonging rather
    # than of the person -- a produce customer has a name and needs no
    # pseudonym, which is why this moved off `User` with the split.
    nickname = models.CharField(max_length=60, blank=True)

    # The form uniqueness is actually decided on. Derived by `save` on every
    # write, never set by hand, and not a form field.
    #
    # The rule is "one nickname per member, compared case-insensitively, and
    # blanks do not collide". Its natural spelling is
    # `UniqueConstraint(Lower('nickname'), condition=~Q(nickname=''))` -- an
    # expression index *and* a partial index, and **MySQL builds neither while
    # Django omits what the backend cannot build without saying so**. The rule
    # was therefore absent from every deployed schema while the model, the
    # migration and the tests all still described it. `design/backend.md`
    # section 8.2, and `design/migrations.md` section 2.
    #
    # Null rather than blank for the empty case: nulls are distinct under a
    # unique index on every backend here, so any number of memberships may hold
    # no nickname while no two may hold the same one.
    nickname_key = models.CharField(
        max_length=60, null=True, blank=True, editable=False
    )

    joined_at = models.DateTimeField(auto_now_add=True)
    activated_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ------------------------------------------------------------------
    # The sharing member
    # ------------------------------------------------------------------
    # **C6 is decided: a sharing member is a placeholder, not a person.** One
    # column survives the decision, and three do not.
    #
    # The three that went were the POPIA consent attestation -- who swore that
    # this person had consented and been given the collection notice, when, and
    # under which wording. A placeholder consents to nothing and is given no
    # notice, so an attestation over it recorded a ceremony around a fiction.
    # They were deleted rather than left in place because deleting them was free
    # exactly once: the schema is being rebuilt from empty, and C6's own
    # recommendation is that unwinding "real person" after launch means a
    # migration that deletes stored identity numbers.
    #
    # `User.id_number` follows the same logic and is not enforced for a
    # placeholder -- the column stays on the account for the people who do need
    # one, and `register_sharing_member` stops asking. **C7 is not resolved by
    # this**, only changed: the legal question moves from allocating plants to
    # named adults to the club holding the stock itself.
    #
    # What a placeholder needs beyond this is the swap zone's to define, and is
    # deliberately not guessed at here.
    #
    # Points at the **producer**, not at the person who happened to create it.
    # A placeholder holds a farm's stock, and it must not be orphaned when the
    # grower who keyed it in leaves. A string reference rather than an import,
    # so `membership` does not depend on `cultivators` at module load.

    registered_by = models.ForeignKey(
        'producers.Producer',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='sharing_placeholders',
        help_text='The producer whose stock this placeholder holds.',
    )

    objects = ClubMembershipQuerySet.as_manager()

    class Meta:
        ordering = ('-joined_at',)
        verbose_name = 'club membership'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=MembershipStatus.values),
                name='club_membership_status_is_known',
                violation_error_message=(
                    'That is not a membership status this platform recognises.'
                ),
            ),
            models.UniqueConstraint(
                fields=['nickname_key'],
                name='club_membership_nickname_key_unique',
                violation_error_message='That nickname is already taken.',
            ),
            # The backstop for a write that went around `save`. A stale key is
            # worse here than a stale `is_active` was: it means a member renamed
            # by hand still occupies their old name and can be given somebody
            # else's, silently, because every read goes through the key.
            #
            # `nickname_key__isnull=False` beside the equality is load-bearing.
            # A CHECK fails only when its condition is *false*, and a comparison
            # against null is *unknown*, which passes -- so without the explicit
            # null test a row with a nickname and no key would satisfy this by
            # being unanswerable.
            models.CheckConstraint(
                condition=(
                    models.Q(nickname='', nickname_key__isnull=True)
                    | models.Q(
                        nickname_key__isnull=False,
                        nickname_key=Lower('nickname'),
                    )
                ),
                name='club_membership_nickname_key_matches_nickname',
                violation_error_message=(
                    'nickname_key is derived from nickname and cannot be set '
                    'directly.'
                ),
            ),
            # The one thing a placeholder cannot be without: the cultivator
            # whose stock it holds. Without it the row is orphaned stock, which
            # is the failure this has always been about.
            #
            # **Deliberately weaker than the constraint it replaces.** The old
            # one also required a nickname and a consent attestation. The
            # attestation is gone with C6. The nickname requirement dropped to
            # the service layer, and the erasure exemption went with it: it
            # existed because `User.soft_delete` blanks the nickname and a
            # database CHECK cannot look across to `User.deleted_at` to know
            # why. A placeholder has no personal data to erase, so the whole
            # interaction disappears.
            #
            # The swap zone will want this tighter. Tightening a constraint
            # against a defined feature is ordinary work; loosening one that has
            # governed real rows is not.
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=MembershipStatus.SHARING)
                    | models.Q(registered_by__isnull=False)
                ),
                name='club_membership_sharing_member_has_a_cultivator',
                violation_error_message=(
                    'A sharing member holds a cultivator’s stock, so it needs '
                    'the cultivator it was created under.'
                ),
            ),
        ]

    def __str__(self):
        return self.nickname or str(self.user)

    @property
    def is_sharing_member(self):
        """A placeholder holding flowering stock in the swap zone. C6.

        Not a member and not a person: it pays no subscription, agrees to
        nothing, holds no permissions and signs in nobody. The club's name for
        it is the reason this reads oddly.
        """
        return self.status == MembershipStatus.SHARING

    @property
    def may_use_the_club(self):
        """Whether this membership opens the club's own destinations.

        Distinct from whether the person may sign in, which is ``User.status``
        and is now a separate question. Under the split an unpaid registrant
        *can* sign in and lands on a screen asking them to pay -- see
        ``design/verticals.md`` section 5.
        """
        return self.status == MembershipStatus.ACTIVE

    def save(self, *args, update_fields=None, **kwargs):
        # Trimmed for one stored form, and it is also what makes `nickname_key`
        # exactly `LOWER(nickname)` -- without it ` Bob ` would be stored with a
        # key of `bob` and the check constraint would refuse the model's own
        # write.
        self.nickname = (self.nickname or '').strip()
        self.nickname_key = nickname_key(self.nickname) or None

        if update_fields is not None and 'nickname' in set(update_fields):
            # A partial save that renames a member must not leave the key it is
            # compared on behind.
            update_fields = set(update_fields) | {'nickname_key'}

        super().save(*args, update_fields=update_fields, **kwargs)
