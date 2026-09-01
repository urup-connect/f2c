"""Tests for the retention purge.

The behaviour worth writing down is the last case here: **a purged campaign
leaves the member behind.** ``Attributed`` points at this table with
``SET_NULL``, so the schedule that enforces retention has to be able to run
against an attributed membership without failing and without taking the
membership with it. PROTECT and CASCADE both compile; only one of the three is
right, and this is the test that would fail if somebody changed it.
"""
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from app.core.attribution.models import CampaignTouch
from app.core.storefronts.models import Storefront
from f2c.testing import make_member


class PurgeCampaignTouchesTests(TestCase):
    def make(self, *, age_days, source='instagram'):
        touch = CampaignTouch.objects.create(
            storefront=Storefront.CLUB, source=source, medium='social'
        )
        # `recorded_at` is `auto_now_add`, so ageing a row means going round the
        # model -- the same trick, for the same reason, as the send-record purge
        # tests.
        CampaignTouch.objects.filter(pk=touch.pk).update(
            recorded_at=timezone.now() - timedelta(days=age_days)
        )
        return touch

    def run_command(self, *args):
        output = StringIO()
        call_command('purge_campaign_touches', *args, stdout=output)
        return output.getvalue()

    @override_settings(CAMPAIGN_TOUCH_RETENTION_DAYS=730)
    def test_it_deletes_past_the_window_and_keeps_inside_it(self):
        old = self.make(age_days=800)
        recent = self.make(age_days=30, source='google')

        self.run_command()

        surviving = set(CampaignTouch.objects.values_list('pk', flat=True))
        self.assertEqual({recent.pk}, surviving)
        self.assertNotIn(old.pk, surviving)

    @override_settings(CAMPAIGN_TOUCH_RETENTION_DAYS=730)
    def test_a_dry_run_reports_and_deletes_nothing(self):
        self.make(age_days=800)

        output = self.run_command('--dry-run')

        self.assertIn('1 campaign touch', output)
        self.assertEqual(1, CampaignTouch.objects.count())

    def test_days_overrides_the_configured_window(self):
        self.make(age_days=30)

        self.run_command('--days', '7')

        self.assertEqual(0, CampaignTouch.objects.count())

    @override_settings(CAMPAIGN_TOUCH_RETENTION_DAYS=0)
    def test_zero_keeps_everything_and_says_so(self):
        """A deployment that has decided to keep the lot should hear that its
        schedule ran and deliberately did nothing, not read a silent success."""
        self.make(age_days=4000)

        output = self.run_command()

        self.assertIn('Nothing was deleted', output)
        self.assertEqual(1, CampaignTouch.objects.count())

    def test_a_negative_window_is_refused(self):
        with self.assertRaises(CommandError):
            self.run_command('--days', '-1')

    @override_settings(CAMPAIGN_TOUCH_RETENTION_DAYS=730)
    def test_running_twice_is_safe(self):
        self.make(age_days=800)

        self.run_command()
        self.run_command()

        self.assertEqual(0, CampaignTouch.objects.count())

    @override_settings(CAMPAIGN_TOUCH_RETENTION_DAYS=730)
    def test_the_member_survives_their_purged_campaign(self):
        touch = self.make(age_days=800)
        membership = make_member('joiner@example.com', 'Joiner')
        club_membership = membership.club_membership
        club_membership.first_touch = touch
        club_membership.last_touch = touch
        club_membership.save(update_fields=['first_touch', 'last_touch'])

        self.run_command()

        club_membership.refresh_from_db()
        self.assertIsNone(club_membership.first_touch_id)
        self.assertIsNone(club_membership.last_touch_id)
        # The point of SET_NULL: the retention window took the label and left
        # the member, whose attribution is now what an untagged member's is.
        self.assertEqual(club_membership.nickname, 'Joiner')
