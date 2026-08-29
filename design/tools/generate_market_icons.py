"""Generate the market storefront's app icons from the F2C store logo.

    python design/tools/generate_market_icons.py [output-dir]

Source: design/F2C_new_logo-removebg-preview - Edited 1.png, a 500x274 lossy render on an
opaque cream ground - the only form of the logo there is. Everything below works around that:
the crop boxes are measured off it rather than guessed, the ground is snapped flat because the
source's is not, and the small frames get a contrast boost because a 197px-wide mark has no
detail left to lose at 16px.

Writes the four files Next.js picks up from app/ by convention, plus the maskable PWA icon that
app/manifest.ts points at, in public/. Rerun it after replacing the source; nothing else
changes.
"""
import sys
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "design" / "F2C_new_logo-removebg-preview - Edited 1.png"
# Defaults to the app it exists for; an argument sends the output somewhere else to be looked
# at before it is installed.
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "frontend" / "market" / "app"
OUT.mkdir(parents=True, exist_ok=True)

CREAM = (240, 231, 216)          # #F0E7D8 - the logo's own ground

MARK = (152, 62, 351, 179)       # brown arc -> F2C + leaf -> baseline bar
TIGHT = (152, 76, 351, 167)      # letters + leaf only, for the 16px favicon frame
FULL = (140, 52, 362, 220)       # the whole lockup including both tagline lines


def flatten(img):
    """Snap the source's faintly uneven ground to one exact cream.

    The source is a lossy render: its background drifts a few values across the frame and
    carries a soft vignette, both of which an upscale turns into a visible grey ring on the
    tile. Only pixels already near the ground are touched, so letter edges keep their
    antialiasing."""
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if abs(r - CREAM[0]) < 18 and abs(g - CREAM[1]) < 18 and abs(b - CREAM[2]) < 20:
                px[x, y] = CREAM
    return img


def crisp(img, size):
    up = size[0] > img.width
    out = img.resize(size, Image.LANCZOS)
    if up:
        out = out.filter(ImageFilter.UnsharpMask(radius=1.2, percent=70, threshold=2))
    return out


def tile(box, side, margin):
    mark = flatten(Image.open(SRC).convert("RGB").crop(box))
    avail_w = side * (1 - 2 * margin)
    avail_h = side * (1 - 2 * margin)
    scale = min(avail_w / mark.width, avail_h / mark.height)
    tw, th = max(1, round(mark.width * scale)), max(1, round(mark.height * scale))
    small = crisp(mark, (tw, th))
    if side <= 32:
        # A 16 or 32px frame loses the letterforms to grey without this. The boost is applied
        # to the mark rather than the finished tile so the ground stays exactly CREAM across
        # every size.
        small = ImageEnhance.Contrast(small).enhance(1.4)
        # The boost drags the ground towards white too, so snap every light pixel back.
        px = small.load()
        for y in range(small.height):
            for x in range(small.width):
                r, g, b = px[x, y]
                if min(r, g, b) > 196:
                    px[x, y] = CREAM
    canvas = Image.new("RGB", (side, side), CREAM)
    canvas.paste(small, ((side - tw) // 2, (side - th) // 2))
    return canvas


tile(MARK, 512, 0.10).save(OUT / "icon.png", optimize=True)
tile(MARK, 180, 0.14).save(OUT / "apple-icon.png", optimize=True)

# RGBA, not RGB: Next.js decodes the .ico at build time to read its dimensions and rejects an
# RGB PNG frame outright ("The PNG is not in RGBA format"). The alpha channel is fully opaque.
frames = [tile(MARK, 48, 0.06).convert("RGBA"),
          tile(MARK, 32, 0.06).convert("RGBA"),
          tile(TIGHT, 16, 0.03).convert("RGBA")]
frames[0].save(OUT / "favicon.ico", format="ICO",
               sizes=[(48, 48), (32, 32), (16, 16)], append_images=frames[1:])

# icon-maskable.png - 512, for the Android home screen. A maskable icon is cropped to whatever
# shape the launcher uses, so the mark has to sit inside the middle 80% of the tile. It lives in
# public/ rather than app/ because it is referenced only by the manifest; under app/ the file
# convention would also add a second <link rel="icon"> that no browser needs.
MASKABLE = OUT.parent / "public"
MASKABLE.mkdir(parents=True, exist_ok=True)
tile(MARK, 512, 0.22).save(MASKABLE / "icon-maskable.png", optimize=True)

lockup = flatten(Image.open(SRC).convert("RGB").crop(FULL))
og = Image.new("RGB", (1200, 630), CREAM)
lw = 760
lh = round(lw * lockup.height / lockup.width)
og.paste(crisp(lockup, (lw, lh)), ((1200 - lw) // 2, (630 - lh) // 2))
og.save(OUT / "opengraph-image.png", optimize=True)

for f in sorted(OUT.iterdir()):
    print(f"{f.name:24s} {f.stat().st_size:>8,d} bytes")
