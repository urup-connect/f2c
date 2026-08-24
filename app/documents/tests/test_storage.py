"""Tests for the storage configuration reader.

``documents_storage_config`` is a pure function of an environment mapping, which
is the whole reason it is not written inline in settings: a misconfigured
container, a CDN base that disagrees with it, or a missing account are all
things that should fail loudly at startup, and none of them should need an Azure
subscription to test.

The reader is not asserted to produce a *working* backend -- that needs a real
account. What is asserted is the contract with django-storages: the option names,
and the three refusals that turn a silent 404 on every document link into a
startup error naming the variable at fault.
"""
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from app.documents.storage import (
    AZURE_BACKEND,
    DOCUMENTS_CACHE_CONTROL,
    FILESYSTEM_BACKEND,
    documents_storage_config,
)

# Returned instead of a real DefaultAzureCredential, so nothing here needs
# azure-identity installed or an identity to authenticate as.
CREDENTIAL = object()


def config(**env):
    return documents_storage_config(
        env, debug=env.pop('debug', False), credential_factory=lambda: CREDENTIAL
    )


AZURE = {
    'DJANGO_DOCUMENT_STORAGE_CONTAINER': 'consumer-collective',
    'DJANGO_DOCUMENT_STORAGE_ACCOUNT': 'urupqastatic',
    'DJANGO_CDN_BASE_URL': 'https://qa-static.urup.com/consumer-collective',
}


class LocalFallbackTests(SimpleTestCase):
    def test_no_container_means_local_disk(self):
        """The fallback is what lets the feature be built without an account."""
        self.assertEqual(config(), {'BACKEND': FILESYSTEM_BACKEND})

    def test_a_blank_container_is_the_same_as_none(self):
        self.assertEqual(
            config(DJANGO_DOCUMENT_STORAGE_CONTAINER='   '),
            {'BACKEND': FILESYSTEM_BACKEND},
        )

    def test_the_other_variables_are_ignored_while_the_container_is_blank(self):
        # So a developer can leave real credentials in .env and still work locally.
        self.assertEqual(
            config(
                DJANGO_DOCUMENT_STORAGE_ACCOUNT='urupqastatic',
                DJANGO_DOCUMENT_STORAGE_ACCOUNT_KEY='secret',
                DJANGO_CDN_BASE_URL='http://not-even-https',
            ),
            {'BACKEND': FILESYSTEM_BACKEND},
        )


class AzureOptionsTests(SimpleTestCase):
    def options(self, **overrides):
        return config(**{**AZURE, **overrides})['OPTIONS']

    def test_a_container_selects_the_azure_backend(self):
        self.assertEqual(config(**AZURE)['BACKEND'], AZURE_BACKEND)

    def test_the_container_and_account_are_passed_through(self):
        options = self.options()
        self.assertEqual(options['azure_container'], 'consumer-collective')
        self.assertEqual(options['account_name'], 'urupqastatic')

    def test_a_blob_is_never_overwritten(self):
        """A revision's file is what an agreement points at."""
        self.assertIs(self.options()['overwrite_files'], False)

    def test_urls_are_unsigned(self):
        """A SAS in every link would expire, and these links go into a public page."""
        self.assertIsNone(self.options()['expiration_secs'])

    def test_blobs_are_cached_immutably(self):
        # Safe only because the version is part of the blob name.
        self.assertEqual(self.options()['cache_control'], DOCUMENTS_CACHE_CONTROL)

    def test_the_cdn_host_becomes_the_custom_domain_without_the_container(self):
        """django-storages appends the container itself; a path here would double it."""
        options = self.options()
        self.assertEqual(options['custom_domain'], 'qa-static.urup.com')
        self.assertIs(options['azure_ssl'], True)

    def test_a_cdn_base_with_no_path_is_accepted(self):
        options = self.options(DJANGO_CDN_BASE_URL='https://qa-static.urup.com')
        self.assertEqual(options['custom_domain'], 'qa-static.urup.com')

    def test_no_cdn_base_leaves_the_account_hostname_in_place(self):
        # Valid: the blob endpoint serves the file directly, just without the CDN.
        options = self.options(DJANGO_CDN_BASE_URL='')
        self.assertNotIn('custom_domain', options)
        self.assertNotIn('azure_ssl', options)

    def test_a_location_prefix_is_passed_through_only_when_set(self):
        self.assertNotIn('location', self.options())
        self.assertEqual(
            self.options(DJANGO_DOCUMENT_STORAGE_LOCATION='/shared/')['location'],
            'shared',
        )


class CredentialTests(SimpleTestCase):
    def options(self, **overrides):
        return config(**{**AZURE, **overrides})['OPTIONS']

    def test_no_secret_means_a_managed_identity(self):
        """What App Service should use: nothing to rotate, nothing in a setting."""
        options = self.options()
        self.assertIs(options['token_credential'], CREDENTIAL)
        self.assertNotIn('account_key', options)

    def test_an_account_key_is_used_in_preference_to_an_identity(self):
        # An explicitly configured secret must never be silently ignored.
        options = self.options(DJANGO_DOCUMENT_STORAGE_ACCOUNT_KEY='secret')
        self.assertEqual(options['account_key'], 'secret')
        self.assertNotIn('token_credential', options)

    def test_a_sas_token_is_used_when_there_is_no_key(self):
        options = self.options(DJANGO_DOCUMENT_STORAGE_SAS_TOKEN='sv=2024')
        self.assertEqual(options['sas_token'], 'sv=2024')
        self.assertNotIn('token_credential', options)

    def test_a_key_wins_over_a_sas_token(self):
        options = self.options(
            DJANGO_DOCUMENT_STORAGE_ACCOUNT_KEY='secret',
            DJANGO_DOCUMENT_STORAGE_SAS_TOKEN='sv=2024',
        )
        self.assertEqual(options['account_key'], 'secret')
        self.assertNotIn('sas_token', options)

    def test_a_connection_string_replaces_the_account_and_the_key(self):
        options = self.options(
            DJANGO_DOCUMENT_STORAGE_CONNECTION_STRING='DefaultEndpointsProtocol=https;...'
        )
        self.assertEqual(
            options['connection_string'], 'DefaultEndpointsProtocol=https;...'
        )
        self.assertNotIn('account_name', options)
        self.assertNotIn('token_credential', options)

    def test_a_connection_string_alone_needs_no_account_name(self):
        options = config(
            DJANGO_DOCUMENT_STORAGE_CONTAINER='consumer-collective',
            DJANGO_DOCUMENT_STORAGE_CONNECTION_STRING='DefaultEndpointsProtocol=https;...',
        )['OPTIONS']
        self.assertIn('connection_string', options)


class RefusalTests(SimpleTestCase):
    def test_a_container_with_no_account_is_refused(self):
        with self.assertRaises(ImproperlyConfigured) as caught:
            config(DJANGO_DOCUMENT_STORAGE_CONTAINER='consumer-collective')
        self.assertIn('DJANGO_DOCUMENT_STORAGE_ACCOUNT', str(caught.exception))

    def test_a_cdn_path_that_is_not_the_container_is_refused(self):
        """The misconfiguration whose only other symptom is every link 404ing."""
        with self.assertRaises(ImproperlyConfigured) as caught:
            config(**{**AZURE, 'DJANGO_CDN_BASE_URL': 'https://qa-static.urup.com/wrong'})
        message = str(caught.exception)
        self.assertIn('wrong', message)
        self.assertIn('consumer-collective', message)

    def test_a_deep_cdn_path_is_refused(self):
        with self.assertRaises(ImproperlyConfigured):
            config(
                **{
                    **AZURE,
                    'DJANGO_CDN_BASE_URL': (
                        'https://qa-static.urup.com/consumer-collective/documents'
                    ),
                }
            )

    def test_plain_http_is_refused_outside_debug(self):
        with self.assertRaises(ImproperlyConfigured) as caught:
            config(
                **{
                    **AZURE,
                    'DJANGO_CDN_BASE_URL': 'http://qa-static.urup.com/consumer-collective',
                }
            )
        self.assertIn('https', str(caught.exception))

    def test_plain_http_is_allowed_in_debug(self):
        options = config(
            **{
                **AZURE,
                'DJANGO_CDN_BASE_URL': 'http://localhost:10000/consumer-collective',
                'debug': True,
            }
        )['OPTIONS']
        self.assertEqual(options['custom_domain'], 'localhost:10000')
        self.assertIs(options['azure_ssl'], False)

    def test_a_cdn_base_that_is_not_a_url_is_refused(self):
        for value in ('qa-static.urup.com', '/consumer-collective', 'ftp://host/x'):
            with self.assertRaises(ImproperlyConfigured):
                config(**{**AZURE, 'DJANGO_CDN_BASE_URL': value})

    def test_a_cdn_base_carrying_a_query_is_refused(self):
        with self.assertRaises(ImproperlyConfigured):
            config(
                **{
                    **AZURE,
                    'DJANGO_CDN_BASE_URL': (
                        'https://qa-static.urup.com/consumer-collective?sv=2024'
                    ),
                }
            )
