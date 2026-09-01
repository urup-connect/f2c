"""Tests for what a browser reports becoming what is stored.

Two things are being asserted throughout, and the second is the one that would
be missed.

**One channel is one row.** Every test that folds case, trims, or collapses
whitespace is a test about a report: ``Instagram``, ``instagram`` and
``instagram `` are the same advert, and a table that keeps them apart is a table
somebody stops trusting.

**Nothing here refuses.** Every malformed input has a test proving it produces a
missing value rather than an exception, because the caller is a registration and
the module's one rule is that a marketing parameter cannot cost somebody their
membership. A test that only checked the happy path would leave that rule
resting on nobody.
"""
from datetime import timedelta

from django.db.utils import IntegrityError
from django.test import TestCase
from django.utils import timezone

from app.core.attribution import services
from app.core.attribution.models import (
    ADDRESS_LENGTH,
    CLICK_ID_LENGTH,
    LABEL_LENGTH,
    CampaignTouch,
    ClickNetwork,
)
from app.core.storefronts.models import Storefront

NOW = timezone.now()


def touch(**overrides):
    """A payload naming a campaign, before ``overrides`` are applied."""
    return {
        'source': 'instagram',
        'medium': 'social',
        'campaign': 'spring-open-day',
        'landing_path': '/',
    } | overrides


class TouchFieldsTestCase(TestCase):
    """One helper, and no tests of its own.

    Subclassed four times below rather than inherited from a class that already
    holds assertions: a base with test methods on it runs them again in every
    subclass, which is the same suite four times over and four times the noise
    when one of them breaks.
    """

    def fields(self, raw, **kwargs):
        return services.touch_fields(
            raw, storefront=Storefront.CLUB, now=NOW, **kwargs
        )


class CleaningTests(TouchFieldsTestCase):
    """The cleaning, which is where every reporting question is decided."""

    def test_the_five_parameters_are_kept(self):
        fields = self.fields(
            touch(term='cannabis club cape town', content='carousel-2')
        )
        self.assertEqual(fields['source'], 'instagram')
        self.assertEqual(fields['medium'], 'social')
        self.assertEqual(fields['campaign'], 'spring-open-day')
        self.assertEqual(fields['term'], 'cannabis club cape town')
        self.assertEqual(fields['content'], 'carousel-2')

    def test_labels_are_folded_to_lower_case(self):
        # One channel, however the link was typed.
        self.assertEqual(self.fields(touch(source='Instagram'))['source'], 'instagram')

    def test_surrounding_whitespace_goes(self):
        self.assertEqual(self.fields(touch(source='  email '))['source'], 'email')

    def test_internal_whitespace_collapses(self):
        fields = self.fields(touch(term='cape  town\tclub'))
        self.assertEqual(fields['term'], 'cape town club')

    def test_a_newline_becomes_a_space_rather_than_disappearing(self):
        # A CSV export of a value with a newline in it is a broken CSV, so it
        # goes -- but it goes the way a tab does, leaving the words either side
        # separate. Deleting it would invent `capetown`.
        self.assertEqual(self.fields(touch(term='cape\ntown'))['term'], 'cape town')

    def test_unprintable_characters_are_stripped(self):
        # A null or a bell is not whitespace and has no business in a label.
        self.assertEqual(self.fields(touch(source='in\x00sta'))['source'], 'insta')

    def test_a_long_label_is_cut_rather_than_refused(self):
        fields = self.fields(touch(content='x' * (LABEL_LENGTH + 50)))
        self.assertEqual(len(fields['content']), LABEL_LENGTH)

    def test_a_value_that_is_not_a_string_becomes_blank(self):
        # A caller getting the shape wrong, not a member getting a form wrong.
        self.assertEqual(self.fields(touch(medium=17))['medium'], '')

    def test_a_payload_that_is_not_a_mapping_is_nothing(self):
        self.assertIsNone(self.fields('utm_source=instagram'))
        self.assertIsNone(self.fields(None))

    def test_the_storefront_is_the_one_the_caller_named(self):
        self.assertEqual(self.fields(touch())['storefront'], Storefront.CLUB)


class EmptinessTests(TouchFieldsTestCase):
    """When a payload is not worth a row.

    The distinction this protects is "we do not know" against "they came from
    nowhere". A row naming no campaign counts as an attributed member in every
    report while answering nothing.
    """

    def test_an_empty_payload_is_nothing(self):
        self.assertIsNone(self.fields({}))

    def test_a_payload_of_blanks_is_nothing(self):
        self.assertIsNone(self.fields({'source': '  ', 'campaign': ''}))

    def test_a_landing_path_alone_is_nothing(self):
        # Every arrival has one, so a touch carrying only this is an ordinary
        # untagged visit.
        self.assertIsNone(self.fields({'landing_path': '/signup'}))

    def test_a_referring_site_alone_is_enough(self):
        # The untagged slice worth keeping: somebody linked to the club and the
        # link had no parameters on it.
        fields = self.fields({'referrer': 'https://news24.com/article'})
        self.assertIsNotNone(fields)
        self.assertEqual(fields['referrer'], 'https://news24.com/article')

    def test_a_click_id_alone_is_enough(self):
        fields = self.fields({'click_network': 'google', 'click_id': 'abc123'})
        self.assertIsNotNone(fields)


class ClickTests(TouchFieldsTestCase):
    """The network and its id, which travel together or not at all."""

    def test_a_known_network_and_its_id_are_kept(self):
        fields = self.fields(touch(click_network='google', click_id='EAIaIQob'))
        self.assertEqual(fields['click_network'], ClickNetwork.GOOGLE)
        self.assertEqual(fields['click_id'], 'EAIaIQob')

    def test_every_network_the_platform_names_is_accepted(self):
        for network in ClickNetwork.values:
            with self.subTest(network=network):
                fields = self.fields(
                    touch(click_network=network, click_id='id')
                )
                self.assertEqual(fields['click_network'], network)

    def test_a_network_nobody_recognises_takes_the_id_with_it(self):
        # An id that cannot be reconciled against anything is a value kept for
        # no reason.
        fields = self.fields(touch(click_network='pinterest', click_id='xyz'))
        self.assertEqual(fields['click_network'], '')
        self.assertEqual(fields['click_id'], '')

    def test_an_id_with_no_network_is_dropped(self):
        fields = self.fields(touch(click_id='xyz'))
        self.assertEqual(fields['click_id'], '')

    def test_a_network_with_no_id_is_dropped(self):
        # `source` already says the click came from Google.
        fields = self.fields(touch(click_network='google'))
        self.assertEqual(fields['click_network'], '')

    def test_the_id_keeps_its_case(self):
        # Unlike a label. It is a token the network looks up, not a name.
        fields = self.fields(touch(click_network='meta', click_id='AbCdEf'))
        self.assertEqual(fields['click_id'], 'AbCdEf')

    def test_a_long_id_is_cut(self):
        fields = self.fields(
            touch(click_network='google', click_id='x' * (CLICK_ID_LENGTH + 10))
        )
        self.assertEqual(len(fields['click_id']), CLICK_ID_LENGTH)


class AddressTests(TouchFieldsTestCase):
    """The referring site and the landing path."""

    def test_a_referrer_keeps_its_origin_and_path(self):
        fields = self.fields(touch(referrer='https://news24.com/health/story'))
        self.assertEqual(fields['referrer'], 'https://news24.com/health/story')

    def test_a_referrer_loses_its_query_string(self):
        # It can carry anything the referring site put in it, including
        # somebody's address in a badly built newsletter link.
        fields = self.fields(
            touch(referrer='https://news24.com/story?email=a@b.co&sid=99')
        )
        self.assertEqual(fields['referrer'], 'https://news24.com/story')

    def test_a_referrer_loses_its_fragment(self):
        fields = self.fields(touch(referrer='https://news24.com/story#comments'))
        self.assertEqual(fields['referrer'], 'https://news24.com/story')

    def test_a_landing_path_loses_its_query_string(self):
        # The parameters worth keeping are already columns of their own.
        fields = self.fields(touch(landing_path='/join?utm_source=instagram'))
        self.assertEqual(fields['landing_path'], '/join')

    def test_a_malformed_referrer_is_still_evidence(self):
        # Not parsed as a URL and not validated as one: where somebody came
        # from is worth keeping even when it is not a well-formed address.
        fields = self.fields(touch(referrer='android-app://com.whatsapp'))
        self.assertEqual(fields['referrer'], 'android-app://com.whatsapp')

    def test_a_long_address_is_cut(self):
        fields = self.fields(touch(referrer='https://x.co/' + 'a' * 400))
        self.assertEqual(len(fields['referrer']), ADDRESS_LENGTH)


class SeenAtTests(TouchFieldsTestCase):
    """The one timestamp that comes from the client, and every way to lose it."""

    def test_an_iso_instant_is_kept(self):
        seen = NOW - timedelta(days=3)
        fields = self.fields(touch(seen_at=seen.isoformat()))
        self.assertEqual(fields['seen_at'], seen)

    def test_a_javascript_instant_is_kept(self):
        # Exactly what `Date.prototype.toISOString` produces, which is what the
        # frontend's cookie carries.
        fields = self.fields(touch(seen_at='2026-08-30T09:15:00.000Z'))
        self.assertIsNotNone(fields['seen_at'])

    def test_a_naive_instant_is_dropped(self):
        # There is no zone to assume, and assuming one puts every first touch
        # two hours out.
        fields = self.fields(touch(seen_at='2026-08-30T09:15:00'))
        self.assertIsNone(fields['seen_at'])

    def test_an_instant_in_the_future_is_dropped(self):
        fields = self.fields(touch(seen_at=(NOW + timedelta(days=1)).isoformat()))
        self.assertIsNone(fields['seen_at'])

    def test_a_few_minutes_of_clock_skew_is_forgiven(self):
        # A phone whose clock is a minute fast is not a fabricated date.
        seen = NOW + timedelta(minutes=1)
        fields = self.fields(touch(seen_at=seen.isoformat()))
        self.assertEqual(fields['seen_at'], seen)

    def test_an_instant_older_than_a_browser_could_hold_is_dropped(self):
        seen = NOW - services.SEEN_AT_MAX_AGE - timedelta(days=1)
        fields = self.fields(touch(seen_at=seen.isoformat()))
        self.assertIsNone(fields['seen_at'])

    def test_a_malformed_instant_is_dropped_rather_than_raising(self):
        for value in ('yesterday', '', '2026-08-30T25:00:00Z', 12345):
            with self.subTest(value=value):
                self.assertIsNone(self.fields(touch(seen_at=value))['seen_at'])

    def test_an_impossible_date_is_dropped_rather_than_raising(self):
        # Well formed and not a date. `parse_datetime` raises for this one.
        self.assertIsNone(self.fields(touch(seen_at='2026-02-31T10:00:00Z'))['seen_at'])

    def test_the_campaign_survives_a_timestamp_that_did_not(self):
        # "We know the campaign and not the moment" is the point of the null.
        fields = self.fields(touch(seen_at='nonsense'))
        self.assertEqual(fields['source'], 'instagram')


class RecordTouchesTests(TestCase):
    """The four outcomes, and the rows each writes."""

    def record(self, first=None, last=None):
        return services.record_touches(
            storefront=Storefront.CLUB, first=first, last=last, now=NOW
        )

    def test_an_untagged_visitor_writes_nothing(self):
        self.assertEqual(self.record(), (None, None))
        self.assertEqual(CampaignTouch.objects.count(), 0)

    def test_two_empty_payloads_write_nothing(self):
        self.assertEqual(self.record({}, {'landing_path': '/'}), (None, None))
        self.assertEqual(CampaignTouch.objects.count(), 0)

    def test_one_visit_writes_one_row_and_points_both_at_it(self):
        first, last = self.record(touch(), touch())

        self.assertEqual(CampaignTouch.objects.count(), 1)
        self.assertEqual(first, last)

    def test_two_campaigns_write_two_rows(self):
        first, last = self.record(
            touch(source='instagram'), touch(source='google', medium='cpc')
        )

        self.assertEqual(CampaignTouch.objects.count(), 2)
        self.assertNotEqual(first, last)
        self.assertEqual(first.source, 'instagram')
        self.assertEqual(last.source, 'google')

    def test_a_known_last_touch_stands_for_both(self):
        # Otherwise "how many joined on the campaign that found them" is
        # unanswerable without knowing which half was missing.
        first, last = self.record(None, touch())

        self.assertEqual(first, last)
        self.assertEqual(CampaignTouch.objects.count(), 1)

    def test_a_known_first_touch_stands_for_both(self):
        first, last = self.record(touch(), {})

        self.assertEqual(first, last)

    def test_the_same_campaign_at_different_times_is_two_visits(self):
        # Same advert, two arrivals. The times are what distinguish them, so
        # they are not collapsed.
        first, last = self.record(
            touch(seen_at=(NOW - timedelta(days=9)).isoformat()),
            touch(seen_at=NOW.isoformat()),
        )

        self.assertNotEqual(first, last)

    def test_what_is_written_is_what_was_cleaned(self):
        first, _ = self.record(touch(source=' Instagram '), touch(source=' Instagram '))

        first.refresh_from_db()
        self.assertEqual(first.source, 'instagram')

    def test_nothing_written_is_a_touch_that_says_nothing(self):
        # The service's own guard, checked against the constraint that backs it.
        first, _ = self.record(touch(), touch())
        self.assertTrue(
            any(
                getattr(first, name)
                for name in (*services.CAMPAIGN_FIELDS, 'click_id', 'referrer')
            )
        )


class ConstraintTests(TestCase):
    """What the database refuses, for a writer that is not ``record_touches``."""

    def test_a_touch_that_says_nothing_is_refused(self):
        with self.assertRaises(IntegrityError):
            CampaignTouch.objects.create(
                storefront=Storefront.CLUB, landing_path='/signup'
            )

    def test_a_click_id_without_its_network_is_refused(self):
        with self.assertRaises(IntegrityError):
            CampaignTouch.objects.create(
                storefront=Storefront.CLUB, source='google', click_id='abc'
            )

    def test_a_network_without_its_click_id_is_refused(self):
        with self.assertRaises(IntegrityError):
            CampaignTouch.objects.create(
                storefront=Storefront.CLUB,
                source='google',
                click_network=ClickNetwork.GOOGLE,
            )

    def test_an_unknown_storefront_is_refused(self):
        with self.assertRaises(IntegrityError):
            CampaignTouch.objects.create(storefront='bakery', source='instagram')


class LabelTests(TestCase):
    """How a touch reads in a list, which is the only thing the admin shows."""

    def test_the_three_dimensions_in_order(self):
        row = CampaignTouch(source='google', medium='cpc', campaign='spring')
        self.assertEqual(row.label, 'google / cpc / spring')

    def test_a_missing_dimension_holds_its_place(self):
        row = CampaignTouch(source='instagram')
        self.assertEqual(row.label, 'instagram / — / —')

    def test_a_referring_site_stands_in_where_there_is_no_campaign(self):
        row = CampaignTouch(referrer='https://news24.com/story')
        self.assertEqual(row.label, 'https://news24.com/story')

    def test_a_click_network_stands_in_where_there_is_nothing_else(self):
        row = CampaignTouch(click_network=ClickNetwork.META, click_id='abc')
        self.assertEqual(row.label, 'Meta (Facebook, Instagram)')
