"""Tests for field encryption and the blind index.

Both fail silently when they go wrong, which is what these check. A nonce that
stops being fresh leaks equality across the column; a context that stops being
authenticated lets ciphertext be moved between fields; a blind index that stops
normalising lets the same value index twice.
"""
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings

from app.common import crypto


class CryptoTests(TestCase):
    def test_round_trip(self):
        token = crypto.encrypt('sensitive', 'ctx')
        self.assertNotIn('sensitive', token)
        self.assertEqual(crypto.decrypt(token, 'ctx'), 'sensitive')

    def test_same_plaintext_gives_different_ciphertext(self):
        """A fresh nonce per record. Without it the column leaks equality."""
        self.assertNotEqual(
            crypto.encrypt('same', 'ctx'), crypto.encrypt('same', 'ctx')
        )

    def test_ciphertext_is_bound_to_its_field(self):
        token = crypto.encrypt('secret', 'accounts.User.id_number')
        with self.assertRaises(crypto.DecryptionError):
            crypto.decrypt(token, 'accounts.User.something_else')

    def test_tampered_ciphertext_is_rejected(self):
        token = crypto.encrypt('secret', 'ctx')
        tampered = token[:-4] + ('AAAA' if not token.endswith('AAAA') else 'BBBB')
        with self.assertRaises(crypto.DecryptionError):
            crypto.decrypt(tampered, 'ctx')

    def test_blind_index_is_deterministic_and_normalising(self):
        self.assertEqual(
            crypto.blind_index('  Craig@Example.COM ', 'ctx'),
            crypto.blind_index('craig@example.com', 'ctx'),
        )

    def test_blind_index_is_namespaced(self):
        self.assertNotEqual(
            crypto.blind_index('12345', 'a'), crypto.blind_index('12345', 'b')
        )

    @override_settings(FIELD_ENCRYPTION_KEY='')
    def test_missing_key_is_loud(self):
        with self.assertRaises(ImproperlyConfigured):
            crypto.encrypt('x', 'ctx')
