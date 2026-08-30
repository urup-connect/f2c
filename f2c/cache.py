"""Which cache this project talks to, read from an environment mapping.

Redis when a URL names one, local memory when nothing does, and a refusal in
between -- the same shape as :mod:`f2c.database`, and a pure function of a
mapping for the same reason: every branch and every refusal is testable with no
cache server anywhere near it.

**This is not a performance setting.** Nothing in this project caches a query or
a rendered page. The only thing in the cache is the throttle counters behind
``auth/start``, ``otp/start``, ``otp/verify`` and ``passkey/verify``, and
``otp/start``'s limit is the only thing standing between the API and its use as
a mailbomb relay. A cache that is not shared is a rate limit multiplied by the
number of processes reading it, silently -- which is what ``LocMemCache`` was
doing per Uvicorn worker, and what it would do per container replica.

**Why Redis and not the database.** The database was tried and cannot serve
this. django-ninja checks throttles synchronously from inside
``AsyncOperation._run_checks``, every endpoint here is async, and
``DatabaseCache`` reaches the database through ``connection.cursor()``, which
Django decorates ``@async_unsafe`` -- so the first throttled request raises
``SynchronousOnlyOperation``. Redis does blocking *socket* I/O rather than ORM
I/O and carries no such decoration, so it is permitted where the database is
not. ``design/conflict.md`` C31 records the attempt.

**Two things below are not obvious.**

**``LocMemCache`` is the fallback and it is a real one, but only for one
process.** The test suite runs on it, which is what keeps the whole suite
runnable with no servers at all, and a developer who has not started the Redis
container gets it too. What makes that safe is that it is refused in ``qa`` and
``prod``: the failure it produces there is a rate limit that quietly does not
hold, and no log line anywhere says so.

**Plaintext Redis is refused outside development.** Azure Managed Redis speaks
TLS on port 10000 and the access key travels in the URL, so a ``redis://`` URL
in a deployed environment either sends that key in clear or is pointed at
something that is not the managed instance. Both are worth stopping at startup
rather than discovering later, and the check is one character wide: ``rediss``.
``DJANGO_CACHE_ALLOW_PLAINTEXT`` is the deliberate way out, for CI -- which runs
as ``qa`` so that it exercises the deployed backends, against a Redis container
on the runner's own loopback with no key in the URL and no network to cross. It
is spelled as a permission rather than as the absence of a setting, so that it
reads as a downgrade wherever it appears, the same call ``database.tls_options``
makes about ``DJANGO_DB_SSL_DISABLED``.
"""
from django.core.exceptions import ImproperlyConfigured

LOCMEM_BACKEND = 'django.core.cache.backends.locmem.LocMemCache'
REDIS_BACKEND = 'django.core.cache.backends.redis.RedisCache'

#: Environments that connect to a real cache server and refuse to start without
#: one. Mirrors ``database.database_config``.
DEPLOYED = ('qa', 'prod')

#: The TLS scheme. Azure Managed Redis serves it on 10000; Azure Cache for Redis
#: served it on 6380. Both are ``rediss``.
TLS_SCHEME = 'rediss://'
PLAINTEXT_SCHEME = 'redis://'

#: What counts as "yes" in an environment variable, matching ``f2c.database``.
TRUE_VALUES = frozenset({'1', 'true', 'yes', 'on'})


def cache_config(env):
    """The ``CACHES['default']`` entry, read from an environment mapping.

    :param env: a mapping, normally ``os.environ``.
    """
    environment = (env.get('DJANGO_ENV') or 'dev').strip().lower()
    url = (env.get('DJANGO_REDIS_URL') or '').strip()

    if environment not in DEPLOYED:
        if not url:
            # No Redis container running, or a test run. One process, one set of
            # counters, and the limits hold within it.
            return {'BACKEND': LOCMEM_BACKEND, 'LOCATION': 'f2c'}
        return _redis(url)

    if not url:
        raise ImproperlyConfigured(
            'DJANGO_REDIS_URL is not set. A deployed environment needs a cache '
            'every replica can see: the throttle counters live there, and a '
            'per-process cache turns every published rate limit into that '
            'limit multiplied by the replica count -- including the one on '
            'otp/start, which is what stops the API being used to mailbomb a '
            'member. QA and production use Azure Managed Redis; locally, run '
            'the container in compose.yaml and point this at it.'
        )

    allow_plaintext = (
        env.get('DJANGO_CACHE_ALLOW_PLAINTEXT') or ''
    ).strip().lower() in TRUE_VALUES

    if not url.startswith(TLS_SCHEME) and not allow_plaintext:
        raise ImproperlyConfigured(
            f'DJANGO_REDIS_URL must use {TLS_SCHEME} in {environment}, not '
            f'{url.split("://")[0]}://. The access key travels inside this URL, '
            'so a plaintext connection either puts it on the wire in clear or '
            'is pointed at something that is not the managed instance. Azure '
            'Managed Redis serves TLS on port 10000. If this is a cache on the '
            'machine itself with no key and no network to cross -- CI against a '
            'Redis container -- set DJANGO_CACHE_ALLOW_PLAINTEXT=true and say '
            'so on purpose.'
        )

    return _redis(url)


def _redis(url):
    """A Redis cache entry.

    ``KEY_PREFIX`` is set because QA and production may share an instance during
    a migration, and two environments incrementing each other's throttle
    counters would be a rate limit that tightens for no reason anyone could
    trace.
    """
    return {
        'BACKEND': REDIS_BACKEND,
        'LOCATION': url,
        'KEY_PREFIX': 'f2c',
        'OPTIONS': {
            # Bounded, because this connection is made from inside an async
            # request path: django-ninja checks throttles synchronously, so a
            # Redis that has stopped answering would otherwise hold the event
            # loop rather than fail the request.
            'socket_connect_timeout': 2,
            'socket_timeout': 2,
        },
    }
