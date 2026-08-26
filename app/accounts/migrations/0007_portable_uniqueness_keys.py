"""Move nickname and mobile uniqueness onto columns every backend can index.

``design/backend.md`` section 8.2. Both rules were partial unique indexes --
``UniqueConstraint(Lower('nickname'), condition=~Q(nickname=''))`` and
``UniqueConstraint(fields=['mobile'], condition=~Q(mobile=''))`` -- and **MySQL
builds neither.** Django omits a constraint the backend cannot build without
raising anything, so both rules were absent from any MySQL schema while the
model, this app's migrations and its tests all still described them.

The rules now hang off two derived columns that are null where the old condition
excluded a row, which expresses the same thing as an unconditional unique index
on every backend.

**The backfill is the part worth reading.** Adding the columns leaves every
existing row null, so without it the new constraints would be satisfied
trivially and no existing account would be protected.

It also refuses rather than repairs, and this is the first migration in a
position to have to. Because the constraints it replaces may never have existed
on a MySQL database, this is the first moment anything has actually checked
whether the data obeys them -- so duplicates are counted before the first
``ALTER`` rather than discovered when the index build fails. MySQL has no
transactional DDL, so a migration that dies halfway leaves a partly changed
schema.

**It counts, and never names**, which is the rule ``0003_mobile_unique``
established and the reason its message reads the way it does: a nickname and a
mobile number are both personal information, and a migration that printed one
would write it into every deploy log and CI transcript that ran. Whoever resolves
the clash finds the rows in the admin, where reading them is an authorised act.
"""
from django.db import migrations, models
from django.db.models.functions import Lower


def normalise_nickname(value):
    """Must match ``common.validators.nickname_key``.

    Inlined rather than imported. A migration is a historical record and has to
    keep applying the same way in five years; importing application code would
    let a later edit to that function silently change what this migration did.
    """
    return str(value or '').strip().lower()


def count_clashes(values):
    """How many keys are held by more than one row. Never which keys."""
    holders = {}
    for value in values:
        if value:
            holders[value] = holders.get(value, 0) + 1
    return sum(1 for held_by in holders.values() if held_by > 1)


def fill_keys(apps, schema_editor):
    User = apps.get_model('accounts', 'User')

    rows = list(User.objects.values_list('pk', 'nickname', 'mobile'))

    clashes = count_clashes(normalise_nickname(nickname) for _, nickname, _ in rows)
    if clashes:
        raise RuntimeError(
            f'{clashes} nickname(s) are held by more than one account, so a '
            'unique constraint cannot be added. This is what the partial index '
            'being replaced was meant to prevent and, on MySQL, never built. '
            'Find them in the Django admin by searching the Members list, and '
            'decide which account keeps each one -- the nicknames are '
            'deliberately not printed here, because a deploy log is not a place '
            "for members' personal details."
        )

    clashes = count_clashes(mobile for _, _, mobile in rows)
    if clashes:
        raise RuntimeError(
            f'{clashes} mobile number(s) are held by more than one account, so '
            'a unique constraint cannot be added. One handset, one member is a '
            'club rule (see the field on accounts.User), so this needs a '
            'decision per clash rather than an automatic fix. Find them in the '
            'Django admin by searching the Members list on mobile number -- the '
            'numbers are deliberately not printed here.'
        )

    for pk, nickname, mobile in rows:
        User.objects.filter(pk=pk).update(
            nickname_key=normalise_nickname(nickname) or None,
            mobile_key=mobile or None,
        )


def drop_keys(apps, schema_editor):
    """Reverse. The columns go with the migration, so there is nothing to undo.

    Declared rather than left as ``None`` so that the migration is reversible and
    a failed deploy can be rolled back to 0006.
    """


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_member_avatar'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        # The old constraints go first. On a backend that did build them they
        # would refuse nothing the new ones allow, but dropping them up front
        # keeps the schema from briefly carrying two rules for one column.
        migrations.RemoveConstraint(
            model_name='user',
            name='user_nickname_unique_ci',
        ),
        migrations.RemoveConstraint(
            model_name='user',
            name='user_mobile_unique',
        ),
        migrations.AddField(
            model_name='user',
            name='nickname_key',
            field=models.CharField(
                blank=True, editable=False, max_length=60, null=True
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='mobile_key',
            field=models.CharField(
                blank=True, editable=False, max_length=16, null=True
            ),
        ),
        # Between the columns and the indexes over them, deliberately. See the
        # module docstring.
        migrations.RunPython(fill_keys, drop_keys),
        migrations.AddConstraint(
            model_name='user',
            constraint=models.UniqueConstraint(
                fields=('nickname_key',),
                name='user_nickname_key_unique',
                violation_error_message='That nickname is already taken.',
            ),
        ),
        migrations.AddConstraint(
            model_name='user',
            constraint=models.UniqueConstraint(
                fields=('mobile_key',),
                name='user_mobile_key_unique',
                violation_error_message=(
                    'Another account already holds that mobile number.'
                ),
            ),
        ),
        # In the same migration as the indexes above, deliberately. These are
        # what stop a write that bypasses `save` leaving a stale key, so a
        # deploy must never sit between the two -- a schema with the unique
        # indexes and not these would enforce uniqueness over a column nothing
        # guarantees is current.
        migrations.AddConstraint(
            model_name='user',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(('nickname', ''), ('nickname_key__isnull', True)),
                    models.Q(
                        ('nickname_key', Lower('nickname')),
                        ('nickname_key__isnull', False),
                    ),
                    _connector='OR',
                ),
                name='user_nickname_key_matches_nickname',
                violation_error_message=(
                    'nickname_key is derived from nickname and cannot be set '
                    'directly.'
                ),
            ),
        ),
        migrations.AddConstraint(
            model_name='user',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(('mobile', ''), ('mobile_key__isnull', True)),
                    models.Q(
                        ('mobile_key', models.F('mobile')),
                        ('mobile_key__isnull', False),
                    ),
                    _connector='OR',
                ),
                name='user_mobile_key_matches_mobile',
                violation_error_message=(
                    'mobile_key is derived from mobile and cannot be set '
                    'directly.'
                ),
            ),
        ),
    ]
