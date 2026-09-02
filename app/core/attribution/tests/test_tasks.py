"""The nightly job that enforces the campaign-touch retention window.

The same argument ``storefronts.tests.test_tasks`` makes, for the table that
says which campaign brought a member. The window arithmetic is shared and
tested through the command; what this adds is that the schedule reaches it, that
the run is recorded, and the one thing that is specific to this table --
**a purge leaves the member behind.**

``Attributed`` points here with ``SET_NULL``, so the nightly job has to be able
to run against an attributed membership without failing and without taking the
membership with it. PROTECT and CASCADE both compile; only one of the three is
right, and the last test here is what would fail if somebody changed it.
"""
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from app.core.attribution.models import CampaignTouch
from app.core.attribution.tasks import purge_touches
from app.core.scheduling.models import Outcome, ScheduledRun, ScheduledTask
from app.core.storefronts.models import Storefront


class PurgeCampaignTouchTaskTests(TestCase):
    def make(self, *, age_days, source='instagram'):
        touch = CampaignTouch.objects.create(
            storefront=Storefront.CLUB, source=source, medium='social'
        )
        # `recorded_at` is `auto_now_add`, so ageing a row means going round the
        # model.
        CampaignTouch.objects.filter(pk=touch.pk).update(
            recorded_at=timezone.now() - timedelta(days=age_days)
        )
        return touch

    @override_settings(CAMPAIGN_TOUCH_RETENTION_DAYS=730)
    def test_it_deletes_past_the_window_and_keeps_inside_it(self):
        old = self.make(age_days=800)
        recent = self.make(age_days=30, source='google')

        self.assertEqual(1, purge_touches())

        surviving = set(CampaignTouch.objects.values_list('pk', flat=True))
        self.assertEqual({recent.pk}, surviving)
        self.assertNotIn(old.pk, surviving)

    @override_settings(CAMPAIGN_TOUCH_RETENTION_DAYS=730)
    def test_the_run_is_recorded(self):
        self.make(age_days=800)

        purge_touches()

        run = ScheduledRun.objects.get()
        self.assertEqual(ScheduledTask.PURGE_CAMPAIGN_TOUCHES, run.task)
        self.assertEqual(Outcome.SUCCEEDED, run.outcome)
        self.assertEqual(1, run.affected)

    @override_settings(CAMPAIGN_TOUCH_RETENTION_DAYS=0)
    def test_zero_keeps_everything_and_the_row_says_why(self):
        self.make(age_days=4000)

        purge_touches()

        run = ScheduledRun.objects.get()
        self.assertEqual(0, run.affected)
        self.assertIn('Nothing was deleted', run.detail)
        self.assertEqual(1, CampaignTouch.objects.count())

    @override_settings(CAMPAIGN_TOUCH_RETENTION_DAYS=730)
    def test_a_purged_campaign_leaves_the_member_behind(self):
        """The one that matters. See the module docstring.

        The member's attribution goes back to "not known", which is where every
        untagged member already sits -- so the state a purge leaves behind is
        one the rest of the platform already handles.
        """
        from app.club.membership.models import ClubMembership
        from f2c.testing import make_member

        member = make_member('member@example.com', nickname='Thabo')
        membership = ClubMembership.objects.get(user=member)
        membership.first_touch = self.make(age_days=800)
        membership.last_touch = membership.first_touch
        membership.save(update_fields=['first_touch', 'last_touch'])

        purge_touches()

        membership.refresh_from_db()
        self.assertIsNone(membership.first_touch)
        self.assertIsNone(membership.last_touch)
        self.assertTrue(
            ClubMembership.objects.filter(pk=membership.pk).exists(),
            'the purge took the membership with it',
        )
