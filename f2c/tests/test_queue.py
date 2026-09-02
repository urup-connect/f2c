"""Which broker the queue connects to, and the refusals in between.

``broker_url`` is a pure function of a mapping, so all of this runs with no
Redis and no worker anywhere near it -- the same property that makes
``cache_config`` and ``database_config`` testable, and for the same reason: the
branches that matter are the ones that refuse.

**The test worth naming is ``test_a_deployed_environment_refuses_no_broker``.**
Eager execution is a correct fallback for one process and a silent catastrophe
for a deployment. With no broker, ``beat`` publishes into nothing, no worker
ever runs, and the three jobs that were the whole reason for this module simply
do not happen -- an unpaid membership keeps its access indefinitely and both
retention windows go unenforced. Nothing raises and nothing is logged, because
from Celery's point of view there is nothing wrong: the schedule is configured
and the tasks exist. So a deployed environment with no broker is an error rather
than a fallback, and this is the test that keeps it one.

The second is ``test_the_broker_is_not_the_cache_database``. Sharing a Redis
database between the throttle counters and the queue works right up until
somebody flushes it, and the two are flushed for completely different reasons --
resetting a rate-limit window costs nothing, and losing the queue loses whatever
was in it.
"""
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from ..queue import BROKER_DB, broker_url

TLS_URL = 'rediss://:key@f2c-cache.westeurope.redis.azure.net:10000/0'
PLAIN_URL = 'redis://localhost:6379/0'


class DevelopmentTests(SimpleTestCase):
    def test_no_configuration_at_all_means_eager(self):
        """A developer who has not started the container still has working code.

        Every task runs inline at the point it is called, which is also what
        keeps the whole suite runnable with no servers.
        """
        self.assertEqual('', broker_url({}))

    def test_a_redis_url_is_enough(self):
        """One variable configures the cache and the queue together."""
        self.assertTrue(broker_url({'DJANGO_REDIS_URL': PLAIN_URL}))

    def test_plaintext_is_allowed_in_development(self):
        """No key in the URL and no network to cross."""
        self.assertEqual(
            f'redis://localhost:6379/{BROKER_DB}',
            broker_url({'DJANGO_ENV': 'dev', 'DJANGO_REDIS_URL': PLAIN_URL}),
        )

    def test_an_unset_environment_is_development(self):
        self.assertEqual('', broker_url({'DJANGO_REDIS_URL': ''}))


class DerivationTests(SimpleTestCase):
    def test_the_broker_is_not_the_cache_database(self):
        """The assertion the whole derivation exists for.

        ``FLUSHDB`` on the cache is a rate-limit window reset and costs
        nothing. On the broker it is every queued task gone. They do not share
        a keyspace.
        """
        url = broker_url({'DJANGO_REDIS_URL': 'redis://redis:6379/0'})

        self.assertTrue(url.endswith(f'/{BROKER_DB}'))
        self.assertNotEqual('redis://redis:6379/0', url)

    def test_it_keeps_the_credentials_and_the_host(self):
        """Only the database index is rewritten. The access key travels in the
        URL, so losing any other part of it would produce a broker that cannot
        authenticate -- and a rewrite that dropped the key silently would look
        like a network fault."""
        url = broker_url({'DJANGO_ENV': 'qa', 'DJANGO_REDIS_URL': TLS_URL})

        self.assertEqual(
            f'rediss://:key@f2c-cache.westeurope.redis.azure.net:10000/{BROKER_DB}',
            url,
        )

    def test_it_keeps_a_query_string(self):
        """A managed instance's parameters live there."""
        url = broker_url({
            'DJANGO_REDIS_URL': 'redis://redis:6379/0?ssl_cert_reqs=none',
        })

        self.assertIn('?ssl_cert_reqs=none', url)

    def test_a_url_with_no_database_index_still_gets_one(self):
        url = broker_url({'DJANGO_REDIS_URL': 'redis://redis:6379'})

        self.assertEqual(f'redis://redis:6379/{BROKER_DB}', url)

    def test_an_explicit_broker_wins(self):
        """For the deployment that wants the queue on its own instance."""
        url = broker_url({
            'DJANGO_REDIS_URL': PLAIN_URL,
            'DJANGO_CELERY_BROKER_URL': 'redis://queue:6379/3',
        })

        self.assertEqual('redis://queue:6379/3', url)

    def test_a_non_redis_broker_is_left_alone(self):
        """Celery speaks AMQP too, and rewriting the path of an AMQP URL would
        silently change the virtual host."""
        url = broker_url({
            'DJANGO_REDIS_URL': 'amqp://guest:guest@rabbit:5672/f2c',
        })

        self.assertEqual('amqp://guest:guest@rabbit:5672/f2c', url)


class DeployedTests(SimpleTestCase):
    def test_a_deployed_environment_refuses_no_broker(self):
        """The one that matters. See the module docstring."""
        for environment in ('qa', 'prod'):
            with self.subTest(environment=environment):
                with self.assertRaises(ImproperlyConfigured) as raised:
                    broker_url({'DJANGO_ENV': environment})

                # The message has to name what breaks, not just what is
                # missing: "no broker configured" reads like a warning, and
                # "an unpaid membership keeps its access indefinitely" does not.
                self.assertIn('lapse_memberships', str(raised.exception))

    def test_it_refuses_plaintext(self):
        """The access key travels inside the URL."""
        with self.assertRaises(ImproperlyConfigured) as raised:
            broker_url({'DJANGO_ENV': 'prod', 'DJANGO_REDIS_URL': PLAIN_URL})

        self.assertIn('rediss://', str(raised.exception))

    def test_tls_is_accepted(self):
        self.assertTrue(
            broker_url({'DJANGO_ENV': 'prod', 'DJANGO_REDIS_URL': TLS_URL})
        )

    def test_plaintext_can_be_permitted_on_purpose(self):
        """CI, and the compose stack. Both run as ``qa`` so that they exercise
        the deployed backends, against a Redis on their own loopback with no key
        in the URL."""
        url = broker_url({
            'DJANGO_ENV': 'qa',
            'DJANGO_REDIS_URL': PLAIN_URL,
            'DJANGO_CACHE_ALLOW_PLAINTEXT': 'true',
        })

        self.assertEqual(f'redis://localhost:6379/{BROKER_DB}', url)

    def test_the_cache_switch_is_the_only_switch(self):
        """One deployment fact, one variable.

        A queue-specific opt-out could only fail by disagreeing with the
        cache's, and the shape of that failure is a stack with a TLS cache and
        a plaintext queue sending the same access key in clear. So the queue
        has no switch of its own, and a name invented for one does nothing.
        """
        with self.assertRaises(ImproperlyConfigured):
            broker_url({
                'DJANGO_ENV': 'prod',
                'DJANGO_REDIS_URL': PLAIN_URL,
                'DJANGO_QUEUE_ALLOW_PLAINTEXT': 'true',
            })

    def test_an_explicit_plaintext_broker_is_refused_too(self):
        """The override is not a way round the TLS rule."""
        with self.assertRaises(ImproperlyConfigured):
            broker_url({
                'DJANGO_ENV': 'prod',
                'DJANGO_REDIS_URL': TLS_URL,
                'DJANGO_CELERY_BROKER_URL': 'redis://queue:6379/1',
            })
