"""Loading stock, as a caller over HTTP reaches it.

``services`` is the validator and the write, shared by the management commands,
the admin's add form and this. It asks no permission question, deliberately: a
person with a shell on the application server has already passed every check
this project can make, and putting an authorisation call inside the one function
both entry points share would have ``manage.py upload_plants`` inventing a user
to satisfy it.

This module is the other half -- the same three operations with the question
asked -- and it exists rather than a check in ``api`` for the reason
``strains.services`` and ``membership.administration`` both give: a router that
authorised its own callers would be the only thing between one cultivator and
another's inventory, and a second caller (a Block 11 support handler acting on a
cultivator's request, a later bulk tool) would have nothing. ``api`` translates
what is raised here into status codes and does nothing else.

**Two questions, not one, and the second is the point.**
``platform.manage_plant_stock`` says whether this account loads stock at all.
It is granted by ``PRODUCER_BASE_PERMISSIONS`` to anybody appointed to any
producer, so on its own it would let somebody appointed to one farm load plants
into another's inventory -- exactly the thing ``spreadsheet``'s docstring says
must have no path. The catalogue cannot express "their own": ``permissions_for``
accumulates the sets across every appointment and says so in as many words.

So the object-level half is asked here, against the ``ProducerMembership`` rows,
which is where ``accounts.roles`` now says it belongs -- "answered by the same
appointment rows, in the service that owns the record". That was the half C13
recorded as having nothing to point at. It has something to point at now, and
this is the first service to use it.

**The producer is an argument, never a payload the caller is trusted on.** It is
checked against the caller's own appointments before anything is read or
written, so passing somebody else's identifier is a 403 rather than a load into
their greenhouse. When Block 9 gives a cultivator their own portal the session
will supply it and this check will still be the thing that makes that safe.

**A superuser passes the object question.** ``permissions_for`` already grants
them every codename, and refusing them on the second half would leave the
platform operator able to load stock for nobody at all while the Django admin
lets them do it anyway.
"""
from django.core.exceptions import PermissionDenied

from app.commerce.producers.models import ProducerMembership

from . import services

#: Named in ``accounts.roles`` as "Upload plant stock and adjust how many plants
#: are available", which is this module in one sentence.
MANAGE_STOCK = 'platform.manage_plant_stock'


def _authorise(user, cultivator):
    """Refuse a caller who may not load stock, or may not load *this* farm's.

    ``PermissionDenied`` rather than ``ValidationError``, matching
    ``strains.services._authorise``: nothing about the submission is wrong, the
    caller simply may not do this. Asked on the template download too -- it lists
    a cultivator's own strain offerings and what each is delivered as, which is
    their commercial position and not a public document.
    """
    if user is None or not user.has_perm(MANAGE_STOCK):
        raise PermissionDenied('This account may not load plant stock.')

    if user.is_superuser:
        return

    appointed = ProducerMembership.objects.filter(
        producer=cultivator, user=user
    ).exists()
    if not appointed:
        raise PermissionDenied(
            'This account is not appointed to that producer. Stock belongs to '
            'the farm, and only the people appointed to it may load any.'
        )


def capture(user, cultivator, **raw):
    """One plant, for a caller who may load stock for this producer.

    Raises ``PermissionDenied``, or ``ValidationError`` keyed by field. See
    ``services.capture_plant``.
    """
    _authorise(user, cultivator)
    return services.capture_plant(cultivator, **raw)


def upload(user, cultivator, source, *, dry_run=False):
    """A workbook of plants. Returns a ``services.UploadReport``.

    Raises ``PermissionDenied``, or ``spreadsheet.SheetError`` when the file is
    not a template at all. Row-level complaints come back on the report rather
    than as an exception -- see ``services.upload_plants``.
    """
    _authorise(user, cultivator)
    return services.upload_plants(cultivator, source, dry_run=dry_run)


def template_for(user, cultivator):
    """``(strain name, product types)`` pairs for this producer's template."""
    _authorise(user, cultivator)
    return services.template_reference(cultivator)
