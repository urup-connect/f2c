"""A leaf rating floors at 0.1 instead of rounding away to 0.0.

`swap-zone.md` gives no floor and its cheapest worked example is R500, so the
formula alone put anything under R250 at 0.0 -- a plant with no swap value to be
equivalent to. The brief's question is now answered there: a price that low is
not expected, and the floor exists so the unexpected case is a plant that is
merely unswappable rather than one that breaks equivalence.

`leaf_rating` is derived on write and, alone among this project's derived
columns, has no check constraint tying it to its source (the field says why). So
a rule change to `models.leaf_rating_for` leaves stored values stale until
something saves the row, and the backfill below is not optional -- Block 10 will
read this column in a `WHERE` clause, not through the model.
"""
from decimal import Decimal

from django.db import migrations, models

#: Kept local rather than imported from `models`. `design/migrations.md`: a
#: migration is a record of what was run, and importing a constant lets a later
#: edit rewrite history.
OLD_FLOOR = Decimal('0.0')
NEW_FLOOR = Decimal('0.1')


def apply_floor(apps, schema_editor):
    """Lift every rating the old formula rounded to nothing.

    An `update` on the queryset rather than a save loop: this touches only the
    derived column, the new value is a constant, and a five-hundred-row crop is
    one statement. Idempotent -- a second run matches no rows.
    """
    Plant = apps.get_model('plant', 'Plant')
    Plant.objects.filter(leaf_rating=OLD_FLOOR).update(leaf_rating=NEW_FLOOR)


def remove_floor(apps, schema_editor):
    """Reverse, and lossy in the way a reverse of this kind always is.

    Any plant genuinely priced at a 0.1 rating is under R250, which is the only
    way to reach 0.1 at all -- so putting them back to 0.0 restores exactly what
    the old formula would have derived.
    """
    Plant = apps.get_model('plant', 'Plant')
    Plant.objects.filter(leaf_rating=NEW_FLOOR).update(leaf_rating=OLD_FLOOR)


class Migration(migrations.Migration):

    dependencies = [
        ('plant', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='plant',
            name='leaf_rating',
            field=models.DecimalField(decimal_places=1, editable=False, help_text='Swap value: grow price ÷ 1000, to the nearest 0.5, with a floor of 0.1 for a price too low to earn a whole step. Never shown alongside a Rand value.', max_digits=5),
        ),
        migrations.RunPython(apply_floor, remove_floor),
    ]
