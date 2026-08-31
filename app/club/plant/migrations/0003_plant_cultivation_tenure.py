"""The farm becomes a holder in the ownership ledger — C13.

*Each plant must always have a verifiable owner, and there must be an audit
trail of all ownership until final ownership.* The ledger did not answer that
before this migration: it opened at the first sale, and the farm's holding was
an inference from `Plant.listing.cultivator` rather than a row. Three schema
changes and a backfill close it.

**Schema.** `owner` becomes nullable and `producer` arrives beside it, with
`tenure_has_one_holder` making exactly one of the two present — the alternative,
a service account standing in for the farm, would put an account nobody signs
into on the member tables and every permission rule would then have to exclude
it. `tenure_reason_matches_holder` keeps `cultivation` producer-held and
purchase, swap and allocation member-held; `adjustment` stays free in both
directions, because C9's substitution path returns a member's plant to the farm
and that is a correction rather than a second cultivation.

**Neither constraint can fail on existing data.** Every row predating this
migration carries an owner and one of the four old reasons, so both conditions
are already true of them — which is why they are added before the backfill
rather than after it.

**The backfill writes the front of the trail.** One cultivation tenure per
plant, from `created_at` — when the platform first knew of the plant — to the
first transfer, or still open where the farm holds it yet. Idempotent: a plant
that already has a cultivation row is skipped, so a re-run matches nothing.

**Where it refuses to guess.** A plant whose `created_at` is not strictly before
its first tenure cannot be given a tenure that ends after it began — the
`tenure_ends_after_it_starts` constraint would refuse the row, and inventing an
earlier `acquired_at` to get around it would be fabricating the one date this
record exists to attest. Those plants keep a trail that starts at the first
transfer, and the count is reported. Counted, never named:
`design/migrations.md` section 1 — a serial in a build log is a member's
certificate in a build log.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

#: Must match `models.OwnershipReason.CULTIVATION`. Inlined rather than
#: imported: a migration is a historical record and a later rename must not
#: change what this one did. `design/migrations.md` section 1.
CULTIVATION = 'cultivation'


def open_cultivation_tenures(apps, schema_editor):
    """Give every plant a tenure that starts where the plant does."""
    Plant = apps.get_model('plant', 'Plant')
    PlantOwnership = apps.get_model('plant', 'PlantOwnership')

    already_recorded = set(
        PlantOwnership.objects.filter(reason=CULTIVATION).values_list(
            'plant_id', flat=True
        )
    )

    # The first tenure per plant, which is what the farm's row has to end at.
    # One query rather than one per plant: a season's capture is a five-hundred
    # row crop and this runs inside the deploy.
    first_tenure_at = {}
    for plant_id, acquired_at in (
        PlantOwnership.objects.order_by('plant_id', 'acquired_at')
        .values_list('plant_id', 'acquired_at')
    ):
        first_tenure_at.setdefault(plant_id, acquired_at)

    tenures = []
    unrecoverable = 0

    for plant_id, created_at, producer_id in (
        Plant.objects.order_by('created_at')
        .values_list('id', 'created_at', 'listing__cultivator_id')
    ):
        if plant_id in already_recorded:
            continue

        sold_at = first_tenure_at.get(plant_id)
        if sold_at is not None and created_at >= sold_at:
            unrecoverable += 1
            continue

        tenures.append(
            PlantOwnership(
                plant_id=plant_id,
                producer_id=producer_id,
                acquired_at=created_at,
                released_at=sold_at,
                reason=CULTIVATION,
                # Derived by `PlantOwnership.save`, which a historical model
                # does not carry, so it is set here. Null for a closed tenure:
                # the open-tenure unique index would otherwise refuse the second
                # row against a plant a member already holds.
                current_for_plant=None if sold_at else plant_id,
            )
        )

    PlantOwnership.objects.bulk_create(tenures, batch_size=500)

    if unrecoverable:
        print(
            f'  {unrecoverable} plant(s) were captured no earlier than their '
            f'first transfer, so no cultivation tenure could be written for '
            f'them: their trail still starts at that transfer. Find them in '
            f'the plant admin by filtering ownership history for a missing '
            f'cultivation row.'
        )


def drop_cultivation_tenures(apps, schema_editor):
    """Reverse, and exact: the only rows carrying this reason are the ones the
    function above writes, and `Plant.save` writes for a new plant."""
    PlantOwnership = apps.get_model('plant', 'PlantOwnership')
    PlantOwnership.objects.filter(reason=CULTIVATION).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('plant', '0002_leaf_rating_floor'),
        ('producers', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='plantownership',
            name='producer',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='plant_tenures', to='producers.producer'),
        ),
        migrations.AlterField(
            model_name='plantownership',
            name='owner',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='plant_ownerships', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='plantownership',
            name='reason',
            field=models.CharField(choices=[('cultivation', 'Held by the cultivator'), ('purchase', 'Purchased'), ('swap', 'Swapped'), ('allocation', 'Allocated to a sharing member'), ('adjustment', 'Adjusted by staff')], max_length=16),
        ),
        migrations.AddIndex(
            model_name='plantownership',
            index=models.Index(fields=['producer', '-acquired_at'], name='tenure_by_producer'),
        ),
        migrations.AddConstraint(
            model_name='plantownership',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('owner__isnull', False), ('producer__isnull', True)), models.Q(('owner__isnull', True), ('producer__isnull', False)), _connector='OR'), name='tenure_has_one_holder', violation_error_message='A tenure is held by a member or by a producer, not by both and not by neither.'),
        ),
        migrations.AddConstraint(
            model_name='plantownership',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('producer__isnull', False), ('reason', 'cultivation')), models.Q(('owner__isnull', False), ('reason__in', ('purchase', 'swap', 'allocation'))), ('reason', 'adjustment'), _connector='OR'), name='tenure_reason_matches_holder', violation_error_message='A cultivation tenure is held by a producer and a purchase, swap or allocation by a member.'),
        ),
        migrations.RunPython(open_cultivation_tenures, drop_cultivation_tenures),
    ]
