"""Which cache the project connects to, and the refusals in between.

``cache_config`` is a pure function of a mapping, so all of this runs with no
Redis anywhere near it -- the same property that makes ``database_config``
testable, and for the same reason: the branches that matter are the ones that
refuse.

**The test worth naming is ``test_a_deployed_environment_refuses_locmem``.** The
quiet failure of a cache is not an outage. A per-process cache serves every
read and write correctly; it simply keeps its own copy. What that does to a rate
limit is multiply it by the number of processes -- so `otp/start`, published as
five sends an hour, becomes five per replica per hour, and the endpoint that
exists to stop the API being used to mailbomb a member does so five times less
well every time the platform scales out. Nothing raises, nothing is logged, and
the numbers in the settings file still say five. So a deployed environment with
no Redis is an error rather than a fallback.
"""
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from ..cache import (
    LOCMEM_BACKEND,
    REDIS_BACKEND,
    cache_config,
)

TLS_URL = 'rediss://:key@f2c-cache.westeurope.redis.azure.net:10000/0'
PLAIN_URL = 'redis://localhost:6379/0'


class DevelopmentTests(SimpleTestCase):
    def test_no_configuration_at_all_is_local_memory(self):
        """A developer who has not started the container still has a working
        application. One process, one set of counters."""
        config = cache_config({})

        self.assertEqual(config['BACKEND'], LOCMEM_BACKEND)

    def test_the_test_environment_is_local_memory(self):
        """What keeps the whole suite runnable with no servers."""
        config = cache_config({'DJANGO_ENV': 'test'})

        self.assertEqual(config['BACKEND'], LOCMEM_BACKEND)

    def test_the_local_container_is_used_when_it_is_named(self):
        """`compose.yaml` runs Redis on 6379. Pointing at it should reproduce
        the deployed backend, which is the point of running it at all."""
        config = cache_config({'DJANGO_ENV': 'dev', 'DJANGO_REDIS_URL': PLAIN_URL})

        self.assertEqual(config['BACKEND'], REDIS_BACKEND)
        self.assertEqual(config['LOCATION'], PLAIN_URL)

    def test_plaintext_is_allowed_in_development(self):
        """A container on localhost has no certificate and needs none."""
        config = cache_config({'DJANGO_ENV': 'dev', 'DJANGO_REDIS_URL': PLAIN_URL})

        self.assertEqual(config['LOCATION'], PLAIN_URL)

    def test_a_blank_url_is_the_same_as_none(self):
        config = cache_config({'DJANGO_ENV': 'dev', 'DJANGO_REDIS_URL': '   '})

        self.assertEqual(config['BACKEND'], LOCMEM_BACKEND)


class DeployedTests(SimpleTestCase):
    def test_qa_and_production_take_the_tls_url(self):
        for environment in ('qa', 'prod'):
            with self.subTest(environment=environment):
                config = cache_config({
                    'DJANGO_ENV': environment, 'DJANGO_REDIS_URL': TLS_URL
                })

                self.assertEqual(config['BACKEND'], REDIS_BACKEND)
                self.assertEqual(config['LOCATION'], TLS_URL)

    def test_a_deployed_environment_refuses_locmem(self):
        """The reason this module exists. See the module docstring."""
        with self.assertRaises(ImproperlyConfigured) as refused:
            cache_config({'DJANGO_ENV': 'prod'})

        message = str(refused.exception)
        self.assertIn('DJANGO_REDIS_URL', message)
        self.assertIn('mailbomb', message)

    def test_plaintext_is_refused_in_a_deployed_environment(self):
        """The access key travels in the URL, so redis:// puts it on the wire."""
        with self.assertRaises(ImproperlyConfigured) as refused:
            cache_config({'DJANGO_ENV': 'prod', 'DJANGO_REDIS_URL': PLAIN_URL})

        self.assertIn('rediss://', str(refused.exception))

    def test_the_refusal_names_the_environment(self):
        with self.assertRaises(ImproperlyConfigured) as refused:
            cache_config({'DJANGO_ENV': 'qa', 'DJANGO_REDIS_URL': PLAIN_URL})

        self.assertIn('qa', str(refused.exception))

    def test_a_scheme_that_merely_contains_rediss_is_not_enough(self):
        """`http://rediss.example.com` starts with neither scheme."""
        with self.assertRaises(ImproperlyConfigured):
            cache_config({
                'DJANGO_ENV': 'prod',
                'DJANGO_REDIS_URL': 'http://rediss.example.com:10000/0',
            })


class RedisOptionsTests(SimpleTestCase):
    def config(self):
        return cache_config({'DJANGO_ENV': 'prod', 'DJANGO_REDIS_URL': TLS_URL})

    def test_the_keys_are_namespaced(self):
        """QA and production may share an instance during a migration, and two
        environments incrementing each other's counters would tighten a rate
        limit for no reason anyone could trace."""
        self.assertEqual(self.config()['KEY_PREFIX'], 'f2c')

    def test_the_socket_timeouts_are_bounded(self):
        """django-ninja checks throttles synchronously from an async request
        path, so an unresponsive Redis must fail rather than hold the loop."""
        options = self.config()['OPTIONS']

        self.assertEqual(options['socket_connect_timeout'], 2)
        self.assertEqual(options['socket_timeout'], 2)


class PlaintextOptOutTests(SimpleTestCase):
    """CI runs as `qa` against a Redis container on the runner's loopback."""

    def test_plaintext_is_allowed_when_said_on_purpose(self):
        config = cache_config({
            'DJANGO_ENV': 'qa',
            'DJANGO_REDIS_URL': PLAIN_URL,
            'DJANGO_CACHE_ALLOW_PLAINTEXT': 'true',
        })

        self.assertEqual(config['BACKEND'], REDIS_BACKEND)
        self.assertEqual(config['LOCATION'], PLAIN_URL)

    def test_the_opt_out_accepts_the_usual_spellings(self):
        for spelling in ('1', 'true', 'TRUE', 'yes', 'on'):
            with self.subTest(spelling=spelling):
                config = cache_config({
                    'DJANGO_ENV': 'qa',
                    'DJANGO_REDIS_URL': PLAIN_URL,
                    'DJANGO_CACHE_ALLOW_PLAINTEXT': spelling,
                })
                self.assertEqual(config['LOCATION'], PLAIN_URL)

    def test_an_unrecognised_spelling_is_not_an_opt_out(self):
        """`DJANGO_CACHE_ALLOW_PLAINTEXT=maybe` must not read as "yes". It falls
        through to the refusal, which is the safe direction."""
        with self.assertRaises(ImproperlyConfigured):
            cache_config({
                'DJANGO_ENV': 'qa',
                'DJANGO_REDIS_URL': PLAIN_URL,
                'DJANGO_CACHE_ALLOW_PLAINTEXT': 'maybe',
            })

    def test_the_opt_out_does_not_excuse_a_missing_url(self):
        """It permits a scheme. It does not conjure a cache server."""
        with self.assertRaises(ImproperlyConfigured) as refused:
            cache_config({
                'DJANGO_ENV': 'prod', 'DJANGO_CACHE_ALLOW_PLAINTEXT': 'true'
            })

        self.assertIn('DJANGO_REDIS_URL', str(refused.exception))
