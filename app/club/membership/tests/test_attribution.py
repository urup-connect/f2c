"""Tests for the campaign a registration arrives with.

``app.core.attribution`` has its own suite for the cleaning. These are about the
wiring, and about the two things a wiring test is for.

**The touches and the member are one write.** A campaign touch belonging to a
registration that rolled back is a row claiming a member who does not exist, and
a membership pointing at nothing is attribution silently lost. Both are asserted
against a registration that fails after the touches would have been written.

**A duplicate submission still writes nothing.** The rule the whole endpoint
turns on, checked again here because attribution is a new write on that path and
it would be an easy one to put above the duplicate check by accident.
"""
import json

from django.core.cache import cache
from django.test import Client

from app.core.attribution.models import CampaignTouch, ClickNetwork
from app.club.membership import services
from app.core.storefronts.models import Storefront

from .support import SECOND_ADULT_ID, RegistrationTestCase

REGISTER = '/api/members/register'

#: What the frontend's campaign cookie holds after a visitor followed a tagged
#: link. Written out in full once here, because a partial one is what most of
#: these tests are about.
INSTAGRAM = {
    'source': 'Instagram',
    'medium': 'social',
    'campaign': 'spring-open-day',
    'content': 'carousel-2',
    'referrer': 'https://l.instagram.com/',
    'landing_path': '/join',
    'seen_at': '2026-08-20T09:15:00.000Z',
}

GOOGLE_ADS = {
    'source': 'google',
    'medium': 'cpc',
    'campaign': 'cape-town-club',
    'term': 'cannabis club cape town',
    'click_network': 'google',
    'click_id': 'EAIaIQobChMI',
    'landing_path': '/signup',
    'seen_at': '2026-08-28T18:40:00.000Z',
}


class RegistrationAttributionTests(RegistrationTestCase):
    """What a completed registration records about where the member came from."""

    def register(self, campaign=None, **overrides):
        return services.register_member(
            **self.submission(**overrides), campaign=campaign
        )

    def test_a_first_and_last_campaign_are_both_recorded(self):
        result = self.register({'first': INSTAGRAM, 'last': GOOGLE_ADS})
        membership = result.user.club_membership

        self.assertEqual(membership.first_touch.source, 'instagram')
        self.assertEqual(membership.last_touch.source, 'google')
        self.assertEqual(CampaignTouch.objects.count(), 2)

    def test_arriving_and_joining_in_one_visit_is_one_row(self):
        result = self.register({'first': INSTAGRAM, 'last': INSTAGRAM})
        membership = result.user.club_membership

        self.assertEqual(membership.first_touch_id, membership.last_touch_id)
        self.assertEqual(CampaignTouch.objects.count(), 1)

    def test_an_untagged_member_has_no_campaign(self):
        result = self.register()
        membership = result.user.club_membership

        # Absent, not a row saying "direct" -- see `attribution.models`.
        self.assertIsNone(membership.first_touch_id)
        self.assertIsNone(membership.last_touch_id)
        self.assertEqual(CampaignTouch.objects.count(), 0)

    def test_a_campaign_of_nothing_is_the_same_as_none(self):
        result = self.register({'first': {}, 'last': {'landing_path': '/'}})

        self.assertIsNone(result.user.club_membership.first_touch_id)
        self.assertEqual(CampaignTouch.objects.count(), 0)

    def test_the_touch_is_recorded_against_the_club(self):
        """Named by the service, never read off the request host.

        The same reason the consents are resolved against the club's storefront:
        joining the club is club-scoped by definition, and a campaign recorded
        against the market would put a club signup in the market's report.
        """
        self.register({'first': INSTAGRAM, 'last': INSTAGRAM})

        self.assertEqual(
            CampaignTouch.objects.get().storefront, Storefront.CLUB
        )

    def test_the_ad_click_survives_the_trip(self):
        # The one value that reconciles a member against money spent.
        result = self.register({'first': GOOGLE_ADS, 'last': GOOGLE_ADS})
        touch = result.user.club_membership.first_touch

        self.assertEqual(touch.click_network, ClickNetwork.GOOGLE)
        self.assertEqual(touch.click_id, 'EAIaIQobChMI')

    def test_the_referrer_keeps_no_query_string(self):
        result = self.register(
            {
                'first': INSTAGRAM | {'referrer': 'https://l.instagram.com/?u=x'},
                'last': INSTAGRAM,
            }
        )

        self.assertEqual(
            result.user.club_membership.first_touch.referrer,
            'https://l.instagram.com/',
        )

    def test_a_duplicate_submission_records_no_campaign(self):
        """A second submission writes nothing, and that includes this.

        The duplicate check comes first in ``register_member`` and this is what
        holds it there. A campaign touch written before it would be a row
        recording that somebody submitted the form again -- which is the one
        thing that path exists not to disclose.
        """
        self.register({'first': INSTAGRAM, 'last': INSTAGRAM})
        CampaignTouch.objects.all().delete()

        result = self.register({'first': GOOGLE_ADS, 'last': GOOGLE_ADS})

        self.assertFalse(result.created)
        self.assertEqual(CampaignTouch.objects.count(), 0)

    def test_a_failed_registration_leaves_no_campaign_behind(self):
        """One transaction, and the touches are inside it.

        A nickname taken by somebody else is the refusal that happens *after*
        the point where a careless implementation would already have written the
        touch.
        """
        self.register({'first': INSTAGRAM, 'last': INSTAGRAM})
        CampaignTouch.objects.all().delete()

        with self.assertRaises(services.NicknameTaken):
            self.register(
                {'first': GOOGLE_ADS, 'last': GOOGLE_ADS},
                email='someone.else@example.com',
                mobile='083 555 1234',
                id_number=SECOND_ADULT_ID,
            )

        self.assertEqual(CampaignTouch.objects.count(), 0)


class RegisterEndpointAttributionTests(RegistrationTestCase):
    """The contract, and the one thing it must never do: refuse over a label."""

    def setUp(self):
        super().setUp()
        # Limits live in the cache and are keyed on client IP, so without this
        # they carry from one test into the next.
        cache.clear()
        self.client = Client()

    def post(self, payload):
        return self.client.post(
            REGISTER, data=json.dumps(payload), content_type='application/json'
        )

    def test_a_body_with_no_campaign_at_all_still_registers(self):
        # Every caller that predates this field, and every visitor who typed
        # the address.
        response = self.post(self.submission())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(CampaignTouch.objects.count(), 0)

    def test_a_campaign_on_the_body_is_recorded(self):
        response = self.post(
            self.submission() | {'campaign': {'first': INSTAGRAM, 'last': INSTAGRAM}}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(CampaignTouch.objects.get().source, 'instagram')

    def test_a_malformed_campaign_does_not_refuse_the_registration(self):
        """The rule the whole app is built on, asserted at the boundary.

        A 400-character parameter, a timestamp that is not one, an ad network
        nobody has heard of, and a click id with no network. Each of these is a
        value that would be refused if it were a member's field; none of them may
        cost a member their membership.
        """
        response = self.post(
            self.submission()
            | {
                'campaign': {
                    'first': {
                        'source': 'x' * 400,
                        'medium': 'social',
                        'seen_at': 'the day before yesterday',
                        'click_network': 'carrier-pigeon',
                        'click_id': 'abc',
                    },
                    'last': None,
                }
            }
        )

        self.assertEqual(response.status_code, 200)
        touch = CampaignTouch.objects.get()
        self.assertEqual(len(touch.source), 200)
        self.assertIsNone(touch.seen_at)
        self.assertEqual(touch.click_network, '')
        self.assertEqual(touch.click_id, '')

    def test_the_response_says_nothing_about_the_campaign(self):
        # The success response says nothing about the member either, and for the
        # same reason: it is read by a server action that then redirects.
        response = self.post(
            self.submission() | {'campaign': {'first': GOOGLE_ADS, 'last': GOOGLE_ADS}}
        )

        body = json.loads(response.content)
        self.assertNotIn('campaign', body)
        self.assertNotIn('EAIaIQobChMI', response.content.decode())
