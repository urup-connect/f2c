"""Which storefront a request is for.

The club and the produce market sit on separate registrable domains, so the
storefront a request belongs to is a property of the host it arrived on. Most
endpoints do not need to ask -- what they operate on already carries a
storefront, or a session says who is asking. **Two cannot ask anything else.**
``GET /documents/published`` and ``GET /documents/current`` are unauthenticated
by necessity: sign-up has to read the club's terms before an account exists, and
the market's privacy notice is a public page. There is no session to scope them
by, so the host is what is left.

This is the same question ``authn.webauthn.rp_id`` has to answer, and for the
same reason -- ``design/verticals.md`` section 8.

**Configuration, not a table.** ``DJANGO_STOREFRONT_HOSTS`` maps hosts to
storefront codes. A table would need a migration to add a QA domain, and the
hosts a deployment answers on are already environment configuration --
``ALLOWED_HOSTS``, ``CSRF_TRUSTED_ORIGINS`` and ``WEBAUTHN_ORIGINS`` are all
env-shaped for the same reason.

**An unmapped host falls back rather than refusing**, and the fallback is
configured. Refusing would take down local development, every preview
deployment and any health check that arrives on an IP address; serving the
default storefront's public documents to an unrecognised host discloses nothing
that is not already public. It is logged at warning outside DEBUG, because in a
deployed environment an unmapped host means the mapping is wrong.
"""
import logging

from django.conf import settings

from .models import Storefront

logger = logging.getLogger(__name__)

__all__ = ['default_storefront', 'storefront_for_host', 'storefront_for_request']


def _host_map():
    """``{host: storefront}``, lower-cased, from settings. Never ``None``."""
    return getattr(settings, 'STOREFRONT_HOSTS', None) or {}


def default_storefront():
    """Where anything unresolved lands. Never raises, never returns ``None``.

    Public because it is not only the host resolver that needs it. ``mail`` asks
    the same question for a caller with no request at all -- a management
    command, a shell -- and a second copy of this two-line fallback is a second
    place for a misconfigured ``DEFAULT_STOREFRONT`` to be handled differently.

    A ``DEFAULT_STOREFRONT`` naming no storefront falls back to the club rather
    than raising, for the reason in the module docstring: resolving a storefront
    must never be the thing that turns a served request into a 500.
    """
    configured = getattr(settings, 'DEFAULT_STOREFRONT', None)
    return configured if configured in Storefront.values else Storefront.CLUB


#: Retained as the module-private spelling the functions below already use.
_default = default_storefront


def storefront_for_host(host):
    """The storefront served on this host name.

    The port is stripped: a host header is ``example.com:8000`` in development
    and ``example.com`` in production, and a mapping that had to list both would
    be wrong in one environment or the other. IPv6 literals are left alone --
    they are bracketed, so the last colon is inside the brackets and stripping
    it would corrupt the address.
    """
    host = (host or '').strip().lower()
    if host.startswith('['):
        host = host.split(']', 1)[0] + ']'
    elif ':' in host:
        host = host.rsplit(':', 1)[0]

    if not host:
        return _default()

    mapped = _host_map().get(host)
    if mapped in Storefront.values:
        return mapped

    if not settings.DEBUG:
        # Warning rather than error: the request is served. What is wrong is the
        # deployment's configuration, and this is where somebody finds out.
        logger.warning(
            'storefronts: no storefront mapped for host %r; serving %s. Check '
            'DJANGO_STOREFRONT_HOSTS.',
            host,
            _default(),
        )
    return _default()


def storefront_for_request(request):
    """The storefront this request is for.

    ``get_host()`` rather than the raw header: Django has already validated it
    against ``ALLOWED_HOSTS`` by then, so a forged Host cannot name a storefront
    the deployment does not serve.
    """
    if request is None:
        return _default()
    try:
        host = request.get_host()
    except Exception:  # noqa: BLE001 - DisallowedHost, and anything like it
        # Unreachable behind ALLOWED_HOSTS, and handled rather than assumed
        # away: resolving a storefront must not be the thing that turns a
        # rejected host into a 500.
        return _default()
    return storefront_for_host(host)
