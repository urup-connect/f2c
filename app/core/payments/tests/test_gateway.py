"""Tests for the Payfast protocol itself.

Nothing here touches the database, and that is the point of the module: a
signature is the one part of a payment integration that fails silently and
identically for a dozen different reasons -- Payfast answers every bad one with
the same generic refusal -- so each rule that produces one is pinned separately.

Three groups matter most.

**The encoding**, because it has to match PHP's ``urlencode`` byte for byte and
Python's nearest equivalent does not. A test per difference.

**The ordering**, because Payfast signs a checkout in its documented order and a
notification in arrival order, and code that used one for both would still
produce a plausible 32-character hex string.

**The configuration refusals**, because every one of them is a deployment that
would otherwise take real money into the wrong account or over plain http.
"""
from decimal import Decimal

from django.core.exceptions import ImproperlyConfigured

from app.core.payments import gateway

from .support import PAYFAST, GatewayTestCase


class EncodingTests(GatewayTestCase):
    """Where ``quote_plus`` and PHP's ``urlencode`` disagree."""

    def test_a_space_becomes_a_plus(self):
        self.assertEqual(gateway._encode('Club membership'), 'Club+membership')

    def test_a_literal_plus_is_escaped_rather_than_left_as_a_space(self):
        """The other half of the rule above, and the one that would silently
        corrupt an item name containing a plus sign."""
        self.assertEqual(gateway._encode('Club+membership'), 'Club%2Bmembership')

    def test_a_tilde_is_escaped(self):
        """``quote_plus`` treats ``~`` as always safe; PHP escapes it.

        Asserted against the literal escape rather than against another call,
        because the whole risk here is that both sides of a comparison share the
        same mistake.
        """
        self.assertEqual(gateway._encode('a~b'), 'a%7Eb')

    def test_hex_escapes_are_upper_case(self):
        self.assertEqual(gateway._encode('a/b'), 'a%2Fb')

    def test_values_are_trimmed_before_signing(self):
        self.assertEqual(
            gateway.signature_over([('amount', ' 150.00 ')], ''),
            gateway.signature_over([('amount', '150.00')], ''),
        )


class SignatureTests(GatewayTestCase):
    def test_an_empty_value_is_omitted_not_signed_as_empty(self):
        """Signing ``key=`` produces a signature Payfast rejects."""
        with_blank = gateway.signature_over(
            [('merchant_id', '10000100'), ('item_description', '')], ''
        )
        without = gateway.signature_over([('merchant_id', '10000100')], '')

        self.assertEqual(with_blank, without)

    def test_a_whitespace_only_value_is_omitted_too(self):
        self.assertEqual(
            gateway.signature_over([('a', '1'), ('b', '   ')], ''),
            gateway.signature_over([('a', '1')], ''),
        )

    def test_the_passphrase_changes_the_signature(self):
        pairs = [('merchant_id', '10000100')]

        self.assertNotEqual(
            gateway.signature_over(pairs, ''),
            gateway.signature_over(pairs, 'jt7NOE43FZPn'),
        )

    def test_the_passphrase_is_appended_last(self):
        """Not sorted in among the fields. Asserted by construction: a
        passphrase appended by hand has to produce the same digest."""
        pairs = [('merchant_id', '10000100'), ('amount', '150.00')]

        self.assertEqual(
            gateway.signature_over(pairs, 'secret'),
            gateway.signature_over(pairs + [('passphrase', 'secret')], ''),
        )

    def test_order_changes_the_signature(self):
        """The reason ``pairs`` is a sequence and not a mapping."""
        forward = [('a', '1'), ('b', '2')]

        self.assertNotEqual(
            gateway.signature_over(forward, ''),
            gateway.signature_over(list(reversed(forward)), ''),
        )


class CheckoutSignatureTests(GatewayTestCase):
    def test_it_signs_in_payfast_s_documented_order_not_the_dict_order(self):
        """A dict built the other way round must sign the same."""
        fields = {'amount': '150.00', 'merchant_id': '10000100'}
        reversed_fields = {'merchant_id': '10000100', 'amount': '150.00'}

        self.assertEqual(
            gateway.checkout_signature(fields, 'x'),
            gateway.checkout_signature(reversed_fields, 'x'),
        )

    def test_the_documented_order_is_merchant_first_then_amount(self):
        fields = {'amount': '150.00', 'merchant_id': '10000100'}

        self.assertEqual(
            gateway.checkout_signature(fields, ''),
            gateway.signature_over(
                [('merchant_id', '10000100'), ('amount', '150.00')], ''
            ),
        )

    def test_a_field_payfast_does_not_know_is_refused_here(self):
        """Refused locally rather than at Payfast, which would answer with a
        generic decline and nothing to debug."""
        with self.assertRaises(ValueError) as raised:
            gateway.checkout_signature({'merchant_id': '1', 'nickname': 'x'}, '')

        self.assertIn('nickname', str(raised.exception))


class CheckoutTests(GatewayTestCase):
    def setUp(self):
        self.checkout = gateway.checkout(PAYFAST, m_payment_id='sub-1')

    def test_it_posts_to_the_sandbox_when_configured_for_sandbox(self):
        self.assertEqual(
            self.checkout['url'], 'https://sandbox.payfast.co.za/eng/process'
        )

    def test_a_live_configuration_posts_to_the_live_engine(self):
        live = gateway.sandbox_settings(sandbox=False)

        self.assertEqual(
            gateway.checkout(live, m_payment_id='sub-1')['url'],
            'https://www.payfast.co.za/eng/process',
        )

    def test_it_carries_no_personal_data_at_all(self):
        """The decision behind the whole checkout endpoint. If any of these ever
        appears, the token in the URL stops being a way to pay and becomes a way
        to read somebody's details."""
        personal = {
            'name_first',
            'name_last',
            'email_address',
            'cell_number',
            'confirmation_address',
        }

        self.assertEqual(personal & set(self.checkout['fields']), set())

    def test_it_asks_for_a_subscription_rather_than_a_single_payment(self):
        self.assertEqual(self.checkout['fields']['subscription_type'], '1')

    def test_it_sends_the_recurring_amount_as_well_as_the_first_one(self):
        fields = self.checkout['fields']

        self.assertEqual(fields['amount'], '150.00')
        self.assertEqual(fields['recurring_amount'], '150.00')

    def test_cycles_of_zero_means_until_cancelled(self):
        self.assertEqual(self.checkout['fields']['cycles'], '0')

    def test_the_signature_verifies_over_the_fields_it_returns(self):
        fields = dict(self.checkout['fields'])
        signature = fields.pop('signature')

        self.assertEqual(
            signature, gateway.checkout_signature(fields, PAYFAST.passphrase)
        )

    def test_the_billing_date_is_south_african_not_utc(self):
        """Payfast refuses a date in the past, and UTC is two hours behind."""
        from datetime import datetime, timezone as dt_timezone
        from unittest.mock import patch

        # 23:30 SAST on the 2nd is 21:30 UTC on the 2nd -- but 00:30 SAST on the
        # 3rd is 22:30 UTC on the *2nd*, which is the case that breaks.
        late = datetime(2026, 3, 2, 22, 30, tzinfo=dt_timezone.utc)
        with patch('django.utils.timezone.now', return_value=late):
            self.assertEqual(gateway.billing_date().isoformat(), '2026-03-03')

    def test_an_empty_m_payment_id_is_refused(self):
        """It is the only thing tying a notification back to a member."""
        with self.assertRaises(ValueError):
            gateway.checkout(PAYFAST, m_payment_id='  ')


class SourceTests(GatewayTestCase):
    def test_an_address_payfast_resolves_to_is_accepted(self):
        self.assertTrue(gateway.source_is_payfast('1.2.3.4', {'1.2.3.4'}))

    def test_any_other_address_is_not(self):
        self.assertFalse(gateway.source_is_payfast('5.6.7.8', {'1.2.3.4'}))

    def test_no_address_is_not(self):
        self.assertFalse(gateway.source_is_payfast('', {'1.2.3.4'}))

    def test_it_fails_closed_when_nothing_resolves(self):
        """Every host unreachable means reject, not allow. Payfast retries; the
        alternative is trusting an unverified caller."""
        self.assertFalse(gateway.source_is_payfast('1.2.3.4', set()))

    def test_resolution_failures_do_not_take_the_others_down(self):
        addresses = gateway.payfast_addresses(('no-such-host.invalid',))

        self.assertEqual(addresses, set())


class SourceAddressTests(GatewayTestCase):
    def test_remote_addr_is_used_by_default(self):
        meta = {'REMOTE_ADDR': '1.2.3.4', 'HTTP_X_FORWARDED_FOR': '9.9.9.9'}

        self.assertEqual(gateway.notification_source_ip(meta), '1.2.3.4')

    def test_the_forwarded_header_is_ignored_unless_it_is_opted_into(self):
        """Reading it unconditionally hands an attacker the source check."""
        meta = {'REMOTE_ADDR': '1.2.3.4', 'HTTP_X_FORWARDED_FOR': '197.97.145.144'}

        self.assertEqual(gateway.notification_source_ip(meta), '1.2.3.4')

    def test_behind_a_proxy_the_first_forwarded_entry_is_used(self):
        meta = {'REMOTE_ADDR': '10.0.0.1', 'HTTP_X_FORWARDED_FOR': '1.2.3.4, 10.0.0.1'}

        self.assertEqual(
            gateway.notification_source_ip(meta, behind_proxy=True), '1.2.3.4'
        )

    def test_a_port_is_stripped(self):
        """App Service writes client:port rather than a bare address."""
        meta = {'HTTP_X_FORWARDED_FOR': '1.2.3.4:52144'}

        self.assertEqual(
            gateway.notification_source_ip(meta, behind_proxy=True), '1.2.3.4'
        )

    def test_it_falls_back_to_remote_addr_when_the_header_is_absent(self):
        meta = {'REMOTE_ADDR': '10.0.0.1'}

        self.assertEqual(
            gateway.notification_source_ip(meta, behind_proxy=True), '10.0.0.1'
        )


class AmountTests(GatewayTestCase):
    def test_the_agreed_amount_matches(self):
        self.assertTrue(gateway.amount_matches('150.00', Decimal('150.00')))

    def test_a_different_amount_does_not(self):
        self.assertFalse(gateway.amount_matches('1.00', Decimal('150.00')))

    def test_a_cent_short_does_not(self):
        self.assertFalse(gateway.amount_matches('149.99', Decimal('150.00')))

    def test_trailing_zeroes_do_not_change_the_answer(self):
        self.assertTrue(gateway.amount_matches('150', Decimal('150.00')))

    def test_something_that_is_not_a_number_does_not_match(self):
        self.assertFalse(gateway.amount_matches('free', Decimal('150.00')))


class VerificationTests(GatewayTestCase):
    def pairs(self, **overrides):
        base = [
            ('m_payment_id', 'sub-1'),
            ('payment_status', 'COMPLETE'),
            ('amount_gross', '150.00'),
            ('merchant_id', PAYFAST.merchant_id),
        ]
        base = [(k, overrides.get(k, v)) for k, v in base]
        return base + [
            ('signature', gateway.notification_signature(base, PAYFAST.passphrase))
        ]

    def test_a_correctly_signed_notification_from_payfast_verifies(self):
        posted = gateway.verify_notification(
            self.pairs(), PAYFAST, source_ip='1.2.3.4', addresses={'1.2.3.4'}
        )

        self.assertEqual(posted['m_payment_id'], 'sub-1')

    def test_a_notification_from_anywhere_else_is_rejected(self):
        with self.assertRaises(gateway.NotificationRejected):
            gateway.verify_notification(
                self.pairs(), PAYFAST, source_ip='5.6.7.8', addresses={'1.2.3.4'}
            )

    def test_another_merchant_is_rejected(self):
        with self.assertRaises(gateway.NotificationRejected):
            gateway.verify_notification(
                self.pairs(merchant_id='99999999'),
                PAYFAST,
                source_ip='1.2.3.4',
                addresses={'1.2.3.4'},
            )

    def test_a_forged_signature_is_rejected(self):
        pairs = self.pairs()[:-1] + [('signature', '0' * 32)]

        with self.assertRaises(gateway.NotificationRejected):
            gateway.verify_notification(
                pairs, PAYFAST, source_ip='1.2.3.4', addresses={'1.2.3.4'}
            )

    def test_a_tampered_amount_breaks_the_signature(self):
        """The signature is what makes the amount trustworthy enough to compare."""
        pairs = self.pairs()
        tampered = [
            (k, '1.00' if k == 'amount_gross' else v) for k, v in pairs
        ]

        with self.assertRaises(gateway.NotificationRejected):
            gateway.verify_notification(
                tampered, PAYFAST, source_ip='1.2.3.4', addresses={'1.2.3.4'}
            )

    def test_a_missing_signature_is_rejected(self):
        pairs = [(k, v) for k, v in self.pairs() if k != 'signature']

        with self.assertRaises(gateway.NotificationRejected):
            gateway.verify_notification(
                pairs, PAYFAST, source_ip='1.2.3.4', addresses={'1.2.3.4'}
            )

    def test_a_field_this_application_does_not_read_is_still_signed_over(self):
        """Payfast adds fields. A verifier that signed only the ones it knew
        would start rejecting everything the day it did."""
        base = [
            ('m_payment_id', 'sub-1'),
            ('payment_status', 'COMPLETE'),
            ('merchant_id', PAYFAST.merchant_id),
            ('some_future_field', 'whatever'),
        ]
        pairs = base + [
            ('signature', gateway.notification_signature(base, PAYFAST.passphrase))
        ]

        posted = gateway.verify_notification(
            pairs, PAYFAST, source_ip='1.2.3.4', addresses={'1.2.3.4'}
        )

        self.assertEqual(posted['some_future_field'], 'whatever')


class ConfirmationTests(GatewayTestCase):
    """The one function here that makes a network call, so the call is injected."""

    def opener(self, body=None, error=None):
        class Response:
            def __enter__(inner):
                return inner

            def __exit__(inner, *args):
                return False

            def read(inner):
                return body

        def send(request, timeout=None):
            if error:
                raise error
            self.sent = request
            return Response()

        return send

    def test_valid_is_a_confirmation(self):
        self.assertIs(
            gateway.confirm_with_payfast(
                [('a', '1')], PAYFAST, opener=self.opener(b'VALID')
            ),
            True,
        )

    def test_invalid_is_a_refusal(self):
        self.assertIs(
            gateway.confirm_with_payfast(
                [('a', '1')], PAYFAST, opener=self.opener(b'INVALID')
            ),
            False,
        )

    def test_anything_else_is_a_refusal_rather_than_a_guess(self):
        self.assertIs(
            gateway.confirm_with_payfast(
                [('a', '1')], PAYFAST, opener=self.opener(b'<html>oops</html>')
            ),
            False,
        )

    def test_a_network_failure_is_neither(self):
        """None, not False. "Payfast says no" is final; "we could not ask" is
        worth a retry, and the endpoint answers them with different codes."""
        self.assertIsNone(
            gateway.confirm_with_payfast(
                [('a', '1')], PAYFAST, opener=self.opener(error=OSError('down'))
            )
        )

    def test_a_timeout_is_neither(self):
        self.assertIsNone(
            gateway.confirm_with_payfast(
                [('a', '1')], PAYFAST, opener=self.opener(error=TimeoutError())
            )
        )

    def test_it_asks_the_sandbox_when_configured_for_sandbox(self):
        gateway.confirm_with_payfast(
            [('a', '1')], PAYFAST, opener=self.opener(b'VALID')
        )

        self.assertEqual(
            self.sent.full_url, 'https://sandbox.payfast.co.za/eng/query/validate'
        )


class ConfigTests(GatewayTestCase):
    """Every refusal a deployment can hit, without a merchant account."""

    LIVE = {
        'DJANGO_PAYFAST_MERCHANT_ID': '12345678',
        'DJANGO_PAYFAST_MERCHANT_KEY': 'abcdef123456',
        'DJANGO_PAYFAST_PASSPHRASE': 'a-long-passphrase',
        'DJANGO_PAYFAST_RETURN_URL': 'https://app.example.co.za/signup/paid',
        'DJANGO_PAYFAST_CANCEL_URL': 'https://app.example.co.za/signup/cancelled',
        'DJANGO_PAYFAST_NOTIFY_URL': 'https://api.example.co.za/api/payments/payfast/notify',
        'DJANGO_MEMBERSHIP_CHECKOUT_URL': 'https://app.example.co.za/pay',
        'DJANGO_MEMBERSHIP_SUBSCRIPTION_AMOUNT': '150.00',
    }

    def live(self, **overrides):
        return {**self.LIVE, **overrides}

    def test_a_bare_environment_works_in_development(self):
        config = gateway.payfast_config({}, debug=True)

        self.assertEqual(config.merchant_id, gateway.SANDBOX_MERCHANT_ID)
        self.assertTrue(config.sandbox)

    def test_a_bare_environment_refuses_to_start_in_production(self):
        with self.assertRaises(ImproperlyConfigured):
            gateway.payfast_config({}, debug=False)

    def test_a_full_environment_is_accepted(self):
        config = gateway.payfast_config(self.live(), debug=False)

        self.assertEqual(config.merchant_id, '12345678')
        self.assertEqual(config.amount, Decimal('150.00'))

    def test_live_is_never_the_default(self):
        """A deployment that means to take real money says so."""
        self.assertTrue(gateway.payfast_config(self.live(), debug=False).sandbox)

    def test_live_has_to_be_asked_for(self):
        config = gateway.payfast_config(
            self.live(DJANGO_PAYFAST_SANDBOX='false'), debug=False
        )

        self.assertFalse(config.sandbox)

    def test_a_merchant_key_without_an_id_is_refused(self):
        environ = self.live()
        del environ['DJANGO_PAYFAST_MERCHANT_ID']

        with self.assertRaises(ImproperlyConfigured):
            gateway.payfast_config(environ, debug=False)

    def test_a_missing_passphrase_is_refused(self):
        """Payfast refuses subscriptions from a merchant without one, so an
        integration missing it fails at the checkout rather than at startup."""
        environ = self.live()
        del environ['DJANGO_PAYFAST_PASSPHRASE']

        with self.assertRaises(ImproperlyConfigured) as raised:
            gateway.payfast_config(environ, debug=False)

        self.assertIn('PASSPHRASE', str(raised.exception))

    def test_a_plain_http_url_is_refused_in_production(self):
        with self.assertRaises(ImproperlyConfigured) as raised:
            gateway.payfast_config(
                self.live(DJANGO_PAYFAST_RETURN_URL='http://app.example.co.za/paid'),
                debug=False,
            )

        self.assertIn('https', str(raised.exception))

    def test_plain_http_is_allowed_in_development(self):
        config = gateway.payfast_config({}, debug=True)

        self.assertTrue(config.return_url.startswith('http://localhost'))

    def test_a_missing_notify_url_is_refused(self):
        environ = self.live()
        del environ['DJANGO_PAYFAST_NOTIFY_URL']

        with self.assertRaises(ImproperlyConfigured):
            gateway.payfast_config(environ, debug=False)

    def test_a_missing_checkout_url_is_refused(self):
        """It is what the emailed fallback link is built from."""
        environ = self.live()
        del environ['DJANGO_MEMBERSHIP_CHECKOUT_URL']

        with self.assertRaises(ImproperlyConfigured):
            gateway.payfast_config(environ, debug=False)

    def test_an_amount_that_is_not_a_number_is_refused(self):
        with self.assertRaises(ImproperlyConfigured):
            gateway.payfast_config(
                self.live(DJANGO_MEMBERSHIP_SUBSCRIPTION_AMOUNT='free'), debug=False
            )

    def test_a_free_membership_is_refused(self):
        with self.assertRaises(ImproperlyConfigured):
            gateway.payfast_config(
                self.live(DJANGO_MEMBERSHIP_SUBSCRIPTION_AMOUNT='0'), debug=False
            )

    def test_a_negative_amount_is_refused(self):
        with self.assertRaises(ImproperlyConfigured):
            gateway.payfast_config(
                self.live(DJANGO_MEMBERSHIP_SUBSCRIPTION_AMOUNT='-10.00'),
                debug=False,
            )

    def test_an_unknown_frequency_is_refused_and_names_the_options(self):
        with self.assertRaises(ImproperlyConfigured) as raised:
            gateway.payfast_config(
                self.live(DJANGO_MEMBERSHIP_SUBSCRIPTION_FREQUENCY='fortnightly'),
                debug=False,
            )

        self.assertIn('quarterly', str(raised.exception))

    def test_a_frequency_is_read_in_english_and_stored_as_payfast_s_code(self):
        config = gateway.payfast_config(
            self.live(DJANGO_MEMBERSHIP_SUBSCRIPTION_FREQUENCY='annual'), debug=False
        )

        self.assertEqual(config.frequency, 6)
        self.assertEqual(config.cycle_days, 366)

    def test_cycles_that_are_not_a_whole_number_are_refused(self):
        with self.assertRaises(ImproperlyConfigured):
            gateway.payfast_config(
                self.live(DJANGO_MEMBERSHIP_SUBSCRIPTION_CYCLES='2.5'), debug=False
            )

    def test_the_proxy_header_is_off_unless_asked_for(self):
        self.assertFalse(gateway.payfast_config(self.live(), debug=False).behind_proxy)

    def test_the_proxy_header_can_be_asked_for(self):
        config = gateway.payfast_config(
            self.live(DJANGO_PAYFAST_BEHIND_PROXY='true'), debug=False
        )

        self.assertTrue(config.behind_proxy)
