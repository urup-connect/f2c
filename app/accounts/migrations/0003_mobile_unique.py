"""One handset, one member: the mobile number becomes the third identity key.

The alteration drops the plain index, because the unique constraint below
provides one. Nothing else about the column changes.

The check in front of the constraint is the point of writing this migration by
hand. Adding a unique index to a column that already holds duplicates fails
with an ``IntegrityError`` naming an index, which on a deploy is a stack trace
somebody has to interpret under pressure. So the duplicates are counted first
and the failure says what to do about them.

**It counts, and never names.** A mobile number is personal information, and a
migration that printed one would write it into every deploy log and CI
transcript that ran. Whoever has to resolve the clash can find the rows in the
admin, where reading them is an authorised act.
"""
import app.common.validators
from django.db import migrations, models


def refuse_existing_duplicates(apps, schema_editor):
    """Fail with a usable message if two live accounts share a handset.

    Blank numbers are excluded, matching the constraint: staff have none, and
    erasure blanks the field, so any number of erased members may hold none.
    """
    User = apps.get_model('accounts', 'User')
    clashes = (
        User.objects.exclude(mobile='')
        .values('mobile')
        .annotate(held_by=models.Count('id'))
        .filter(held_by__gt=1)
    )
    count = clashes.count()
    if not count:
        return
    raise RuntimeError(
        f'{count} mobile number(s) are held by more than one account, so a '
        'unique constraint cannot be added. Find them in the Django admin by '
        'searching the Members list on mobile number, and decide which account '
        'keeps each one -- the numbers are deliberately not printed here, '
        'because a deploy log is not a place for members personal details.'
    )


def noop(apps, schema_editor):
    """Nothing to undo: the check writes nothing."""


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_member_registration'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='mobile',
            field=models.CharField(blank=True, help_text='Stored as +27 and nine digits, whatever form it was given in.', max_length=16, validators=[app.common.validators.validate_sa_mobile_number]),
        ),
        migrations.RunPython(refuse_existing_duplicates, noop),
        migrations.AddConstraint(
            model_name='user',
            constraint=models.UniqueConstraint(condition=models.Q(('mobile', ''), _negated=True), fields=('mobile',), name='user_mobile_unique', violation_error_message='Another account already holds that mobile number.'),
        ),
    ]
