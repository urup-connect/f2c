"""What a cultivator profile guarantees.

Short, because the model is. The one thing worth asserting is the decision the
module docstring defends: **there is no second name namespace.** ``pseudonym``
reads ``User.display_name``, so a cultivator's public name is the nickname the
club already holds unique, and a test that pins that is what stops somebody
adding a ``pseudonym`` column later without noticing what it opens.

The rest is publication. A profile is drafted before it is shown, and a row
created by staff must not be visible by the act of existing.
"""
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from app.accounts.roles import UserRole

from ..models import CultivatorProfile

User = get_user_model()


class CultivatorProfileTests(TestCase):
    def setUp(self):
        self.cultivator = User.objects.create_user(
            email='grower@example.com',
            nickname='Kloof Farm',
            role=UserRole.CULTIVATOR,
        )

    def test_the_pseudonym_is_the_accounts_own_display_name(self):
        """One name namespace. See the module docstring, and backend.md 3.6."""
        profile = CultivatorProfile.objects.create(cultivator=self.cultivator)

        self.assertEqual(profile.pseudonym, self.cultivator.display_name)
        self.assertEqual(profile.pseudonym, 'Kloof Farm')

    def test_a_profile_is_unpublished_when_it_is_created(self):
        """Creating the row is not the act of publishing it."""
        profile = CultivatorProfile.objects.create(cultivator=self.cultivator)

        self.assertFalse(profile.is_published)
        self.assertEqual(list(CultivatorProfile.objects.published()), [])

    def test_published_finds_only_published_profiles(self):
        CultivatorProfile.objects.create(
            cultivator=self.cultivator, is_published=True
        )
        CultivatorProfile.objects.create(
            cultivator=User.objects.create_user(
                email='other@example.com', nickname='Tygerberg',
                role=UserRole.CULTIVATOR,
            )
        )

        self.assertEqual(
            [p.pseudonym for p in CultivatorProfile.objects.published()],
            ['Kloof Farm'],
        )

    def test_an_account_holds_at_most_one_profile(self):
        CultivatorProfile.objects.create(cultivator=self.cultivator)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CultivatorProfile.objects.create(cultivator=self.cultivator)

    def test_the_string_form_shows_a_nickname_and_never_an_email_address(self):
        profile = CultivatorProfile.objects.create(cultivator=self.cultivator)

        self.assertEqual(str(profile), 'Kloof Farm')
        self.assertNotIn('@', str(profile))
