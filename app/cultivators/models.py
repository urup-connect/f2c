"""The cultivator's public face.

The third model ``todo.md`` Block 1 asks for, beside the strain and the finished
product type: "Cultivator profile: public description, image, pseudonym". It is
its own app rather than a fourth class in ``strains`` because it is not a strain,
and because Block 2 grows it into the cultivator organisation -- the farm as a
record, with its primary cultivator, its appointed staff, its collection address
and its bank details. Those arrive here.

**There is no pseudonym field, and that is the decision worth defending.**

``member-roles.md`` conceals members behind a nickname, and
``plant-id-numbers.md`` puts a "cultivator pseudonym" on the certificate of
ownership -- so the club clearly needs a public name for a grower. What it does
not need is a *second namespace* for one. ``backend.md`` section 3.6 already
settled the same question for sharing members and gave the reason in one line:
"two people wearing one name in the swap zone is impersonation, not a
collision". A ``pseudonym`` column here would be exactly that second namespace,
free to hold a value identical to another member's nickname, and no single
constraint can span the two.

So the pseudonym *is* ``User.nickname``. It is already unique
case-insensitively across every account, it is already what
``accounts.User.display_name`` returns, and it is already the only member
identifier the API is allowed to expose. A cultivator wanting a trading name
sets it as their nickname.

One consequence, recorded because it is not obvious: nickname uniqueness is
enforced by a **partial** unique index (blanks excluded, because staff have none
and erasure blanks the field), and MySQL cannot express one. Django omits it
silently on a backend that does not support it, so on MySQL nothing stops two
accounts sharing a nickname. That is a pre-existing hole in ``accounts``, not one
this app opens, but this app is the first thing to depend on the guarantee.

**MySQL.** The same four considerations as ``strains.models``, and one more:
this table's uniqueness is a one-to-one on a foreign key, which is an
unconditional unique index and portable.
"""
import uuid

from django.conf import settings
from django.db import models


def profile_image_upload_to(instance, filename):
    """``cultivators/<profile id>/image<ext>``.

    One path per profile, overwritten in place -- the same reasoning as
    ``strains.models.listing_image_upload_to``, which also records the open
    question about which storage a public catalogue image belongs in.
    """
    extension = (filename.rsplit('.', 1)[-1] or 'jpg').lower()[:8]
    return f'cultivators/{instance.pk}/image.{extension}'


class CultivatorProfileQuerySet(models.QuerySet):
    def published(self):
        """Profiles a member may see."""
        return self.filter(is_published=True)


class CultivatorProfile(models.Model):
    """What a member sees about a grower, and nothing else about them.

    A profile is optional in the sense that an account holds the cultivator role
    without one -- the role is granted in the admin, and a profile is written
    afterwards. Stock can exist before the profile does; what cannot happen is a
    member reaching an unpublished one.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # One profile per account. PROTECT rather than CASCADE, consistent with
    # `accounts.User.registered_by`: the routine answer to a departing grower is
    # erasure, which keeps the row, and a hard delete that silently removed the
    # public identity attached to sold plants is not something to make easy.
    #
    # Points at a user, and in Block 2 will point at -- or be absorbed into --
    # the farm. `strains.CultivatorStrainListing` carries the same note at
    # length.
    cultivator = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='cultivator_profile',
    )

    public_description = models.TextField(
        blank=True,
        help_text='Your description of your farm, shown to members. '
                  'Compliance-governed copy: no claim about what cannabis does.',
    )
    image = models.ImageField(
        upload_to=profile_image_upload_to,
        blank=True,
        help_text='One photograph, shown beside your name.',
    )

    # A profile is drafted before it is shown. Unpublished is the default so
    # that creating the row is never itself the act of publishing -- the same
    # argument `documents` makes for publication being an action rather than a
    # save.
    is_published = models.BooleanField(
        default=False,
        help_text='Members see this profile only once it is published.',
    )

    objects = CultivatorProfileQuerySet.as_manager()

    class Meta:
        ordering = ('cultivator__nickname',)
        verbose_name = 'cultivator profile'

    def __str__(self):
        # `display_name`, never a legal name or an email address. Section 6.6 of
        # `roles-and-permissions.md`, and `__str__` reaches admin log entries.
        return self.cultivator.display_name

    @property
    def pseudonym(self):
        """The grower's public name. See the module docstring on why it is read.

        Every caller that wants a cultivator pseudonym -- the strain comparison
        screen, the certificate of ownership, the plant's derived pseudonym field
        in Block 3 -- reads this rather than reaching for ``nickname`` directly,
        so that if the club ever does decide a farm needs a trading name distinct
        from its owner's nickname, there is one place to change.
        """
        return self.cultivator.display_name
