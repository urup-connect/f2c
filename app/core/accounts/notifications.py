"""Emails that tell somebody they cannot get in, and why.

**These exist because the sign-in endpoints deliberately will not say.**
``authn.api._find_user`` resolves an address through ``active_by_email``, which
filters to Active -- so a suspended account gets the same answer as a stranger,
*"if that address belongs to a member, a code is on its way"*, and no code
arrives. That vagueness is not an oversight: an endpoint that answered "your
account is blocked" would confirm to anybody typing addresses that this one
belongs to a member of a cannabis club, which is the disclosure the whole
authentication design is built to avoid.

So the sign-in screen stays vague and the explanation goes to the mailbox, which
only its owner reads. The same reasoning ``accounts.registration`` already uses
for a duplicate registration: the neutral screen, the informative email.

Two messages, because there are two different blocks and they are not
interchangeable:

``email_membership_suspended``
    The club has suspended a **club membership**. Club-branded, and it says the
    member area is closed -- not the platform, because it is not.
``email_access_revoked``
    An **account** has been barred from the platform, both storefronts. Sent as
    the account's home storefront, because a produce customer barred from the
    market should not receive a cannabis club's letterhead.

Both send on commit, and neither reports failure to its caller. See
``_deliver``.
"""
import logging

from django.db import transaction
from django.template.loader import render_to_string

from app.core.storefronts.mail import brand_for, send_storefront_email
from app.core.storefronts.models import Storefront

logger = logging.getLogger(__name__)


def _deliver(*, storefront, template, subject_template, email, name):
    """Render and send, blocking, swallowing a mail failure into the log.

    **The one place in this project that sends with the failure suppressed, and
    it is deliberate.** Everywhere else a send that raises should reach the
    caller: a sign-in code that did not send means the member cannot sign in, so
    a 503 is the truthful answer. Here the caller is an administrator who has
    just suspended somebody, and the suspension is already committed. Raising
    would fail the admin action after the block took effect -- telling the
    administrator it did not work when it did, and inviting them to do it again.

    A block that took effect and a member who was not told is the lesser
    failure, and it is recoverable: the log line names the account, and until
    ``P1`` configures a mail provider it is the *expected* outcome rather than an
    exception, because the console backend cannot reach anybody.
    """
    brand = brand_for(storefront)
    body = render_to_string(template, {'name': name, 'brand': brand})

    try:
        send_storefront_email(
            storefront=storefront,
            subject=subject_template.format(brand=brand),
            body=body,
            to=[email],
        )
    except Exception:
        logger.exception(
            'accounts: could not email %s about their access; the change itself '
            'stands. Somebody should tell them.',
            email,
        )


def _addressee(user):
    """``(email, name)``, or ``None`` where there is nobody to write to.

    An erased account has no address -- POPIA erasure removes it -- and a
    placeholder never had one. Both are reachable: an administrator can suspend
    a sharing member's identity, and ``erase`` leaves a row behind. Returning
    ``None`` rather than sending to an empty address is what keeps the caller
    from having to know that.
    """
    email = (user.email or '').strip()
    if not email:
        return None
    return email, user.get_short_name() or 'there'


def email_membership_suspended(user):
    """Tell ``user`` their club membership is on hold. Club-branded.

    :returns: ``True`` when a message was queued for after the commit.
    """
    addressee = _addressee(user)
    if addressee is None:
        logger.info(
            'accounts: membership suspended for account %s, which holds no '
            'email address; nobody was told.',
            user.pk,
        )
        return False

    email, name = addressee
    # On commit, for the reason `email_outstanding_checkout` gives: the
    # suspension is written inside a transaction, and telling somebody they are
    # suspended before the write that suspends them can still roll back is
    # telling them something that may not be true.
    transaction.on_commit(
        lambda: _deliver(
            storefront=Storefront.CLUB,
            template='emails/membership_suspended.txt',
            subject_template='Your {brand} membership is on hold',
            email=email,
            name=name,
        )
    )
    return True


def email_access_revoked(user, *, storefront=None):
    """Tell ``user`` their account can no longer sign in anywhere.

    ``storefront`` names the letterhead. Left to the default it is resolved by
    ``brand_for``, which is the right answer for the Django admin: the operator
    barring an account is not acting for one storefront.

    :returns: ``True`` when a message was queued for after the commit.
    """
    addressee = _addressee(user)
    if addressee is None:
        logger.info(
            'accounts: access revoked for account %s, which holds no email '
            'address; nobody was told.',
            user.pk,
        )
        return False

    email, name = addressee
    transaction.on_commit(
        lambda: _deliver(
            storefront=storefront,
            template='emails/account_access_revoked.txt',
            subject_template='Your {brand} access has been withdrawn',
            email=email,
            name=name,
        )
    )
    return True
