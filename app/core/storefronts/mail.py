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
memberships. The sign-in endpoint accepts any address and answers every one of
them the same way, so at the moment the storefront has to be chosen there is
nothing else to ask; and a member of both storefronts signing in at the store
should be answered by the store. For mail that is inherently one
storefront's business -- the club's membership subscription, say -- the caller
names it outright, because the host is then merely where the request happened to
land.

**And one more thing follows from being the one place: the record that it was
sent.** ``send_storefront_email`` writes an ``EmailDispatch`` row for every
message -- before the hand-over and again after it. Nothing else in this project
constructs an ``EmailMessage``, which is what makes that log complete rather than
merely well-intentioned, and it is why the function now asks for a ``kind`` and a
member instead of a subject and a list of addresses. ``EmailDispatch`` says what
can and cannot be known about a message once it has left, which on an SMTP-only
deployment is less than three timestamps suggest.
"""
import logging

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.mail import EmailMessage

from .models import EmailDispatch, Storefront
from .resolution import default_storefront

__all__ = [
    'EmailDispatch',
    'asend_storefront_email',
    'brand_for',
    'from_email_for',
    'mailer_for',
    'send_storefront_email',
]

logger = logging.getLogger(__name__)


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


def _address_for(recipient, kind):
    """The address to write to, off the account, or a ``ValueError``.

    **Off the recipient rather than from the caller**, so that nothing can log
    one member and send to another. Every email this platform sends goes to a
    member record -- a sign-in code is only issued for an account that exists, a
    suspension notice is about one -- so the account is the address, and there is
    no second source of truth to keep in step.

    An account holding no address is a programming error rather than a runtime
    condition: whether there is anybody to write to is the caller's question --
    ``notifications._addressee`` is the pattern -- and it is asked before this.
    """
    address = (getattr(recipient, 'email', '') or '').strip()
    if not address:
        raise ValueError(
            f'{kind} cannot be sent to account {getattr(recipient, "pk", None)}: '
            'it holds no email address. Whether there is anybody to write to is '
            "the caller's question, and it is asked before this."
        )
    return address


def _provider_message_id(message):
    """The provider's own id for a message just sent, or ``''``.

    Django's SMTP backend has none to give, so this is blank on every send
    today. An ESP backend -- Anymail's, for any of the providers -- hangs an
    ``anymail_status`` on the message after ``send()``, and its ``message_id``
    is what a delivery webhook will later quote. Read defensively, and in one
    place: it is the single line that has to exist for a provider switch to be
    configuration rather than a migration, and it must not raise on a backend
    that sets nothing.
    """
    status = getattr(message, 'anymail_status', None)
    if status is None:
        return ''
    return getattr(status, 'message_id', '') or ''


def _hand_over(*, storefront, subject, body, address):
    """Build one message, send it, and report what came back. **No database.**

    Kept free of the ORM on purpose. This is the only part of a send that talks
    to a mail server, so it is the only part worth pushing off the event loop --
    and a worker thread holds its own database connection, which must not be the
    thread that writes the dispatch row. ``asend_storefront_email`` is what that
    separation is for.

    :returns: ``(sent, provider_message_id)``. ``sent`` is falsy where the
        backend declined without raising.
    """
    message = EmailMessage(
        subject=subject,
        body=body,
        from_email=from_email_for(storefront),
        to=[address],
    )
    sent = message.send(using=mailer_for(storefront))
    return sent, _provider_message_id(message)


#: The SMTP hand-over, off the event loop, on a thread of its own.
#:
#: ``thread_sensitive=False`` for the reason ``otp`` gives about hashing: an
#: unreachable mail server holds this for the ten-second socket timeout, and
#: doing that on the shared main-thread executor would stall every other piece
#: of sync work in the process. It is safe here only because ``_hand_over``
#: touches no database -- a thread of its own means a database connection of its
#: own, which cannot see the transaction the request is running in.
_hand_over_in_thread = sync_to_async(_hand_over, thread_sensitive=False)


def _swallow(description):
    """Log a dispatch update that could not be written, and carry on.

    The send has already happened by the time any of these run -- successfully
    or not -- so the outcome of this write must not change the outcome the
    caller sees. ``send_storefront_email`` says why that is the right way round
    here and the wrong way round for the row's creation.
    """
    logger.exception(
        'storefronts.mail: an email was sent but its dispatch record could not '
        'be %s. The send stands; the tracking row is now wrong.',
        description,
    )


def send_storefront_email(
    *,
    storefront,
    kind,
    recipient,
    subject,
    body,
    trigger=EmailDispatch.Trigger.SYSTEM,
    triggered_by=None,
):
    """Send one message as, and through, one storefront, and record that it went.

    Returns the number of messages sent, as ``EmailMessage.send`` does.

    **Every send is recorded, because this is the only way to send.** The row is
    written before the hand-over and updated after it. ``EmailDispatch`` says
    what the three statuses mean and which two this deployment cannot fill in.

    **The two failure paths run in opposite directions, deliberately.** Failing
    to *write the row* raises: nothing has been sent, the caller's error path is
    intact, and a log with holes in it is worse than a send that was refused.
    Failing to *update the row after a successful send* is swallowed into the
    application log, because the message is already in the hands of a mail
    server and raising would invite the caller to send it again -- a second
    sign-in code, or a second suspension notice, over a bookkeeping fault.

    Blocking, and for a caller on an event loop that is the wrong function:
    ``asend_storefront_email`` is the same contract without the block. Both
    callers here reach this from ``transaction.on_commit``, which is ordinary
    synchronous code.
    """
    storefront = _resolved(storefront)
    address = _address_for(recipient, kind)

    dispatch = EmailDispatch.objects.queue(
        kind=kind,
        storefront=storefront,
        recipient=recipient,
        subject=subject,
        trigger=trigger,
        triggered_by=triggered_by,
    )

    try:
        sent, message_id = _hand_over(
            storefront=storefront, subject=subject, body=body, address=address
        )
    except Exception as error:
        try:
            dispatch.mark_failed(error)
        except Exception:
            _swallow('marked as failed')
        raise

    try:
        if sent:
            dispatch.mark_sent(provider_message_id=message_id)
        else:
            # `send()` returning 0 without raising means the backend was asked
            # not to complain -- `fail_silently`, or a backend with the same
            # habit of its own. Nothing went out, so the row must not say it did.
            dispatch.mark_failed('the mail backend reported nothing sent')
    except Exception:
        _swallow('updated')

    return sent


async def asend_storefront_email(
    *,
    storefront,
    kind,
    recipient,
    subject,
    body,
    trigger=EmailDispatch.Trigger.SYSTEM,
    triggered_by=None,
):
    """``send_storefront_email`` for a caller on the event loop.

    **Why there are two of these rather than one wrapped in ``sync_to_async``.**
    A send is now two different kinds of work: an SMTP conversation that can
    block for ten seconds, and three small database writes. Wrapping the whole
    thing puts both on one thread, and neither choice of thread is right --
    ``thread_sensitive=False`` gives that thread its own database connection,
    which cannot see the transaction the request is running in and deadlocks on
    a database that locks per table; ``thread_sensitive=True`` fixes that by
    serialising every send through the one shared executor thread, so a mail
    server that stops answering stalls unrelated sync work across the process.

    So the split is by kind of work rather than by convenience: the hand-over
    goes to a worker thread, and the ORM stays on the caller's connection where
    Django's async ORM can reach it.
    """
    storefront = _resolved(storefront)
    address = _address_for(recipient, kind)

    dispatch = await EmailDispatch.objects.aqueue(
        kind=kind,
        storefront=storefront,
        recipient=recipient,
        subject=subject,
        trigger=trigger,
        triggered_by=triggered_by,
    )

    try:
        sent, message_id = await _hand_over_in_thread(
            storefront=storefront, subject=subject, body=body, address=address
        )
    except Exception as error:
        try:
            await dispatch.amark_failed(error)
        except Exception:
            _swallow('marked as failed')
        raise

    try:
        if sent:
            await dispatch.amark_sent(provider_message_id=message_id)
        else:
            await dispatch.amark_failed(
                'the mail backend reported nothing sent'
            )
    except Exception:
        _swallow('updated')

    return sent
