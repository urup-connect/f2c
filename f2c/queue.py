"""Which broker the task queue talks to, read from an environment mapping.

The same shape as :mod:`f2c.cache` and :mod:`f2c.database`, and a pure function
of a mapping for the same reason: every branch and every refusal is testable
with no Redis and no worker anywhere near it.

**What the queue is for.** Two kinds of work, and the broker is the only thing
they have in common.

**The scheduled three, which is why this module exists.** Each is computed
rather than driven by an event, and none of them runs itself:
``lapse_memberships`` withdraws access from a membership that stopped paying,
and the two purges enforce the retention windows POPIA's retention principle
asks for. Until something schedules them, an unpaid membership keeps its access
indefinitely and a retention policy is a sentence in a settings file.

**And every outbound email, which was added afterwards.** This module used to
say that nothing in a request path was deferred to a worker. That is no longer
true and the change was deliberate: a send held an SMTP conversation inside the
request that asked for it, so a mail provider having a bad afternoon meant a
ten-second timeout on the sign-in path -- and a refused message got no second
attempt, on the one route into an account that has no passkey yet.
``app/core/storefronts/mail.py`` carries that argument in full.

**What it costs is a second queue, and the reason is the first kind of work.**
The purges are long delete passes and a worker runs one task at a time, so a
sign-in code sharing their queue at 01:05 waits behind them. ``mail`` and
``scheduled`` are separated in ``CELERY_TASK_ROUTES`` and the deployment runs a
worker for each.

**Why not the Function App.** ``design/todo.md`` carried a timer-triggered Azure
Function App calling a new protected endpoint on the API, and ``deploy.md`` 5.2
replaced it with a Container Apps Job. Both are a scheduler that lives outside
the application: the schedule is in platform configuration rather than in the
repository, a failed run is visible only in that platform's own logs, and
neither can be exercised locally or in CI. Celery moves all three into Django --
the schedule is ``CELERY_BEAT_SCHEDULE`` in ``settings.py`` and reviewed as
code, a run leaves a ``scheduling.ScheduledRun`` row readable in the admin, and
``compose.yaml`` runs the same worker a deployment runs. Redis is already here
for the throttle counters, so the broker costs no new managed service.

**The broker is a Redis database, not a cache.** It is derived from
``DJANGO_REDIS_URL`` with the database index moved off the cache's, so a
deployment configures one Redis and gets both -- see :data:`BROKER_DB`.
``DJANGO_CELERY_BROKER_URL`` overrides that outright, for the deployment that
wants the queue on its own instance.

**Two things below are not obvious.**

**No broker means eager, and that is a real fallback for one process.** A
developer who has not started the Redis container, and the whole test suite, run
every task inline at the point it is called -- which is what keeps the suite
runnable with no servers at all, exactly as ``LocMemCache`` does for the cache.
It carries more weight since email joined the queue than it did when only the
nightly jobs were here: inline is what makes a local sign-in work with no broker
and no worker process running.

What makes it safe is that it is refused in ``qa`` and ``prod``: eager there
would mean ``beat`` publishing to nothing, the three jobs silently never
running, and -- now -- every email sent from inside the request that composed
it, which is the block this project moved them out of.

**Plaintext is refused outside development through the cache's own switch.**
``DJANGO_CACHE_ALLOW_PLAINTEXT`` governs this too, deliberately, and it is not
read here because the name fits. It is one deployment fact -- *this Redis is on
the machine, carries no access key and crosses no network* -- and one variable,
the same call ``BEHIND_PROXY`` makes in ``settings.py``. A second switch could
only fail by disagreeing with the first, and the shape of that failure is a
stack with a TLS cache and a plaintext queue sending the same access key in
clear.
"""
from urllib.parse import urlsplit, urlunsplit

from django.core.exceptions import ImproperlyConfigured

#: Environments that require a real broker and refuse to start without one.
#: Mirrors ``cache.DEPLOYED`` and ``database.database_config``.
DEPLOYED = ('qa', 'prod')

#: The Redis database the broker gets when it is derived from the cache URL.
#:
#: Not the cache's. Celery's own keys are prefixed and would not collide, but
#: they share a keyspace with the throttle counters -- and the operations an
#: operator reaches for on each are incompatible. ``FLUSHDB`` on a cache is a
#: rate-limit window reset and costs nothing; on a broker it is every queued
#: task gone. Separating them means the blunt instrument stays safe to use.
BROKER_DB = 1

#: Azure Managed Redis serves TLS on 10000; Azure Cache for Redis served it on
#: 6380. Both are ``rediss``. Same pair as ``f2c.cache``.
TLS_SCHEME = 'rediss://'
PLAINTEXT_SCHEME = 'redis://'

#: What counts as "yes" in an environment variable, matching ``f2c.cache``.
TRUE_VALUES = frozenset({'1', 'true', 'yes', 'on'})


def broker_url(env):
    """The Celery broker URL, or ``''`` where there is no broker.

    An empty string is the instruction to run tasks eagerly -- see the module
    docstring -- and is only ever returned outside a deployed environment.

    :param env: a mapping, normally ``os.environ``.
    :raises ImproperlyConfigured: in ``qa`` or ``prod``, when no broker is
        configured or when the URL would carry an access key in cleartext.

    **The no-broker refusal below is a backstop, not the first line of
    defence.** Because the broker is derived from ``DJANGO_REDIS_URL``, the
    condition that would trigger it -- a deployed environment with no Redis at
    all -- is the same condition ``cache_config`` refuses, and ``CACHES`` is
    evaluated earlier in ``settings.py``. So in practice the cache's message is
    the one an operator reads. This one is still here for the two cases it
    covers on its own: a caller using this function directly, and a settings
    file that ever reads the queue before the cache.
    """
    environment = (env.get('DJANGO_ENV') or 'dev').strip().lower()

    explicit = (env.get('DJANGO_CELERY_BROKER_URL') or '').strip()
    url = explicit or _from_cache_url(env.get('DJANGO_REDIS_URL'))

    if environment not in DEPLOYED:
        # No Redis container running, or a test run. Tasks execute inline.
        return url

    if not url:
        raise ImproperlyConfigured(
            'No Celery broker is configured. A deployed environment needs one: '
            'every email this platform sends goes out through it, including '
            'the sign-in codes, and three scheduled jobs run through it -- the '
            'first of them, lapse_memberships, is what withdraws access from a '
            'membership that has stopped paying. Without a broker, beat '
            'publishes nowhere, no worker ever runs, no member can sign in '
            'without a passkey, and an unpaid membership keeps its access '
            'indefinitely with nothing in any log saying so. Set '
            'DJANGO_REDIS_URL, which the broker is derived from, or '
            'DJANGO_CELERY_BROKER_URL to put the queue on its own instance.'
        )

    allow_plaintext = (
        env.get('DJANGO_CACHE_ALLOW_PLAINTEXT') or ''
    ).strip().lower() in TRUE_VALUES

    if not url.startswith(TLS_SCHEME) and not allow_plaintext:
        raise ImproperlyConfigured(
            f'The Celery broker must use {TLS_SCHEME} in {environment}, not '
            f'{url.split("://")[0]}://. The access key travels inside this URL, '
            'so a plaintext connection either puts it on the wire in clear or '
            'is pointed at something that is not the managed instance. Azure '
            'Managed Redis serves TLS on port 10000. If this is a Redis on the '
            'machine itself with no key and no network to cross -- CI, or the '
            'compose stack -- set DJANGO_CACHE_ALLOW_PLAINTEXT=true and say so '
            'on purpose. That one variable governs the cache and the queue '
            'together because it describes one Redis.'
        )

    return url


def _from_cache_url(cache_url):
    """The cache's Redis URL with the database index moved to :data:`BROKER_DB`.

    Everything else is kept exactly as it arrived -- scheme, credentials, host,
    port, and any query string, which is where a managed instance's parameters
    live. Only the path is rewritten, because only the database index differs.

    A URL that is not Redis is returned untouched. Celery speaks to RabbitMQ and
    SQS as well, and a deployment that has pointed ``DJANGO_CELERY_BROKER_URL``
    at one of those does not reach here -- but a future caller might, and
    silently rewriting the path of an AMQP URL would break a virtual host.
    """
    url = (cache_url or '').strip()
    if not url:
        return ''

    parts = urlsplit(url)
    if parts.scheme not in ('redis', 'rediss'):
        return url

    return urlunsplit(parts._replace(path=f'/{BROKER_DB}'))
