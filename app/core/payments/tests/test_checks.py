"""The deploy check that catches a proxied Payfast endpoint reading REMOTE_ADDR.

The failure this guards is silent end to end -- see ``checks.py`` -- so the
tests worth having are the ones asserting it fires in the configuration a
container deployment actually has, and stays quiet in the two where the setting
is genuinely correct.
"""
from django.core.checks import Warning
from django.test import SimpleTestCase, override_settings

from app.core.payments import gateway
from app.core.payments.checks import check_payfast_reads_the_forwarded_address

DIRECT = gateway.sandbox_settings(behind_proxy=False)
PROXIED = gateway.sandbox_settings(behind_proxy=True)


class ForwardedAddressCheckTests(SimpleTestCase):
    def run_check(self):
        return check_payfast_reads_the_forwarded_address(app_configs=None)

    @override_settings(DEBUG=False, PAYFAST=DIRECT)
    def test_a_deployed_endpoint_without_the_setting_is_flagged(self):
        """The configuration every Container Apps deployment starts in."""
        warnings = self.run_check()

        self.assertEqual(len(warnings), 1)
        self.assertIsInstance(warnings[0], Warning)
        self.assertEqual(warnings[0].id, 'payments.W001')

    @override_settings(DEBUG=False, PAYFAST=DIRECT)
    def test_the_warning_names_the_variable_and_the_consequence(self):
        """Somebody reading `check --deploy` output has to be able to act on it
        without opening the source."""
        warning = self.run_check()[0]
        text = f'{warning.msg} {warning.hint}'

        self.assertIn('DJANGO_BEHIND_PROXY', text)
        self.assertIn('DJANGO_PAYFAST_BEHIND_PROXY', text)
        self.assertIn('REMOTE_ADDR', text)
        self.assertIn('never activated', text)

    @override_settings(DEBUG=False, PAYFAST=PROXIED)
    def test_a_proxied_endpoint_that_says_so_is_quiet(self):
        self.assertEqual(self.run_check(), [])

    @override_settings(DEBUG=True, PAYFAST=DIRECT)
    def test_development_is_quiet(self):
        """`manage.py payfast_notify` posts from localhost with no proxy in
        sight, so the warning would be noise."""
        self.assertEqual(self.run_check(), [])


class PrivateAddressTests(SimpleTestCase):
    """`address_is_private` only ever explains a rejection -- it admits nobody."""

    def test_the_ingress_proxy_ranges_are_private(self):
        for address in ('10.0.0.4', '172.16.3.9', '192.168.1.1', '127.0.0.1'):
            with self.subTest(address=address):
                self.assertTrue(gateway.address_is_private(address))

    def test_a_public_address_is_not(self):
        self.assertFalse(gateway.address_is_private('197.221.32.5'))

    def test_ipv6_is_understood(self):
        self.assertTrue(gateway.address_is_private('fd00::1'))
        self.assertFalse(gateway.address_is_private('2001:4860:4860::8888'))

    def test_a_missing_address_is_not_an_error(self):
        """`notification_source_ip` returns '' when neither source has one."""
        self.assertFalse(gateway.address_is_private(''))

    def test_something_that_is_not_an_address_is_not_an_error(self):
        """X-Forwarded-For arrives from the client and can say anything."""
        self.assertFalse(gateway.address_is_private('not-an-address'))


class ProxySwitchFallbackTests(SimpleTestCase):
    """`DJANGO_BEHIND_PROXY` answers for both Django and Payfast.

    Two switches for one deployment fact fails by having one of them set, and
    the half that fails silently is this one -- see `checks.py`. So the general
    variable is read when the Payfast-specific one says nothing, and the
    specific one still wins when it says something, for the edge that
    terminates TLS without overwriting X-Forwarded-For.
    """
    def config(self, **environ):
        base = {
            'DJANGO_PAYFAST_MERCHANT_ID': '10000100',
            'DJANGO_PAYFAST_MERCHANT_KEY': '46f0cd694581a',
            'DJANGO_PAYFAST_PASSPHRASE': 'passphrase',
        }
        return gateway.payfast_config(base | environ, debug=True)

    def test_neither_variable_means_remote_addr(self):
        self.assertFalse(self.config().behind_proxy)

    def test_the_general_variable_is_enough(self):
        self.assertTrue(self.config(DJANGO_BEHIND_PROXY='true').behind_proxy)

    def test_the_specific_variable_still_works_alone(self):
        self.assertTrue(
            self.config(DJANGO_PAYFAST_BEHIND_PROXY='true').behind_proxy
        )

    def test_the_specific_variable_overrides_the_general_one(self):
        """A deployment behind an edge that terminates TLS but appends to
        X-Forwarded-For: safe for Django's scheme, not safe for the source
        check, and it must be possible to say so."""
        config = self.config(
            DJANGO_BEHIND_PROXY='true', DJANGO_PAYFAST_BEHIND_PROXY='false'
        )

        self.assertFalse(config.behind_proxy)

    def test_a_blank_specific_variable_falls_through(self):
        """A deployment template that renders an empty string has not spoken."""
        config = self.config(
            DJANGO_BEHIND_PROXY='true', DJANGO_PAYFAST_BEHIND_PROXY='  '
        )

        self.assertTrue(config.behind_proxy)
