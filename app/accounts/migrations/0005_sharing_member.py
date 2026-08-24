"""The sharing member arrives: a fourth role, a status, and the record it needs.

A sharing member is an identity a cultivator registers so it can hold flowering
plants that appear in the swap zone. They never sign in. Four things follow, and
all four are in this migration.

The **role** and the **status** are new choices, so the two `AlterField`
operations carry no data change — an existing account is none of these things.

The **columns** are the sharing member's own: the cultivator who registered
them, and the three that record the consent attestation POPIA needs for holding
somebody else's name and identity number. All nullable, because every account
already on file is not a sharing member and never was.

The **two check constraints** are the part worth writing by hand, and they are
why this is not four `AddField`s in a row. `sharing_member_never_signs_in` makes
"holds stock, does not authenticate" a fact about the database rather than a
convention someone can undo by typing an email address into the admin.
`sharing_member_is_complete` refuses a sharing member with no cultivator, no
attestation or no nickname — orphaned stock, an unlawful record, and unnamed
stock in the swap zone respectively.

`sharing_member_is_complete` exempts erased rows. `User.soft_delete` blanks the
nickname by design, so without the exemption the POPIA erasure route — the one
operation that must always work — would be refused by the database on exactly
the records most likely to need it.

The **group** is seeded the way migration 0004 seeded the first three, with the
name written out as a literal for the same reason: a group name is a row in a
table, and this migration must keep saying what it once said even if the
application later renames a label.

No backfill. There is nothing to convert: a sharing member is created by
`accounts.services.register_sharing_member`, and before this migration none
existed.
"""
import django.db.models.deletion
from django.db import migrations, models

#: The group mirroring the new role, as of this migration. Deliberately literal.
SHARING_MEMBER_GROUP = 'Sharing members'

#: Role and status values as of this migration, frozen here so a later rename in
#: `accounts.roles` cannot change what these operations did.
ROLE_CHOICES = [
    ('admin', 'Admin'),
    ('cultivator', 'Cultivator'),
    ('member', 'Member'),
    ('sharing_member', 'Sharing member'),
]
STATUS_CHOICES = [
    ('pending', 'Pending verification'),
    ('pending_payment', 'Pending payment'),
    ('active', 'Active'),
    ('suspended', 'Suspended'),
    ('inactive', 'Inactive'),
    ('sharing', 'Sharing member (no sign-in)'),
]


def seed_sharing_member_group(apps, schema_editor):
    """Create the group the new role mirrors into.

    Nobody holds the role yet, so there is nothing to add to it. It exists ahead
    of the first sharing member so that staff opening *Authentication and
    Authorisation* see the four roles the platform has, and so the model
    permissions the plant and swap apps will bring have somewhere to hang.
    """
    Group = apps.get_model('auth', 'Group')
    Group.objects.get_or_create(name=SHARING_MEMBER_GROUP)


def drop_sharing_member_group(apps, schema_editor):
    """Remove it again. Membership rows go with it.

    Any account still wearing the role keeps the role — the reverse of
    `AlterField` restores the old choices but touches no data — so reversing
    this migration with sharing members on file leaves rows whose role the
    application no longer recognises. `roles.permissions_for` answers nothing
    for an unknown role rather than raising, which is what makes that survivable
    rather than an outage, but it is a reason not to reverse this casually.
    """
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name=SHARING_MEMBER_GROUP).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_user_role'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=ROLE_CHOICES,
                db_index=True,
                default='member',
                help_text=(
                    'What this account is. Separate from staff status, which '
                    'opens the Django admin and is granted independently.'
                ),
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name='user',
            name='status',
            field=models.CharField(
                choices=STATUS_CHOICES,
                db_index=True,
                default='pending',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='registered_by',
            field=models.ForeignKey(
                blank=True,
                help_text='The cultivator who registered this sharing member.',
                limit_choices_to={'role': 'cultivator'},
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='sharing_members',
                to='accounts.user',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='sharing_consent_attested_by',
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    'Who confirmed that this sharing member consented and was '
                    'given the collection notice.'
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='sharing_consents_attested',
                to='accounts.user',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='sharing_consent_attested_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='sharing_consent_version',
            field=models.CharField(blank=True, default='1', max_length=32),
        ),
        # The check constraint from 0004 named the three roles that existed
        # then. It has to be replaced rather than added to, or `sharing_member`
        # is a role the application grants and the database refuses.
        migrations.RemoveConstraint(
            model_name='user',
            name='user_role_is_known',
        ),
        migrations.AddConstraint(
            model_name='user',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    role__in=['admin', 'cultivator', 'member', 'sharing_member']
                ),
                name='user_role_is_known',
                violation_error_message=(
                    'That is not a role this platform recognises.'
                ),
            ),
        ),
        migrations.AddConstraint(
            model_name='user',
            constraint=models.CheckConstraint(
                condition=(
                    ~models.Q(role='sharing_member')
                    | ~models.Q(status='active')
                ),
                name='sharing_member_never_signs_in',
                violation_error_message=(
                    'A sharing member holds stock and never signs in, so the '
                    'account cannot be Active.'
                ),
            ),
        ),
        migrations.AddConstraint(
            model_name='user',
            constraint=models.CheckConstraint(
                condition=(
                    ~models.Q(role='sharing_member')
                    | models.Q(deleted_at__isnull=False)
                    | (
                        models.Q(registered_by__isnull=False)
                        & models.Q(sharing_consent_attested_by__isnull=False)
                        & models.Q(sharing_consent_attested_at__isnull=False)
                        & ~models.Q(nickname='')
                    )
                ),
                name='sharing_member_is_complete',
                violation_error_message=(
                    'A sharing member needs the cultivator who registered '
                    'them, a recorded consent attestation, and a nickname.'
                ),
            ),
        ),
        migrations.RunPython(seed_sharing_member_group, drop_sharing_member_group),
    ]
