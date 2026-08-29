"""Tests for the guard that keeps the email settings in step with `Storefront`.

Settings cannot import `Storefront`, so the storefront codes are written out
twice -- once in the enum and once in the `MAILERS` and `STOREFRONT_FROM_EMAIL`
blocks. This is what stops the two drifting, and it matters because the drift is
invisible: `mail.mailer_for` falls back rather than raising, deliberately, so a
storefront with no mailer sends successfully through somebody else's server.
"""
from django.test import SimpleTestCase, override_settings

from app.core.storefronts.checks import check_every_storefront_can_send_email
from app.core.storefronts.models import Storefront

COMPLETE_MAILERS = {
    'default': {'BACKEND': 'django.core.mail.backends.locmem.EmailBackend'},
    'club': {'BACKEND': 'django.core.mail.backends.locmem.EmailBackend'},
    'market': {'BACKEND': 'django.core.mail.backends.locmem.EmailBackend'},
}
COMPLETE_SENDERS = {'club': 'club@example.com', 'market': 'market@example.com'}


def run():
    return check_every_storefront_can_send_email(app_configs=None)


class StorefrontMailCheckTests(SimpleTestCase):
    @override_settings(
        MAILERS=COMPLETE_MAILERS, STOREFRONT_FROM_EMAIL=COMPLETE_SENDERS
    )
    def test_a_complete_configuration_passes(self):
        self.assertEqual(run(), [])

    def test_the_projects_own_settings_cover_every_storefront(self):
        """No override: this runs the guard against what settings.py really built.

        The test runner swaps each MAILERS alias for locmem but keeps the alias
        names, so a storefront missing from that block is missing here too.
        """
        self.assertEqual(run(), [])

    @override_settings(
        MAILERS={
            'default': COMPLETE_MAILERS['default'],
            'club': COMPLETE_MAILERS['club'],
        },
        STOREFRONT_FROM_EMAIL=COMPLETE_SENDERS,
    )
    def test_a_storefront_with_no_mailer_is_an_error(self):
        errors = run()

        self.assertEqual([error.id for error in errors], ['storefronts.E001'])
        self.assertIn('market', errors[0].msg)

    @override_settings(
        MAILERS=COMPLETE_MAILERS,
        STOREFRONT_FROM_EMAIL={'club': COMPLETE_SENDERS['club']},
    )
    def test_a_storefront_with_no_sender_address_is_an_error(self):
        errors = run()

        self.assertEqual([error.id for error in errors], ['storefronts.E002'])
        self.assertIn('market', errors[0].msg)

    @override_settings(MAILERS={}, STOREFRONT_FROM_EMAIL={})
    def test_nothing_configured_reports_both_faults_for_every_storefront(self):
        errors = run()

        self.assertEqual(len(errors), 2 * len(Storefront.values))
