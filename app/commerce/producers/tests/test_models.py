"""What a producer guarantees.

**This module's whole premise was reversed by the producer generalisation.** It
used to open by defending a decision — *"there is no second name namespace;
``pseudonym`` reads ``User.display_name``, so a cultivator's public name is the
nickname the club already holds unique"* — and to pin that so nobody added a
trading-name column later without noticing what it opened.

A farm with three appointed staff has no single owner whose nickname to borrow,
so the column exists now and the namespace is real. What replaced that test is
the one thing the new namespace needs: ``TradingNameTests``, which holds the
uniqueness rule the old design got from the nickname index for free.

The rest is what the organisation added. Publication is unchanged — a producer
is drafted before it is shown, and a row created by staff must not be visible by
the act of existing. Appointments, storefronts and the encrypted account number
are new, and each has one thing worth asserting.
"""
from django.db import IntegrityError, transaction
from django.test import TestCase

from app.core.storefronts.models import Storefront
from f2c.testing import make_account, make_cultivator, make_producer

from ..models import Producer, ProducerMembership, ProducerRole, ProducerStorefront


class TradingNameTests(TestCase):
    """The namespace the old design did not have."""

    def test_the_pseudonym_is_the_trading_name(self):
        """Every caller wanting a grower's public name reads this one thing.

        The strain comparison screen, the certificate of ownership and the
        plant's derived pseudonym all go through it, so a farm renaming itself
        is one write rather than a sweep.
        """
        producer = make_producer('Kloof Farm')

        self.assertEqual(producer.pseudonym, 'Kloof Farm')
        self.assertEqual(str(producer), 'Kloof Farm')

    def test_two_producers_cannot_trade_under_one_name(self):
        make_producer('Kloof Farm')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_producer('Kloof Farm')

    def test_the_comparison_is_case_insensitive(self):
        """Two farms reading as the same name to everybody but the database is
        the same impersonation problem the nickname rule exists for."""
        make_producer('Kloof Farm')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_producer('KLOOF FARM')

    def test_the_name_is_trimmed_and_the_key_follows_it(self):
        """So the key really is `LOWER(trading_name)`, which is what the check
        constraint compares — without it the constraint would refuse the
        model's own write."""
        producer = make_producer('  Kloof Farm  ')

        self.assertEqual(producer.trading_name, 'Kloof Farm')
        self.assertEqual(producer.trading_name_key, 'kloof farm')

    def test_a_stale_key_is_refused_by_the_database(self):
        """The backstop for a write that went around `save`.

        A raw update is the write this constraint exists for: a farm renamed by
        a queryset would still occupy its old name for uniqueness purposes while
        displaying the new one.
        """
        producer = make_producer('Kloof Farm')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Producer.objects.filter(pk=producer.pk).update(
                    trading_name='Tygerberg'
                )


class PublicationTests(TestCase):
    def test_a_producer_is_unpublished_when_it_is_created(self):
        """Creating the row is not the act of publishing it."""
        producer = make_producer('Kloof Farm')

        self.assertFalse(producer.is_published)
        self.assertEqual(list(Producer.objects.published()), [])

    def test_published_finds_only_published_producers(self):
        make_producer('Kloof Farm', is_published=True)
        make_producer('Tygerberg')

        self.assertEqual(
            [p.pseudonym for p in Producer.objects.published()], ['Kloof Farm']
        )


class AppointmentTests(TestCase):
    """The people, which is what replaced the one-to-one to an account."""

    def test_the_primary_is_the_appointment_that_says_so(self):
        person, producer = make_cultivator('grower@example.com')

        self.assertEqual(producer.primary.user, person)
        self.assertTrue(producer.primary.is_primary)

    def test_a_producer_with_nobody_appointed_has_no_primary(self):
        """A legitimate intermediate state — a farm created in the admin before
        anybody is appointed to it — so this returns None rather than raising at
        a call site that only wanted a name to display."""
        self.assertIsNone(make_producer('Kloof Farm').primary)

    def test_a_producer_may_have_only_one_primary(self):
        """`member-roles` gives appointing staff to the primary alone, which
        means nothing if there can be two.

        Enforced by a derived null-slot column rather than a partial index —
        the same trick as `nickname_key` and `live_for_user`, for the same MySQL
        reason.
        """
        _person, producer = make_cultivator('grower@example.com')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProducerMembership.objects.create(
                    producer=producer,
                    user=make_account('second@example.com'),
                    role=ProducerRole.PRIMARY,
                )

    def test_two_producers_may_each_have_a_primary(self):
        """The slot is per farm, not per platform."""
        make_cultivator('one@example.com', trading_name='Kloof')
        make_cultivator('two@example.com', trading_name='Tygerberg')

        self.assertEqual(ProducerMembership.objects.count(), 2)

    def test_the_slot_follows_a_demotion(self):
        """Derived on every write, so a primary stepping down frees the slot."""
        _person, producer = make_cultivator('grower@example.com')
        appointment = producer.primary
        appointment.role = ProducerRole.FULL
        appointment.save()

        producer = Producer.objects.get(pk=producer.pk)
        self.assertIsNone(producer.primary)

    def test_one_person_is_appointed_to_a_producer_once(self):
        person, producer = make_cultivator('grower@example.com')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProducerMembership.objects.create(
                    producer=producer, user=person, role=ProducerRole.LIMITED
                )

    def test_full_rights_are_what_the_primary_also_holds(self):
        """Being the primary is *more than* full rights, not an alternative."""
        _person, producer = make_cultivator('grower@example.com')

        self.assertTrue(producer.primary.has_full_rights)


class StorefrontTests(TestCase):
    """Which shopfronts a farm sells into. Not the same question as which
    produce it sells, which is the market catalogue's."""

    def test_a_producer_may_sell_into_both(self):
        producer = make_producer('Kloof Farm')
        ProducerStorefront.objects.create(
            producer=producer, storefront=Storefront.CLUB
        )
        ProducerStorefront.objects.create(
            producer=producer, storefront=Storefront.MARKET
        )

        self.assertEqual(producer.storefronts.count(), 2)

    def test_a_producer_sells_into_one_storefront_once(self):
        producer = make_producer('Kloof Farm')
        ProducerStorefront.objects.create(
            producer=producer, storefront=Storefront.CLUB
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProducerStorefront.objects.create(
                    producer=producer, storefront=Storefront.CLUB
                )

    def test_selling_into_narrows_to_one_storefront(self):
        club = make_producer('Kloof Farm')
        ProducerStorefront.objects.create(producer=club, storefront=Storefront.CLUB)
        market = make_producer('Veg Co')
        ProducerStorefront.objects.create(
            producer=market, storefront=Storefront.MARKET
        )

        self.assertEqual(
            list(Producer.objects.selling_into(Storefront.MARKET)), [market]
        )


class BankDetailTests(TestCase):
    """What settlement needs, and no more than the brief names — C10."""

    def test_the_account_number_is_encrypted_at_rest(self):
        producer = make_producer('Kloof Farm')
        producer.bank_account_number = '62 1234 5678'
        producer.save()

        stored = Producer.objects.get(pk=producer.pk)
        self.assertNotIn('621234', stored.bank_account_number_encrypted)
        self.assertEqual(stored.bank_account_number, '6212345678')

    def test_no_number_reads_back_as_blank(self):
        producer = make_producer('Kloof Farm')

        self.assertEqual(producer.bank_account_number, '')

    def test_the_number_is_not_blind_indexed(self):
        """Deliberately, and the asymmetry with the identity number is the
        point: an identity number is *searched* — "is this person already on
        file" — and an account number is only ever read back to whoever runs the
        payout. An index nothing queries is a second place for ciphertext to
        leak from.
        """
        fields = {field.name for field in Producer._meta.get_fields()}

        self.assertNotIn('bank_account_number_hash', fields)
