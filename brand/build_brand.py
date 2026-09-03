"""Hazard Watch brand assets.

Renders the typographic logo, the LinkedIn page cover and the LinkedIn
profile banner, each in a dark and a light variant. Everything is
monochrome, so it never collides with the per-peril accent colours used in
the post graphics.

Corner ticks are placed from the measured ink box of the type they frame,
never from hand-set coordinates, so the padding is equal on all four sides
whatever the string or the size.

Run:  python build_brand.py
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent

# ---------------------------------------------------------------- palette
INK        = "#0B0E12"   # near black, dark ground and light-variant type
PAPER      = "#F2F0EB"   # warm off white, light ground and dark-variant type

GREY       = "#8B929B"   # secondary type on ink
DIM        = "#767D87"   # tertiary type on ink
HAIRLINE   = "#2A323B"   # rules on ink
GRATICULE  = "#141A21"   # background grid on ink

PAPER_SEC  = "#4E555E"   # secondary type on paper
PAPER_DIM  = "#6B727C"   # tertiary type on paper
PAPER_RULE = "#C9C6BE"   # rules on paper
PAPER_GRAT = "#E5E2DA"   # background grid on paper

BAHN = r"C:\Windows\Fonts\bahnschrift.ttf"   # variable DIN-like: weight 300-700, width 75-100
MONO = r"C:\Windows\Fonts\CascadiaMono.ttf"

WORDMARK = "HAZARD WATCH"
EQUATION = "Hazard \u00d7 Exposure \u00d7 Vulnerability = Loss"
STRAP    = "Satellite-observed footprints. Modelled loss estimates. Open method."
DISCLAIM = "Modelled estimate. Not a loss adjustment, official assessment, or insurance advice."


def theme(dark):
    if dark:
        return dict(fg=PAPER, bg=INK, sec=GREY, dim=DIM,
                    rule=HAIRLINE, grat=GRATICULE, disc="#6C737D")
    return dict(fg=INK, bg=PAPER, sec=PAPER_SEC, dim=PAPER_DIM,
                rule=PAPER_RULE, grat=PAPER_GRAT, disc="#7A818A")


# ------------------------------------------------------------- type tools
_SCRATCH = ImageDraw.Draw(Image.new("L", (1, 1)))


def bahn(size, weight=400, width=100):
    f = ImageFont.truetype(BAHN, int(round(size)))
    f.set_variation_by_axes([weight, width])
    return f


def mono(size):
    return ImageFont.truetype(MONO, int(round(size)))


def ink_width(f, s, tracking=0.0):
    """Advance width of s as it will be drawn: per-character advances plus tracking."""
    if not s:
        return 0.0
    return sum(f.getlength(c) for c in s) + tracking * (len(s) - 1)


def tracking_to_fit(f, s, target):
    """Letterspacing that makes s span exactly target pixels."""
    n = len(s) - 1
    if n <= 0:
        return 0.0
    return (target - sum(f.getlength(c) for c in s)) / n


def size_to_fit(s, target, weight=400, width=100, tracking_em=0.0, lo=8, hi=400):
    """Largest Bahnschrift size at which s fits target, tracking given as a fraction of size."""
    best = lo
    while lo <= hi:
        mid = (lo + hi) // 2
        f = bahn(mid, weight, width)
        if ink_width(f, s, tracking_em * mid) <= target:
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    return best


def _origin(xy, s, f, tracking, anchor):
    w = ink_width(f, s, tracking)
    x, y = xy
    if anchor == "m":
        x -= w / 2
    elif anchor == "r":
        x -= w
    return x, y


def box_tracked(xy, s, f, tracking=0.0, anchor="l"):
    """Ink box of a tracked string: where the strokes actually start and stop.

    The advance width overshoots on the right by the last glyph's side
    bearing, and undershoots on the left by the first one. Framing off the
    advance box is what leaves corner ticks looking off centre.
    """
    x, y = _origin(xy, s, f, tracking, anchor)
    first = _SCRATCH.textbbox((0, 0), s[0], font=f, anchor="ls")
    left = x + first[0]
    cursor = x
    for c in s[:-1]:
        cursor += f.getlength(c) + tracking
    last = _SCRATCH.textbbox((0, 0), s[-1], font=f, anchor="ls")
    right = cursor + last[2]
    whole = _SCRATCH.textbbox((0, 0), s, font=f, anchor="ls")
    return (left, y + whole[1], right, y + whole[3])


def tracked(d, xy, s, f, fill, tracking=0.0, anchor="l"):
    """Draw s on a baseline with explicit letterspacing. Returns its ink box."""
    x, y = _origin(xy, s, f, tracking, anchor)
    for c in s:
        d.text((x, y), c, font=f, fill=fill, anchor="ls")
        x += f.getlength(c) + tracking
    return box_tracked(xy, s, f, tracking, anchor)


def union(*boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


# ------------------------------------------------------------ decorations
def corner_ticks(d, box, length, weight, fill):
    """Area-of-interest frame: four corner marks, never a closed rectangle."""
    x0, y0, x1, y1 = box
    for cx, cy, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
        d.line([(cx, cy), (cx + dx * length, cy)], fill=fill, width=weight)
        d.line([(cx, cy), (cx, cy + dy * length)], fill=fill, width=weight)


def frame(d, ink_box, pad, length, weight, fill):
    """Corner ticks at an equal distance from the type on all four sides."""
    x0, y0, x1, y1 = ink_box
    corner_ticks(d, (x0 - pad, y0 - pad, x1 + pad, y1 + pad), length, weight, fill)


def graticule(d, size, step, fill):
    w, h = size
    for x in range(0, w, step):
        d.line([(x, 0), (x, h)], fill=fill, width=1)
    for y in range(0, h, step):
        d.line([(0, y), (w, y)], fill=fill, width=1)


def canvas(w, h, bg):
    im = Image.new("RGB", (int(w), int(h)), bg)
    return im, ImageDraw.Draw(im)


# ------------------------------------------------------------------ logos
def logo_avatar(s=1, dark=True):
    """Square lockup, for the LinkedIn page logo. 300 px minimum, 800 supplied."""
    S = 800 * s
    c = theme(dark)
    im, d = canvas(S, S, c["bg"])

    target = 470 * s                       # both words are set to the same width
    base = size_to_fit("HAZARD", target, 600, 100, 0.10)
    f = bahn(base, 600, 100)
    t1 = tracking_to_fit(f, "HAZARD", target)
    t2 = tracking_to_fit(f, "WATCH", target)
    leading = base * 1.12
    pad = 56 * s
    cx = S / 2

    # measure the lockup against a baseline of 0, then centre the framed block
    m = union(box_tracked((cx, 0), "HAZARD", f, t1, "m"),
              box_tracked((cx, leading), "WATCH", f, t2, "m"))
    y0 = (S - (m[3] - m[1] + 2 * pad)) / 2 - m[1] + pad

    b1 = tracked(d, (cx, y0), "HAZARD", f, c["fg"], t1, anchor="m")
    b2 = tracked(d, (cx, y0 + leading), "WATCH", f, c["fg"], t2, anchor="m")
    frame(d, union(b1, b2), pad, 30 * s, max(1, int(3 * s)), c["fg"])
    return im


def logo_monogram(s=1, dark=True):
    """Fallback mark for the 48 px feed avatar, where two words stop being readable."""
    S = 800 * s
    c = theme(dark)
    im, d = canvas(S, S, c["bg"])

    target = 470 * s
    base = size_to_fit("HW", target, 600, 100, 0.08)
    f = bahn(base, 600, 100)
    t = tracking_to_fit(f, "HW", target)
    pad = 86 * s

    m = box_tracked((S / 2, 0), "HW", f, t, "m")
    y0 = (S - (m[3] - m[1] + 2 * pad)) / 2 - m[1] + pad

    b = tracked(d, (S / 2, y0), "HW", f, c["fg"], t, anchor="m")
    frame(d, b, pad, 44 * s, max(1, int(4 * s)), c["fg"])
    return im


def logo_horizontal(s=1, dark=True):
    """One-line lockup with strapline, for documents and slide footers."""
    W, H = 2400 * s, 600 * s
    c = theme(dark)
    im, d = canvas(W, H, c["bg"])

    target = 1600 * s
    base = size_to_fit(WORDMARK, target, 600, 100, 0.12)
    f = bahn(base, 600, 100)
    t = tracking_to_fit(f, WORDMARK, target)

    m = mono(34 * s)
    sub = "natural catastrophe loss estimates"
    tsub = tracking_to_fit(m, sub, target * 0.72)
    leading = 84 * s
    pad = 74 * s
    cx = W / 2

    block = union(box_tracked((cx, 0), WORDMARK, f, t, "m"),
                  box_tracked((cx, leading), sub, m, tsub, "m"))
    y0 = (H - (block[3] - block[1] + 2 * pad)) / 2 - block[1] + pad

    b1 = tracked(d, (cx, y0), WORDMARK, f, c["fg"], t, anchor="m")
    b2 = tracked(d, (cx, y0 + leading), sub, m, c["sec"], tsub, anchor="m")
    frame(d, union(b1, b2), pad, 46 * s, max(1, int(4 * s)), c["fg"])
    return im


# --------------------------------------------------------- linkedin cover
def page_cover(s=1, dark=True):
    """LinkedIn page cover, 1128 x 191.

    LinkedIn composites the page logo tile over the bottom left, so nothing
    that matters goes left of x = 200.
    """
    W, H = 1128 * s, 191 * s
    c = theme(dark)
    im, d = canvas(W, H, c["bg"])
    graticule(d, (W, H), int(24 * s), c["grat"])

    x0 = 228 * s
    f = bahn(size_to_fit(EQUATION, 838 * s, 600, 100, 0.0), 600, 100)
    tracked(d, (x0, 96 * s), EQUATION, f, c["fg"], 0.0)

    d.text((x0, 128 * s), STRAP, font=mono(15 * s), fill=c["sec"], anchor="ls")
    d.text((x0, 157 * s), DISCLAIM, font=mono(12.5 * s), fill=c["disc"], anchor="ls")
    return im


# -------------------------------------------------------- linkedin banner
def profile_banner(s=1, dark=True):
    """LinkedIn personal profile banner, 1584 x 396.

    The profile photo sits over the bottom left, so the block below and left
    of roughly (400, 210) is left empty. Mobile crops the outer edges, so
    nothing essential goes past x = 1500.
    """
    W, H = 1584 * s, 396 * s
    c = theme(dark)
    im, d = canvas(W, H, c["bg"])
    graticule(d, (W, H), int(36 * s), c["grat"])

    # wordmark, top left, clear of the photo
    fw = bahn(28 * s, 600, 100)
    bw = tracked(d, (72 * s, 92 * s), WORDMARK, fw, c["fg"],
                 tracking_to_fit(fw, WORDMARK, 268 * s))
    rule_y = bw[3] + 20 * s
    d.line([(bw[0], rule_y), (bw[2], rule_y)], fill=c["rule"], width=max(1, int(1 * s)))
    mw = mono(13 * s)
    d.text((bw[0], rule_y + 26 * s), "natural catastrophe", font=mw, fill=c["dim"], anchor="ls")
    d.text((bw[0], rule_y + 45 * s), "loss estimates", font=mw, fill=c["dim"], anchor="ls")

    # main block, right of the photo keep-out
    x0 = 430 * s
    f = bahn(size_to_fit(EQUATION, 1020 * s, 600, 100, 0.0), 600, 100)
    tracked(d, (x0, 172 * s), EQUATION, f, c["fg"], 0.0)

    d.text((x0, 212 * s), STRAP, font=mono(19 * s), fill=c["sec"], anchor="ls")
    d.line([(x0, 246 * s), (1450 * s, 246 * s)], fill=c["rule"], width=max(1, int(1 * s)))

    m = mono(17 * s)
    d.text((x0, 288 * s), "Sentinel-1  \u00b7  CLIMADA  \u00b7  QGIS  \u00b7  Python", font=m, fill=c["sec"], anchor="ls")
    d.text((x0, 318 * s), "Master 2 Dynarisk, Paris 1 Panth\u00e9on-Sorbonne", font=m, fill=c["dim"], anchor="ls")
    d.text((x0, 348 * s), "Available February 2027  \u00b7  reinsurance, Zurich", font=m, fill=c["dim"], anchor="ls")
    return im


# ------------------------------------------------------------------ check
def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def has_marks(im, box, bg, tol=24):
    """True when box holds something other than the ground and its faint grid."""
    lo_hi = im.crop(box).getextrema()
    return any(abs(lo - ch) > tol or abs(hi - ch) > tol
               for (lo, hi), ch in zip(lo_hi, _rgb(bg)))


def demo():
    """Smallest check that the layout rules and the framing actually hold."""
    assert page_cover(2).size == (2256, 382)
    assert profile_banner(2).size == (3168, 792)

    for dark in (True, False):
        bg = INK if dark else PAPER
        cov, ban = page_cover(1, dark), profile_banner(1, dark)
        assert cov.size == (1128, 191) and ban.size == (1584, 396)
        # keep-out zones stay empty
        assert not has_marks(cov, (0, 0, 190, 191), bg), "page cover: logo keep-out is not clear"
        assert not has_marks(ban, (0, 215, 400, 396), bg), "profile banner: photo keep-out is not clear"
        # content zones are not
        assert has_marks(cov, (228, 40, 1100, 160), bg), "page cover: content zone is empty"
        assert has_marks(ban, (430, 120, 1500, 360), bg), "profile banner: content zone is empty"

    # the frame sits at an equal distance from the type on all four sides
    for build in (logo_avatar, logo_monogram, logo_horizontal):
        im = build(1, True)
        w, h = im.size
        col = im.convert("L").point(lambda v: 255 if v > 110 else 0)
        px = col.load()
        rows = [y for y in range(h) if any(px[x, y] for x in range(w))]
        cols = [x for x in range(w) if any(px[x, y] for y in range(h))]
        top, bottom = rows[0], h - 1 - rows[-1]
        left, right = cols[0], w - 1 - cols[-1]
        assert abs(top - bottom) <= 2, "%s: frame is not vertically centred (%d vs %d)" % (
            build.__name__, top, bottom)
        assert abs(left - right) <= 2, "%s: frame is not horizontally centred (%d vs %d)" % (
            build.__name__, left, right)

    print("demo: layout and framing checks passed")


def main():
    jobs = []
    for tag, dark in (("ink", True), ("paper", False)):
        jobs += [
            ("logo-avatar-%s.png" % tag,                     logo_avatar(1, dark)),
            ("logo-monogram-%s.png" % tag,                   logo_monogram(1, dark)),
            ("logo-horizontal-%s.png" % tag,                 logo_horizontal(1, dark)),
            ("linkedin-page-cover-%s-1128x191.png" % tag,    page_cover(1, dark)),
            ("linkedin-page-cover-%s-2256x382.png" % tag,    page_cover(2, dark)),
            ("linkedin-profile-banner-%s-1584x396.png" % tag, profile_banner(1, dark)),
            ("linkedin-profile-banner-%s-3168x792.png" % tag, profile_banner(2, dark)),
        ]
    for name, im in jobs:
        im.save(OUT / name)
        print("%-44s %d x %d" % (name, im.size[0], im.size[1]))
    demo()


if __name__ == "__main__":
    main()
