"""Endpoints for reading the current club documents and recording agreements.

``GET /api/documents/current`` is the one endpoint the sign-up page depends on,
and it is unauthenticated because sign-up happens before an account exists. It
either returns every required document at the revision in force, or it fails
with 503 -- never a partial list. A form rendering four of five documents
collects an agreement that is incomplete in a way nobody can see.

The two authenticated endpoints are the re-acceptance path: what this member
still owes, and the write that clears it. They exist so publishing a materially
changed document has somewhere to lead. The screen that uses them is not built.

Nothing here trusts the version the browser sends. ``resolve_submitted`` checks
each one against what is actually in force, because a revision can be published
between a page rendering and its form being submitted.
"""
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from app.core.storefronts.resolution import storefront_for_request
from ninja import Router
from ninja.errors import HttpError

from . import services
from .models import DocumentConsent
from .schemas import (
    AcceptConsentsIn,
    AcceptConsentsOut,
    DocumentsOut,
)

router = Router(tags=['documents'])


def _absolute_url(url, request):
    """A revision's address as an origin the browser can resolve.

    The Azure backend already returns an absolute URL, because the CDN host is
    part of it -- so this is a no-op in every deployed environment, and the
    check is on the URL rather than on which backend is configured.

    The filesystem fallback returns a root-relative path instead (``/media/...``),
    and that path is not resolvable by the caller: the frontend is served from
    its own origin, so a relative address resolves against the Next.js dev
    server and 404s there while the file sits happily on Django. Absolutised
    against this request, which is the only thing that knows the API's own
    origin.
    """
    if not url or urlsplit(url).netloc:
        return url
    return request.build_absolute_uri(url)


def _serialise(version, request):
    """One revision as the frontend reads it.

    Built by hand rather than resolved from the model, so the payload is
    visible in one place. ``url`` comes from the storage backend, which is what
    makes the CDN host configuration rather than markup.
    """
    return {
        'document': version.document.slug,
        'title': version.document.title,
        'version': version.label,
        'url': _absolute_url(version.url, request),
        'consent_text': version.consent_text,
        'sha256': version.sha256,
        'requires_reacceptance': version.requires_reacceptance,
        'effective_from': version.effective_from,
    }


@router.get('/published', response=DocumentsOut, auth=None)
def published_documents(request):
    """Every document on this storefront that anybody may read.

    The market's legal pages, and the club's rules — both readable without an
    account, because sign-up already has to show them before one exists.
    Producer agreements are excluded: neither public nor read at sign-up.

    **Scoped by host.** There is no session here and there cannot be one, so the
    storefront comes from the domain the request arrived on. See
    ``app.core.storefronts.resolution``, which is the same question the passkey RP ID
    has to answer.
    """
    revisions = services.published_documents(storefront_for_request(request))
    return {'documents': [_serialise(revision, request) for revision in revisions]}


@router.get('/current', response=DocumentsOut, auth=None)
def current_documents(request):
    """Every document a joining member must agree to, at the live revision.

    503 rather than an empty list when a required document has no published
    revision: the caller's only correct response is to refuse the form, and a
    200 with a short list does not say so. That is the one thing this does
    differently from ``/published`` above, and the reason the two are separate
    endpoints rather than one with a flag.

    Scoped by host, like ``/published``.
    """
    try:
        revisions = services.current_revisions(storefront_for_request(request))
    except services.DocumentsNotReady as error:
        raise HttpError(503, str(error))
    return {'documents': [_serialise(revision, request) for revision in revisions]}


@router.get('/outstanding', response=DocumentsOut)
def outstanding_documents(request):
    """Revisions this member has yet to agree to.

    Empty for a member who is up to date. Non-empty after a revision is
    published with ``requires_reacceptance`` set, which is what a re-acceptance
    gate would read.
    """
    revisions = services.outstanding_for(
        request.user, storefront_for_request(request)
    )
    return {'documents': [_serialise(revision, request) for revision in revisions]}


@router.post('/accept', response={200: AcceptConsentsOut})
def accept_documents(request, payload: AcceptConsentsIn):
    """Record this member's agreement to the revisions they were shown.

    Idempotent: agreeing twice to the same revision keeps the first row and its
    original timestamp. A submission naming a superseded version is refused
    with 409 rather than upgraded to the current one -- the member ticked a box
    beside text they were shown, and recording that against a revision
    published since would attribute an agreement to a document they never read.
    """
    submitted = [
        {'document': entry.document, 'version': entry.version}
        for entry in payload.consents
    ]
    try:
        versions = services.resolve_submitted(
            submitted, storefront_for_request(request)
        )
    except services.DocumentsNotReady as error:
        raise HttpError(503, str(error))
    except ValidationError as error:
        raise HttpError(409, ' '.join(error.messages))

    services.record_consents(
        request.user, versions, source=DocumentConsent.Source.REACCEPTANCE
    )

    recorded = DocumentConsent.objects.for_user(request.user).filter(
        version__in=versions
    )
    return {
        'recorded': [
            {
                'document': consent.version.document.slug,
                'version': consent.version.label,
                'accepted_at': consent.accepted_at,
            }
            for consent in recorded
        ],
        'outstanding': [
            _serialise(revision, request)
            for revision in services.outstanding_for(
                request.user, storefront_for_request(request)
            )
        ],
    }
