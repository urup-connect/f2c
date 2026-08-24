"""Every account gets a role, and the three groups that mirror them appear.

Three operations and one judgement call.

The **column** lands with a default of ``member``, so every account already on
file becomes a member without a backfill. That is the right default rather than
merely the convenient one: it grants nothing over anybody else's records, and
membership is where a completed registration leaves everybody.

The **check constraint** is the part worth writing by hand. ``choices`` is a
form-level rule, and the interesting writes here -- a queryset ``.update()``, a
later data migration, a hand-typed ``UPDATE`` -- do not go near a form. Without
the constraint an unrecognised role leaves an account silently powerless, since
``roles.permissions_for`` returns an empty set for a role it does not know.

The **groups** are created here rather than being conjured on first use, so a
member of staff opening *Authentication and Authorisation* sees the three roles
waiting for the model permissions the strain, plant and order apps will bring.
Their names are written out as literals rather than imported from
``accounts.roles``: a group name is a row in a table, and a migration must keep
saying what it once did even if the application later renames a label.

The judgement call is the **superuser backfill**. ``role`` and ``is_staff`` are
independent by decision -- neither derives from the other -- so this is not a
rule being introduced, it is a one-time reading of an existing database: the
accounts that bootstrapped this deployment are its club administrators, and
``UserManager.create_superuser`` defaults new ones the same way. Any of them can
be moved back to Member in the admin.
"""
from django.db import migrations, models

#: The group names as of this migration. Deliberately literal -- see the module
#: docstring.
ROLE_GROUPS = {
    'admin': 'Admins',
    'cultivator': 'Cultivators',
    'member': 'Members',
}


def seed_role_groups(apps, schema_editor):
    """Create the three groups, backfill superusers, and mirror every account.

    The mirroring loop is what ``User.save`` would have done, done once for the
    rows that predate it. Historical models carry no custom ``save``, which is
    the usual reason a data migration has to repeat model behaviour rather than
    trigger it -- and the usual reason it must not drift from it.
    """
    Group = apps.get_model('auth', 'Group')
    User = apps.get_model('accounts', 'User')

    groups = {
        role: Group.objects.get_or_create(name=name)[0]
        for role, name in ROLE_GROUPS.items()
    }

    # See the module docstring: a reading of what is already there, not a rule.
    User.objects.filter(is_superuser=True).update(role='admin')

    for user in User.objects.only('id', 'role').iterator():
        group = groups.get(user.role)
        if group is not None:
            user.groups.add(group)


def drop_role_groups(apps, schema_editor):
    """Remove the three groups. Membership rows go with them.

    Reversible only in that sense: any model permission a member of staff had
    attached to a role group is removed along with the group, because the group
    is where it was attached. The column itself is removed by the reverse of
    ``AddField``, so nothing here has to unset it.
    """
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name__in=list(ROLE_GROUPS.values())).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_mobile_unique'),
        # The groups this seeds live in `auth`, and the same dependency the two
        # migrations before this one carry.
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('admin', 'Admin'),
                    ('cultivator', 'Cultivator'),
                    ('member', 'Member'),
                ],
                db_index=True,
                default='member',
                help_text=(
                    'What this account is. Separate from staff status, which '
                    'opens the Django admin and is granted independently.'
                ),
                max_length=16,
            ),
        ),
        migrations.AddConstraint(
            model_name='user',
            constraint=models.CheckConstraint(
                condition=models.Q(role__in=['admin', 'cultivator', 'member']),
                name='user_role_is_known',
                violation_error_message=(
                    'That is not a role this platform recognises.'
                ),
            ),
        ),
        migrations.RunPython(seed_role_groups, drop_role_groups),
    ]
