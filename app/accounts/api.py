"""The endpoints a member's own profile screen reads and writes.

Five endpoints, all authenticated, all about ``request.user`` and nothing else.
There is no account identifier in any path here, which is deliberate: an endpoint
that takes one is an endpoint that has to decide whether the caller may act on
it, and the only correct answer for a profile is "only your own". Removing the
parameter removes the decision.

``GET /me/avatar`` is the reason this app has a router at all. The avatars store
is private and has no public address -- see ``accounts.storage`` -- so a
photograph has exactly one way out of it, and this is the view that checks the
session before a byte leaves. It is the only endpoint in the project that returns
something other than JSON.

Nothing here decides anything else. Every rule is in ``accounts.profile`` and
``accounts.avatars``, so each function is a translation of exceptions into status
codes and nothing more -- the same shape as ``membership.api``.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse
from django.utils.cache import patch_vary_headers
from ninja import File, Router
from ninja.errors import HttpError
from ninja.files import UploadedFile

from . import avatars, profile
from .schemas import ProfileIn, ProfileOut, ProfileRefusedOut
from .throttles import AvatarUploadThrottle, ProfileWriteThrottle

router = Router(tags=['accounts'])

#: How long a browser may keep an avatar it has fetched.
#:
#: A week, and safe at that length only because the address carries
#: ``?v=<avatar_updated_at>``: replacing a photograph changes the URL, so a
#: stale cache entry is never consulted again rather than being waited out.
#:
#: ``private`` is the part that matters. The response is the product of a session
#: check, so no shared cache -- proxy, CDN, anything -- may hold it. Paired with
#: ``Vary: Cookie`` below, which is what tells an intermediary that ignores
#: ``private`` that this varies per caller anyway.
AVATAR_CACHE_CONTROL = 'private, max-age=604800'


def _refusal(error):
    """A ``ValidationError`` as the refusal body, per field where it has one.

    Django puts field errors in ``message_dict`` and non-field ones in
    ``messages``; ``accounts.profile`` raises the former, ``accounts.avatars``
    the latter, and this endpoint answers both.
    """
    fields = getattr(error, 'message_dict', None) or {}
    return {
        'detail': ' '.join(error.messages),
        'fields': {field: list(messages) for field, messages in fields.items()},
    }


@router.get('/me/profile', response=ProfileOut)
def read_profile(request):
    """This member's own record, including the two fields they may only read.

    A GET of its own rather than more fields on ``/api/auth/me``, because two of
    the values here are not free: the masked identity number decrypts, and the
    avatar address is assembled. ``/auth/me`` is on the path of every signed-in
    page render; this is asked for by one screen.
    """
    return profile.profile_of(request.user)


@router.put(
    '/me/profile',
    response={200: ProfileOut, 409: ProfileRefusedOut, 422: ProfileRefusedOut},
    throttle=[ProfileWriteThrottle()],
)
def write_profile(request, payload: ProfileIn):
    """Replace the three editable fields, and return the whole profile.

    A PUT rather than a PATCH, matching ``ProfileIn``: the screen holds all three
    fields and sends all three, so behaviour does not depend on what a browser
    chose to omit.

    * **200** -- saved. The body is the record as it now stands, read back rather
      than echoed, so the member sees the normalised number they will be rung on
      instead of the punctuation they typed.
    * **409** -- the mobile number belongs to another account. One handset, one
      membership; see ``accounts.profile`` on why this refusal names itself here
      when registration's equivalent does not.
    * **422** -- a field is not acceptable, named field by field. The frontend
      refuses each of these first, so a member reaching one has bypassed the
      form or the two rule sets have drifted.
    """
    try:
        user = profile.update_profile(
            request.user,
            first_name=payload.first_name,
            last_name=payload.last_name,
            mobile=payload.mobile,
        )
    except profile.MobileUnavailable as refusal:
        return 409, {'detail': str(refusal), 'mobile_unavailable': True}
    except ValidationError as error:
        return 422, _refusal(error)
    except PermissionDenied as refusal:
        # 403 rather than 422: nothing about the submission is wrong. Reachable
        # only for an account that holds no permissions, which cannot hold a
        # session either -- so this is a floor, not a gate.
        raise HttpError(403, str(refusal))

    return 200, profile.profile_of(user)


@router.post(
    '/me/avatar',
    response={200: ProfileOut, 422: ProfileRefusedOut},
    throttle=[AvatarUploadThrottle()],
)
def upload_avatar(request, image: UploadedFile = File(...)):
    """Store a new photograph for this member, and return the whole profile.

    A POST rather than a PUT even though it replaces: Django does not parse a
    multipart body on PUT, and django-ninja's workaround for that is a global
    setting rather than a per-route one. A POST that replaces is a smaller
    surprise than a project-wide change to how request bodies are read.

    The bytes are read into memory in one go, which is what the size cap in
    ``accounts.avatars`` bounds -- and why that cap is checked on the byte length
    before anything is decoded. Django has already spooled anything large to a
    temporary file by this point, so the ceiling on memory is one image per
    concurrent upload, and the throttle bounds how many of those one account can
    have in flight.

    * **200** -- stored. The body carries the new ``avatar_url``, version and
      all, so the screen has an address that will not serve the previous
      photograph from cache.
    * **413** -- larger than Django's own request limit, which it refuses before
      this function runs.
    * **422** -- not a usable image: too large, not an image at all, a format the
      club does not decode, or damaged. ``accounts.avatars`` words each one.

    Whatever arrives is decoded and re-encoded rather than stored: EXIF and its
    GPS coordinates go, and a file that is valid JPEG to a decoder and valid
    markup to a browser loses the half that was not pixels. See that module.
    """
    try:
        data = image.read()
    except OSError:
        # A truncated upload. The connection dropped mid-body, which is neither
        # the member's fault nor something they can fix by choosing another file.
        raise HttpError(400, 'The upload did not finish. Try again.')

    try:
        user = profile.set_avatar(request.user, data)
    except ValidationError as error:
        return 422, _refusal(error)
    except PermissionDenied as refusal:
        raise HttpError(403, str(refusal))

    return 200, profile.profile_of(user)


@router.delete('/me/avatar', response=ProfileOut)
def delete_avatar(request):
    """Take this member's photograph down, and delete the stored image.

    Idempotent, and a 200 either way. An account with no photograph is already
    in the state the caller asked for, and a 404 would have a screen report a
    failure for having got what it wanted.
    """
    try:
        user = profile.clear_avatar(request.user)
    except PermissionDenied as refusal:
        raise HttpError(403, str(refusal))

    return profile.profile_of(user)


@router.get('/me/avatar', response=None)
def read_avatar(request):
    """Stream this member's photograph. The only way out of the avatars store.

    ``response=None`` so django-ninja returns the ``FileResponse`` untouched
    rather than trying to serialise it. This is the one endpoint in the project
    that answers with something other than JSON, and it exists because the
    alternative -- a public container, or a signed URL -- is an address that
    works without a session. A photograph of a member's face should not have one.

    * **404** -- no photograph on file. Not an error: the frontend asks only when
      ``avatar_url`` was non-null, so this is the narrow race where a member
      removed their picture in another tab.
    * **410** -- the column points at a blob storage does not have. A broken
      deployment or a half-finished migration rather than anything the member
      did, and said differently from 404 so the two are distinguishable in a log.

    The content type is stated rather than guessed. Every stored avatar is a JPEG
    because ``accounts.avatars`` produced it, so there is nothing to sniff -- and
    ``nosniff`` below means a browser will not try.
    """
    user = request.user

    if not user.has_avatar:
        raise HttpError(404, 'No photograph is on file for this account.')

    try:
        handle = user.avatar.open('rb')
    except FileNotFoundError:
        raise HttpError(
            410, 'The stored photograph is missing. Upload it again.'
        )

    response = FileResponse(
        handle,
        content_type=avatars.AVATAR_CONTENT_TYPE,
        # Never as an attachment. This is drawn in an `img` element, and a
        # `Content-Disposition` of attachment would have some browsers offer it
        # as a download instead.
        as_attachment=False,
        filename='avatar.jpg',
    )
    response['Cache-Control'] = AVATAR_CACHE_CONTROL
    # The response is the product of a session check, so it varies by caller even
    # though the path does not say so. Without this an intermediary that ignores
    # `private` could serve one member's photograph to the next caller.
    #
    # `patch_vary_headers` rather than an assignment: corsheaders adds `Origin`
    # to `Vary` on its way out, and a plain assignment here would be a race
    # between two pieces of middleware over which of them gets to be the whole
    # header. This adds to whatever is already there.
    patch_vary_headers(response, ('Cookie',))
    response['X-Content-Type-Options'] = 'nosniff'
    return response
