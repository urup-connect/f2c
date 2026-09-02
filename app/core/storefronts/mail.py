"""Which server an email leaves by, the address it leaves as, whose name is on it -- and, since the queue, *when*.

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
message. Nothing else in this project constructs an ``EmailMessage``, which is
what makes that log complete rather than merely well-intentioned, and it is why
the function asks for a ``kind`` and a member instead of a subject and a list of
addresses.

Sending is two halves now
-------------------------

**A send no longer happens where it is asked for.** ``send_storefront_email``
composes the message, writes the ``EmailDispatch`` row and publishes one task;
:func:`deliver` is the other half, and it runs in a Celery worker off the
``mail`` queue. What that changed, and why it was worth changing:

**The mail server was in the request path, and a mail server is not ours.** The
sign-in endpoint held an SMTP conversation before it answered -- a ten-second
socket timeout against a provider having a bad afternoon, inside a request a
member is waiting on, on the one path into an account that has no passkey yet.
Sending from a worker means the endpoint answers on a database write, and a
provider that stops answering costs a queue that drains late instead of an
authentication outage.

**A failed send is now retried, which is the part the row could not do.** Before
this, a refused hand-over left ``FAILED`` and there it stayed: the member never
got the code, and the only recovery was asking them to request another. The
worker retries transport failures with backoff -- see :func:`transient` for
which failures those are, because retrying a ``550`` forever is not resilience.

**The caller stopped learning whether the mail went.** That is the real cost and
it is worth stating plainly: ``send_storefront_email`` returns once the message
is durably recorded, not once a server has taken it, so the sign-in endpoint
cannot answer 503 on a mail failure any more. It answers *"if that address
belongs to a member, a code is on its way"* -- which is what it said before,
deliberately, for reasons ``accounts.notifications`` sets out. The authoritative
answer to "did it go?" was always the ``EmailDispatch`` row rather than the
return value, and it still is.

**The message text travels through the database, not through the broker.**
``EmailDispatch.body`` carries that argument at length. In short: a task
argument sits in Redis in cleartext, and the two things worth stealing from this
platform's outbound mail are a sign-in code and a checkout token.

**Publishing is deferred to commit, always.** The worker reads the row by id, so
a task published before its own row commits is a task that finds nothing. Every
caller here already sends from ``transaction.on_commit`` for a related reason,
but the guard belongs where the mistake is possible rather than where it happens
not to be made -- so :func:`send_storefront_email` registers its own callback.
``transaction.on_commit`` runs it immediately in autocommit, which is what those
existing callers get.
"""
import logging
import smtplib

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction

from .models import EmailDispatch, Storefront
from .resolution import default_storefront

__all__ = [
    'EmailDispatch',
    'asend_storefront_email',
    'brand_for',
    'deliver',
    'from_email_for',
    'mailer_for',
    'send_storefront_email',
    'transient',
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

    **Read at hand-over rather than at composition**, which is now a different
    moment. If an account's address changes between the two, the message goes to
    the address the account holds when it is actually sent. That is the right way
    round: the row names the member and never an address, so sending to a stale
    copy of one would make the log point at a message the member never received.
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


def transient(error):
    """Whether ``error`` is worth trying the same message against again.

    **This is the whole difference between a retry policy and a nuisance.** A
    mail server that is not answering will answer later, and retrying is the
    point of putting sends on a queue at all. A mail server that said *550 no
    such user* has given a final answer, and retrying it five times over twenty
    minutes achieves nothing except five entries in somebody's abuse log -- and,
    where the refusal is per-recipient, five deliveries of the same sign-in code
    if one of the attempts does land.

    So the classification follows the server's own verdict where there is one,
    and treats everything below the SMTP conversation as transport:

    * **A response code decides it.** 4xx is SMTP's own "try later"; 5xx is
      permanent. That one rule covers an authentication failure (``535``, not
      retried -- credentials do not fix themselves), a refused sender, an
      over-quota mailbox (``452``, retried) and a rejected message body.
    * **A refusal carrying no code is transport**, not a verdict.
      ``SMTPConnectError`` and ``SMTPServerDisconnected`` arrive with nothing or
      with a zero, because no server got far enough to judge the message.
    * **Per-recipient refusals go by their own codes.** Every recipient here is
      one address off one account, so "are they all 4xx" is a question about a
      single answer.
    * **An HTTP status, for the ESP backend that is not configured yet.**
      Anymail raises with a ``status_code``; ``429`` and 5xx are its transport
      equivalents. Four lines, and the alternative is discovering at
      provider-switch time that every rate-limit response had been treated as a
      permanent bounce. Duck-typed rather than imported, because the dependency
      is not installed.
    * **Anything else is not retried.** A ``TypeError`` from a template or a
      misconfigured backend alias is a bug, and a bug retried five times is the
      same bug with a longer log.

    :param error: the exception a hand-over raised.
    :returns: ``True`` where the same message should be attempted again.
    """
    code = getattr(error, 'smtp_code', None)
    if isinstance(error, smtplib.SMTPResponseException) and code:
        return 400 <= code < 500

    if isinstance(error, smtplib.SMTPRecipientsRefused):
        codes = [response[0] for response in (error.recipients or {}).values()]
        return bool(codes) and all(400 <= each < 500 for each in codes)

    status = getattr(error, 'status_code', None)
    if isinstance(status, int):
        return status == 429 or 500 <= status < 600

    # `smtplib.SMTPException` subclasses `OSError`, as do `socket.timeout`,
    # `ssl.SSLError` and every `ConnectionError`. Reached only after the checks
    # above, so a coded 5xx has already been ruled permanent by the first of
    # them rather than swept in here.
    return isinstance(error, OSError)


def _hand_over(*, storefront, subject, body, address):
    """Build one message, send it, and report what came back. **No database.**

    Kept free of the ORM on purpose, and that separation is what let the whole
    hand-over move into a worker without the row-writing having to follow it
    there.

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


def _swallow(description):
    """Log a dispatch update that could not be written, and carry on.

    The send has already happened by the time this runs -- successfully or not
    -- so the outcome of this write must not change the outcome the caller sees.
    :func:`deliver` says why that is the right way round here and the wrong way
    round for the row's creation.
    """
    logger.exception(
        'storefronts.mail: an email was sent but its dispatch record could not '
        'be %s. The send stands; the tracking row is now wrong.',
        description,
    )


def deliver(dispatch, *, final=False):
    """Hand one recorded message to a mail server. **This is the worker's half.**

    ``dispatch`` is a row :func:`send_storefront_email` wrote, holding
    everything the hand-over needs except the address, which is read off the
    account now rather than then -- see :func:`_address_for`.

    :param dispatch: the :class:`~app.core.storefronts.models.EmailDispatch` to
        send, still ``QUEUED``.
    :param final: whether this is the last attempt that will be made. Decided by
        the caller, because only the task knows how many retries are left, and
        it is what turns a transport failure into ``FAILED`` rather than into a
        row left waiting for an attempt that is never coming.
    :returns: ``True`` where a mail server took the message.
    :raises Exception: whatever the hand-over raised, re-raised once the row has
        been updated, so that the task can retry on it and the worker log gets a
        traceback. The row is always written first. **An account with no address
        is the exception**: it is recorded as failed and ``False`` returned,
        because there is nothing a retry could fix -- see the branch itself.

    **A row that is already sent is not sent again.** ``task_acks_late`` is off
    for this task precisely so a redelivery cannot duplicate a send, but the
    guard costs one comparison and covers what that setting does not: a task
    published twice, or an operator replaying one by hand.

    **The two failure paths run in opposite directions, deliberately.** Failing
    to *write the row* raises, because a log with holes in it is worse than a
    send that was refused. Failing to *update the row after a successful send*
    is swallowed into the application log, because the message is already in the
    hands of a mail server and raising would invite Celery to retry the task --
    a second sign-in code, or a second suspension notice, over a bookkeeping
    fault.
    """
    if dispatch.send_status == EmailDispatch.SendStatus.SENT:
        logger.warning(
            'storefronts.mail: dispatch %s has already been sent; not sending '
            'it again. Its task was delivered more than once.',
            dispatch.pk,
        )
        return True

    try:
        address = _address_for(dispatch.recipient, dispatch.kind)
    except ValueError as error:
        # **A failure mode the queue created, and one the caller cannot cover.**
        # `send_storefront_email` checks the address before it writes the row,
        # so a caller that never asked whether there was anybody to write to is
        # caught there. This is the other case: the account held an address when
        # the message was composed and holds none now, because POPIA erasure ran
        # in between. Composing and sending used to be one statement, and there
        # was no "in between" for this to happen in.
        #
        # Settled rather than re-raised, and settled rather than retried.
        # Waiting will not restore an erased address, and a row left on `queued`
        # would sit in `pending()` forever -- which is the query that means "no
        # worker is consuming the mail queue", the one outage nothing else on
        # this platform reports. A single un-sendable message must not be able
        # to look like that.
        #
        # `mark_failed` also clears the body, which is the right end for a
        # sign-in code addressed to an account that has been erased.
        logger.warning(
            'storefronts.mail: dispatch %s cannot be sent -- account %s holds '
            'no email address. Erased between composing and sending; recorded '
            'as failed.',
            dispatch.pk,
            dispatch.recipient_id,
        )
        try:
            dispatch.mark_failed(error)
        except Exception:
            _swallow('marked as failed')
        return False

    dispatch.note_attempt()

    try:
        sent, message_id = _hand_over(
            storefront=dispatch.storefront,
            subject=dispatch.subject,
            body=dispatch.body,
            address=address,
        )
    except Exception as error:
        retrying = transient(error) and not final
        try:
            if retrying:
                dispatch.note_retry(error)
            else:
                dispatch.mark_failed(error)
        except Exception:
            # Named apart, because the two leave the row in different states and
            # only one of them is recoverable. A `note_retry` that did not write
            # costs an attempt count and an error message; the next attempt
            # still happens. A `mark_failed` that did not write leaves a row on
            # `queued` that nothing will ever settle -- which is the state that
            # makes `pending()` lie about whether a worker is running.
            _swallow('updated for a retry' if retrying else 'marked as failed')
        raise

    try:
        if sent:
            dispatch.mark_sent(provider_message_id=message_id)
        else:
            # `send()` returning 0 without raising means the backend was asked
            # not to complain -- `fail_silently`, or a backend with the same
            # habit of its own. Nothing went out, so the row must not say it
            # did, and there is nothing to retry on: a backend that declines
            # silently has given no error to classify.
            dispatch.mark_failed('the mail backend reported nothing sent')
    except Exception:
        _swallow('updated')

    return bool(sent)


def _enqueue(dispatch_id):
    """Publish the send task for ``dispatch_id``, once its row has committed.

    ``transaction.on_commit`` rather than a bare ``delay()``: the worker looks
    the row up by id, so publishing inside an open transaction is publishing a
    task that finds nothing. In autocommit -- which is where every current
    caller is, since they all send from ``on_commit`` themselves -- Django runs
    the callback immediately, so it costs those callers nothing.

    The task is imported here rather than at module scope because
    ``storefronts.tasks`` imports :func:`deliver` from this module. One of the
    two has to be deferred, and the cheaper one to defer is the import that runs
    once per send rather than the one that runs once per worker.
    """
    from .tasks import deliver_email

    transaction.on_commit(lambda: deliver_email.delay(str(dispatch_id)))


#: Publishing, off the event loop. ``thread_sensitive=True`` on purpose, and it
#: is the opposite of the call it replaced: ``on_commit`` registers against
#: *this* connection's transaction, so it has to run on the thread that owns it.
#: What made the old ``thread_sensitive=False`` necessary -- a ten-second SMTP
#: timeout holding the shared executor thread -- went with the send itself. What
#: is left is a local Redis publish, or, where no broker is configured, the
#: whole task run inline.
_enqueue_in_thread = sync_to_async(_enqueue, thread_sensitive=True)


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
    """Compose one message as one storefront, record it, and queue it for sending.

    Returns the :class:`~app.core.storefronts.models.EmailDispatch` the send
    will be made against -- the row is the useful thing to hand back, now that
    nothing here can know whether a mail server took the message. The module
    docstring says what that changed for callers.

    **Every send is recorded, because this is the only way to send**, and the
    row is now the hand-off as well as the record: :func:`deliver` reads it in a
    worker. A row this wrote that no worker ever collected stays ``QUEUED``,
    which is what ``EmailDispatch.objects.pending()`` is for.

    **A failure to write the row raises.** Nothing has been queued, the caller's
    error path is intact, and a member who was told nothing is a better outcome
    than a log claiming they were told. Every failure after that point belongs
    to the worker.

    :raises ValueError: where the account holds no address. Raised before the
        row, so that a caller who never asked ``notifications._addressee``'s
        question gets an error rather than a task that fails five times in a
        worker log.
    """
    storefront = _resolved(storefront)

    # Before the row, and deliberately the same check `deliver` makes against
    # the address it will actually send to. This one catches the programming
    # error -- a caller that never asked whether there was anybody to write to
    # -- and catching it here keeps it in that caller's traceback.
    _address_for(recipient, kind)

    dispatch = EmailDispatch.objects.queue(
        kind=kind,
        storefront=storefront,
        recipient=recipient,
        subject=subject,
        body=body,
        trigger=trigger,
        triggered_by=triggered_by,
    )
    _enqueue(dispatch.pk)
    return dispatch


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

    **Why there are still two of these.** The reason has changed and shrunk. It
    used to be that a send was an SMTP conversation plus three database writes,
    and wrapping the pair in ``sync_to_async`` put both on one thread with no
    right choice of thread available. The SMTP conversation is in a worker now
    and what is left is one ``INSERT`` and one publish -- so this exists for the
    ordinary reason an async twin exists: Django's async ORM wants awaiting, and
    the publish wants the connection-owning thread.
    """
    storefront = _resolved(storefront)
    _address_for(recipient, kind)

    dispatch = await EmailDispatch.objects.aqueue(
        kind=kind,
        storefront=storefront,
        recipient=recipient,
        subject=subject,
        body=body,
        trigger=trigger,
        triggered_by=triggered_by,
    )
    await _enqueue_in_thread(dispatch.pk)
    return dispatch
