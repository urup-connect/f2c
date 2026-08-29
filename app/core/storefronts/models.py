"""Which storefront a thing belongs to, and who administers one.

Two storefronts sit on this platform: the members' cannabis club, and the public
produce market. ``design/verticals.md`` is the whole reasoning; this module is
the two records the rest of the code hangs off.

**A storefront is a column, not a table.** There are exactly two, adding a third
is a product decision rather than runtime data, and every row that carries one
carries exactly one -- a document belongs to the club or to the market and never
to both, by decision (``verticals.md`` section 6). That is the same shape as
``UserRole`` before it and gets the same treatment: choices for the form layer,
a check constraint for everything that walks past the form layer. A table would
buy a foreign key and cost a join on every scoped query, a seed migration, and
the question of what happens when somebody deletes a row.

``StorefrontStaff`` is the administrator of one storefront. It is deliberately
*not* a role on ``ClubMembership``: an administrator is not a member, pays no
subscription, and the market has administrators but no membership at all. See
C28 and C29.

**There is no UC tier here.** The platform operator is ``User.is_staff`` and
works in the Django admin -- C29. Nothing in this module grants that, and adding
a ``uc_admin`` storefront value would be the fifth-role mistake again.
"""
import uuid

from django.conf import settings
from django.db import models

__all__ = ['Storefront', 'StorefrontStaff']


class Storefront(models.TextChoices):
    """The two shopfronts this platform serves.

    ``CLUB`` is Cultivators Collective: membership, subscription, age gate, and
    a plant owned by the member who bought it. ``MARKET`` is the produce market:
    no membership, no subscription, and fungible stock sold by quantity.

    The values are short and stable because they appear in storage paths --
    ``documents/<storefront>/<slug>/<label>/<file>`` -- and in the host-to-
    storefront resolution the unauthenticated endpoints need. Renaming one would
    move every document a member has already agreed to.
    """

    CLUB = 'club', 'Cultivators Collective'
    MARKET = 'market', 'Produce market'


class StorefrontStaffQuerySet(models.QuerySet):
    def for_storefront(self, storefront):
        return self.filter(storefront=storefront)

    def administrators_of(self, storefront):
        """The people who run one storefront, newest appointment last."""
        return self.for_storefront(storefront).order_by('appointed_at')


class StorefrontStaff(models.Model):
    """One person's appointment as an administrator of one storefront.

    Held as its own table rather than as a value on the membership because the
    two relationships are different: a club administrator runs the club without
    joining it, and a market administrator has nothing to join. Under the old
    single-column model an administrator was ``role='admin'`` on a ``User``
    whose status had to be ``ACTIVE``, which after the split would have meant
    issuing them a club membership they never pay for.

    One person may hold rows for both storefronts. That is the point of the
    split: a column could not say it.

    **Revocation deletes the row.** There is no ``revoked_at``, and the absence
    is deliberate rather than an oversight -- an appointment that has ended is
    not a fact the platform needs to reason about, and Django's admin
    ``LogEntry`` already records who removed it and when. That is a weaker audit
    than ``DocumentConsent`` keeps, and the difference is intended: a consent is
    evidence a member gave, and an appointment is bookkeeping the club did.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='storefront_appointments',
    )
    storefront = models.CharField(
        max_length=16,
        choices=Storefront.choices,
        db_index=True,
        help_text='Which storefront this person administers.',
    )

    # Who made the appointment. SET_NULL rather than PROTECT: an administrator
    # appointed by somebody who has since been erased is still an
    # administrator, and the appointment must not block that erasure. The
    # opposite call to `DocumentConsent.version`, and for the opposite reason --
    # there the pointed-at row *is* the meaning of the record, and here it is
    # provenance.
    appointed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='storefront_appointments_made',
        help_text='The platform operator who granted this. Blank once they are erased.',
    )
    appointed_at = models.DateTimeField(auto_now_add=True)

    objects = StorefrontStaffQuerySet.as_manager()

    class Meta:
        ordering = ('storefront', 'appointed_at')
        verbose_name = 'storefront administrator'
        verbose_name_plural = 'storefront administrators'
        constraints = [
            # One appointment per person per storefront. Appointing somebody
            # twice is not a second appointment, it is the same one.
            models.UniqueConstraint(
                fields=('user', 'storefront'),
                name='storefront_staff_once_per_storefront',
                violation_error_message=(
                    'This person already administers that storefront.'
                ),
            ),
            # `choices` is a form-level rule that a queryset `.update()` or a
            # data migration walks straight past, and the failure mode is quiet:
            # an unrecognised storefront is an appointment to nothing that no
            # scoped query will ever return. The same argument the old
            # `user_role_is_known` constraint made.
            models.CheckConstraint(
                condition=models.Q(storefront__in=Storefront.values),
                name='storefront_staff_storefront_is_known',
                violation_error_message=(
                    'That is not a storefront this platform serves.'
                ),
            ),
        ]

    @property
    def administers_club(self):
        """Whether this appointment is over the club rather than the market.

        Asked of the appointment by ``accounts.roles.permissions_for`` so that
        module needs no import from here and the dependency stays
        one-directional -- ``accounts`` is the app everything else depends on.
        """
        return self.storefront == Storefront.CLUB

    def __str__(self):
        return f'{self.user} — {self.get_storefront_display()} administrator'
