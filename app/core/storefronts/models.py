"""Which storefront a thing belongs to, and who administers one.

Two storefronts sit on this platform: the members' cannabis club, and the public
produce market. ``design/verticals.md`` is the whole reasoning; this module is
the two records the rest of the code hangs off.

**A storefront is a column, not a table.** There are exactly two, adding a third
is a product decision rather than runtime data, and every row that carries one
carries exactly one -- a document belongs to the club or to the market and never
to both, by decision (``verticals.md`` section 6). That is the same shape as
``UserRole`` before it and gets the same treatment: choices for the form layer,
a check constraint for everything that walks past the form layer. A table would
buy a foreign key and cost a join on every scoped query, a seed migration, and
the question of what happens when somebody deletes a row.

``StorefrontStaff`` is the administrator of one storefront. It is deliberately
*not* a role on ``ClubMembership``: an administrator is not a member, pays no
subscription, and the market has administrators but no membership at all. See
C28 and C29.

**There is no UC tier here.** The platform operator is ``User.is_staff`` and
works in the Django admin -- C29. Nothing in this module grants that, and adding
a ``uc_admin`` storefront value would be the fifth-role mistake again.

``EmailDispatch`` is the third thing here, and it is here because ``mail`` is:
this app already owns which server a message leaves by and whose name is on it,
and the record of what happened to it belongs beside that rather than in a
fourth app that would have to import back. It is written by
``mail.send_storefront_email`` and by nothing else.
"""
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

__all__ = [
    'EmailDeliveryStatus',
    'EmailDispatch',
    'EmailKind',
    'EmailReadStatus',
    'EmailSendStatus',
    'EmailTrigger',
    'Storefront',
    'StorefrontStaff',
]


class Storefront(models.TextChoices):
    """The two shopfronts this platform serves.

    ``CLUB`` is Cultivators Collective: membership, subscription, age gate, and
    a plant owned by the member who bought it. ``MARKET`` is the produce market:
    no membership, no subscription, and fungible stock sold by quantity.

    The values are short and stable because they appear in storage paths --
    ``documents/<storefront>/<slug>/<label>/<file>`` -- and in the host-to-
    storefront resolution the unauthenticated endpoints need. Renaming one would
    move every document a member has already agreed to.
    """

    CLUB = 'club', 'Cultivators Collective'
    MARKET = 'market', 'Produce market'


class StorefrontStaffQuerySet(models.QuerySet):
    def for_storefront(self, storefront):
        return self.filter(storefront=storefront)

    def administrators_of(self, storefront):
        """The people who run one storefront, newest appointment last."""
        return self.for_storefront(storefront).order_by('appointed_at')


class StorefrontStaff(models.Model):
    """One person's appointment as an administrator of one storefront.

    Held as its own table rather than as a value on the membership because the
    two relationships are different: a club administrator runs the club without
    joining it, and a market administrator has nothing to join. Under the old
    single-column model an administrator was ``role='admin'`` on a ``User``
    whose status had to be ``ACTIVE``, which after the split would have meant
    issuing them a club membership they never pay for.

    One person may hold rows for both storefronts. That is the point of the
    split: a column could not say it.

    **Revocation deletes the row.** There is no ``revoked_at``, and the absence
    is deliberate rather than an oversight -- an appointment that has ended is
    not a fact the platform needs to reason about, and Django's admin
    ``LogEntry`` already records who removed it and when. That is a weaker audit
    than ``DocumentConsent`` keeps, and the difference is intended: a consent is
    evidence a member gave, and an appointment is bookkeeping the club did.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='storefront_appointments',
    )
    storefront = models.CharField(
        max_length=16,
        choices=Storefront.choices,
        db_index=True,
        help_text='Which storefront this person administers.',
    )

    # Who made the appointment. SET_NULL rather than PROTECT: an administrator
    # appointed by somebody who has since been erased is still an
    # administrator, and the appointment must not block that erasure. The
    # opposite call to `DocumentConsent.version`, and for the opposite reason --
    # there the pointed-at row *is* the meaning of the record, and here it is
    # provenance.
    appointed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='storefront_appointments_made',
        help_text='The platform operator who granted this. Blank once they are erased.',
    )
    appointed_at = models.DateTimeField(auto_now_add=True)

    objects = StorefrontStaffQuerySet.as_manager()

    class Meta:
        ordering = ('storefront', 'appointed_at')
        verbose_name = 'storefront administrator'
        verbose_name_plural = 'storefront administrators'
        constraints = [
            # One appointment per person per storefront. Appointing somebody
            # twice is not a second appointment, it is the same one.
            models.UniqueConstraint(
                fields=('user', 'storefront'),
                name='storefront_staff_once_per_storefront',
                violation_error_message=(
                    'This person already administers that storefront.'
                ),
            ),
            # `choices` is a form-level rule that a queryset `.update()` or a
            # data migration walks straight past, and the failure mode is quiet:
            # an unrecognised storefront is an appointment to nothing that no
            # scoped query will ever return. The same argument the old
            # `user_role_is_known` constraint made.
            models.CheckConstraint(
                condition=models.Q(storefront__in=Storefront.values),
                name='storefront_staff_storefront_is_known',
                violation_error_message=(
                    'That is not a storefront this platform serves.'
                ),
            ),
        ]

    @property
    def administers_club(self):
        """Whether this appointment is over the club rather than the market.

        Asked of the appointment by ``accounts.roles.permissions_for`` so that
        module needs no import from here and the dependency stays
        one-directional -- ``accounts`` is the app everything else depends on.
        """
        return self.storefront == Storefront.CLUB

    def __str__(self):
        return f'{self.user} — {self.get_storefront_display()} administrator'


class EmailKind(models.TextChoices):
    """Which of this platform's emails a send record is.

    Named for the message rather than for the template: the template may be
    split or renamed, and this value is written into rows that outlive it.
    Adding a member-facing email means adding a value here. There is no
    ``other``, deliberately -- an untypeable email is one nothing can report on,
    which defeats the log.

    Module level rather than nested inside ``EmailDispatch``, along with the four
    status enums below, because ``Meta.constraints`` cannot see a sibling nested
    class: a class body is not an enclosing scope. ``Storefront`` is where it is
    for the same reason. Each is aliased onto the model, so
    ``EmailDispatch.Kind`` is what callers use and nothing outside this module
    has to know the difference.
    """

    LOGIN_CODE = 'login_code', 'Sign-in code'
    PAYMENT_LINK = 'payment_link', 'Membership payment link'
    MEMBERSHIP_SUSPENDED = 'membership_suspended', 'Membership suspended'
    ACCESS_REVOKED = 'access_revoked', 'Platform access revoked'


class EmailTrigger(models.TextChoices):
    """What set a send off -- the "system or a person" question.

    ``EmailDispatch.triggered_by`` names the person where there is one, and this
    column is what stops a blank there being ambiguous. A sign-in code is
    requested by whoever typed the address, who is by definition not signed in:
    the request is a member's and the identity is unknown, which is ``MEMBER``
    with no ``triggered_by``. A suspension notice is an operator's, with the
    operator named. A scheduled job is ``SYSTEM``, where having nobody to name is
    the truth rather than a gap.
    """

    SYSTEM = 'system', 'The platform itself'
    MEMBER = 'member', 'The recipient'
    OPERATOR = 'operator', 'An operator'


class EmailSendStatus(models.TextChoices):
    """Whether a mail server took the message. The one stage SMTP reports.

    **``QUEUED`` means literally that now.** Before the queue it meant "an
    attempt is in flight and nobody knows how it went", which was a window of
    milliseconds and only ever seen on a row left behind by a process that died
    mid-send. It is now the ordinary state of every message between the request
    that composed it and the worker that hands it over -- normally a second or
    two, longer while a mail server is refusing connections and the send is
    being retried. ``attempts`` and ``send_error`` are what tell those two
    apart: a queued row with attempts against it is a send being retried.

    **``FAILED`` is terminal, and only the worker writes it.** A transport
    failure that will be tried again leaves the row ``QUEUED``; ``FAILED``
    means no further attempt will be made -- either the mail server refused the
    message outright, or the retries are exhausted. That is what makes
    ``failed()`` the queue an operator should actually be watching rather than a
    list of messages that are still on their way.
    """

    QUEUED = 'queued', 'Waiting to be handed over'
    SENT = 'sent', 'Accepted by the mail server'
    FAILED = 'failed', 'Refused by the mail server'


class EmailDeliveryStatus(models.TextChoices):
    """Whether it reached the mailbox, as reported by a provider.

    ``UNKNOWN`` is the default and, on an SMTP-only deployment, the permanent
    answer. It is a distinct statement from a bounce: nothing has said the
    message failed, and nothing has said it arrived.
    """

    UNKNOWN = 'unknown', 'Not reported'
    DELIVERED = 'delivered', 'Delivered'
    DEFERRED = 'deferred', 'Delayed, still trying'
    BOUNCED = 'bounced', 'Bounced'
    REJECTED = 'rejected', 'Rejected'
    COMPLAINED = 'complained', 'Reported as spam'


class EmailReadStatus(models.TextChoices):
    """Whether the message was opened, where that is tracked at all.

    Three values rather than two, and ``NOT_TRACKED`` is the important one: it
    says the platform did not ask, which is not the same as the member not
    opening it. Everything sent today is ``NOT_TRACKED`` -- see
    ``EmailDispatch.record_read``.
    """

    NOT_TRACKED = 'not_tracked', 'Not tracked'
    UNOPENED = 'unopened', 'Tracked, not opened yet'
    READ = 'read', 'Opened'


#: Provider event names, normalised, and what each one means for a dispatch.
#: The keys are this project's vocabulary rather than any one provider's --
#: Postmark says ``Delivery``, SES wraps the same word in an SNS envelope,
#: Mailgun says ``delivered`` -- so the webhook handler that eventually arrives
#: translates into these and nothing downstream has to know which provider is
#: in use. See ``EmailDispatch.apply_provider_event``.
PROVIDER_DELIVERY_EVENTS = {
    'delivered': EmailDeliveryStatus.DELIVERED,
    'deferred': EmailDeliveryStatus.DEFERRED,
    'bounced': EmailDeliveryStatus.BOUNCED,
    'rejected': EmailDeliveryStatus.REJECTED,
    'complained': EmailDeliveryStatus.COMPLAINED,
}


class EmailDispatchQuerySet(models.QuerySet):
    def for_recipient(self, user):
        """One member's mail. The support question this log exists to answer."""
        return self.filter(recipient=user)

    def of_kind(self, kind):
        return self.filter(kind=kind)

    def failed(self):
        """Never left the building, and never will. See ``EmailSendStatus``."""
        return self.filter(send_status=EmailSendStatus.FAILED)

    def pending(self):
        """Composed and not yet handed over -- on the queue, or being retried.

        Fresh rows here are the normal state of a message in flight. Rows that
        stay is the signal that matters: no worker is consuming the ``mail``
        queue, and nothing else on this platform will say so.
        """
        return self.filter(send_status=EmailSendStatus.QUEUED)

    def unconfirmed(self):
        """Accepted by a mail server and never heard of again.

        Every sent row on an SMTP-only deployment, and that is the point of the
        name: *sent* is not *delivered*, and a report that treats them as the
        same thing tells somebody a message arrived when nothing knows that.
        """
        return self.filter(
            send_status=EmailSendStatus.SENT,
            delivery_status=EmailDeliveryStatus.UNKNOWN,
        )

    def queued_before(self, cutoff):
        """Older than ``cutoff`` by when the send was attempted.

        By ``queued_at`` rather than ``sent_at`` so that a failed or interrupted
        send ages too -- see ``purge_email_dispatches``.
        """
        return self.filter(queued_at__lt=cutoff)

    def by_provider_message(self, message_id):
        """The dispatch a provider's webhook is talking about, or ``None``.

        A blank id is refused rather than matched. Nothing sets one today -- the
        SMTP backend has none to give -- so a blank lookup would otherwise match
        an untracked row and stamp a delivery onto the wrong message.
        """
        message_id = (message_id or '').strip()
        if not message_id:
            return None
        return self.filter(provider_message_id=message_id).first()

    def _queued_values(self, *, kind, storefront, recipient, subject, body,
                       trigger, triggered_by):
        """The row a send is about to be attempted against.

        Shared by ``queue`` and ``aqueue`` so the two cannot drift. The subject
        is truncated rather than allowed to raise: it is descriptive, not
        load-bearing, and losing the tail of one is better than failing a
        sign-in over it. The body is not truncated -- it is the message.
        """
        limit = EmailDispatch._meta.get_field('subject').max_length
        return {
            'kind': kind,
            'storefront': storefront,
            'recipient': recipient,
            'subject': subject[:limit],
            'body': body,
            'trigger': trigger,
            'triggered_by': triggered_by,
        }

    def queue(self, *, kind, storefront, recipient, subject, body, trigger,
              triggered_by=None):
        """Record an email, with its text, for a worker to hand over.

        Written *before* the send and holding the message itself, which is what
        makes the row the hand-off between the request that composed the email
        and the worker that sends it. ``EmailDispatch.body`` says why the text
        travels through this table rather than through the broker, and why it
        does not stay here.
        """
        return self.create(
            **self._queued_values(
                kind=kind,
                storefront=storefront,
                recipient=recipient,
                subject=subject,
                body=body,
                trigger=trigger,
                triggered_by=triggered_by,
            )
        )

    async def aqueue(self, *, kind, storefront, recipient, subject, body,
                     trigger, triggered_by=None):
        """:meth:`queue` for a caller on the event loop. See ``mail``."""
        return await self.acreate(
            **self._queued_values(
                kind=kind,
                storefront=storefront,
                recipient=recipient,
                subject=subject,
                body=body,
                trigger=trigger,
                triggered_by=triggered_by,
            )
        )


class EmailDispatch(models.Model):
    """One email this platform sent to one member, and what became of it.

    **Why this table exists.** "Did the member get their sign-in code?" was
    answerable only from a mail server's logs, which nobody operating the club
    has access to and which the provider keeps for as long as it pleases. The
    same question is asked of a suspension notice, where the answer decides
    whether somebody was properly told, and of a payment link, where it decides
    whether to phone them.

    **Three stages, three statuses, and two of them are honest about not
    knowing.** A send has three separable outcomes, and one column for all three
    would assert things this deployment cannot know:

    ``send_status``
        Did the mail server accept it. The only stage plain SMTP reports, and
        genuinely known.
    ``delivery_status``
        Did it reach the mailbox. SMTP cannot say -- acceptance by a relay is
        not delivery -- so it stays ``unknown`` until a provider with webhooks
        is configured. See :meth:`apply_provider_event`.
    ``read_status``
        Did somebody open it. That needs a tracking pixel, which this platform
        deliberately does not embed, so it stays ``not_tracked``. A different
        statement from "not read", and the difference is the reason the value
        exists.

    **No email address is stored, by design.** Every email this platform sends
    goes to a member record, so ``recipient`` *is* the address: the log points at
    the account and the address is read off it at send time. POPIA erasure clears
    ``User.email`` and keeps the row -- ``design/backend.md`` section 5 -- so a
    send history de-identifies itself along with the account it belongs to and
    there is nothing here to scrub. It also makes one class of mistake
    impossible: nothing can log one member and write to another.

    **The body is stored only while the message is in flight; the subject
    always is.** A sign-in code and a payment token both live in the body, and a
    table operators read is not the place for either -- so ``body`` is written
    by the request that composes the email, read by the worker that sends it,
    and cleared in the same statement that records the outcome. A settled row
    holds no message text, ``email_dispatch_body_is_cleared_once_settled``
    enforces that in the database, and the column is not in any admin fieldset.
    ``body`` carries the reasoning.
    """

    # The choice sets live at module level -- `EmailKind` says why -- and are
    # aliased here so that callers write `EmailDispatch.Kind.LOGIN_CODE` and read
    # the model as though they were nested.
    Kind = EmailKind
    Trigger = EmailTrigger
    SendStatus = EmailSendStatus
    DeliveryStatus = EmailDeliveryStatus
    ReadStatus = EmailReadStatus

    id = models.UUIDField(primary_key=True, default=uuid.uuid7, editable=False)

    # No `db_index` on this or on `send_status`: the composite indexes in `Meta`
    # start with each of them, and a B-tree serves a prefix lookup, so a second
    # single-column index would be paid for on every insert and read by nothing.
    kind = models.CharField(
        max_length=32,
        choices=EmailKind.choices,
        help_text='Which of the platform’s emails this was.',
    )
    storefront = models.CharField(
        max_length=16,
        choices=Storefront.choices,
        db_index=True,
        help_text='Whose letterhead it carried, and whose server it left by.',
    )

    # CASCADE, as `authn.PasskeyCredential` does: a hard-deleted account takes
    # its send history with it. That path is rare -- POPIA erasure is
    # `soft_delete`, which keeps the row -- and it is the right answer, because
    # without the account there is nothing left to say who the mail went to.
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='emails_received',
        help_text='The account it was addressed to. The address is read off it.',
    )
    subject = models.CharField(
        max_length=255,
        help_text='The subject line as sent. Kept for the life of the row.',
    )

    # **The message text, and it is carriage rather than record.** A send is now
    # two processes: the request composes the email and a Celery worker hands it
    # to a mail server. Something has to carry the text between them, and the
    # two candidates were this column and the task payload.
    #
    # The task payload was rejected. A sign-in code and a checkout token are the
    # two things in this project's outbound mail worth stealing, and a task
    # argument sits in a Redis list in cleartext until a worker takes it --
    # readable by anything holding the broker key, and captured by any tooling
    # that inspects the queue. This column is inside MySQL, behind TLS, in the
    # database the rest of the platform's personal information already lives in,
    # and under the same access control.
    #
    # **It does not stay.** `SENT_FIELDS` and `FAILED_FIELDS` both include
    # `body`, and `_set_sent`/`_set_failed` blank it -- so the text exists for
    # the seconds between composing and sending, and a row an operator ever
    # reads has none. That keeps the standing decision intact: `EmailOtp` hashes
    # the code at rest, and a plaintext copy of it sitting in a send log for a
    # year would have undone that quietly. It is also why nothing purges this
    # column separately: it is empty long before the retention window matters.
    #
    # A row that dies `QUEUED` -- worker killed between the two writes -- keeps
    # its body, and that is correct: it is the one case where the message may
    # still need to go, and the retention purge collects it in due course.
    body = models.TextField(
        blank=True,
        help_text=(
            'The message text, held only until the send settles and then '
            'cleared. Empty on every row that has been sent or has failed.'
        ),
    )

    trigger = models.CharField(
        max_length=16,
        choices=EmailTrigger.choices,
        db_index=True,
        help_text='Whether the platform, the recipient, or an operator caused it.',
    )
    # SET_NULL rather than CASCADE, for the reason `StorefrontStaff.appointed_by`
    # gives: this is provenance, and losing the operator must not lose the record
    # that the member was written to.
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='emails_triggered',
        help_text=(
            'The person who caused it, where one can be named. Blank for a '
            'system send and for a request that was not signed in.'
        ),
    )

    send_status = models.CharField(
        max_length=16,
        choices=EmailSendStatus.choices,
        default=EmailSendStatus.QUEUED,
    )

    # How many times a mail server has been asked to take this message. Zero
    # while it waits on the queue, one for the overwhelming majority of rows.
    # It exists because `send_error` holds only the most recent failure, and
    # "refused once and then accepted" and "refused four times and then
    # accepted" are the same row without this -- the first is a blip and the
    # second is a mail provider an operator should be looking at.
    attempts = models.PositiveSmallIntegerField(
        default=0,
        help_text='How many times a mail server has been asked to take it.',
    )

    queued_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the mail server accepted it. Not when it arrived.',
    )
    send_error = models.TextField(
        blank=True,
        help_text='Why the mail server refused it, as it was reported.',
    )

    delivery_status = models.CharField(
        max_length=16,
        choices=EmailDeliveryStatus.choices,
        default=EmailDeliveryStatus.UNKNOWN,
        db_index=True,
    )
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            'When the delivery outcome was reported — an arrival or a '
            'bounce. Empty on an SMTP-only deployment, which is told neither.'
        ),
    )
    delivery_detail = models.TextField(
        blank=True,
        help_text='What the provider said, e.g. a bounce reason.',
    )

    read_status = models.CharField(
        max_length=16,
        choices=EmailReadStatus.choices,
        default=EmailReadStatus.NOT_TRACKED,
        db_index=True,
    )
    read_at = models.DateTimeField(null=True, blank=True)

    # The provider's own id for the message, and the join a webhook needs. Blank
    # under SMTP, which issues none. Indexed but not unique: blanks repeat, and a
    # `UniqueConstraint` over them would fail the second untracked send.
    provider_message_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text='The mail provider’s id for this message, where it gives one.',
    )

    objects = EmailDispatchQuerySet.as_manager()

    class Meta:
        ordering = ('-queued_at',)
        verbose_name = 'email sent'
        verbose_name_plural = 'emails sent'
        indexes = [
            # "What has this member been sent?" -- the support question, and the
            # only one asked often enough to earn a composite index.
            models.Index(
                fields=('recipient', '-queued_at'),
                name='email_dispatch_by_recipient',
            ),
            models.Index(
                fields=('kind', '-queued_at'), name='email_dispatch_by_kind'
            ),
            models.Index(
                fields=('send_status', '-queued_at'),
                name='email_dispatch_by_send_status',
            ),
        ]
        constraints = [
            # `choices` is a form-level rule and none of these rows come from a
            # form. The same argument `storefront_staff_storefront_is_known`
            # makes: an unrecognised value here is a row no report will ever
            # count, and nothing would have raised.
            models.CheckConstraint(
                condition=models.Q(kind__in=EmailKind.values),
                name='email_dispatch_kind_is_known',
                violation_error_message='That is not an email this platform sends.',
            ),
            models.CheckConstraint(
                condition=models.Q(storefront__in=Storefront.values),
                name='email_dispatch_storefront_is_known',
                violation_error_message=(
                    'That is not a storefront this platform serves.'
                ),
            ),
            # A status without its timestamp is the failure this table is most
            # likely to develop: a `mark_sent` that sets one field and not the
            # other reads as a send that happened at no time, and every report
            # over it drops the row without saying so.
            models.CheckConstraint(
                condition=(
                    ~models.Q(send_status=EmailSendStatus.SENT)
                    | models.Q(sent_at__isnull=False)
                ),
                name='email_dispatch_sent_has_a_timestamp',
                violation_error_message='A sent email has to say when it was sent.',
            ),
            # The message text does not outlive the send. Enforced here and
            # not merely in `_set_sent`/`_set_failed`, because the whole reason
            # `body` was allowed onto this table is that it is transient -- and
            # a future `save()` that settles a row without clearing it would
            # leave sign-in codes in a send log for a year with nothing raising.
            models.CheckConstraint(
                condition=(
                    models.Q(send_status=EmailSendStatus.QUEUED)
                    | models.Q(body='')
                ),
                name='email_dispatch_body_is_cleared_once_settled',
                violation_error_message=(
                    'A sent or failed email must not keep its message text.'
                ),
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(delivery_status=EmailDeliveryStatus.UNKNOWN)
                    | models.Q(delivered_at__isnull=False)
                ),
                name='email_dispatch_delivery_has_a_timestamp',
                violation_error_message=(
                    'A reported delivery outcome has to say when it was reported.'
                ),
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(read_status=EmailReadStatus.READ)
                    | models.Q(read_at__isnull=False)
                ),
                name='email_dispatch_read_has_a_timestamp',
                violation_error_message='An opened email has to say when.',
            ),
        ]

    def __str__(self):
        return f'{self.get_kind_display()} to {self.recipient} ({self.send_status})'

    #: The columns each ``mark_`` method writes. Named once so the sync and async
    #: forms of each cannot come to disagree about what they persist -- a
    #: mismatch there is the silent kind, leaving a status written and its
    #: timestamp not.
    #: Both settling methods write ``body`` -- see the field -- so the
    #: statement that records an outcome is the statement that erases the
    #: message text. Splitting those into two saves would leave a window in
    #: which a crash keeps the text against a settled row, which is the one
    #: state ``email_dispatch_body_is_cleared_once_settled`` forbids.
    SENT_FIELDS = (
        'send_status', 'sent_at', 'send_error', 'provider_message_id',
        'attempts', 'body',
    )
    FAILED_FIELDS = ('send_status', 'send_error', 'attempts', 'body')

    #: What a retry writes: the failure so far, and that another go was had. The
    #: status stays ``QUEUED`` and the body is deliberately **not** in this
    #: list -- the next attempt still needs the text to send.
    RETRY_FIELDS = ('send_error', 'attempts')

    def _set_sent(self, at, provider_message_id):
        self.send_status = EmailSendStatus.SENT
        self.sent_at = at or timezone.now()
        self.send_error = ''
        self.body = ''
        if provider_message_id:
            self.provider_message_id = str(provider_message_id)[:255]

    def _set_failed(self, reason):
        self.send_status = EmailSendStatus.FAILED
        self.send_error = str(reason)[:2000]
        self.body = ''

    def note_attempt(self):
        """Count an attempt about to be made, in memory. Nothing is saved.

        Called by ``mail.deliver`` immediately before the hand-over so that
        whichever of the three settling methods runs next persists the count as
        part of its own single statement. Incrementing in a save of its own
        would double the writes on the happy path for a number nothing reads
        until the send is over.
        """
        self.attempts += 1
        return self

    def mark_sent(self, *, at=None, provider_message_id=''):
        """The mail server took it. Records when, and the provider's id if any.

        Clears ``body`` in the same statement -- see the field.

        ``provider_message_id`` is blank under SMTP and populated by an ESP
        backend -- ``storefronts.mail`` is the one place that knows how to ask
        for it.
        """
        self._set_sent(at, provider_message_id)
        self.save(update_fields=list(self.SENT_FIELDS))
        return self

    async def amark_sent(self, *, at=None, provider_message_id=''):
        """:meth:`mark_sent` for a caller on the event loop."""
        self._set_sent(at, provider_message_id)
        await self.asave(update_fields=list(self.SENT_FIELDS))
        return self

    def mark_failed(self, reason):
        """The send is over and it did not go. **Terminal**, and it clears ``body``.

        Written when a mail server refused the message outright, and when the
        retries ran out. A failure that will be tried again is
        :meth:`note_retry` instead, because a row saying ``failed`` while a
        worker is still going to send it is the one thing that would make
        ``failed()`` useless to an operator.

        The reason is stored as text rather than an exception class, because what
        is useful six weeks later is "550 relay access denied" and the class name
        is ``SMTPRecipientsRefused`` for a dozen unrelated faults.
        """
        self._set_failed(reason)
        self.save(update_fields=list(self.FAILED_FIELDS))
        return self

    async def amark_failed(self, reason):
        """:meth:`mark_failed` for a caller on the event loop."""
        self._set_failed(reason)
        await self.asave(update_fields=list(self.FAILED_FIELDS))
        return self

    def note_retry(self, reason):
        """This attempt failed and another one is coming. Stays ``QUEUED``.

        Keeps the body, because the next attempt needs it, and records what went
        wrong so that a row being retried says why rather than merely sitting
        there. See :data:`RETRY_FIELDS`.
        """
        self.send_error = str(reason)[:2000]
        self.save(update_fields=list(self.RETRY_FIELDS))
        return self

    def record_delivery(self, status, *, at=None, detail=''):
        """A provider has reported what happened after the hand-over.

        Nothing calls this yet -- no provider is configured to report it. It is
        here now because the alternative is discovering at provider-switch time
        that the columns were the easy part.
        """
        self.delivery_status = status
        self.delivered_at = at or timezone.now()
        if detail:
            self.delivery_detail = str(detail)[:2000]
        self.save(
            update_fields=['delivery_status', 'delivered_at', 'delivery_detail']
        )
        return self

    def record_read(self, *, at=None):
        """Somebody opened it, as far as an open can be known.

        Unreachable while no tracking pixel is embedded, which is the standing
        decision -- an open beacon on a one-time code is surveillance of a
        security event, and Apple Mail's privacy proxy prefetches images anyway,
        so a fair share of the answers would be wrong in both directions. Kept
        because that decision is one template change away from being reversed,
        and this is where the reversal lands.
        """
        self.read_status = EmailReadStatus.READ
        self.read_at = at or timezone.now()
        self.save(update_fields=['read_status', 'read_at'])
        return self

    @classmethod
    def apply_provider_event(cls, message_id, event, *, at=None, detail=''):
        """Apply one normalised provider event. The whole of the future webhook.

        A provider webhook handler has three jobs: verify the signature, map the
        provider's event name onto a key of ``PROVIDER_DELIVERY_EVENTS`` or the
        literal ``'opened'``, and call this. Only the first two are
        provider-specific, which is why they are the only two left to write.

        Unknown events and unknown ids are ignored rather than raised on. Every
        provider sends events this platform has no use for, and a webhook that
        500s on one gets retried by the provider forever.

        :returns: the dispatch that was updated, or ``None``.
        """
        dispatch = cls.objects.by_provider_message(message_id)
        if dispatch is None:
            return None

        if event == 'opened':
            return dispatch.record_read(at=at)

        status = PROVIDER_DELIVERY_EVENTS.get(event)
        if status is None:
            return None
        return dispatch.record_delivery(status, at=at, detail=detail)
