"""Visual identity for the published figures.

Map styling happens **once**, here, and never again by hand. Every figure the
pipeline produces draws its colours, type, spacing and furniture from these
definitions, so output stays consistent from one post to the next.

Layout model
------------
Two zones, and the distinction matters:

* the **basemap** bleeds to the edge of the image, passing behind the title and
  the footer, faded so text stays readable;
* the **canvas** is the rectangle where map *information* lives — hazard
  extent, study-area outline, labels, scale, north, locator, bubbles. It is
  bounded laterally by the page margins and vertically by the title block and
  the sources block.

Framing targets the hazard layer, not the administrative study area.

Glass
-----
Overlay elements are real frosted glass, not a flat translucent fill: the
basemap behind each one is cropped, blurred and lightened, then clipped to the
element's shape. That is what separates a premium overlay from a white box at
80 % opacity.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import matplotlib
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch

# ---------------------------------------------------------------------------
# Output formats
# ---------------------------------------------------------------------------

SQUARE = (1080, 1080)
PORTRAIT = (1080, 1350)
WIDE = (1200, 628)
DPI = 100

BRAND = "HAZARD WATCH"

# The image lockup that replaces the text wordmark in the top-right corner.
# Lives one level up from this repository, alongside the other brand assets
# that are shared across more than one project.
BRAND_MARK = Path(__file__).resolve().parent.parent / "brand" / "logo-avatar-paper.png"

# ---------------------------------------------------------------------------
# Colour
# ---------------------------------------------------------------------------

PERIL_COLOURS = {
    "flood": "#0E6BA8",
    "wildfire": "#C43C1B",
    "earthquake": "#6A3D9A",
    "storm": "#1B7F79",
    "drought": "#B8860B",
    "landslide": "#7A5230",
    "volcano": "#A11D45",
}

# GDACS alert level. Three values only, and the names are the ones GDACS uses,
# so the colour never has to be explained in a legend.
ALERT_COLOURS = {
    "Red": "#B3261E",
    "Orange": "#C87A1E",
    "Green": "#2E7D5B",
}

# Study-area boundary: always the same deep blood red, whatever the peril.
STUDY_AREA = "#8E1B2E"

# Dash and gap for the study-area outline, in points. Held here rather than
# written at each call site so the map and the legend cannot drift apart.
STUDY_AREA_DASH = (7.0, 3.5)

# Official observed event, as mapped by the responders. A second boundary
# colour, deliberately far from the study area red so the two never read as
# the same line at a glance.
OBSERVED_EVENT = "#1F3A5F"
OBSERVED_EVENT_DASH = (2.5, 2.5)

# Damage grades as Copernicus EMS publishes them. Sequential rather than
# categorical: the grades are ordered, and a reader should be able to rank
# them without reading the legend.
DAMAGE_GRADES_ORDER = ("Destroyed", "Damaged", "Possibly damaged")

DAMAGE_COLOURS = {
    "Destroyed": "#8E1B2E",
    "Damaged": "#D4703A",
    "Possibly damaged": "#E3B23C",
    "No visible damage": "#7A8B7F",
}

# Critical facilities and severed transport, which are the part of a grading
# product that a reinsurance reader looks for first. The road is black rather
# than red: the damage palette is already three warm tones, and a fourth
# competed with the destroyed buildings instead of sitting under them.
FACILITY = "#5B2A86"
ROAD_CUT = "#0A0C0E"

# Drawing order for a grading sheet, bottom to top. What a reader must not
# lose sits highest: a destroyed hospital is never hidden under a road.
LAYER_ORDER = {
    "study_area": 3,
    "flooded": 4,
    "road": 5,
    "Possibly damaged": 6,
    "Damaged": 7,
    "Destroyed": 8,
    "facility": 9,
    "label": 11,
}

WATER = "#AEC6D6"

THEME = {
    "background": "#FBFAF7",
    "text": "#14171A",
    "muted": "#14171A",
    "faint": "#3A4045",
    "rule": "#D8D3CA",
}

# ---------------------------------------------------------------------------
# Type — one family throughout, including map labels. Weight and size carry
# the hierarchy, not a change of typeface.
# ---------------------------------------------------------------------------

FONT_STACK = ["Segoe UI", "Franklin Gothic Book", "DejaVu Sans"]

TYPE = {
    "title": 28,
    "subtitle": 14,
    "bubble_primary": 40,
    "bubble_secondary": 32,
    "bubble_label": 14,
    "bubble_note": 12,
    "place": 12,
    "legend": 12.5,
    "caption": 11,
    "credit": 10,
    "brand": 12,
    "byline": 16,
}

CANVAS = {"left": 0.06, "right": 0.94, "bottom": 0.175, "top": 0.815}

DISCLAIMER = (
    "Modelled estimate from open satellite data. Not a loss adjustment, "
    "an official assessment, or insurance advice."
)


def apply() -> dict:
    matplotlib.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": FONT_STACK,
            "figure.facecolor": THEME["background"],
            "axes.facecolor": THEME["background"],
            "savefig.facecolor": THEME["background"],
            "text.color": THEME["text"],
            "figure.dpi": DPI,
            "savefig.dpi": DPI,
            # Never "tight": blocks sit in figure coordinates and a tight
            # bounding box would recrop the canvas around them.
            "savefig.bbox": None,
            "savefig.pad_inches": 0.0,
        }
    )
    return THEME


def canvas(size: tuple = PORTRAIT):
    return plt.figure(figsize=(size[0] / DPI, size[1] / DPI),
                      facecolor=THEME["background"])


# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------


def frame_extent(target_bounds: tuple, figure_size: tuple = PORTRAIT,
                 fill: float = 0.9) -> tuple:
    """Geographic extent of the full-bleed basemap.

    Solves the layout backwards: we know where the canvas sits on the page and
    how much of it the hazard should occupy, so we work out how much ground the
    whole image must cover for that to be true, then centre it.

    ``target_bounds`` is what should be framed — the hazard footprint, not the
    study area.
    """
    x0, y0, x1, y1 = target_bounds
    target_w, target_h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

    canvas_w = CANVAS["right"] - CANVAS["left"]
    canvas_h = CANVAS["top"] - CANVAS["bottom"]

    need_w = target_w / (canvas_w * fill)
    need_h = target_h / (canvas_h * fill)

    aspect = figure_size[0] / figure_size[1]
    width = max(need_w, need_h * aspect)
    height = width / aspect

    # The canvas centre is not the page centre; shift the ground so the target
    # lands in the middle of the canvas rather than the middle of the image.
    canvas_cx = (CANVAS["left"] + CANVAS["right"]) / 2
    canvas_cy = (CANVAS["bottom"] + CANVAS["top"]) / 2
    cx -= (canvas_cx - 0.5) * width
    cy -= (canvas_cy - 0.5) * height

    return (cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2)


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


def soft_halo(colour: str = "#FFFFFF", layers: int = 5, width: float = 5.0,
              alpha: float = 0.32):
    """A diffuse glow behind text, instead of a hard outline.

    A single thick stroke is what makes default GIS output look like default
    GIS output. Stacking several strokes of decreasing width and opacity
    approximates a blur, so the label lifts off the terrain without drawing a
    cartoon border around every letter.
    """
    effects = []
    for i in range(layers, 0, -1):
        effects.append(
            pe.withStroke(linewidth=width * i / layers,
                          foreground=colour, alpha=alpha / i)
        )
    effects.append(pe.Normal())
    return effects


def place_label(ax, x: float, y: float, name: str, offset: float = 0.0,
                kind: str = "town", align: str = None, dot: bool = True):
    """A map label: dot for settlements, plain text for regions and water.

    Set at subtitle size with a clean white outline so it holds up against
    terrain at thumbnail scale. `align` overrides the style's own alignment,
    which is how a label near the right edge is flipped to sit on the left of
    its marker instead of running off the sheet.
    """
    style = LABEL_STYLES[kind]
    if style["dot"] and dot:
        ax.plot(x, y, "o", ms=style["dot"], color=THEME["text"],
                markeredgecolor="white", markeredgewidth=1.2,
                zorder=LAYER_ORDER["label"])
    ax.text(x + offset, y, name, fontsize=style["size"], color=style["colour"],
            va="center", ha=align or style["ha"], zorder=LAYER_ORDER["label"],
            fontweight=style["weight"], style=style["italic"],
            linespacing=1.15,
            path_effects=[pe.withStroke(linewidth=3.2, foreground="white"),
                          pe.Normal()])
    return ax


LABEL_STYLES = {
    "town": {"size": TYPE["subtitle"], "weight": "bold", "dot": 5.0,
             "colour": THEME["text"], "ha": "left", "italic": "normal"},
    "city": {"size": TYPE["subtitle"], "weight": "bold", "dot": 6.5,
             "colour": THEME["text"], "ha": "left", "italic": "normal"},
    "country": {"size": TYPE["subtitle"] + 1, "weight": "bold", "dot": 0,
                "colour": "#4A5158", "ha": "center", "italic": "normal"},
    "water": {"size": TYPE["subtitle"], "weight": "normal", "dot": 0,
              "colour": "#3E6E8E", "ha": "center", "italic": "italic"},
}
# ---------------------------------------------------------------------------
# Basemap
# ---------------------------------------------------------------------------

HYPSOMETRIC = [
    (0.00, "#A9C6A0"),
    (0.12, "#BCD0A2"),
    (0.28, "#D3D9A6"),
    (0.45, "#DFCF9E"),
    (0.62, "#CBB189"),
    (0.78, "#B79A7C"),
    (0.90, "#C7B9AE"),
    (1.00, "#F0EDEA"),
]


def terrain_colormap():
    from matplotlib.colors import LinearSegmentedColormap

    return LinearSegmentedColormap.from_list("hypsometric", HYPSOMETRIC)


def draw_basemap(ax, dem: np.ndarray, extent: tuple, vert_exag: float = 8,
                 shade_strength: float = 0.5, sea_level: float = 0.0,
                 outside=None, outside_fade: float = 0.55):
    """Hypsometric tint with hillshade, filling the axes edge to edge.

    Sea is painted flat: a hillshade computed over an ocean of zeros produces
    texture that reads as terrain.

    ``outside`` is an optional boolean mask of ground that carries no
    information. Terrain there is faded towards the page background so relief
    does not compete for attention where there is nothing to see.

    Returns the rendered RGB array, which the glass elements sample.
    """
    from matplotlib.colors import LightSource, Normalize

    sea = ~np.isfinite(dem) | (dem <= sea_level)
    land = np.where(sea, np.nan, dem)

    finite = land[np.isfinite(land)]
    if finite.size == 0:
        finite = np.array([0.0, 1.0])
    lo, hi = np.percentile(finite, 1), np.percentile(finite, 99.5)
    norm = Normalize(vmin=lo, vmax=max(hi, lo + 1))

    ls = LightSource(azdeg=315, altdeg=42)
    shaded = ls.shade(
        np.nan_to_num(land, nan=float(lo)),
        cmap=terrain_colormap(), norm=norm,
        blend_mode="soft", vert_exag=vert_exag, fraction=shade_strength,
    )[..., :3]

    shaded[sea] = matplotlib.colors.to_rgb(WATER)

    if outside is not None:
        bg = np.array(matplotlib.colors.to_rgb(THEME["background"]))
        blend = np.where(outside[..., None], outside_fade, 0.0)
        shaded = shaded * (1 - blend) + bg * blend

    ax.imshow(shaded, extent=extent, origin="upper", interpolation="bilinear",
              zorder=0)
    return shaded


def fade(fig, top: float = 0.815, bottom: float = 0.175,
         hold: float = 0.030, reach: float = 0.30):
    """Fade the basemap out behind the title and the footer.

    Not decoration. Black type over a hillshade is unreadable wherever the
    terrain happens to be dark, and this is what buys the contrast back.

    Three zones, and the middle one is what was missing. From the page edge the
    band stays fully opaque until `hold` past the canvas edge, so the type
    always sits on flat ground. Then it ramps to nothing over `reach` of the
    band's own height *beyond* the canvas edge, rather than inside the band.
    Squeezed into the band, as it was, the whole ramp ran in a few dozen pixels
    and read as a hard line drawn across the map.

    The alpha follows a raised cosine, which has zero slope at both ends. A
    straight ramp shows a corner where it starts and where it stops, and the
    eye finds both immediately.
    """
    bg = matplotlib.colors.to_rgb(THEME["background"])

    def band(y0: float, y1: float, hold_at: float, flip: bool, n: int = 1024):
        span = y1 - y0
        held_frac = (y1 - hold_at) / span if not flip else (hold_at - y0) / span
        held = max(0, min(n, int(round(n * held_frac))))
        ramp = np.linspace(0, 1, n - held) if n > held else np.array([])
        eased = 0.5 * (1 + np.cos(np.pi * ramp)) if ramp.size else ramp
        alpha = np.concatenate([np.ones(held), eased])
        if flip:
            alpha = alpha[::-1]

        block = np.zeros((n, 1, 4))
        block[..., 0], block[..., 1], block[..., 2] = bg
        block[..., 3] = alpha.reshape(-1, 1)

        ax = fig.add_axes([0, y0, 1, span], zorder=2)
        ax.imshow(block, aspect="auto", extent=(0, 1, 0, 1))
        ax.axis("off")
        return ax

    band(top - reach * (1 - top), 1.0, hold_at=top + hold, flip=False)
    band(0.0, bottom + reach * bottom, hold_at=bottom - hold, flip=True)
    return fig

# ---------------------------------------------------------------------------
# Glass
# ---------------------------------------------------------------------------


def _backdrop_crop(backdrop: np.ndarray, x: float, y: float, w: float, h: float):
    """The slice of the rendered basemap sitting behind a figure-space box."""
    ih, iw = backdrop.shape[:2]
    c0, c1 = int(np.clip(x, 0, 1) * iw), int(np.clip(x + w, 0, 1) * iw)
    r0, r1 = int((1 - np.clip(y + h, 0, 1)) * ih), int((1 - np.clip(y, 0, 1)) * ih)
    if c1 <= c0 or r1 <= r0:
        return None
    return backdrop[r0:r1, c0:c1]


def _frost(crop: np.ndarray, blur: float = 18.0, tint: float = 0.30,
           saturate: float = 1.18) -> np.ndarray:
    """Blur the backdrop, lift it towards white, and boost saturation slightly.

    Desaturating would read as fog. Real glass keeps colour and adds light,
    which is why saturation goes *up* while the whole image is lifted.
    """
    from scipy import ndimage

    out = np.stack(
        [ndimage.gaussian_filter(crop[..., i], sigma=blur) for i in range(3)],
        axis=-1,
    )
    grey = out.mean(axis=-1, keepdims=True)
    out = np.clip(grey + (out - grey) * saturate, 0, 1)
    return np.clip(out * (1 - tint) + tint, 0, 1)


def _refract(img: np.ndarray, strength: float = 0.26, rim: float = 0.34
             ) -> np.ndarray:
    """Bend the image near the rim, the way a thick lens does.

    This is what separates liquid glass from frosted glass: the centre stays
    flat and the outer band is pulled outward, so the edge reads as a curved
    body of material rather than a cut-out.
    """
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    ny = (yy - (h - 1) / 2) / ((h - 1) / 2)
    nx = (xx - (w - 1) / 2) / ((w - 1) / 2)
    r = np.sqrt(nx ** 2 + ny ** 2)

    t = np.clip((r - (1 - rim)) / max(rim, 1e-6), 0, 1)
    push = 1.0 + strength * (t ** 2)

    src_x = np.clip((nx / push + 1) / 2 * (w - 1), 0, w - 1)
    src_y = np.clip((ny / push + 1) / 2 * (h - 1), 0, h - 1)
    return img[src_y.astype(int), src_x.astype(int)]


def _rim_light(shape: tuple, strength: float = 0.55):
    """Specular rim: bright at the top-left, faintly dark at the bottom-right."""
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    ny = (yy - (h - 1) / 2) / ((h - 1) / 2)
    nx = (xx - (w - 1) / 2) / ((w - 1) / 2)
    r = np.sqrt(nx ** 2 + ny ** 2)

    band = np.exp(-((r - 0.94) ** 2) / 0.004)
    lit = (-nx - ny) / np.sqrt(2)

    light = np.zeros((h, w, 4))
    light[..., :3] = 1.0
    light[..., 3] = np.clip(lit, 0, 1) * band * strength

    dark = np.zeros((h, w, 4))
    dark[..., 3] = np.clip(-lit, 0, 1) * band * strength * 0.45
    return light, dark


def _fig_ellipse(centre, rx, ry, **kwargs):
    """A shape that is round *in pixels*.

    Figure coordinates are not square on a portrait page, so a Circle drawn in
    them comes out as an ellipse. Everything round is therefore built as an
    Ellipse with the two radii already corrected.
    """
    from matplotlib.patches import Ellipse

    return Ellipse(centre, 2 * rx, 2 * ry, **kwargs)


def _rounded_path(w_fig: float, h_fig: float, radius_px: float = 16.0):
    """Rounded-rectangle path in axes coordinates, with corners round in pixels.

    ``FancyBboxPatch`` takes a single rounding size, which stretches into an
    oval on a non-square box. Building the path by hand with a separate radius
    per axis keeps the corners circular whatever the proportions.
    """
    from matplotlib.path import Path

    rx = radius_px / max(w_fig * PORTRAIT[0], 1e-6)
    ry = radius_px / max(h_fig * PORTRAIT[1], 1e-6)
    rx, ry = min(rx, 0.5), min(ry, 0.5)
    k = 0.5523  # circular arc as a cubic Bezier

    verts, codes = [], []
    verts.append((rx, 0)); codes.append(Path.MOVETO)
    verts.append((1 - rx, 0)); codes.append(Path.LINETO)
    verts += [(1 - rx + rx * k, 0), (1, ry - ry * k), (1, ry)]
    codes += [Path.CURVE4] * 3
    verts.append((1, 1 - ry)); codes.append(Path.LINETO)
    verts += [(1, 1 - ry + ry * k), (1 - rx + rx * k, 1), (1 - rx, 1)]
    codes += [Path.CURVE4] * 3
    verts.append((rx, 1)); codes.append(Path.LINETO)
    verts += [(rx - rx * k, 1), (0, 1 - ry + ry * k), (0, 1 - ry)]
    codes += [Path.CURVE4] * 3
    verts.append((0, ry)); codes.append(Path.LINETO)
    verts += [(0, ry - ry * k), (rx - rx * k, 0), (rx, 0)]
    codes += [Path.CURVE4] * 3
    verts.append((rx, 0)); codes.append(Path.CLOSEPOLY)
    return Path(verts, codes)


def glass_circle(fig, backdrop: np.ndarray, centre: tuple, radius: float,
                 blur: float = 18.0, tint: float = 0.30):
    """A liquid-glass circular pane. Returns its axes so callers add content."""
    from matplotlib.patches import Circle

    cx, cy = centre
    ar = PORTRAIT[0] / PORTRAIT[1]
    rx, ry = radius, radius * ar
    x, y, w, h = cx - rx, cy - ry, 2 * rx, 2 * ry

    for spread, alpha in ((1.05, 0.045), (1.025, 0.065), (1.008, 0.085)):
        fig.patches.append(
            _fig_ellipse((cx, cy - 0.0024), rx * spread, ry * spread,
                         transform=fig.transFigure, facecolor="#0A0C0E",
                         alpha=alpha, edgecolor="none", zorder=4)
        )

    ax = fig.add_axes([x, y, w, h], zorder=5)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.patch.set_alpha(0)

    crop = _backdrop_crop(backdrop, x, y, w, h)
    if crop is not None and crop.size:
        pane = _refract(_frost(crop, blur, tint))
        img = ax.imshow(pane, extent=(0, 1, 0, 1), zorder=0,
                        interpolation="bilinear")
        img.set_clip_path(Circle((0.5, 0.5), 0.5, transform=ax.transAxes))
        for layer in _rim_light(pane.shape[:2])[::-1]:
            a = ax.imshow(layer, extent=(0, 1, 0, 1), zorder=1,
                          interpolation="bilinear")
            a.set_clip_path(Circle((0.5, 0.5), 0.5, transform=ax.transAxes))

    fig.patches.append(
        _fig_ellipse((cx, cy), rx, ry, transform=fig.transFigure,
                     facecolor="none", edgecolor="#FFFFFF", linewidth=1.6,
                     alpha=0.92, zorder=6)
    )
    return ax


def glass_box(fig, backdrop: np.ndarray, xy: tuple, size: tuple,
              blur: float = 18.0, tint: float = 0.30, radius_px: float = 18.0):
    """A liquid-glass rounded rectangle. Same material as the bubbles."""
    from matplotlib.patches import PathPatch

    x, y = xy
    w, h = size

    ax = fig.add_axes([x, y, w, h], zorder=5)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.patch.set_alpha(0)

    path = _rounded_path(w, h, radius_px)


    crop = _backdrop_crop(backdrop, x, y, w, h)
    if crop is not None and crop.size:
        # aspect="auto" is essential here: imshow otherwise forces the axes box
        # square to match the image, and the pane silently ignores the size it
        # was given.
        img = ax.imshow(_frost(crop, blur, tint), extent=(0, 1, 0, 1), zorder=0,
                        interpolation="bilinear", aspect="auto")
        img.set_clip_path(PathPatch(path, transform=ax.transAxes))

    ax.add_patch(
        PathPatch(path, transform=ax.transAxes, facecolor="none",
                  edgecolor="#FFFFFF", linewidth=1.6, alpha=0.92, zorder=6)
    )
    return ax


def bubble(fig, backdrop: np.ndarray, centre: tuple, radius: float,
           value: str, label: str, note: str = "", peril: str = "flood"):
    """A circular headline figure.

    Type is sized from the bubble's own diameter rather than from a fixed
    table, so a smaller bubble stays as readable as a large one and the third
    line always takes the space actually left to it.
    """
    accent = PERIL_COLOURS.get(peril, THEME["text"])
    ax = glass_circle(fig, backdrop, centre, radius)

    diameter_px = 2 * radius * PORTRAIT[0]
    value_size = diameter_px * 0.150
    label_size = diameter_px * 0.062
    note_size = diameter_px * 0.058

    for y, text, size, weight, colour in (
        (0.635, value, value_size, "bold", accent),
        (0.435, label.upper(), label_size, "bold", THEME["text"]),
        (0.285, note, note_size, "normal", THEME["text"]),
    ):
        if not text:
            continue
        ax.text(0.5, y, text, fontsize=_fit_size(fig, text, size, y, diameter_px),
                fontweight=weight, color=colour, ha="center", va="center",
                transform=ax.transAxes, zorder=3)
    return ax


def _fit_size(fig, text: str, size: float, y: float, diameter_px: float,
              padding: float = 0.86) -> float:
    """Shrink a line until it fits the chord of the circle at that height.

    A bubble is round, so the room a line has depends on how far it sits from
    the middle. Sizing from the diameter alone put "10% of the EMS mapped
    event" outside the glass. Measured with the renderer rather than counted
    in characters, because the answer depends on the actual glyphs.
    """
    half = math.sqrt(max(0.25 - (0.5 - y) ** 2, 0.0))
    limit = 2 * half * diameter_px * padding

    renderer = fig.canvas.get_renderer()
    probe = fig.text(0, -1, text, fontsize=size, fontweight="bold")
    width = probe.get_window_extent(renderer).width
    probe.remove()

    return size if width <= limit else size * (limit / width)


# ---------------------------------------------------------------------------
# Map furniture, drawn from the project's own SVG assets
# ---------------------------------------------------------------------------

FURNITURE_INK = "#0A0C0E"

# Traced from NORD.svg: an "N" whose upstroke carries the arrowhead.
_NORTH_PATH = [
    (1601.499, 814.583), (1566.622, 814.583), (1525.386, 731.347),
    (1524.846, 731.347), (1525.565, 814.583), (1495.722, 814.583),
    (1495.722, 687.301), (1530.779, 687.301), (1571.836, 770.358),
    (1572.375, 770.358), (1571.786, 667.892), (1558.766, 667.741),
    (1586.706, 635.572), (1614.609, 667.741), (1601.609, 667.925),
    (1601.499, 814.583),
]


def _axes_pixels(ax) -> tuple:
    """Pixel size of an axes, without needing the figure to be drawn first."""
    box = ax.get_position()
    return box.width * PORTRAIT[0], box.height * PORTRAIT[1]


def north_glyph(ax, centre=(0.86, 0.50), height: float = 0.72,
                colour: str = FURNITURE_INK):
    """The project's north mark, drawn from its SVG outline.

    The glyph's own proportions are preserved: its width follows from its
    height in *pixels*, not in axes units, otherwise a wide panel would
    stretch it flat.
    """
    pts = np.array(_NORTH_PATH, dtype=float)
    pts[:, 1] *= -1  # SVG y runs downward

    span_x = pts[:, 0].max() - pts[:, 0].min()
    span_y = pts[:, 1].max() - pts[:, 1].min()
    native_ratio = span_x / span_y

    ax_w_px, ax_h_px = _axes_pixels(ax)
    height_px = height * ax_h_px
    width_px = height_px * native_ratio

    pts[:, 0] = (pts[:, 0] - pts[:, 0].mean()) / span_x * (width_px / ax_w_px)
    pts[:, 1] = (pts[:, 1] - pts[:, 1].mean()) / span_y * height
    pts[:, 0] += centre[0]
    pts[:, 1] += centre[1]

    ax.add_patch(plt.Polygon(pts, closed=True, transform=ax.transAxes,
                             facecolor=colour, edgecolor="none", zorder=3))
    return ax


def scale_glyph(ax, length_km: float, centre_y: float = 0.5,
                left: float = 0.06, right: float = 0.70,
                colour: str = FURNITURE_INK, box_width: float = None):
    """The project's scale bar: value, hollow box, unit.

    `box_width` is the width the bar must have, in this axes' coordinates, for
    the box to actually represent `length_km` on the map beside it. Passing it
    is not optional in practice: without it the box takes whatever room the
    layout leaves and the number printed on it is decorative. Measured on the
    sheets this project had already produced, the bars were out by five to
    nine per cent, always in the direction of understating the distance.

    The text is measured rather than guessed, so the gaps either side of the
    box stay equal whatever the number of digits.
    """
    ax_w_px, ax_h_px = _axes_pixels(ax)
    gap = 10 / ax_w_px               # a constant 10 px either side of the box
    label_w = (len(f"{length_km:g}") * 9 + 6) / ax_w_px
    unit_w = 30 / ax_w_px

    box_x0 = left + label_w + gap
    box_x1 = (box_x0 + box_width) if box_width else (right - unit_w - gap)
    box_h = 16 / ax_h_px

    ax.text(left, centre_y, f"{length_km:g}", transform=ax.transAxes,
            ha="left", va="center", fontsize=13, fontweight="bold",
            color=colour, zorder=3)
    ax.add_patch(
        plt.Rectangle((box_x0, centre_y - box_h / 2), box_x1 - box_x0, box_h,
                      transform=ax.transAxes, facecolor="none",
                      edgecolor=colour, linewidth=1.7, zorder=3)
    )
    ax.text(box_x1 + gap, centre_y, "Km", transform=ax.transAxes, ha="left",
            va="center", fontsize=13, fontweight="bold", color=colour,
            zorder=3)
    return ax


LEGEND_HANDLE_LENGTH = 1.8          # in font-size units, as matplotlib counts it


def legend_dashes(pattern: tuple, cycles: int = 2,
                  fontsize: float = None,
                  handlelength: float = LEGEND_HANDLE_LENGTH) -> tuple:
    """The same dash pattern, fitted to end cleanly inside a legend handle.

    A legend handle is about 22 points long and the map's pattern has a period
    of 10.5, so the handle ends two thirds of the way through a third dash.
    The result reads as a line followed by a stray dot, which is what a reader
    sees rather than a dashed line.

    The ratio of dash to gap is what carries the meaning, so it is preserved
    and only the period is rescaled, to a whole number of cycles across the
    handle. The handle then ends on a gap and shows `cycles` complete dashes.
    """
    dash, gap = pattern
    fontsize = fontsize or TYPE["legend"]
    period = (handlelength * fontsize) / cycles
    scale = period / (dash + gap)
    return (0, (dash * scale, gap * scale))


def legend_panel(fig, backdrop: np.ndarray, handles, anchor: tuple,
                 pad_px: float = 20.0):
    """The legend on a glass pane sized to its own text.

    The pane is built from the measured width of each label rather than from
    the legend object: a Legend only computes its layout when the figure is
    drawn, so asking it for a size beforehand returns something far too small.
    Individual Text artists measure correctly without a draw.

    ``anchor`` is the fixed bottom-left corner, constant across posts.
    """
    size = TYPE["legend"]
    renderer = fig.canvas.get_renderer()

    probe = fig.text(0, -1, "", fontsize=size)
    widths, heights = [], []
    for handle in handles:
        probe.set_text(handle.get_label())
        bb = probe.get_window_extent(renderer)
        widths.append(bb.width)
        heights.append(bb.height)
    probe.remove()

    px_per_pt = DPI / 72.0
    handle_px = 1.8 * size * px_per_pt      # handlelength, in font-size units
    gap_px = 0.7 * size * px_per_pt         # handletextpad
    line_px = max(heights) * 1.35
    spacing_px = 0.55 * size * px_per_pt

    width = (handle_px + gap_px + max(widths) + 2 * pad_px) / PORTRAIT[0]
    height = (len(handles) * line_px + (len(handles) - 1) * spacing_px
              + 2 * pad_px) / PORTRAIT[1]

    ax = glass_box(fig, backdrop, anchor, (width, height), blur=15, tint=0.32)
    legend = ax.legend(
        handles=handles, loc="center", bbox_to_anchor=(0.5, 0.5),
        frameon=False, fontsize=size, labelcolor=THEME["text"],
        handlelength=1.8, borderpad=0.0, labelspacing=0.55, handletextpad=0.7,
    )
    legend.set_zorder(3)
    return ax
def byline_furniture(fig, ax_map, bottom: float, right: float = 0.94,
                     width: float = 0.30, height: float = 0.052):
    """Scale bar and north mark, set on the byline row rather than on the map.

    Orientation and scale are reference information, not part of the picture.
    Putting them on the same line as the byline frees the map and removes the
    dead space a shared panel would need.
    """
    ax = fig.add_axes([right - width, bottom, width, height], zorder=6)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.patch.set_alpha(0)

    # The bar has to measure what it says it measures. The map axes spans the
    # whole page, so a distance of `total` kilometres occupies `total/span` of
    # the page width, and this furniture axes is `width` of that page. Picking
    # a round number and then letting the layout size the box, which is what
    # this did before, prints a number the box does not represent.
    xmin, xmax = ax_map.get_xlim()
    span_km = abs(xmax - xmin) / 1000
    # Room the box may take, leaving the unit label clear of the north
    # mark. A correctly-sized bar is longer than the old decorative one,
    # and the first honest render pushed "Km" into the N.
    room = 0.46

    nice = [1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000]
    fits = [v for v in nice if (v / span_km) / width <= room]
    total = max(fits) if fits else min(nice)
    box_width = (total / span_km) / width

    scale_glyph(ax, total, centre_y=0.42, left=0.02, right=0.72,
                box_width=box_width)
    north_glyph(ax, centre=(0.90, 0.50), height=0.94)
    return ax, total


def locator(fig, point: tuple, coastlines, xy=(0.75, 0.60),
            size: tuple = None, radius_km: float = 3000.0, borders=None):
    """Locator centred on the event, cut to a fixed radius.

    An azimuthal equidistant projection about the event puts it at the centre
    by construction, and clipping to a constant radius means every post is
    framed identically — the reader learns the scale once.
    """
    from matplotlib.patches import Circle
    from pyproj import Transformer

    size = size or LOCATOR_SIZE
    lon, lat = point
    proj = (f"+proj=aeqd +lat_0={lat} +lon_0={lon} +x_0=0 +y_0=0 "
            f"+datum=WGS84 +units=m +no_defs")
    to_local = Transformer.from_crs("EPSG:4326", proj, always_xy=True)

    ax = fig.add_axes([xy[0], xy[1], size[0], size[1]], zorder=5)
    ax.patch.set_alpha(0)
    limit = radius_km * 1000

    # Clip in geographic space first. Projecting the whole globe and cropping
    # afterwards fails: points near the antipode blow up and the projection
    # wraps them back across the disc.
    from shapely.geometry import LineString, Point as ShapelyPoint

    span_deg = radius_km / 111.0 * 1.25
    window = ShapelyPoint(lon, lat).buffer(span_deg, quad_segs=64)

    clip = Circle((0, 0), limit, transform=ax.transData)

    def draw(segments, **style):
        """Clip in geographic space, then project, then draw."""
        for xs, ys in segments:
            ring = LineString(np.column_stack([np.asarray(xs), np.asarray(ys)]))
            piece = ring.intersection(window)
            if piece.is_empty:
                continue
            parts = piece.geoms if hasattr(piece, "geoms") else [piece]
            for part in parts:
                if part.geom_type != "LineString" or len(part.coords) < 2:
                    continue
                arr = np.asarray(part.coords)
                px, py = to_local.transform(arr[:, 0], arr[:, 1])
                px, py = np.asarray(px), np.asarray(py)
                good = np.isfinite(px) & np.isfinite(py)
                if good.sum() < 2:
                    continue
                line, = ax.plot(px[good], py[good], **style)
                line.set_clip_path(clip)

    # The weight every line inside the disc is judged against. The outer ring
    # is drawn at the same width and the same full opacity, rather than at its
    # own fainter value, so it reads as the frame the coastline sits inside
    # rather than as a second, weaker line competing with it.
    coastline_lw = 0.95

    # Borders under the coast, and dotted: a political line is context for the
    # coastline rather than a feature of equal weight.
    if borders:
        draw(borders, color="#0A0C0E", lw=0.7, alpha=0.55,
             ls=(0, (1.0, 1.6)), dash_capstyle="round", zorder=1)
    draw(coastlines, color="#0A0C0E", lw=coastline_lw, solid_capstyle="round",
         solid_joinstyle="round", zorder=2)

    ax.plot(0, 0, "o", ms=10, color="#D62828", markeredgecolor="none",
            zorder=4)
    ax.add_patch(Circle((0, 0), limit, facecolor="none", edgecolor="#0A0C0E",
                        lw=coastline_lw, zorder=3))

    # The disc is inscribed in a square axes, so its top, bottom, left and
    # right points sit exactly on the data limits. A stroke is centred on its
    # path, so half its width falls outside that limit and the default axes
    # clipping cuts it off there — visible as four flat notches rather than a
    # round rim. Padding the limits past the disc's own radius gives the
    # stroke room to sit fully inside the axes without changing what the
    # radius means.
    pad = limit * 0.035
    ax.set_xlim(-limit - pad, limit + pad)
    ax.set_ylim(-limit - pad, limit + pad)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    return ax


# ---------------------------------------------------------------------------
# Automatic placement
# ---------------------------------------------------------------------------


def place_boxes(information: np.ndarray, sizes: list) -> list:
    """Positions for overlay boxes that hide as little information as possible.

    ``information`` is a boolean array covering the canvas, True where there is
    something a reader would not want covered. ``sizes`` is a list of
    (width, height) in figure coordinates, placed in order of priority: each
    box takes the best remaining slot, then blocks it for the ones after.
    """
    h, w = information.shape
    cw = CANVAS["right"] - CANVAS["left"]
    ch = CANVAS["top"] - CANVAS["bottom"]
    pad = 0.012

    taken, placed = [], []

    for (bw, bh) in sizes:
        # Bubbles may spill past the canvas edge, which reads as depth, but
        # never past the image itself.
        left = max(0.012, CANVAS["left"] - bw * 0.32)
        right = min(1 - bw - 0.012, CANVAS["right"] - bw + bw * 0.32)
        bottom = CANVAS["bottom"] + pad
        top = CANVAS["top"] - bh - pad
        mid_y = (bottom + top) / 2
        slots = [
            (left, top), (right, top), (left, bottom), (right, bottom),
            (left, mid_y), (right, mid_y),
        ]

        scored = []
        for (bx, by) in slots:
            if any(bx < tx + tw and bx + bw > tx and by < ty + th and by + bh > ty
                   for (tx, ty, tw, th) in taken):
                continue
            fx0 = (bx - CANVAS["left"]) / cw
            fx1 = (bx + bw - CANVAS["left"]) / cw
            fy0 = (by - CANVAS["bottom"]) / ch
            fy1 = (by + bh - CANVAS["bottom"]) / ch
            c0, c1 = int(np.clip(fx0, 0, 1) * w), int(np.clip(fx1, 0, 1) * w)
            r0, r1 = int((1 - np.clip(fy1, 0, 1)) * h), int((1 - np.clip(fy0, 0, 1)) * h)
            patch = information[r0:r1, c0:c1]
            scored.append((float(patch.mean()) if patch.size else 1.0, (bx, by)))

        if not scored:
            scored = [(1.0, (left, bottom))]
        scored.sort(key=lambda s: s[0])
        pos = scored[0][1]
        placed.append(pos)
        taken.append((pos[0], pos[1], bw, bh))

    return placed


BUBBLE_PRIMARY_R = 0.115
BUBBLE_SECONDARY_R = 0.095
LOCATOR_SIZE = (0.165, 0.132)
LOCATOR_XY = (0.775, 0.756)      # top edge aligned with the title
PANEL_XY = (0.655, 0.192)        # bottom right, constant

PANEL_SIZE = (0.285, 0.150)



def circle_slot(radius: float) -> tuple:
    """Bounding-box size of a circular bubble, for the placement solver."""
    ar = PORTRAIT[0] / PORTRAIT[1]
    return (2 * radius, 2 * radius * ar)


def slot_centre(xy: tuple, radius: float) -> tuple:
    ar = PORTRAIT[0] / PORTRAIT[1]
    return (xy[0] + radius, xy[1] + radius * ar)


# ---------------------------------------------------------------------------
# Map furniture
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Page furniture
# ---------------------------------------------------------------------------


def peril_icon(fig, peril: str, xy=(0.06, 0.947), size: float = 0.036):
    colour = PERIL_COLOURS.get(peril, THEME["text"])
    ax = fig.add_axes([xy[0], xy[1] - size, size * (PORTRAIT[1] / PORTRAIT[0]), size],
                      zorder=6)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.patch.set_alpha(0)

    if peril == "flood":
        for i, y in enumerate((0.26, 0.47, 0.68)):
            x = np.linspace(0.06, 0.94, 120)
            ax.plot(x, y + 0.052 * np.sin((x - 0.06) * 9.5), color=colour,
                    lw=3.2, solid_capstyle="round", alpha=1.0 - i * 0.20)
    elif peril == "wildfire":
        t = np.linspace(0, 1, 100)
        ax.fill(0.5 + 0.30 * np.sin(t * np.pi) * (1 - t), 0.10 + 0.84 * t,
                color=colour)
    elif peril == "earthquake":
        x = np.linspace(0.06, 0.94, 220)
        ax.plot(x, 0.5 + 0.36 * np.sin(x * 22) * np.exp(-((x - 0.5) ** 2) / 0.03),
                color=colour, lw=3.2, solid_capstyle="round")
    else:
        ax.add_patch(plt.Circle((0.5, 0.5), 0.34, color=colour))
    return ax


_brand_mark_cache = None


def _brand_mark_crop():
    """The wordmark image, cropped to its own ink so no blank margin is spent.

    The source file is a square avatar with the mark sitting inside a lot of
    padding, sized for a profile picture rather than a corner lockup. Cropping
    to the content's own bounding box means the space this function is given
    on the page goes to the mark, not to the paper around it.
    """
    global _brand_mark_cache
    if _brand_mark_cache is not None:
        return _brand_mark_cache

    import numpy as _np
    from PIL import Image as _Image

    img = _np.asarray(_Image.open(BRAND_MARK).convert("RGB"))
    background = img[0, 0].astype(int)
    ink = (_np.abs(img.astype(int) - background).sum(axis=2)) > 18
    rows, cols = _np.where(ink)
    if rows.size == 0:
        _brand_mark_cache = img
        return img

    pad = max(2, int(round(0.015 * max(img.shape[:2]))))
    r0, r1 = max(0, rows.min() - pad), min(img.shape[0], rows.max() + pad)
    c0, c1 = max(0, cols.min() - pad), min(img.shape[1], cols.max() + pad)
    _brand_mark_cache = img[r0:r1, c0:c1]
    return _brand_mark_cache


def brand_mark(fig, xy=(0.94, 0.929), height: float = 0.058):
    """The wordmark image, anchored top-right at its own aspect ratio.

    `xy` is the mark's right edge and vertical centre, in figure fraction —
    the spot the text lockup used to occupy. `height` is sized to that same
    row; the width follows from the crop's own aspect ratio, converted through
    the page's non-square pixel grid, so the mark is never stretched.
    """
    crop = _brand_mark_crop()
    crop_h, crop_w = crop.shape[:2]

    height_px = height * PORTRAIT[1]
    width_px = height_px * (crop_w / crop_h)
    width = width_px / PORTRAIT[0]

    ax = fig.add_axes([xy[0] - width, xy[1] - height / 2, width, height],
                      zorder=6)
    ax.imshow(crop)
    ax.axis("off")
    return ax


def header(fig, title: str, subtitle: str = "", peril: str = "flood"):
    peril_icon(fig, peril)
    fig.text(0.06, 0.888, title, fontsize=TYPE["title"], fontweight="bold",
             color=THEME["text"], va="top", ha="left", zorder=6)
    if subtitle:
        fig.text(0.06, 0.846, subtitle, fontsize=TYPE["subtitle"],
                 color=THEME["muted"], va="top", ha="left", zorder=6)
    brand_mark(fig)
    return fig


def _wrap_to_margin(fig, text: str, fontsize: float,
                    left: float = 0.06, right: float = 0.94) -> str:
    """Wrap text so lines reach the right margin without crossing it.

    The wrap width is found by measuring candidate strings with the renderer
    and widening until the next word would overflow. Estimating from character
    counts leaves either a ragged short block or text off the edge.
    """
    import textwrap

    limit_px = (right - left) * PORTRAIT[0]
    renderer = fig.canvas.get_renderer()
    probe = fig.text(0, -1, "", fontsize=fontsize)

    def width_of(s: str) -> float:
        probe.set_text(s)
        return probe.get_window_extent(renderer).width

    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if current and width_of(trial) > limit_px:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)

    probe.remove()
    return "\n".join(lines)


def footer(fig, sources: str, byline: str, notes: str = "",
           disclaimer: str = DISCLAIMER):
    """Byline, numbered notes, disclaimer, sources.

    The byline is set larger than everything else here on purpose: the point of
    publishing is that a reader remembers who did the work.

    `disclaimer` is overridable because the default one describes a modelled
    estimate, and the weekly digest models nothing. A disclaimer that disclaims
    something the graphic does not contain is noise at best.
    """
    fig.text(0.06, 0.128, byline, fontsize=TYPE["byline"], fontweight="bold",
             color=THEME["text"], va="top", ha="left", zorder=6)

    y = 0.096
    if notes:
        wrapped = _wrap_to_margin(fig, notes, TYPE["caption"])
        fig.text(0.06, y, wrapped, fontsize=TYPE["caption"],
                 color=THEME["text"], va="top", ha="left", zorder=6,
                 linespacing=1.5)
        y -= 0.0205 * (wrapped.count("\n") + 1)

    wrapped_disclaimer = _wrap_to_margin(fig, disclaimer, TYPE["caption"])
    fig.text(0.06, y, wrapped_disclaimer, fontsize=TYPE["caption"],
             color=THEME["text"], va="top", ha="left", zorder=6)
    y -= 0.026 * (wrapped_disclaimer.count("\n") + 1)

    fig.text(0.06, y, _wrap_to_margin(fig, sources, TYPE["credit"]),
             fontsize=TYPE["credit"], color=THEME["faint"], va="top",
             ha="left", zorder=6, linespacing=1.5)
    return fig
def label_is_clear(map_xy: tuple, extent: tuple, reserved: list,
                   margin: float = 0.055) -> bool:
    """Whether a map label would land somewhere a reader can actually see it.

    Rejects anything falling off the sheet or under a fixed panel. Labels are
    context, so one that collides with the figures is worse than no label.
    """
    x, y = map_xy
    fx = (x - extent[0]) / (extent[2] - extent[0])
    fy = (y - extent[1]) / (extent[3] - extent[1])
    if not (margin < fx < 1 - margin):
        return False
    if not (CANVAS["bottom"] + 0.01 < fy < CANVAS["top"] + 0.05):
        return False
    return not any(rx <= fx <= rx + rw and ry <= fy <= ry + rh
                   for (rx, ry, rw, rh) in reserved)
