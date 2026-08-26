"""Move "one live subscription per member" onto a column MySQL can index.

``design/backend.md`` section 8.2. The rule was
``UniqueConstraint(fields=('user',), condition=Q(status__in=LIVE_STATUSES))`` --
a partial unique index, which **MySQL cannot build at any version.** Django omits
what the backend will not build without raising anything, so on MySQL the rule
was absent while this app's model, migration and tests all still described it.

What it was preventing is not abstract: two live subscriptions against one member
means Payfast holding two mandates and billing both.

``live_for_user`` carries the rule instead -- a copy of ``user_id`` while the
subscription is in force and null once it is not -- because nulls are distinct
under a unique index on every backend this project runs on.

The backfill refuses rather than repairs. Two live subscriptions against one
member is a money question: which mandate is real, whether the other was ever
charged, and whether anything is owed back. That is not a decision a migration
gets to make silently, and section 8.2's whole point is that this rule may never
have been enforced on the deployed database.
"""
from django.db import migrations, models

#: Must match ``models.LIVE_STATUSES``. Inlined rather than imported: a migration
#: is a historical record, and a later edit to that tuple must not change what
#: this migration did.
LIVE_STATUSES = ('pending', 'active')


def fill_live_slot(apps, schema_editor):
    Subscription = apps.get_model('payments', 'Subscription')

    live = Subscription.objects.filter(status__in=LIVE_STATUSES)

    holders = {}
    for pk, user_id in live.values_list('pk', 'user_id'):
        holders.setdefault(user_id, []).append(pk)

    clashes = sum(1 for pks in holders.values() if len(pks) > 1)
    if clashes:
        raise RuntimeError(
            f'{clashes} member(s) already hold more than one live subscription, '
            'so a unique constraint cannot be added. This is the exact failure '
            'the partial index being replaced was written to prevent and, on '
            'MySQL, never built. Each one needs checking against Payfast before '
            'anything is cancelled, because both mandates may have taken money. '
            'Find them in the Django admin under Subscriptions, filtered by '
            'status -- the members are deliberately not identified here, because '
            'a deploy log is not a place for that.'
        )

    for user_id, pks in holders.items():
        Subscription.objects.filter(pk__in=pks).update(live_for_user=user_id)


def clear_live_slot(apps, schema_editor):
    """Reverse. The column goes with the migration, so there is nothing to undo."""


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0001_initial'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='subscription',
            name='one_live_subscription_per_member',
        ),
        migrations.AddField(
            model_name='subscription',
            name='live_for_user',
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        # Between the column and the index over it. See the module docstring.
        migrations.RunPython(fill_live_slot, clear_live_slot),
        migrations.AddConstraint(
            model_name='subscription',
            constraint=models.UniqueConstraint(
                fields=('live_for_user',),
                name='one_live_subscription_per_member',
                violation_error_message=(
                    'That member already holds a live subscription.'
                ),
            ),
        ),
        # In the same migration as the index above, deliberately: this is what
        # keeps `live_for_user` current, and an index over a stale column
        # enforces nothing. See the model.
        migrations.AddConstraint(
            model_name='subscription',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ('live_for_user', models.F('user')),
                        # Not redundant: a CHECK passes when its condition is
                        # unknown, and a comparison against null is unknown.
                        # See the model.
                        ('live_for_user__isnull', False),
                        ('status__in', list(LIVE_STATUSES)),
                    ),
                    models.Q(
                        models.Q(('status__in', list(LIVE_STATUSES)), _negated=True),
                        ('live_for_user__isnull', True),
                    ),
                    _connector='OR',
                ),
                name='live_for_user_matches_status',
                violation_error_message=(
                    'live_for_user is derived from status and cannot be set '
                    'directly.'
                ),
            ),
        ),
    ]
