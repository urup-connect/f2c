"""Which server an email leaves by, the address it leaves as, and whose name is on it.

**One question, asked in one place.** Every email this platform sends belongs to
exactly one storefront, and three things follow from that answer: the SMTP
server, the ``From`` address, and the name in the subject and the signature. They
have to agree. A sign-in code sent through the store's provider but signed
"Cultivators Collective" is worse than either mistake alone -- it looks like a
phishing attempt, which is precisely what a member is taught to distrust about a
one-time code.

So callers do not choose a mailer. They say which storefront the message is for
and this module resolves all three, the same way ``resolution`` is the one place
that turns a host into a storefront and ``webauthn.rp_id`` the one place that
turns a storefront into a relying party.

**Storefront is optional everywhere.** A caller with no request -- a management
command, a cron job, a shell -- gets ``DEFAULT_STOREFRONT`` rather than having to
invent one, which is the same accommodation ``rp_id`` makes and the reason a
single-storefront deployment needs no new configuration.

**What decides the storefront.** For anything reached over HTTP it is the host
the request arrived on, through ``storefront_for_request`` -- not the member's
memberships. A sign-in code has to be sendable to an address with no account at
all, so there is nothing else to ask; and a member of both storefronts signing in
at the store should be answered by the store. For mail that is inherently one
storefront's business -- the club's membership subscription, say -- the caller
names it outright, because the host is then merely where the request happened to
land.
"""
from django.conf import settings
from django.core.mail import EmailMessage

from .models import Storefront
from .resolution import default_storefront

__all__ = ['brand_for', 'from_email_for', 'mailer_for', 'send_storefront_email']


def _resolved(storefront):
    """A known storefront, always. Falls back to the deployment's default.

    The fallback is ``resolution.default_storefront`` rather than a second copy
    of it: a caller with no request and a request on an unmapped host are the
    same situation, and they must not land in different places.
    """
    if storefront in Storefront.values:
        return storefront
    return default_storefront()


def mailer_for(storefront=None):
    """The ``MAILERS`` alias one storefront sends through.

    The alias *is* the storefront code -- see the MAILERS block in settings --
    so this is a validation step rather than a lookup. It is still a function:
    ``.send(using=...)`` on a value that came from a request needs something to
    reject an unmapped storefront before it becomes a ``MailerDoesNotExist``
    halfway through a sign-in.
    """
    return _resolved(storefront)


def from_email_for(storefront=None):
    """The address one storefront's mail is sent as.

    ``MAILERS`` has no per-mailer sender, so this comes from
    ``STOREFRONT_FROM_EMAIL`` and is applied per message. A storefront with
    nothing configured falls back to ``DEFAULT_FROM_EMAIL``, which only happens
    in local development -- settings refuses a blank one otherwise.
    """
    mapping = getattr(settings, 'STOREFRONT_FROM_EMAIL', None) or {}
    return mapping.get(_resolved(storefront)) or settings.DEFAULT_FROM_EMAIL


def brand_for(storefront=None):
    """The name a storefront calls itself in an email.

    Taken from ``Storefront.choices`` rather than held as its own setting, so the
    subject line, the signature and the Django admin can never disagree about
    what a storefront is called.
    """
    return Storefront(_resolved(storefront)).label


def send_storefront_email(*, storefront, subject, body, to):
    """Send one message as, and through, one storefront. Blocking.

    Returns the number of messages sent, as ``EmailMessage.send`` does.

    Blocking on purpose: both callers are async views that already push the send
    into a worker thread, and burying a thread hop in here would hide it from the
    place that has to reason about it.
    """
    return EmailMessage(
        subject=subject,
        body=body,
        from_email=from_email_for(storefront),
        to=to,
    ).send(using=mailer_for(storefront))
