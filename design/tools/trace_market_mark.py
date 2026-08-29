"""Trace the F2C mark out of the logo raster into flat SVG paths.

    python design/tools/trace_market_mark.py <epsilon> <min-area> <out.svg>

The paths in frontend/market/components/Brand/Mark.tsx came from `... 3.5 600 mark.svg`.
Epsilon is the simplification tolerance in upscaled pixels and min-area drops specks; both are
worth retuning if the source is ever replaced with something sharper.

No vector tracer is installed and none is worth a dependency for one logo, so this is the whole
pipeline: classify each pixel to one of the brand colours, build a binary mask per layer,
follow the mask boundaries into closed loops, simplify the staircases away, and emit one path per
layer.
"""
import sys
from colorsys import rgb_to_hls
from pathlib import Path
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "design" / "F2C_new_logo-removebg-preview - Edited 1.png"
MARK = (152, 62, 351, 179)
UP = 6                     # supersample before thresholding, to pick up sub-source detail

LAYERS = ["bark", "leaf", "wheat", "ink"]
LAYER_INDEX = {name: i for i, name in enumerate(LAYERS, start=1)}


def classify(img):
    """Assign each pixel to a layer by hue and lightness, not by nearest RGB.

    Nearest-RGB fails on this source: the antialiased pixels along a black letter edge sit at a
    mid warm grey whose closest brand colour is the tan, and the trace comes out with every glyph
    wearing a tan outline. Hue and saturation separate them cleanly instead - an edge pixel is
    desaturated and a real tan pixel is not - so a pixel that is only a blend falls through to the
    ground and is not traced at all.
    """
    w, h = img.size
    px = img.load()
    out = bytearray(w * h)
    cache = {}
    for y in range(h):
        row = y * w
        for x in range(w):
            c = px[x, y]
            i = cache.get(c)
            if i is None:
                hue, light, sat = rgb_to_hls(c[0] / 255, c[1] / 255, c[2] / 255)
                hue *= 360
                if light < 0.10:
                    # Below this the hue is meaningless: the wordmark black carries a faint cast
                    # that would otherwise read as leaf green in the middle of a letter.
                    i = LAYER_INDEX["ink"]
                elif 80 < hue < 170 and sat > 0.30 and light < 0.50:
                    i = LAYER_INDEX["leaf"]
                elif 8 < hue < 50 and sat > 0.45 and light < 0.36:
                    i = LAYER_INDEX["bark"]
                elif 15 < hue < 48 and sat > 0.25 and 0.44 < light < 0.78:
                    i = LAYER_INDEX["wheat"]
                elif light < 0.28:
                    i = LAYER_INDEX["ink"]
                else:
                    i = 0
                cache[c] = i
            out[row + x] = i
    return out, w, h


def loops(mask, w, h):
    """Follow the boundary between set and unset cells into closed loops.

    Each set cell contributes the edges it shares with an unset neighbour, directed so the set
    side is always on the left. Every boundary vertex then has as many outgoing edges as incoming,
    so chaining them greedily consumes the whole boundary and closes every loop, holes included.
    """
    edges = {}

    def add(a, b):
        edges.setdefault(a, []).append(b)

    for y in range(h):
        row = y * w
        for x in range(w):
            if not mask[row + x]:
                continue
            if y == 0 or not mask[row - w + x]:
                add((x + 1, y), (x, y))
            if y == h - 1 or not mask[row + w + x]:
                add((x, y + 1), (x + 1, y + 1))
            if x == 0 or not mask[row + x - 1]:
                add((x, y), (x, y + 1))
            if x == w - 1 or not mask[row + x + 1]:
                add((x + 1, y + 1), (x + 1, y))

    out = []
    for start in list(edges):
        while edges.get(start):
            loop = [start]
            cur = start
            while True:
                nxt = edges[cur].pop()
                if not edges[cur]:
                    del edges[cur]
                if nxt == start:
                    break
                loop.append(nxt)
                cur = nxt
                if cur not in edges:
                    break
            if len(loop) > 3:
                out.append(loop)
    return out


def rdp(pts, eps):
    """Douglas-Peucker. Turns the boundary staircase into the diagonals it stands in for."""
    if len(pts) < 3:
        return pts
    ax, ay = pts[0]
    bx, by = pts[-1]
    dx, dy = bx - ax, by - ay
    norm = (dx * dx + dy * dy) ** 0.5
    worst, at = 0.0, 0
    for i in range(1, len(pts) - 1):
        cx, cy = pts[i]
        if norm:
            d = abs(dy * cx - dx * cy + bx * ay - by * ax) / norm
        else:
            d = ((cx - ax) ** 2 + (cy - ay) ** 2) ** 0.5
        if d > worst:
            worst, at = d, i
    if worst <= eps:
        return [pts[0], pts[-1]]
    return rdp(pts[:at + 1], eps)[:-1] + rdp(pts[at:], eps)


def main(eps, min_area, out_path):
    img = Image.open(SRC).convert("RGB").crop(MARK)
    img = img.resize((img.width * UP, img.height * UP), Image.LANCZOS)
    # The source is a lossy render and its flat areas are not flat. A median pass at the upscaled
    # size removes the ringing without moving an edge, which a blur would.
    img = img.filter(ImageFilter.MedianFilter(7))
    idx, w, h = classify(img)

    parts = []
    for name in LAYERS:
        layer = LAYER_INDEX[name]
        mask = bytearray(1 if v == layer else 0 for v in idx)
        subpaths = []
        for loop in loops(mask, w, h):
            n = len(loop)
            area = abs(sum(loop[i][0] * loop[(i + 1) % n][1] - loop[(i + 1) % n][0] * loop[i][1]
                           for i in range(n))) / 2
            if area < min_area:
                continue
            simple = rdp(loop + [loop[0]], eps)[:-1]
            pts = [f"{x / UP:.2f} {y / UP:.2f}" for x, y in simple]
            subpaths.append("M" + pts[0] + "L" + "L".join(pts[1:]) + "Z")
        parts.append((name, "".join(subpaths), len(subpaths)))

    body = "\n".join(f'  <path data-layer="{n}" d="{d}"/>' for n, d, _ in parts if d)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w / UP:.2f} {h / UP:.2f}" '
           f'fill-rule="evenodd">\n{body}\n</svg>\n')
    Path(out_path).write_text(svg)
    for n, d, c in parts:
        print(f"  {n:6s} loops={c:3d} chars={len(d):7,d}")
    print(f"  total {len(svg):,d} bytes -> {out_path}")


if __name__ == "__main__":
    sys.setrecursionlimit(100000)
    main(float(sys.argv[1]), float(sys.argv[2]), sys.argv[3])
