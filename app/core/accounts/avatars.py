"""Turning whatever a member uploaded into the one image the club will store.

The browser crops before it uploads, so what arrives here is already square and
already small. None of that is trusted. This module exists on the assumption
that the upload came from something other than our own form, because eventually
one will.

**Every upload is decoded and re-encoded rather than stored as it arrived.**
That single decision does most of the work here:

* a file that is not an image is refused, rather than served back later with a
  content type we invented for it;
* a polyglot -- valid JPEG for a decoder, valid HTML for a browser -- loses the
  half that was not pixels, because only pixels survive a decode;
* EXIF goes, and with it the GPS coordinates of wherever the photograph was
  taken. A member uploading a picture of themselves is not consenting to hand
  the club their home address, and most of them do not know the file carries it;
* the output is one format at one size, so nothing downstream has to branch on
  what it is looking at.

The orientation tag is applied before it is discarded, which is the one piece of
EXIF that matters: a phone photograph is usually stored rotated with a tag
saying which way up it goes, and dropping the tag without acting on it turns
every portrait upload on its side.

Refusals are ``ValidationError``, in the member's own words, because the
endpoint above translates them straight into a 422 -- and because a member who
uploaded a 40MB RAW file should be told that rather than shown a failure.
"""
import io

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

#: The side of the square that is stored, in pixels. Retina-sharp at the 128px
#: the profile screen draws it at and at any avatar-sized use after that, and
#: small enough that the whole file is a single packet's worth of a few tens of
#: kilobytes. Bigger would be storing detail nothing renders.
AVATAR_SIZE = 512

#: What is stored, always. JPEG rather than PNG because a photograph is what
#: this is: a 512px PNG of a face is several times the bytes for no visible
#: difference, and rather than branch on the input every upload is flattened to
#: the same thing. Transparency is composited onto white on the way -- an avatar
#: is drawn on cards of more than one colour, and a transparent hole would show
#: whatever is behind it.
AVATAR_FORMAT = 'JPEG'
AVATAR_CONTENT_TYPE = 'image/jpeg'

#: Quality 85 with optimisation. Above this the file grows faster than it
#: improves; below it, skin tones band.
AVATAR_QUALITY = 85

#: The largest upload accepted, in bytes. Generous next to a 512px square,
#: because what arrives is a phone photograph the browser may not have managed
#: to shrink, and mean next to what a phone will happily upload untouched.
AVATAR_MAX_UPLOAD_BYTES = 8 * 1024 * 1024

#: The largest image accepted, in pixels per side. A decompression bomb is a
#: small file that decodes to an enormous bitmap, and Pillow reports the size
#: from the header before any of it is decoded -- so this is checked there, not
#: after. Pillow has its own global guard; this one is ours, it is a great deal
#: tighter, and it refuses in words a member can act on.
AVATAR_MAX_PIXELS_PER_SIDE = 10_000

#: What the decoders are allowed to be. Everything Pillow can read is a
#: potential parser, and a member's avatar has no business exercising the ones
#: for scientific formats or fax encodings.
AVATAR_ACCEPTED_FORMATS = frozenset({'JPEG', 'PNG', 'WEBP', 'HEIF', 'HEIC'})


def _refuse(message, code):
    raise ValidationError(message, code=code)


def normalise_avatar(data):
    """Return ``(bytes, content_type)`` for a square JPEG, or raise.

    Takes bytes rather than an ``UploadedFile`` so that it is a pure function
    with no file handles or storage in it, which is what makes every branch here
    testable from a few dozen bytes of fixture.

    The order of the checks is the order in which each becomes cheap to make:
    the byte length before anything is decoded, the header before any pixel is,
    and the decode itself last.
    """
    if not data:
        _refuse('Choose an image to upload.', 'avatar_empty')

    if len(data) > AVATAR_MAX_UPLOAD_BYTES:
        _refuse(
            'That image is larger than {} MB. Choose a smaller one.'.format(
                AVATAR_MAX_UPLOAD_BYTES // (1024 * 1024)
            ),
            'avatar_too_large',
        )

    try:
        # Opened twice, deliberately. `Image.open` is lazy: this first pass
        # reads the header only, which is what makes the size check below a
        # check on a claim rather than on a bitmap already in memory.
        with Image.open(io.BytesIO(data)) as probe:
            image_format = (probe.format or '').upper()
            width, height = probe.size
    except UnidentifiedImageError:
        _refuse('That file is not an image the club can read.', 'avatar_unreadable')
    except Exception:
        # Pillow raises a wide family for a truncated or malformed file, and
        # every one of them means the same thing to a member.
        _refuse('That image could not be read. It may be damaged.', 'avatar_damaged')

    if image_format not in AVATAR_ACCEPTED_FORMATS:
        _refuse(
            'That image is a {} file. Upload a JPEG, PNG or WebP.'.format(
                image_format or 'unrecognised'
            ),
            'avatar_format',
        )

    if width > AVATAR_MAX_PIXELS_PER_SIDE or height > AVATAR_MAX_PIXELS_PER_SIDE:
        _refuse(
            'That image is {}x{} pixels, which is larger than the club '
            'accepts.'.format(width, height),
            'avatar_dimensions',
        )

    if width < 1 or height < 1:
        _refuse('That image has no picture in it.', 'avatar_empty')

    try:
        with Image.open(io.BytesIO(data)) as image:
            # Applies the EXIF orientation tag and drops it. Both halves
            # matter: without the first every portrait photograph from a phone
            # arrives on its side, and without the second the file keeps the
            # GPS coordinates it was taken at.
            image = ImageOps.exif_transpose(image)
            # Centre-cropped to a square before the resize rather than squashed
            # into one. The browser has already cropped, so for our own form
            # this is a no-op; for anything else, a face stays a face.
            square = ImageOps.fit(
                image,
                (AVATAR_SIZE, AVATAR_SIZE),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            flattened = _flatten(square)

            out = io.BytesIO()
            flattened.save(
                out,
                format=AVATAR_FORMAT,
                quality=AVATAR_QUALITY,
                optimize=True,
                # No EXIF, no ICC profile, no comment. Whatever the source
                # carried, what is stored carries nothing.
                exif=b'',
            )
    except ValidationError:
        raise
    except Exception:
        _refuse('That image could not be read. It may be damaged.', 'avatar_damaged')

    return out.getvalue(), AVATAR_CONTENT_TYPE


def _flatten(image):
    """RGB, with any transparency composited onto white.

    JPEG has no alpha channel, so something has to happen to a PNG's
    transparent corners. Left to Pillow they become black, which reads as a
    photograph taken in the dark rather than as a rounded avatar.
    """
    if image.mode in ('RGBA', 'LA') or (
        image.mode == 'P' and 'transparency' in image.info
    ):
        converted = image.convert('RGBA')
        canvas = Image.new('RGB', converted.size, (255, 255, 255))
        canvas.paste(converted, mask=converted.split()[-1])
        return canvas

    return image.convert('RGB') if image.mode != 'RGB' else image


def avatar_file(data):
    """The normalised image as a Django file, ready to assign to the field.

    The name is a placeholder: ``accounts.storage.avatar_upload_to`` discards it
    and writes one path per account. It is supplied because ``FileField``
    requires one, and it says what it is so that a name appearing anywhere is
    recognisably not a member's own file name.
    """
    content, _ = normalise_avatar(data)
    return ContentFile(content, name='avatar.jpg')
