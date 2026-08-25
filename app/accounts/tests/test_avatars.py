"""Tests for the image pipeline: what it accepts, and what it throws away.

The interesting assertions here are all about what does *not* survive an upload,
because every one of them is invisible when it breaks. An avatar still renders
perfectly with the photographer's GPS coordinates attached to it, and a polyglot
file still renders perfectly as an image right up to the moment something serves
it as markup.

So the tests are mostly negative: no EXIF in the output, no HTML tail, no alpha
channel, one format, one size. ``test_orientation_is_applied_before_it_is_
dropped`` is the one that pairs with them -- dropping the tag without acting on
it would satisfy every other assertion in this file and turn every portrait
photograph from a phone on its side.
"""
import io

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from PIL import Image

from app.accounts import avatars


def png_bytes(size=(600, 400), colour=(120, 160, 90), mode='RGB'):
    """A real PNG, built rather than fixtured so the dimensions are the test's."""
    buffer = io.BytesIO()
    Image.new(mode, size, colour).save(buffer, format='PNG')
    return buffer.getvalue()


def jpeg_bytes(size=(600, 400), colour=(120, 160, 90), exif=None):
    buffer = io.BytesIO()
    image = Image.new('RGB', size, colour)
    if exif is None:
        image.save(buffer, format='JPEG')
    else:
        image.save(buffer, format='JPEG', exif=exif)
    return buffer.getvalue()


def opened(data):
    return Image.open(io.BytesIO(data))


class AcceptedInputTests(SimpleTestCase):
    def test_a_jpeg_becomes_a_square_jpeg_of_the_stored_size(self):
        content, content_type = avatars.normalise_avatar(jpeg_bytes())

        self.assertEqual(content_type, avatars.AVATAR_CONTENT_TYPE)
        image = opened(content)
        self.assertEqual(image.format, 'JPEG')
        self.assertEqual(
            image.size, (avatars.AVATAR_SIZE, avatars.AVATAR_SIZE)
        )

    def test_a_png_becomes_a_jpeg(self):
        # One stored format, whatever arrived. Nothing downstream branches on
        # what it is looking at.
        content, _ = avatars.normalise_avatar(png_bytes())

        self.assertEqual(opened(content).format, 'JPEG')

    def test_a_webp_is_accepted(self):
        buffer = io.BytesIO()
        Image.new('RGB', (500, 500), (10, 20, 30)).save(buffer, format='WEBP')

        content, _ = avatars.normalise_avatar(buffer.getvalue())

        self.assertEqual(opened(content).format, 'JPEG')

    def test_an_image_smaller_than_the_stored_size_is_scaled_up(self):
        # Upscaled rather than refused. A member with a small picture of
        # themselves has a picture of themselves, and one square at one size is
        # what lets every screen draw an avatar without measuring it.
        content, _ = avatars.normalise_avatar(jpeg_bytes(size=(64, 64)))

        self.assertEqual(
            opened(content).size, (avatars.AVATAR_SIZE, avatars.AVATAR_SIZE)
        )

    def test_a_wide_image_is_cropped_rather_than_squashed(self):
        # ImageOps.fit centre-crops. The alternative -- resize to a square --
        # would make every face on the platform slightly wrong in a way nobody
        # can name, which is worse than losing the edges of the frame.
        content, _ = avatars.normalise_avatar(jpeg_bytes(size=(1200, 300)))

        self.assertEqual(
            opened(content).size, (avatars.AVATAR_SIZE, avatars.AVATAR_SIZE)
        )

    def test_the_largest_accepted_dimensions_are_accepted(self):
        # The boundary itself, so the check is `>` and not `>=`. A 10000px side
        # is a legitimate photograph from a real camera.
        side = avatars.AVATAR_MAX_PIXELS_PER_SIDE
        content, _ = avatars.normalise_avatar(jpeg_bytes(size=(side, 1)))

        self.assertEqual(
            opened(content).size, (avatars.AVATAR_SIZE, avatars.AVATAR_SIZE)
        )


class DiscardedMetadataTests(SimpleTestCase):
    """What must not survive. Every one of these is silent when it regresses."""

    def test_exif_does_not_survive(self):
        source = Image.new('RGB', (400, 400), (200, 100, 50))
        exif = source.getexif()
        # 0x0110 is Model, 0x8825 the GPS pointer. A phone writes both, and a
        # member uploading a photograph of their face is not offering the club
        # the coordinates of wherever they took it.
        exif[0x0110] = 'A Phone'
        buffer = io.BytesIO()
        source.save(buffer, format='JPEG', exif=exif)

        self.assertIn(b'A Phone', buffer.getvalue())

        content, _ = avatars.normalise_avatar(buffer.getvalue())

        self.assertNotIn(b'A Phone', content)
        self.assertEqual(len(opened(content).getexif()), 0)

    def test_a_polyglot_loses_the_half_that_was_not_pixels(self):
        # A file that is a valid image to a decoder and valid markup to a
        # browser. Re-encoding is what defeats it: only pixels survive a decode.
        payload = b'<script>alert(1)</script>'
        content, _ = avatars.normalise_avatar(jpeg_bytes() + payload)

        self.assertNotIn(payload, content)

    def test_transparency_becomes_white_rather_than_black(self):
        # JPEG has no alpha, so something has to happen to a transparent
        # corner. Left to Pillow it becomes black, which reads as a photograph
        # taken in the dark rather than as a rounded avatar.
        source = Image.new('RGBA', (400, 400), (0, 0, 0, 0))
        buffer = io.BytesIO()
        source.save(buffer, format='PNG')

        content, _ = avatars.normalise_avatar(buffer.getvalue())

        image = opened(content)
        self.assertEqual(image.mode, 'RGB')
        self.assertEqual(image.getpixel((10, 10)), (255, 255, 255))

    def test_orientation_is_applied_before_it_is_dropped(self):
        """The tag goes, but only after it has been obeyed.

        A portrait photograph from a phone is usually stored landscape with a
        tag saying which way up it goes. Dropping the tag without acting on it
        satisfies every other assertion in this file and puts every such
        upload on its side.
        """
        # A landscape image with orientation 6: rotate 90 degrees clockwise.
        # The left half is red and the right half blue; after the rotation the
        # red half is at the top.
        source = Image.new('RGB', (400, 200), (0, 0, 255))
        source.paste(Image.new('RGB', (200, 200), (255, 0, 0)), (0, 0))
        exif = source.getexif()
        exif[0x0112] = 6
        buffer = io.BytesIO()
        source.save(buffer, format='JPEG', exif=exif, quality=100)

        content, _ = avatars.normalise_avatar(buffer.getvalue())

        image = opened(content)
        top = image.getpixel((avatars.AVATAR_SIZE // 2, 10))
        bottom = image.getpixel(
            (avatars.AVATAR_SIZE // 2, avatars.AVATAR_SIZE - 10)
        )
        # Compared loosely: JPEG is lossy and the resize interpolates, so the
        # assertion is "red above, blue below" rather than exact values.
        self.assertGreater(top[0], top[2])
        self.assertGreater(bottom[2], bottom[0])


class RefusalTests(SimpleTestCase):
    def refusal(self, data):
        with self.assertRaises(ValidationError) as caught:
            avatars.normalise_avatar(data)
        return caught.exception

    def test_nothing_at_all_is_refused(self):
        self.assertEqual(self.refusal(b'').code, 'avatar_empty')

    def test_a_file_that_is_not_an_image_is_refused(self):
        self.assertIn(
            self.refusal(b'this is a text file, not a photograph').code,
            {'avatar_unreadable', 'avatar_damaged'},
        )

    def test_a_truncated_image_is_refused_rather_than_half_decoded(self):
        self.assertIn(
            self.refusal(jpeg_bytes()[:120]).code,
            {'avatar_unreadable', 'avatar_damaged'},
        )

    def test_an_upload_over_the_byte_cap_is_refused_before_it_is_decoded(self):
        # Checked on the byte length, so a 40MB file costs nothing to refuse.
        oversized = b'\xff\xd8\xff' + b'\x00' * avatars.AVATAR_MAX_UPLOAD_BYTES

        error = self.refusal(oversized)

        self.assertEqual(error.code, 'avatar_too_large')
        self.assertIn('MB', error.messages[0])

    def test_a_decompression_bomb_is_refused_from_its_header(self):
        """A small file that decodes to an enormous bitmap.

        Pillow reports the size from the header before any of it is decoded,
        which is why this check is there and not after: refusing it afterwards
        means having already allocated the bitmap it was trying to make us
        allocate.
        """
        side = avatars.AVATAR_MAX_PIXELS_PER_SIDE + 1
        buffer = io.BytesIO()
        # A blank PNG of these dimensions compresses to a few kilobytes. Only
        # one side is oversized, deliberately: a square this wide would trip
        # Pillow's own global pixel guard, and what is under test is *our*
        # limit, which is a great deal tighter and refuses in words a member
        # can act on.
        Image.new('L', (side, 1000)).save(buffer, format='PNG')
        data = buffer.getvalue()

        self.assertLess(len(data), avatars.AVATAR_MAX_UPLOAD_BYTES)

        error = self.refusal(data)

        self.assertEqual(error.code, 'avatar_dimensions')
        self.assertIn(str(side), error.messages[0])

    def test_a_format_outside_the_accepted_set_is_refused_by_name(self):
        # Everything Pillow can read is a parser, and an avatar has no business
        # exercising the ones for scientific formats.
        buffer = io.BytesIO()
        Image.new('RGB', (100, 100)).save(buffer, format='BMP')

        error = self.refusal(buffer.getvalue())

        self.assertEqual(error.code, 'avatar_format')
        self.assertIn('BMP', error.messages[0])
        self.assertIn('JPEG', error.messages[0])


class AvatarFileTests(SimpleTestCase):
    def test_the_file_is_named_by_us_rather_than_by_the_member(self):
        # What a phone called the image tells us nothing and may contain
        # anything. `avatar_upload_to` discards the name too; this is the
        # belt to that braces.
        uploaded = avatars.avatar_file(jpeg_bytes())

        self.assertEqual(uploaded.name, 'avatar.jpg')
        self.assertEqual(opened(uploaded.read()).format, 'JPEG')

    def test_a_refused_image_produces_no_file(self):
        with self.assertRaises(ValidationError):
            avatars.avatar_file(b'not an image')
