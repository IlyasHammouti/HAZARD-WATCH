"""The weekly digest as a short video: the week's events one after another,
on a map that flies from each to the next.

Three steps, and the middle one is a person:

1. `candidates(monday)` lists what the week holds and writes a picks file,
   pre-filled with a suggestion.
2. The picks file is edited by hand: lines deleted, reordered, a clip added.
3. `render(monday)` turns the picks into an MP4 and a cover image, with a
   sound layer: a whoosh under every camera flight, an ambient bed under
   every scene, matched to its hazard.

    conda run -n climada_env python video.py candidates 2026-09-28
    conda run -n climada_env python video.py render 2026-09-28

The image digest (`report.weekly_digest`) is unaffected and still produced on
its own.

How the frames are made
-----------------------
Cartography is expensive, so it happens once per place. Each scene's map is
drawn a single time with matplotlib in Web Mercator; whatever moves (a track
drawing itself, a pulse, a label fading in) is composited on top of that
frozen image with numpy. Between scenes the camera flies from one frozen image
to the next and nothing is re-projected. Mercator is what makes that exact:
every map here is a crop of the same plane, so a zoom is a crop and a pan is a
shift.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import warnings
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

import carto
import natcat
import report

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

FPS = 30
W, H = carto.PORTRAIT
R = 6378137.0                      # Web Mercator sphere
WORLD = 2 * math.pi * R            # width of the whole plane, metres
MAX_LAT = 85.0

# Perils that get a scene of their own. Drought is shown on the closing world
# view only: it has no point and no motion to zoom in on.
SCENE_TYPES = ("TC", "EQ", "VO", "FL", "WF")

# Seconds on screen, by peril. A track needs time to be followed; a point
# needs only long enough to be found and read.
SCENE_SECONDS = {"TC": 10.0, "EQ": 7.0, "VO": 7.0, "FL": 6.5, "WF": 6.5}
INTRO_SECONDS = 3.2
OUTRO_HOLD = 4.0
DROUGHT_STAGGER = 1.0
END_SECONDS = 5.5

# Green events listed as candidates, per peril. The suggestion takes one or
# two per peril; the rest are there to be swapped in by hand.
GREEN_PER_TYPE = 4

# Ground shown around a point event, kilometres across.
POINT_WIDTH_KM = {"EQ": 900, "VO": 600, "FL": 900, "WF": 700}
TRACK_MIN_KM = 900

PERIL_KEY = {"TC": "storm", "EQ": "earthquake", "VO": "volcano",
             "FL": "flood", "WF": "wildfire", "DR": "drought"}

# Frame layout, in pixels. The map runs edge to edge; its information sits
# between the header and the title card.
MARGIN = 64
SAFE_TOP, SAFE_BOTTOM = 205, 880
LABEL_TOP = 250                    # place names stay clear of the header fade
# The paper band at the bottom never moves: it fades in from BAND_FADE and is
# solid from BAND_SOLID, whether or not a card is on it.
BAND_FADE, BAND_SOLID = 870, 1000
OWNER = "© Ilyas Hammouti"
# Where the owner's mark sits, bottom right of the map, clear of the fade.
OWNER_BOX = (W - 36 - 200, BAND_FADE - 42, W - 36, BAND_FADE - 6)
FOCUS_Y = (SAFE_TOP + SAFE_BOTTOM) / 2 / H
WORLD_LATS = (-58.0, 78.0)
WORLD_SCALE = 3                    # world map resolution, for the zooms

# Relief strength: the 95th percentile slope of every map is brought to this,
# so a continent and a valley carry the same amount of shading.
RELIEF = 1.4
TINT_TOP_M = 3200.0

TRACK_COLOURS = {-1: "#4C9C94", 0: "#2A8A81", 1: "#1B7F79", 2: "#136E68",
                 3: "#0D5C57", 4: "#084944", 5: "#043633",
                 None: "#7F8C8A"}       # position known, wind not published yet

# Sound. Every file is under the Mixkit Sound Effects Free License
# (https://mixkit.co/license/#sfxFree — commercial use, social media video
# posts, no attribution required) and long enough to cover its longest scene
# without looping, so mixing is trim-and-fade, never loop-and-splice. Fetched
# once and cached like the IBTrACS file; never committed, since that licence
# forbids redistributing an item "on its own... with source files" — a public
# repo cloning the raw file would be exactly that.
SOUND_SOURCES = {
    "transition_whoosh.mp3": "https://assets.mixkit.co/active_storage/sfx/1474/1474-preview.mp3",
    "earthquake_rumble.mp3": "https://assets.mixkit.co/active_storage/sfx/1296/1296-preview.mp3",
    "earthquake_shock.mp3": "https://assets.mixkit.co/active_storage/sfx/1686/1686-preview.mp3",
    "cyclone_wind.mp3": "https://assets.mixkit.co/active_storage/sfx/1200/1200-preview.mp3",
    "wildfire_crackle.mp3": "https://assets.mixkit.co/active_storage/sfx/1333/1333-preview.mp3",
    "flood_water.mp3": "https://assets.mixkit.co/active_storage/sfx/3126/3126-preview.mp3",
    "volcano_rumble.mp3": "https://assets.mixkit.co/active_storage/sfx/2438/2438-preview.mp3",
    "volcano_burst.mp3": "https://assets.mixkit.co/active_storage/sfx/2449/2449-preview.mp3",
}
BED_SOUND = {"TC": "cyclone_wind.mp3", "EQ": "earthquake_rumble.mp3",
             "VO": "volcano_rumble.mp3", "FL": "flood_water.mp3",
             "WF": "wildfire_crackle.mp3"}
BED_FADE = 0.6
# Every clip is peak-normalised to the same ceiling rather than mixed by ear
# (see `_peak_gain_db`): eight sources from eight different recordings are
# never at the same level to start with, and picking one number per hazard by
# ear only fixes the clip actually being listened to at the time. Measured
# 28 September 2026, before normalising: -0.1 dB down to -32.6 dB across the
# eight files — the wildfire crackle sat at -20.5 dB, inaudible next to
# anything else in the mix at any gain that didn't also blow out its noise
# floor once boosted on its own.
TARGET_PEAK_DB = -3.0
# The transition whoosh sits under the hazard beds, not level with them: 60 %
# of their target amplitude (a listener's "volume knob" reading, not a dB
# figure), which is -3.0 + 20*log10(0.6) dB.
TRANSITION_PEAK_DB = TARGET_PEAK_DB + 20 * math.log10(0.6)
SOUND_DIR = report.CACHE / "sounds"

VIDEO_DIR = report.OUTPUT / "digests" / "video"
VIDEO_CACHE = report.CACHE / "video"
DEM_ASSET = "USGS/GMTED2010_FULL"

# Credited only when used (rules section 8): IBTrACS only in a week that
# shows a cyclone track. GDACS is credited through its locked phrase.
TRACK_CREDIT = "Cyclone tracks: IBTrACS v04r01 (NOAA NCEI)."
MAP_CREDIT = "Relief: GMTED2010 (USGS). Places and borders: Natural Earth."

PAPER = np.array(mcolors.to_rgb(carto.THEME["background"]), np.float32)


def rgb(colour) -> np.ndarray:
    return np.array(mcolors.to_rgb(colour), np.float32)


def smooth(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def ramp(t: float, a: float, b: float) -> float:
    return smooth((t - a) / (b - a))


# ---------------------------------------------------------------------------
# Web Mercator
# ---------------------------------------------------------------------------

def mx(lon):
    return R * np.radians(lon)


def my(lat):
    lat = np.clip(lat, -MAX_LAT, MAX_LAT)
    return R * np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))


def lat_of(y):
    return np.degrees(2 * np.arctan(np.exp(np.asarray(y, float) / R)) - np.pi / 2)


def near(lon: float, ref: float) -> float:
    """`lon` moved by whole turns to the copy closest to `ref`.

    Longitudes here are unwrapped: a flight from Japan to Hawaii crosses 180°
    and carries on to 205° rather than jumping back to -155°.
    """
    return lon + 360.0 * round((ref - lon) / 360.0)


class View:
    """What the camera sees: a centre and a width on the Mercator plane."""

    def __init__(self, cx: float, cy: float, width: float):
        self.cx, self.cy, self.width = float(cx), float(cy), float(width)
        self.height = self.width * H / W

    @property
    def box(self) -> tuple:
        return (self.cx - self.width / 2, self.cy - self.height / 2,
                self.cx + self.width / 2, self.cy + self.height / 2)

    @property
    def lon(self) -> float:
        return math.degrees(self.cx / R)

    @property
    def lonlat(self) -> tuple:
        x0, y0, x1, y1 = self.box
        return (math.degrees(x0 / R), float(lat_of(y0)),
                math.degrees(x1 / R), float(lat_of(y1)))

    def px(self, lon, lat):
        """Frame pixels of a point. `lon` must already be near this view."""
        x0, y0, x1, y1 = self.box
        return ((mx(np.asarray(lon, float)) - x0) / self.width * W,
                (y1 - my(np.asarray(lat, float))) / self.height * H)

    def zoom(self) -> float:
        """Web map zoom level, which Natural Earth's label fields are keyed to."""
        return math.log2(WORLD / self.width * W / 256)


def point_view(lon: float, lat: float, width_km: float) -> View:
    """A view with the point on the frame's focus, `width_km` of ground across."""
    width = width_km * 1000 / max(math.cos(math.radians(lat)), 0.2)
    return View(mx(lon), my(lat) - width * H / W * (0.5 - FOCUS_Y), width)


def fit_view(lons, lats, min_km: float = TRACK_MIN_KM, fill: float = 0.78) -> View:
    """The smallest view that holds every point inside the map's safe area."""
    xs, ys = mx(np.asarray(lons, float)), my(np.asarray(lats, float))
    safe_w = (W - 2 * MARGIN) / W * fill
    safe_h = (SAFE_BOTTOM - SAFE_TOP) / H * fill
    lat_c = float(np.mean(lats))
    width = max((xs.max() - xs.min()) / safe_w,
                (ys.max() - ys.min()) / safe_h * W / H,
                min_km * 1000 / max(math.cos(math.radians(lat_c)), 0.2))
    return View((xs.min() + xs.max()) / 2,
                (ys.min() + ys.max()) / 2 - width * H / W * (0.5 - FOCUS_Y),
                width)


def world_view(lon: float, lons=(), whole: bool = False) -> View:
    """The world, its inhabited band centred between header and card.

    Cropped to 80 % of the globe's width when every event fits, which makes
    the map a quarter larger; the part left out is the widest stretch where
    nothing happened, since `gap_centre` puts it at the edges. `whole` keeps
    the full width, for the map the camera flies over.
    """
    spread = max((abs(near(l, lon) - lon) for l in lons), default=0.0)
    degrees = 360.0 if whole else min(360.0, max(288.0, 2 * (spread + 25)))
    width = WORLD * degrees / 360
    band = (my(WORLD_LATS[0]) + my(WORLD_LATS[1])) / 2
    return View(mx(lon), band - width * H / W * (0.5 - FOCUS_Y), width)


def gap_centre(lons: list) -> float:
    """Centre longitude that puts the widest empty stretch at the map's edge.

    A world map cut through the middle of the Pacific splits a week of
    Pacific storms across both edges. Cutting where nothing happened keeps
    every event whole.
    """
    if not lons:
        return 10.0
    ring = sorted(lon % 360 for lon in lons)
    gaps = [((ring[(i + 1) % len(ring)] - ring[i]) % 360) or 360.0
            for i in range(len(ring))]
    i = int(np.argmax(gaps))
    centre = (ring[i] + gaps[i] / 2 + 180) % 360
    return centre - 360 if centre >= 180 else centre


def camera(a: View, b: View, p: float) -> View:
    """The camera part way from `a` to `b`, `p` from 0 to 1.

    Zoom is interpolated on a log scale, which is what makes it look steady,
    and bows outwards when the two places are far apart, so both are briefly
    on screen and the viewer sees where the next event is.
    """
    s = smooth(p)
    u = p ** 3 * (p * (6 * p - 15) + 10)
    d = math.hypot(b.cx - a.cx, b.cy - a.cy)
    lift = max(0.0, math.log(max(1.4 * d / max(a.width, b.width), 1e-9)))
    width = math.exp((1 - s) * math.log(a.width) + s * math.log(b.width)
                     + lift * math.sin(math.pi * s))
    return View(a.cx + (b.cx - a.cx) * u, a.cy + (b.cy - a.cy) * u,
                min(width, WORLD * 1.2))


def flight_seconds(a: View, b: View) -> float:
    d = math.hypot(b.cx - a.cx, b.cy - a.cy)
    lift = max(0.0, math.log(max(1.4 * d / max(a.width, b.width), 1e-9)))
    zoom = abs(math.log(a.width / b.width))
    return float(np.clip(1.5 + 0.2 * zoom + 0.35 * lift, 1.6, 3.0))


# ---------------------------------------------------------------------------
# Candidates and picks
# ---------------------------------------------------------------------------

def week_of(monday) -> tuple:
    """`(monday, first day, last day)`, the same window as the image digest."""
    if isinstance(monday, str):
        monday = date.fromisoformat(monday)
    return monday, monday - timedelta(days=7), monday - timedelta(days=1)


def key_of(event: dict) -> str:
    return f"{event['event_type']}-{event['event_id']}"


def _week_peak(event: dict, start: date, end: date) -> dict | None:
    """A cyclone's strongest IBTrACS fix inside the week, or None.

    GDACS keeps only the alert level of a storm's latest advisory: POLO-26
    reached Category 5 in the week of 21 September 2026 and was listed Green
    by the 25th, once it had weakened. The alert level alone would have
    passed it over for a 45 kt tropical storm.
    """
    opens = datetime.combine(start, datetime.min.time())
    closes = datetime.combine(end + timedelta(days=1), datetime.min.time())
    try:
        fixes = natcat.cyclone_track(event)["fixes"]
    except Exception as error:                                 # noqa: BLE001
        warnings.warn(f"No track for {event.get('event_name')}: {error}",
                      stacklevel=2)
        return None
    inside = [f for f in fixes if opens <= f["time"] < closes and f["wind_kt"]]
    if not inside:
        return None
    peak = max(inside, key=lambda f: f["wind_kt"])
    return {"wind_kt": peak["wind_kt"], "category": peak["category"]}


def _serious(event: dict) -> bool:
    """Orange or Red, or a cyclone that reached Category 3 in the week."""
    peak = event.get("week_peak") or {}
    return (event["alert_level"] != "Green"
            or (peak.get("category") is not None and peak["category"] >= 3))


def _significance(event: dict) -> tuple:
    level = {"Red": 2, "Orange": 1}.get(event["alert_level"], 0)
    peak = (event.get("week_peak") or {}).get("wind_kt") or 0
    return (_serious(event), peak, level, event.get("alert_score") or 0,
            float(event.get("severity") or 0), event["from_date"])


def _describe(event: dict, regions: dict) -> str:
    """One readable line, built with the image digest's own wording rules."""
    peril = report._digest_peril(event)
    place = report._digest_place(event, regions)
    if event["event_type"] == "DR":
        region = _drought_region(event)
        place = region or place
    parts = [f"{peril}, {place}" if place else peril, event["alert_level"],
             report._digest_dates(event)]
    peak = event.get("week_peak")
    if peak:
        parts.append(f"peak in the week {_category_name(peak['category'])}, "
                     f"{peak['wind_kt']:.0f} kt (IBTrACS)")
    elif report._digest_fact(event):
        parts.append(report._digest_fact(event))
    return " - ".join(parts)


def _drought_region(event: dict) -> str:
    """`East Africa-2026` is GDACS's slug for the alert; the region is the rest."""
    return re.sub(r"-\d{4}$", "", (event.get("event_name") or "").strip())


def candidates(monday) -> dict:
    """Every event the video could show this week, and a suggested pick.

    Scene candidates are the image digest's own: what began in the week,
    anything at Red, and the best Green events of each peril. Cyclones are
    taken whenever they ran during the week, whatever their start: their
    track through the week is new even when the storm is not. Droughts go
    to the closing world view, Orange and Red ones by default.
    """
    monday, start, end = week_of(monday)
    days = (end - start).days

    serious = natcat.gdacs_events(days=days, types=SCENE_TYPES + ("DR",),
                                  alert_levels=("Orange", "Red"), end=end)
    pool = {}
    for event in serious:
        kind = event["event_type"]
        if (kind in ("TC", "DR") or event["is_new"]
                or event["alert_level"] == "Red"):
            pool[key_of(event)] = event
    for event in natcat.gdacs_events(days=days, types=("TC", "DR"),
                                     alert_levels=("Green",), end=end):
        pool.setdefault(key_of(event), event)
    for kind in ("EQ", "VO", "FL", "WF"):
        greens = sorted(natcat._green_started(kind, start, end),
                        key=natcat._green_rank, reverse=True)
        for event in greens[:GREEN_PER_TYPE]:
            pool.setdefault(key_of(event), event)

    events = list(pool.values())
    for event in events:
        if event["event_type"] == "TC":
            event["week_peak"] = _week_peak(event, start, end)
    regions = natcat.event_regions(events)
    history = report._load_featured_history()

    by_type = {}
    for event in sorted(events, key=_significance, reverse=True):
        by_type.setdefault(event["event_type"], []).append(event)

    suggested = []
    for kind in SCENE_TYPES:
        ranked = by_type.get(kind, [])
        serious_ones = [e for e in ranked if _serious(e)]
        suggested += serious_ones[:2] or ranked[:1]
    suggested.sort(key=lambda e: e["from_date"])
    chosen = {key_of(e) for e in suggested}

    def record(event):
        shown = history.get(str(event["event_id"]))
        return {
            **{k: (v.isoformat() if isinstance(v, datetime) else v)
               for k, v in event.items()},
            "key": key_of(event),
            "region": regions.get(event["event_id"], ""),
            "label": _describe(event, regions),
            "shown_before": (shown or {}).get("first_shown", ""),
            "suggested": key_of(event) in chosen
                         or (event["event_type"] == "DR"
                             and event["alert_level"] != "Green"),
        }

    ordered = suggested + [e for kind in SCENE_TYPES
                           for e in by_type.get(kind, [])
                           if key_of(e) not in chosen]
    return {
        "monday": str(monday),
        "window": [str(start), str(end)],
        "scenes": [record(e) for e in ordered],
        "droughts": [record(e) for e in by_type.get("DR", [])],
    }


def _paths(monday) -> dict:
    monday = week_of(monday)[0]
    return {"candidates": VIDEO_DIR / f"{monday}-candidates.json",
            "picks": VIDEO_DIR / f"{monday}-picks.txt",
            "video": VIDEO_DIR / f"{monday}-digest.mp4",
            "cover": VIDEO_DIR / f"{monday}-cover.png"}


def write_picks(found: dict) -> dict:
    """Write the candidates file and the editable picks file."""
    paths = _paths(found["monday"])
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    paths["candidates"].write_text(json.dumps(found, indent=1), encoding="utf-8")

    start, end = (date.fromisoformat(d) for d in found["window"])

    def line(c, on):
        note = f"   [named in the {c['shown_before']} digest]" \
            if c["shown_before"] else ""
        return f"{'' if on else '# '}{c['key']:<12} {c['label']}{note}"

    rows = [
        f"# Hazard Watch video digest, week of {report._date_span(start, end)}",
        "#",
        "# One line per scene, played in this order. To drop a scene, delete",
        "# its line or put # in front. To add one, remove the # in front of a",
        "# candidate. Move lines to reorder.",
        "#",
        "# To play a clip after a scene, add it to the end of that line:",
        "#   | clip=C:\\path\\to\\video.mp4 | source=Name of the source",
        "# and optionally | from=3 | to=12 (seconds) to keep part of it.",
        "#",
        "# --- Scenes ---------------------------------------------------------",
    ]
    scenes = found["scenes"]
    rows += [line(c, True) for c in scenes if c["suggested"]]
    rows += ["#", "# --- Other candidates -----------------------------------------------"]
    rows += [line(c, False) for c in scenes if not c["suggested"]]
    rows += ["#", "# --- Drought, closing world view ------------------------------------"]
    rows += [line(c, c["suggested"]) for c in found["droughts"]]
    paths["picks"].write_text("\n".join(rows) + "\n", encoding="utf-8")
    return paths


PICK_LINE = re.compile(r"^(TC|EQ|VO|FL|WF|DR)-\d+$")


def read_picks(path) -> tuple:
    """`(scenes, droughts)` from a picks file.

    Scenes are `{"key", "clip", "source", "from", "to"}` in file order;
    droughts are keys.
    """
    scenes, droughts = [], []
    for number, raw in enumerate(Path(path).read_text(encoding="utf-8")
                                 .splitlines(), 1):
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        head, *options = [part.strip() for part in text.split("|")]
        key = head.split()[0]
        if not PICK_LINE.match(key):
            raise ValueError(f"{path}, line {number}: '{key}' is not an event "
                             f"key such as TC-1001325")
        if key.startswith("DR-"):
            droughts.append(key)
            continue
        pick = {"key": key, "clip": None, "source": None,
                "from": None, "to": None}
        for option in options:
            name, _, value = option.partition("=")
            name, value = name.strip().lower(), value.strip().strip('"')
            if name in ("from", "to"):
                pick[name] = float(value)
            elif name in ("clip", "source"):
                pick[name] = value
        if pick["clip"] and not pick["source"]:
            raise ValueError(f"{path}, line {number}: a clip needs its source "
                             f"(| source=...), which is printed on screen")
        if pick["clip"] and not Path(pick["clip"]).exists():
            raise FileNotFoundError(f"{path}, line {number}: no file at "
                                    f"{pick['clip']}")
        scenes.append(pick)
    return scenes, droughts


def _load_event(record: dict) -> dict:
    event = dict(record)
    for field in ("from_date", "to_date"):
        event[field] = datetime.fromisoformat(event[field])
    return event


# ---------------------------------------------------------------------------
# Geography
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def natural_earth(name: str, resolution: str = "50m",
                  category: str = "cultural"):
    import cartopy.io.shapereader as shapereader
    import geopandas

    return geopandas.read_file(shapereader.natural_earth(
        resolution=resolution, category=category, name=name))


def _detail(view: View) -> str:
    return "10m" if view.width < 6e6 else "50m"


def clipped(frame, view: View, pad: float = 0.15) -> list:
    """`(row index, geometry)` of a GeoDataFrame inside the view, in metres.

    Clipped in longitude and latitude first, one copy per turn of the globe
    the view overlaps, so a view straddling 180° gets both halves of Fiji.
    """
    import shapely

    lon0, lat0, lon1, lat1 = view.lonlat
    dx, dy = (lon1 - lon0) * pad, (lat1 - lat0) * pad
    lon0, lon1 = lon0 - dx, lon1 + dx
    lat0, lat1 = max(lat0 - dy, -MAX_LAT), min(lat1 + dy, MAX_LAT)

    out = []
    for turn in range(math.floor((lon0 + 180) / 360),
                      math.floor((lon1 + 180) / 360) + 1):
        shift = 360.0 * turn
        cut = frame.geometry.clip_by_rect(lon0 - shift, lat0, lon1 - shift, lat1)
        cut = cut[~cut.is_empty]
        for index, geometry in zip(cut.index, cut.values):
            out.append((index, shapely.transform(
                geometry, lambda c, s=shift: np.column_stack(
                    [mx(c[:, 0] + s), my(c[:, 1])]))))
    return out


def _rings(geometry) -> list:
    kind = geometry.geom_type
    if geometry.is_empty:
        return []
    if kind in ("LineString", "LinearRing"):
        return [np.asarray(geometry.coords)]
    if kind == "Polygon":
        return ([np.asarray(geometry.exterior.coords)]
                + [np.asarray(r.coords) for r in geometry.interiors])
    return [ring for part in getattr(geometry, "geoms", []) for ring in _rings(part)]


def _draw_lines(ax, geometries, **style):
    lines = [r[:, :2] for g in geometries for r in _rings(g) if len(r) > 1]
    if lines:
        ax.add_collection(LineCollection(lines, **style))


def _fill(ax, geometries, **style):
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as MPath

    for geometry in geometries:
        parts = ([geometry] if geometry.geom_type == "Polygon"
                 else [p for p in getattr(geometry, "geoms", [])
                       if p.geom_type == "Polygon"])
        for polygon in parts:
            rings = ([np.asarray(polygon.exterior.coords)[:, :2]]
                     + [np.asarray(r.coords)[:, :2] for r in polygon.interiors])
            codes = []
            for ring in rings:
                codes += ([MPath.MOVETO] + [MPath.LINETO] * (len(ring) - 2)
                          + [MPath.CLOSEPOLY])
            ax.add_patch(PathPatch(MPath(np.concatenate(rings), codes), **style))


def dem(view: View, scale: int = 1, lats: tuple | None = None):
    """Elevation on the view's own pixel grid, from GMTED2010, or None.

    Earth Engine reprojects to Web Mercator on its side. Longitudes past 180°
    are fetched as separate strips, one per turn of the globe, because the
    service only knows the real ones. Cached on disk by view.
    """
    w, h = W * scale, H * scale
    x0, y0, x1, y1 = view.box
    tag = f"{DEM_ASSET}|{x0:.0f}|{y0:.0f}|{x1:.0f}|{y1:.0f}|{w}|{h}|{lats}"
    path = VIDEO_CACHE / f"dem_{hashlib.sha1(tag.encode()).hexdigest()[:16]}.npy"
    if path.exists():
        return np.load(path)
    if not natcat.ensure_ee():
        warnings.warn("Earth Engine unavailable: maps are drawn without relief.",
                      stacklevel=2)
        return None
    import ee

    image = (ee.Image(DEM_ASSET).select("mea").resample("bilinear")
             .unmask(0).toInt16())
    step_x, step_y = (x1 - x0) / w, (y1 - y0) / h
    lat_lo, lat_hi = lats or (-MAX_LAT, MAX_LAT)
    r0 = max(0, int(math.floor((y1 - my(lat_hi)) / step_y)))
    r1 = min(h, int(math.ceil((y1 - my(lat_lo)) / step_y)))
    out = np.zeros((h, w), np.float32)
    if r1 <= r0:
        return out

    xs = x0 + (np.arange(w) + 0.5) * step_x
    turns = np.floor((xs + WORLD / 2) / WORLD).astype(int)
    chunk = max(1, int(6_000_000 // (r1 - r0)))
    j = 0
    while j < w:
        stop = j
        while stop < w and turns[stop] == turns[j] and stop - j < chunk:
            stop += 1
        grid = {
            "dimensions": {"width": stop - j, "height": r1 - r0},
            "affineTransform": {
                "scaleX": step_x, "shearX": 0,
                "translateX": x0 + j * step_x - turns[j] * WORLD,
                "shearY": 0, "scaleY": -step_y,
                "translateY": y1 - r0 * step_y},
            "crsCode": "EPSG:3857",
        }
        for attempt in range(4):
            try:
                block = ee.data.computePixels({
                    "expression": image, "fileFormat": "NUMPY_NDARRAY",
                    "grid": grid})
                break
            except Exception as error:                         # noqa: BLE001
                if attempt == 3:
                    raise
                warnings.warn(f"Earth Engine retry {attempt + 1}: {error}",
                              stacklevel=2)
                time.sleep(5 * (attempt + 1))
        out[r0:r1, j:stop] = block["mea"].astype(np.float32)
        j = stop

    VIDEO_CACHE.mkdir(parents=True, exist_ok=True)
    np.save(path, out)
    return out


# ---------------------------------------------------------------------------
# Drawing with matplotlib, once per place
# ---------------------------------------------------------------------------

def _figure(view: View, scale: int = 1, transparent: bool = False):
    carto.apply()
    fig = plt.figure(figsize=(W * scale / 100, H * scale / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    if transparent:
        fig.patch.set_alpha(0)
        ax.patch.set_alpha(0)
    return fig, ax


def _raster(fig, ax, view: View) -> np.ndarray:
    x0, y0, x1, y1 = view.box
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("auto")
    fig.canvas.draw()
    array = np.asarray(fig.canvas.buffer_rgba()).copy()
    plt.close(fig)
    return array


def keyframe(view: View, scale: int = 1, lats: tuple | None = None,
             draw=None) -> np.ndarray:
    """The frozen map for one place: relief, water, coast and borders.

    `draw(ax, scale)` adds anything else that never moves. `lats` limits the
    map to a band of latitude and fades to paper beyond it. Returns RGB,
    float32, 0 to 1.
    """
    fig, ax = _figure(view, scale)
    elevation = dem(view, scale, lats)
    detail = _detail(view)
    x0, y0, x1, y1 = view.box

    if elevation is None:
        ax.set_facecolor(carto.WATER)
        fig.patch.set_facecolor(carto.WATER)
        _fill(ax, [g for _, g in clipped(natural_earth("land", detail,
                                                       "physical"), view)],
              facecolor=carto.HYPSOMETRIC[1][1], edgecolor="none", zorder=1)
    else:
        land = elevation > 0
        gy, gx = np.gradient(elevation)
        slope = np.hypot(gx, gy)[land]
        k = (RELIEF / max(float(np.percentile(slope, 95)), 1e-6)
             if slope.size > 500 else 1.0)
        carto.draw_basemap(ax, elevation * k, (x0, x1, y0, y1),
                           vert_exag=1.0, limits=(0.0, TINT_TOP_M * k))

    _fill(ax, [g for _, g in clipped(natural_earth("lakes", detail, "physical"),
                                     view)],
          facecolor=carto.WATER, edgecolor="none", zorder=2)
    # The world map is seen magnified during every flight, so its lines are
    # finer and solid: a dash pattern enlarged four times reads as rubble.
    wide = scale > 1
    _draw_lines(ax, [g for _, g in clipped(natural_earth("coastline", detail,
                                                         "physical"), view)],
                colors="#4F7389", linewidths=(0.3 if wide else 0.55) * scale,
                alpha=0.45 if wide else 0.65, zorder=3)
    _draw_lines(ax, [g for _, g in clipped(natural_earth(
        "admin_0_boundary_lines_land", detail), view)],
                colors="#555C63", linewidths=(0.4 if wide else 0.75) * scale,
                alpha=0.5, zorder=3,
                linestyles="solid" if wide else (0, (4, 2)))
    if draw:
        draw(ax, scale)

    image = _raster(fig, ax, view)[..., :3].astype(np.float32) / 255
    if lats:
        rows = y1 - (np.arange(H * scale) + 0.5) * (y1 - y0) / (H * scale)
        edge = 22 * scale * (y1 - y0) / (H * scale)
        keep = (np.clip((my(lats[1]) - rows) / edge, 0, 1)
                * np.clip((rows - my(lats[0])) / edge, 0, 1))
        keep = (keep * keep * (3 - 2 * keep))[:, None, None]
        image = image * keep + PAPER * (1 - keep)
    return image


def overlay(view: View, draw) -> "Layer":
    """Anything drawn by `draw(ax)` on a transparent frame, as a layer."""
    fig, ax = _figure(view, transparent=True)
    draw(ax)
    return Layer(_raster(fig, ax, view))


# ---------------------------------------------------------------------------
# Compositing, per frame
# ---------------------------------------------------------------------------

class Layer:
    """Premultiplied RGBA, cropped to what it actually covers."""

    def __init__(self, rgba):
        rgba = np.asarray(rgba)
        if rgba.dtype == np.uint8:
            rgba = rgba.astype(np.float32) / 255
        alpha = rgba[..., 3]
        rows, cols = np.nonzero(alpha > 1 / 255)
        self.empty = rows.size == 0
        if self.empty:
            return
        self.y0, self.x0 = int(rows.min()), int(cols.min())
        crop = rgba[self.y0:rows.max() + 1, self.x0:cols.max() + 1].astype(np.float32)
        crop[..., :3] *= crop[..., 3:4]
        self.image = crop
        # Kept apart and ready, so the common case (fully on, no mask) is two
        # in-place operations and no temporary arrays.
        self.rgb = np.ascontiguousarray(crop[..., :3])
        self.inverse = np.ascontiguousarray(1 - crop[..., 3:4])

    def over(self, frame: np.ndarray, alpha: float = 1.0, mask=None,
             dy: int = 0):
        if self.empty or alpha <= 0.002:
            return
        h, w = self.image.shape[:2]
        top, left = self.y0 + dy, self.x0
        a0, a1 = max(0, -top), min(h, frame.shape[0] - top)
        if a1 <= a0:
            return
        region = frame[top + a0:top + a1, left:left + w]
        if mask is None and alpha >= 0.998:
            region *= self.inverse[a0:a1]
            region += self.rgb[a0:a1]
            return
        image = self.image[a0:a1]
        weight = alpha if mask is None else alpha * mask[a0:a1, :, None]
        region *= 1 - image[..., 3:4] * weight
        region += self.rgb[a0:a1] * weight


@lru_cache(maxsize=None)
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    from matplotlib import font_manager

    path = font_manager.findfont(font_manager.FontProperties(
        family=carto.FONT_STACK, weight="bold" if bold else "normal"))
    return ImageFont.truetype(path, size)


def text(image: Image.Image, xy, words: str, size: int, colour,
         bold: bool = False, anchor: str = "ls", alpha: float = 1.0,
         halo=None, halo_strength: float = 0.9) -> float:
    """Anti-aliased text onto a transparent RGBA image; returns its width.

    Drawn as a coverage mask and filled with the colour, so the edges carry
    the text colour at partial opacity rather than a dark fringe.
    """
    face = font(size, bold)
    left, top, right, bottom = ImageDraw.Draw(image).textbbox(
        xy, words, font=face, anchor=anchor)
    pad = 6
    box = (int(left) - pad, int(top) - pad)
    mask = Image.new("L", (int(right - left) + 2 * pad + 2,
                           int(bottom - top) + 2 * pad + 2), 0)
    ImageDraw.Draw(mask).text((xy[0] - box[0], xy[1] - box[1]), words,
                              font=face, anchor=anchor, fill=255)
    if halo is not None:
        glow = mask.filter(ImageFilter.MaxFilter(5)).filter(
            ImageFilter.GaussianBlur(1.5))
        paint = Image.new("RGBA", mask.size, _rgba(halo, 0))
        paint.putalpha(glow.point(lambda v: int(v * halo_strength * alpha)))
        image.alpha_composite(paint, dest=box)
    paint = Image.new("RGBA", mask.size, _rgba(colour, 0))
    paint.putalpha(mask.point(lambda v: int(v * alpha)))
    image.alpha_composite(paint, dest=box)
    return face.getlength(words)


def _rgba(colour, alpha: int = 255) -> tuple:
    r, g, b = (int(round(c * 255)) for c in mcolors.to_rgb(colour))
    return (r, g, b, alpha)


def blank() -> Image.Image:
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def paste(frame: np.ndarray, image: Image.Image, x: float, y: float,
          alpha: float = 1.0):
    """Composite a small RGBA image onto the frame, centred on (x, y)."""
    if alpha <= 0.002:
        return
    array = np.asarray(image, np.float32) / 255
    h, w = array.shape[:2]
    left, top = int(round(x - w / 2)), int(round(y - h / 2))
    a0, a1 = max(0, -top), min(h, frame.shape[0] - top)
    b0, b1 = max(0, -left), min(w, frame.shape[1] - left)
    if a1 <= a0 or b1 <= b0:
        return
    array = array[a0:a1, b0:b1]
    weight = array[..., 3:4] * alpha
    region = frame[top + a0:top + a1, left + b0:left + b1]
    region *= 1 - weight
    region += array[..., :3] * weight


def ring(frame, x, y, radius, width, colour, alpha):
    """An anti-aliased circle outline, drawn only where it lands."""
    if alpha <= 0.002 or radius <= 0:
        return
    reach = radius + width + 2
    y0, y1 = max(0, int(y - reach)), min(frame.shape[0], int(y + reach) + 1)
    x0, x1 = max(0, int(x - reach)), min(frame.shape[1], int(x + reach) + 1)
    if y1 <= y0 or x1 <= x0:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1]
    d = np.hypot(xx + 0.5 - x, yy + 0.5 - y)
    weight = (np.clip(width / 2 - np.abs(d - radius) + 0.5, 0, 1) * alpha)[..., None]
    region = frame[y0:y1, x0:x1]
    region *= 1 - weight
    region += rgb(colour) * weight


@lru_cache(maxsize=None)
def marker(colour: str, number: int | None = None, size: int = 30,
           shape: str = "disc") -> Image.Image:
    """A map marker drawn four times too large and reduced, for clean edges."""
    big = size * 4
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if shape == "triangle":
        pad = big * 0.08
        outline = [(big / 2, pad), (big - pad, big - pad * 1.6), (pad, big - pad * 1.6)]
        draw.polygon(outline, fill=_rgba("#FFFFFF"))
        inner = [(big / 2, pad + big * 0.13), (big - pad - big * 0.12, big - pad * 1.6 - big * 0.07),
                 (pad + big * 0.12, big - pad * 1.6 - big * 0.07)]
        draw.polygon(inner, fill=_rgba(colour))
    else:
        draw.ellipse((0, 0, big - 1, big - 1), fill=_rgba("#FFFFFF"))
        edge = big * 0.12
        draw.ellipse((edge, edge, big - 1 - edge, big - 1 - edge), fill=_rgba(colour))
    if number is not None:
        # Centred on the digits' own ink, not on the font's line box: a
        # font's middle sits between ascender and descender, and digits have
        # no descender, so "mm" leaves every number low in its disc.
        face = font(int(big * 0.5), True)
        glyphs = Image.new("L", (big, big), 0)
        ImageDraw.Draw(glyphs).text((big / 2, big / 2), str(number), font=face,
                                    anchor="mm", fill=255)
        left, top, right, bottom = glyphs.getbbox()
        centre = (big - 1) / 2
        shift = (round(centre - (left + right - 1) / 2),
                 round(centre - (top + bottom - 1) / 2))
        white = Image.new("RGBA", (big, big), _rgba("#FFFFFF"))
        image.paste(white, (0, 0), glyphs.transform(
            glyphs.size, Image.Transform.AFFINE, (1, 0, -shift[0], 0, 1, -shift[1])))
    return image.resize((size, size), Image.Resampling.LANCZOS)


@lru_cache(maxsize=None)
def day_dot(size: int = 14) -> Image.Image:
    """A white dot ringed in ink, marking midnight UTC on a track."""
    big = size * 4
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((2, 2, big - 3, big - 3), fill=_rgba("#FFFFFF"),
                                  outline=_rgba(INK), width=int(big * 0.14))
    return image.resize((size, size), Image.Resampling.LANCZOS)


@lru_cache(maxsize=None)
def cyclone_glyph(colour: str, size: int = 46) -> Image.Image:
    """The cyclone symbol: an eye and two trailing arms."""
    big = size * 4
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    c = big / 2
    for base in (0.0, math.pi):
        theta = np.linspace(0, 1.25 * math.pi, 40)
        radius = big * (0.16 + 0.25 * theta / (1.25 * math.pi))
        points = [(c + r * math.cos(t + base), c - r * math.sin(t + base))
                  for t, r in zip(theta, radius)]
        draw.line(points, fill=_rgba("#FFFFFF"), width=int(big * 0.17), joint="curve")
        draw.line(points, fill=_rgba(colour), width=int(big * 0.09), joint="curve")
    draw.ellipse((c - big * 0.2, c - big * 0.2, c + big * 0.2, c + big * 0.2),
                 fill=_rgba("#FFFFFF"))
    draw.ellipse((c - big * 0.13, c - big * 0.13, c + big * 0.13, c + big * 0.13),
                 fill=_rgba(colour))
    return image.resize((size, size), Image.Resampling.LANCZOS)


class Sprite:
    """A small premultiplied RGBA drawing, made three times too large and
    averaged down, which is what gives the animated glyphs clean edges.
    Coordinates are in the sprite's own pixels."""

    SS = 3

    def __init__(self, size: int):
        self.size, self.big = size, size * self.SS
        self.rgba = np.zeros((self.big, self.big, 4), np.float32)

    def _over(self, alpha: np.ndarray, box: tuple, colour, strength: float):
        y0, y1, x0, x1 = box
        a = (alpha * strength)[..., None]
        region = self.rgba[y0:y1, x0:x1]
        region *= 1 - a
        region[..., :3] += rgb(colour) * a
        region[..., 3:] += a

    def disc(self, x, y, r, colour, strength: float = 1.0, soft: float = 1.0):
        if strength <= 0.002:
            return
        s = self.SS
        cx, cy, radius, edge = x * s, y * s, r * s, max(soft * s, 1.0)
        reach = radius + edge + 1
        x0, x1 = max(0, int(cx - reach)), min(self.big, int(cx + reach) + 1)
        y0, y1 = max(0, int(cy - reach)), min(self.big, int(cy + reach) + 1)
        if x1 <= x0 or y1 <= y0:
            return
        yy, xx = np.mgrid[y0:y1, x0:x1]
        d = np.hypot(xx + 0.5 - cx, yy + 0.5 - cy)
        self._over(np.clip((radius - d) / edge + 0.5, 0, 1).astype(np.float32),
                   (y0, y1, x0, x1), colour, strength)

    def _shape(self, draw, colour, strength: float):
        if strength <= 0.002:
            return
        mask = Image.new("L", (self.big, self.big), 0)
        draw(ImageDraw.Draw(mask), self.SS)
        self._over(np.asarray(mask, np.float32) / 255,
                   (0, self.big, 0, self.big), colour, strength)

    def polygon(self, points, colour, strength: float = 1.0):
        self._shape(lambda d, s: d.polygon([(x * s, y * s) for x, y in points],
                                           fill=255), colour, strength)

    def line(self, points, width: float, colour, strength: float = 1.0):
        def draw(d, s):
            scaled = [(x * s, y * s) for x, y in points]
            d.line(scaled, fill=255, width=max(1, round(width * s)), joint="curve")
            r = width * s / 2
            for px, py in (scaled[0], scaled[-1]):
                d.ellipse((px - r, py - r, px + r, py + r), fill=255)
        self._shape(draw, colour, strength)

    def done(self) -> np.ndarray:
        s = self.SS
        return self.rgba.reshape(self.size, s, self.size, s, 4).mean(axis=(1, 3))


def stamp(frame: np.ndarray, sprite: np.ndarray, x: float, y: float,
          alpha: float = 1.0):
    """Composite a premultiplied sprite onto the frame, centred on (x, y)."""
    if alpha <= 0.002:
        return
    h, w = sprite.shape[:2]
    left, top = int(round(x - w / 2)), int(round(y - h / 2))
    a0, a1 = max(0, -top), min(h, frame.shape[0] - top)
    b0, b1 = max(0, -left), min(w, frame.shape[1] - left)
    if a1 <= a0 or b1 <= b0:
        return
    piece = sprite[a0:a1, b0:b1]
    region = frame[top + a0:top + a1, left + b0:left + b1]
    region *= 1 - piece[..., 3:] * alpha
    region += piece[..., :3] * alpha


def _badge(sprite: Sprite, c: float, colour: str):
    """White disc with a ring in the peril's colour, and a white rim."""
    sprite.disc(c, c, 28.5, "#FFFFFF")
    sprite.disc(c, c, 27, colour)
    sprite.disc(c, c, 23.5, "#FFFFFF")


def quake_glyph(colour: str, t: float, shock: float) -> np.ndarray:
    """A seismograph trace that jumps at every shock."""
    sprite, c = Sprite(72), 36
    _badge(sprite, c, colour)
    xs = np.linspace(-19, 19, 70)
    envelope = np.exp(-(xs / 9.5) ** 2)
    amplitude = 2.5 + 9.5 * shock
    ys = amplitude * envelope * (np.sin(xs * 1.05 - t * 16)
                                 + 0.35 * np.sin(xs * 2.3 + t * 9))
    sprite.line(list(zip(c + xs, c + ys)), 2.4, colour)
    return sprite.done()


def flood_glyph(colour: str, t: float) -> np.ndarray:
    """Three lines of water, running."""
    sprite, c = Sprite(72), 36
    _badge(sprite, c, colour)
    xs = np.linspace(-17, 17, 50)
    for i, dy in enumerate((-8, 0, 8)):
        ys = c + dy + 2.8 * np.sin(xs * 0.42 + t * 5.5 + i * 1.1)
        sprite.line(list(zip(c + xs, ys)), 2.6, colour, 1.0 - 0.18 * i)
    return sprite.done()


def volcano_glyph(colour: str, t: float) -> np.ndarray:
    """A cone with an ash plume drifting off it and sparks from the crater."""
    sprite, c = Sprite(150), 75
    top, base = c - 8, c + 16
    rising = ramp(t, 0.3, 1.0)
    for k in range(12):
        age = (t * 0.45 + k / 12) % 1.0
        shade = 0.40 + 0.30 * age
        sprite.disc(c + 26 * age ** 1.6 + 3 * math.sin(k * 2.1 + t * 1.5),
                    top - 4 - 58 * age, 4 + 14 * age, (shade, shade, shade + 0.02),
                    0.8 * (1 - age) ** 1.2 * rising, soft=2.5)
    sprite.polygon([(c - 33, base + 2.5), (c - 9.5, top - 2.5),
                    (c + 9.5, top - 2.5), (c + 33, base + 2.5)], "#FFFFFF")
    sprite.polygon([(c - 30, base), (c - 8, top), (c + 8, top), (c + 30, base)],
                   colour)
    sprite.disc(c, top + 1, 6.5, "#FF7A1A", 0.6 + 0.4 * math.sin(t * 5.0) ** 2,
                soft=1.5)
    for k in range(6):
        age = (t * 1.1 + k / 6) % 1.0
        sprite.disc(c + (k - 2.5) * 7 * age, top - 30 * age + 38 * age * age,
                    1.9, "#FFB23B", (1 - age) * rising, soft=0.8)
    return sprite.done()


def _flame(cx: float, base: float, height: float, w: float, sway: float) -> list:
    """A flame outline: round at the bottom, drawn to a swaying tip."""
    theta = np.linspace(np.pi, 2 * np.pi, 16)
    arc = list(zip(cx + w * np.cos(theta), base - w - w * np.sin(theta)))
    tip = np.array((cx + sway, base - height))

    def curve(p0, p1, p2, n=14):
        u = np.linspace(0, 1, n)[:, None]
        return [tuple(p) for p in (1 - u) ** 2 * np.array(p0)
                + 2 * (1 - u) * u * np.array(p1) + u ** 2 * np.array(p2)]

    shoulder = base - w - (height - w) * 0.6
    right = curve((cx + w, base - w), (cx + w * 0.95 + sway * 0.2, shoulder), tip)
    left = curve(tip, (cx - w * 0.95 + sway * 0.2, shoulder), (cx - w, base - w))
    return arc + right[1:] + left[1:]


def fire_glyph(colour: str, t: float) -> np.ndarray:
    """A flickering flame with embers rising off it."""
    sprite, c = Sprite(110), 55
    base = c + 20
    flicker = 1 + 0.10 * math.sin(t * 11) + 0.06 * math.sin(t * 23 + 1.3)
    sway = 3.5 * math.sin(t * 6) + 1.5 * math.sin(t * 13)
    sprite.disc(c, base - 16, 30, "#FF8A2A", 0.16 + 0.04 * math.sin(t * 9), soft=14)
    sprite.polygon(_flame(c, base + 2.5, 46 * flicker + 5, 16.5, sway), "#FFFFFF")
    sprite.polygon(_flame(c, base, 46 * flicker, 14, sway), colour)
    sprite.polygon(_flame(c, base - 1, 33 * flicker, 9.5, sway * 0.8), "#F08A24")
    sprite.polygon(_flame(c, base - 2, 20 * flicker, 5.5, sway * 0.6), "#FFD34D")
    rising = ramp(t, 0.3, 0.8)
    for k in range(7):
        age = (t * 0.7 + k / 7) % 1.0
        sprite.disc(c + (k - 3) * 4 + 7 * math.sin(age * 6 + k), base - 22 - 50 * age,
                    1.7 * (1 - age) + 0.6, "#FFB23B", (1 - age) * rising, soft=0.8)
    return sprite.done()


class Source:
    """A finished image placed on the Mercator plane, for the camera to fly over."""

    def __init__(self, image: np.ndarray, view: View, feather: float = 0.0):
        h, w = image.shape[:2]
        alpha = np.ones((h, w), np.float32)
        if feather:
            reach = feather * min(h, w)
            ry = np.minimum(np.arange(h), np.arange(h)[::-1]) / reach
            rx = np.minimum(np.arange(w), np.arange(w)[::-1]) / reach
            fy, fx = (np.clip(v, 0, 1) for v in (ry, rx))
            alpha = np.outer(fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx))
        rgba = np.dstack([np.clip(image, 0, 1), alpha])
        base = Image.fromarray((rgba * 255).round().astype(np.uint8), "RGBA")
        self.mips = [base, base.reduce(2), base.reduce(4)]
        self.box = view.box

    def draw(self, frame: np.ndarray, view: View, alpha: float = 1.0,
             shift: float = 0.0):
        if alpha <= 0.002:
            return
        x0, y0, x1, y1 = view.box
        sx0, sy0, sx1, sy1 = self.box
        sx0, sx1 = sx0 + shift, sx1 + shift
        if x1 <= sx0 or x0 >= sx1 or y1 <= sy0 or y0 >= sy1:
            return
        iw, ih = self.mips[0].size
        box = ((x0 - sx0) / (sx1 - sx0) * iw, (sy1 - y1) / (sy1 - sy0) * ih,
               (x1 - sx0) / (sx1 - sx0) * iw, (sy1 - y0) / (sy1 - sy0) * ih)
        ratio = (box[2] - box[0]) / W
        level = 0
        while level + 1 < len(self.mips) and ratio / 2 ** (level + 1) >= 1:
            level += 1
        f = 2 ** level
        image = self.mips[level].transform(
            (W, H), Image.Transform.EXTENT, tuple(v / f for v in box),
            resample=Image.Resampling.BILINEAR, fillcolor=(0, 0, 0, 0))
        array = np.asarray(image, np.float32) / 255
        weight = array[..., 3:4] * alpha
        frame *= 1 - weight
        frame += array[..., :3] * weight


# ---------------------------------------------------------------------------
# Place names
# ---------------------------------------------------------------------------

def _pt_px(size_pt: float) -> float:
    return size_pt * 100 / 72


def place_names(view: View, avoid: list, cities: int = 6, countries: int = 4,
                seas: int = 0) -> Layer:
    """Context labels for a view, placed so none overlaps another or the event.

    Chosen in order of rank from Natural Earth: countries, then seas, then the
    largest towns. A label that would overlap anything already placed, sit
    outside the map's safe area or cover the event is skipped, not squeezed.
    """
    zoom = view.zoom()
    placed = [tuple(b) for b in avoid] + [OWNER_BOX]
    chosen = []

    def free(b):
        return (MARGIN * 0.5 < b[0] and b[2] < W - MARGIN * 0.5
                and LABEL_TOP < b[1] and b[3] < SAFE_BOTTOM
                and all(b[2] < o[0] or b[0] > o[2] or b[3] < o[1] or b[1] > o[3]
                        for o in placed))

    def attempt(lon, lat, name, kind):
        lon = near(lon, view.lon)
        x, y = (float(v) for v in view.px(lon, lat))
        style = carto.LABEL_STYLES[kind]
        size = _pt_px(style["size"])
        width = font(int(size), style["weight"] == "bold").getlength(name) + 8
        half = size * 0.72
        if style["dot"]:
            options = [((x + 12, y - half, x + 12 + width, y + half), "left", 12),
                       ((x - 12 - width, y - half, x - 12, y + half), "right", -12)]
        else:
            options = [((x - width / 2, y - half, x + width / 2, y + half), None, 0)]
        for box, align, offset in options:
            if free(box):
                placed.append(box)
                chosen.append((lon, lat, name, kind, align, offset))
                return True
        return False

    lon0, lat0, lon1, lat1 = view.lonlat

    def inside(lon, lat):
        lon = near(lon, view.lon)
        return lon0 < lon < lon1 and lat0 < lat < lat1

    shown = 0
    table = natural_earth("admin_0_countries", "50m")
    for _, row in table.sort_values("LABELRANK").iterrows():
        if shown >= countries:
            break
        if row["MIN_LABEL"] <= zoom + 1.0 and inside(row["LABEL_X"], row["LABEL_Y"]):
            shown += attempt(row["LABEL_X"], row["LABEL_Y"], row["NAME"].upper(),
                             "country")

    if seas:
        shown = 0
        water = natural_earth("geography_marine_polys", "10m", "physical")
        pieces = clipped(water, view, pad=0.0)
        for index, geometry in sorted(pieces, key=lambda p: water.loc[p[0], "scalerank"]):
            row = water.loc[index]
            if shown >= seas or row["min_label"] > zoom + 1.5:
                continue
            point = geometry.representative_point()
            lon, lat = math.degrees(point.x / R), float(lat_of(point.y))
            name = row["name"]
            name = name.title() if name.isupper() else name
            shown += attempt(lon, lat, name, "water")

    shown = 0
    towns = natural_earth("populated_places", "10m")
    ranked = towns.sort_values("POP_MAX", ascending=False)
    for _, row in ranked.iterrows():
        if shown >= cities:
            break
        if "MIN_ZOOM" in row and row["MIN_ZOOM"] > zoom + 1.5:
            continue
        if inside(row["LONGITUDE"], row["LATITUDE"]):
            shown += attempt(row["LONGITUDE"], row["LATITUDE"], row["NAME"], "city")

    def draw(ax):
        per_px = view.width / W
        for lon, lat, name, kind, align, offset in chosen:
            carto.place_label(ax, float(mx(lon)), float(my(lat)), name,
                              offset=offset * per_px, kind=kind, align=align)
    return overlay(view, draw)


# ---------------------------------------------------------------------------
# Header, footer and the title card
# ---------------------------------------------------------------------------

INK = carto.THEME["text"]
FAINT = carto.THEME["faint"]


def _scrim(image: Image.Image, solid: int, clear: int, strength: float = 0.94):
    """Paper, opaque from the frame edge to `solid`, fading out by `clear`.

    Raised cosine, as in `carto.fade`: a straight ramp shows a corner where it
    starts and where it stops.
    """
    top, bottom = sorted((solid, clear))
    span = np.clip((np.arange(top, bottom) - clear) / (solid - clear), 0, 1)
    alpha = strength * (0.5 - 0.5 * np.cos(np.pi * span))
    band = np.zeros((H, W, 4), np.uint8)
    band[..., :3] = (PAPER * 255).round().astype(np.uint8)
    edge = np.arange(H)
    beyond = edge < top if solid < clear else edge >= bottom
    band[beyond, :, 3] = int(round(strength * 255))
    band[top:bottom, :, 3] = (alpha * 255).round().astype(np.uint8)[:, None]
    image.alpha_composite(Image.fromarray(band, "RGBA"))


@lru_cache(maxsize=None)
def brand(height: int) -> Image.Image:
    """The wordmark cropped to its ink, `height` pixels tall.

    The PNG carries a paper-coloured square at 6 % opacity behind the mark.
    Cropping on any alpha kept that square, so the mark filled 40 % of its
    box and a faint rectangle showed around it. Anything that faint is
    dropped before cropping.
    """
    mark = Image.open(carto.BRAND_MARK).convert("RGBA")
    alpha = mark.getchannel("A").point(lambda v: 0 if v <= 40 else v)
    mark.putalpha(alpha)
    mark = mark.crop(alpha.getbbox())
    return mark.resize((round(mark.width * height / mark.height), height),
                       Image.Resampling.LANCZOS)


class Chrome:
    """What stays on screen the whole time: the two paper bands, the header,
    the sources line and the owner's mark.

    The bottom band is here and not on the cards, so it stays put while the
    camera flies between scenes. Two layers rather than one, so the middle
    of the frame is never touched.
    """

    def __init__(self, start: date, end: date, tracks: bool = True):
        top = blank()
        _scrim(top, 175, 300, strength=1.0)
        heading = "HAZARD WATCH · WEEKLY REPORT"
        dates = report._date_span(start, end)
        text(top, (MARGIN, 72), heading, 21, FAINT, bold=True)
        text(top, (MARGIN, 120), dates, 38, INK, bold=True)
        # The mark is exactly as tall as the two lines beside it, from the
        # first line's capitals to the second line's descenders.
        draw = ImageDraw.Draw(top)
        upper = draw.textbbox((MARGIN, 72), heading, font=font(21, True),
                              anchor="ls")[1]
        lower = draw.textbbox((MARGIN, 120), dates, font=font(38, True),
                              anchor="ls")[3]
        mark = brand(int(lower - upper))
        top.alpha_composite(mark, dest=(W - MARGIN - mark.width, int(upper)))

        bottom = blank()
        _scrim(bottom, BAND_SOLID, BAND_FADE, strength=1.0)
        parts = (["Alerts: GDACS"] + (["Tracks: IBTrACS"] if tracks else [])
                 + ["Relief: GMTED2010", "Places: Natural Earth"])
        text(bottom, (MARGIN, H - 28), " · ".join(parts), 17, FAINT)
        # White, on the map just above the band's fade, with a soft shadow so
        # it reads over pale water as well as over land.
        text(bottom, (OWNER_BOX[2], OWNER_BOX[3] - 8), OWNER, 22, "#FFFFFF",
             bold=True, anchor="rs", halo=INK, halo_strength=0.5)
        self.layers = [Layer(np.asarray(top)), Layer(np.asarray(bottom))]

    def over(self, frame: np.ndarray):
        for layer in self.layers:
            layer.over(frame)


def chapters(total: int, current: int | None, colours: list) -> Layer:
    """One dot per scene, bottom right, the current one filled and larger."""
    image = blank()
    gap = 22
    x = W - MARGIN - (total - 1) * gap
    for i in range(total):
        if current is not None and i == current:
            dot = marker(colours[i], None, 18)
        elif current is not None and i < current:
            dot = marker("#9AA0A6", None, 12)
        else:
            dot = marker("#C9C4BA", None, 12)
        image.alpha_composite(dot, dest=(int(x + i * gap - dot.width / 2),
                                         int(H - 34 - dot.height / 2)))
    return Layer(np.asarray(image))


# Figures in a card line are set bold: a number with its unit is what a
# reader scans for, and in regular weight "20,000 ha" hid inside its sentence.
FIGURE = re.compile(r"Magnitude \d+(?:\.\d+)?|Category \d"
                    r"|\d[\d,]*(?:\.\d+)?\s?(?:km2|km/h|km|ha|kt|mph|%)")


def emphasise(line: str) -> str:
    """`**`-mark the figures in a line, unless it is marked already."""
    if not line or "**" in line:
        return line
    return FIGURE.sub(lambda m: f"**{m.group(0)}**", line)


def runs(line, colour: str = FAINT, strong: str = INK) -> list:
    """`(words, colour, bold)` runs: a string with `**bold**`, or runs as is."""
    if not isinstance(line, str):
        return line
    return [(part, strong if i % 2 else colour, bool(i % 2))
            for i, part in enumerate(line.split("**")) if part]


def rich(image: Image.Image, xy, parts: list, size: int) -> float:
    """Runs drawn one after another on a baseline; returns the total width."""
    x, y = xy
    for words, colour, bold in parts:
        x += text(image, (x, y), words, size, colour, bold=bold)
    return x - xy[0]


def rich_width(parts: list, size: int) -> float:
    return sum(font(size, bold).getlength(words) for words, _, bold in parts)


def _fit(words: str, size: int, bold: bool, width: float) -> int:
    while size > 24 and font(size, bold).getlength(words) > width:
        size -= 2
    return size


def card(peril: str, alert: str | None, title: str, lines: list,
         colour: str, note: str = "") -> Layer:
    """The title card: peril and alert, the name, then what the feed says.

    Text only: the paper under it belongs to the chrome, which never moves.
    A line is a string, with `**` around what should stand out, or a list
    of `(words, colour, bold)` runs.
    """
    image = blank()
    y = 1030
    ImageDraw.Draw(image).rectangle((MARGIN, y - 22, MARGIN + 6, y + 1),
                                    fill=_rgba(colour))
    width = text(image, (MARGIN + 18, y), peril.upper(), 25, colour, bold=True)
    if alert:
        text(image, (MARGIN + 18 + width, y), f"  ·  ALERT {alert.upper()}", 25,
             carto.ALERT_COLOURS.get(alert, INK), bold=True)
    size = _fit(title, 58, True, W - 2 * MARGIN)
    text(image, (MARGIN, y + 68), title, size, INK, bold=True)
    y += 68
    for line, size in lines + ([(note, 20)] if note else []):
        if line:
            parts = runs(line)
            while size > 18 and rich_width(parts, size) > W - 2 * MARGIN:
                size -= 1
            y += size + 16
            rich(image, (MARGIN, y), parts, size)
    return Layer(np.asarray(image))


def card_alpha(t: float, duration: float) -> tuple:
    """Card opacity and vertical offset: rises in, fades out before a flight."""
    appear = ramp(t, 0.15, 0.7)
    leave = 1 - ramp(t, duration - 0.45, duration - 0.05)
    return appear * leave, int(round(24 * (1 - appear)))


def _alert(event: dict) -> str:
    return event.get("alert_level") or ""


def _where(event: dict, regions: dict) -> tuple:
    """`(title, place line)`: the name where GDACS gives one, else the place."""
    name = report._event_name(event)
    place = report._digest_place(event, regions)
    if name:
        return name, place
    return place or natcat.GDACS_PERILS.get(event["event_type"], ""), ""


# ---------------------------------------------------------------------------
# Scenes
# ---------------------------------------------------------------------------

class Scene:
    """A frozen map with things moving on it, and a card.

    `frames` yields the map alone; the card is drawn by `decorate`, which
    the renderer calls after the chrome, so the text sits on the paper band
    rather than under it.
    """

    duration = 0.0
    view: View = None
    chapter: int | None = None

    def map(self, t: float) -> np.ndarray:
        raise NotImplementedError

    def decorate(self, frame: np.ndarray, t: float):
        pass

    def frames(self):
        for i in range(int(round(self.duration * FPS))):
            yield self.map(i / FPS)

    def first(self) -> np.ndarray:
        return self.map(0.0)

    def last(self) -> np.ndarray:
        return self.map(self.duration)


def _hours(when: datetime, origin: datetime) -> float:
    return (when - origin).total_seconds() / 3600


def _category_name(category) -> str:
    if category is None:
        return ""
    return {-4: "Extratropical", -3: "Disturbance", -2: "Subtropical",
            -1: "Tropical depression", 0: "Tropical storm"}.get(
        category, f"Category {category}")


def _wind(kt) -> str:
    return f"{kt:.0f} kt ({kt * 1.852:.0f} km/h)"


class TrackScene(Scene):
    """A cyclone's week: its track drawing itself, day by day."""

    def __init__(self, event: dict, regions: dict, anchor: float,
                 start: date, end: date, fixes: list):
        self.event, self.chapter = event, None
        self.duration = SCENE_SECONDS["TC"]
        self.colour = carto.PERIL_COLOURS["storm"]
        opens = datetime.combine(start, datetime.min.time())
        closes = datetime.combine(end + timedelta(days=1), datetime.min.time())

        times = np.array([_hours(f["time"], opens) for f in fixes])
        lons = np.degrees(np.unwrap(np.radians([f["lon"] for f in fixes])))
        lons = lons + (near(lons[-1], anchor) - lons[-1])
        lats = np.array([f["lat"] for f in fixes])
        span = _hours(closes, opens)

        # The week opens part way along a running storm: the track starts at
        # the interpolated position at midnight, not at the next fix. A storm
        # the week barely touches is shown whole rather than as a stub.
        t0, t1 = max(0.0, times[0]), min(span, times[-1])
        if t1 - t0 < 12:
            t0, t1 = times[0], times[-1]
        grid = np.unique(np.concatenate([[t0], times[(times > t0) & (times < t1)], [t1]]))
        self.times = grid
        self.lons = np.interp(grid, times, lons)
        self.lats = np.interp(grid, times, lats)
        self.category = [self._at(fixes, times, t, "category") for t in grid]
        self.wind = [self._at(fixes, times, t, "wind_kt") for t in grid]
        self.origin = opens
        self.hemisphere = 1 if np.mean(self.lats) >= 0 else -1

        self.view = fit_view(self.lons, self.lats)
        before = times <= t0
        past = (lons[before], lats[before]) if before.sum() >= 1 else None
        if past is not None:
            past = (np.append(past[0], self.lons[0]), np.append(past[1], self.lats[0]))

        def draw_past(ax, scale):
            if past is not None and len(past[0]) > 1:
                ax.plot(mx(past[0]), my(past[1]), color=self.colour, lw=2.2 * scale,
                        alpha=0.55, ls=(0, (3, 2.5)), solid_capstyle="round",
                        zorder=5)

        self.base = keyframe(self.view, draw=draw_past)

        xs, ys = self.view.px(self.lons, self.lats)
        self.xs, self.ys = xs, ys
        avoid = [(x - 26, y - 26, x + 26, y + 26) for x, y in zip(xs, ys)]
        self.names = place_names(self.view, avoid, cities=5, countries=4, seas=2)
        self.track, self.param = self._track_layer()
        self.days = self._day_ticks()

        title, place = _where(event, regions)
        # Only fixes inside the shown stretch: the one just before midnight
        # on the first day belongs to the previous week.
        shown = [f for f, t in zip(fixes, times)
                 if t0 <= t <= t1 and f["wind_kt"] is not None]
        if shown:
            peak = max(shown, key=lambda f: f["wind_kt"])
            fact = (f"Peak in the week: **{_category_name(peak['category'])}, "
                    f"{_wind(peak['wind_kt'])}** · IBTrACS")
        else:
            fact = report._digest_fact(event)
            fact = f"{emphasise(fact)} · GDACS" if fact else ""
        where = " · ".join(p for p in (place, report._digest_dates(event)) if p)
        self.card = card("Tropical cyclone", _alert(event), title,
                         [(where, 30), (fact, 26)], self.colour)

    @staticmethod
    def _at(fixes, times, t, field):
        """The last reported value at or before `t`: winds are not interpolated."""
        index = max(0, int(np.searchsorted(times, t + 1e-6)) - 1)
        return fixes[index][field]

    def _track_layer(self):
        from scipy.spatial import cKDTree

        xs, ys = self.xs, self.ys
        view = self.view

        def draw(ax):
            x, y = mx(self.lons), my(self.lats)
            points = np.column_stack([x, y])
            segments = np.stack([points[:-1], points[1:]], axis=1)
            cats = [max(c, -1) if c is not None else None
                    for c in self.category[:-1]]
            widths = [3.6 + 0.65 * max(c or 0, 0) for c in cats]
            ax.add_collection(LineCollection(segments, colors="#FFFFFF",
                                             linewidths=[w + 3.5 for w in widths],
                                             capstyle="round", joinstyle="round",
                                             zorder=6, alpha=0.9))
            ax.add_collection(LineCollection(segments,
                                             colors=[TRACK_COLOURS[c] for c in cats],
                                             linewidths=widths, capstyle="round",
                                             joinstyle="round", zorder=7))

        layer = overlay(view, draw)
        if layer.empty:
            return layer, None
        # Every pixel of the drawn track takes the time of the nearest point
        # on it, so revealing "everything up to hour T" is one comparison.
        dense_t = np.linspace(self.times[0], self.times[-1], 4000)
        dense = np.column_stack([np.interp(dense_t, self.times, xs),
                                 np.interp(dense_t, self.times, ys)])
        h, w = layer.image.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w]
        pixels = np.column_stack([(xx + layer.x0 + 0.5).ravel(),
                                  (yy + layer.y0 + 0.5).ravel()])
        _, nearest = cKDTree(dense).query(pixels)
        return layer, dense_t[nearest].reshape(h, w).astype(np.float32)

    def _day_ticks(self) -> list:
        """`(hour, layer)` for each midnight UTC on the track: a dot and a date.

        Kept apart from the track so a date appears whole when the storm
        reaches it, rather than letter by letter as the line sweeps past.
        The date sits on the side of the track facing up the frame.
        """
        ticks = []
        day = math.ceil(self.times[0] / 24) * 24
        while day <= self.times[-1] + 1e-6:
            x = float(np.interp(day, self.times, self.xs))
            y = float(np.interp(day, self.times, self.ys))
            ahead = min(day + 3, self.times[-1])
            behind = max(day - 3, self.times[0])
            dx = float(np.interp(ahead, self.times, self.xs)
                       - np.interp(behind, self.times, self.xs))
            dy = float(np.interp(ahead, self.times, self.ys)
                       - np.interp(behind, self.times, self.ys))
            length = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / length, dx / length
            if ny > 0:
                nx, ny = -nx, -ny
            image = blank()
            image.alpha_composite(day_dot(), dest=(int(x) - 7, int(y) - 7))
            when = self.origin + timedelta(hours=day)
            text(image, (x + nx * 24, y + ny * 24),
                 f"{when.day} {report.MONTHS[when.month - 1][:3]}", 17, INK,
                 bold=True, anchor="mm", halo="#FFFFFF")
            ticks.append((day, Layer(np.asarray(image))))
            day += 24
        return ticks

    def _now(self, t: float) -> float:
        draw_from, draw_to = 0.9, self.duration - 1.6
        p = (t - draw_from) / (draw_to - draw_from)
        p = min(max(p, 0.0), 1.0)
        return self.times[0] + (self.times[-1] - self.times[0]) * p

    def map(self, t: float) -> np.ndarray:
        frame = self.base.copy()
        self.names.over(frame, ramp(t, 0.3, 1.1))
        now = self._now(t)
        if self.param is not None:
            soft = max((self.times[-1] - self.times[0]) / 300, 0.3)
            self.track.over(frame, 1.0, mask=np.clip((now - self.param) / soft + 1, 0, 1))
        for hour, tick in self.days:
            tick.over(frame, min(1.0, max(0.0, (now - hour) / 4 + 1)))
        x = float(np.interp(now, self.times, self.xs))
        y = float(np.interp(now, self.times, self.ys))
        spin = (t * 300.0) * self.hemisphere
        glyph = cyclone_glyph(self.colour)
        if self.hemisphere < 0:
            glyph = ImageOps.mirror(glyph)
        paste(frame, glyph.rotate(spin, resample=Image.Resampling.BICUBIC),
              x, y, ramp(t, 0.2, 0.6))
        return frame

    def decorate(self, frame: np.ndarray, t: float):
        alpha, dy = card_alpha(t, self.duration)
        self.card.over(frame, alpha, dy=dy)
        if alpha <= 0.01:
            return
        now = self._now(t)
        index = max(0, int(np.searchsorted(self.times, now + 1e-6)) - 1)
        when = self.origin + timedelta(hours=float(now))
        stamp = (f"{when.day} {report.MONTHS[when.month - 1][:3]} "
                 f"{when:%H}:00 UTC")
        category, wind = self.category[index], self.wind[index]
        # The source stays on the line with its figures (H15).
        if wind is not None:
            live = [(stamp, INK, False), ("  ·  ", FAINT, False),
                    (f"{_category_name(category)}  ·  {_wind(wind)}", INK, True),
                    ("  ·  IBTrACS", FAINT, False)]
        else:
            live = [(stamp, INK, False),
                    ("  ·  position from GDACS, no wind yet", FAINT, False)]
        hud = Image.new("RGBA", (W, 60), (0, 0, 0, 0))
        rich(hud, (MARGIN, 42), live, 26)
        paste(frame, hud, W / 2, 1236 - 12 + dy, alpha)


class PointScene(Scene):
    """An event at one point: earthquake, eruption, flood or fire.

    Each has its own animated glyph, and the figure a reader looks for first
    is written beside it on the map, with its source.
    """

    SHOCK_START, SHOCK_PERIOD = 0.45, 1.9
    # Distance from the event point to its callout, by glyph size.
    CALLOUT_GAP = {"EQ": 40, "VO": 44, "WF": 30}

    def __init__(self, event: dict, regions: dict, anchor: float):
        self.event, self.chapter = event, None
        self.kind = kind = event["event_type"]
        # A cyclone lands here only when it has no usable track.
        self.duration = SCENE_SECONDS[kind] if kind != "TC" else 7.0
        self.colour = carto.PERIL_COLOURS[PERIL_KEY[kind]]
        self.lon, self.lat = near(event["lon"], anchor), event["lat"]
        self.view = point_view(self.lon, self.lat, POINT_WIDTH_KM.get(kind, 1200))
        self.base = keyframe(self.view)
        self.x, self.y = (float(v) for v in self.view.px(self.lon, self.lat))

        if kind == "EQ" and event.get("severity"):
            magnitude = float(event["severity"])
            self.reach = float(np.clip(60 + 38 * (magnitude - 5), 50, 200))
        else:
            self.reach = {"Red": 150, "Orange": 115}.get(event["alert_level"], 85)

        title, place = _where(event, regions)
        self.callout, box = self._callout(place)
        avoid = [(self.x - self.reach * 0.6, self.y - self.reach * 0.6,
                  self.x + self.reach * 0.6, self.y + self.reach * 0.6)]
        if kind == "VO":                          # the plume drifts up and right
            avoid.append((self.x - 40, self.y - 90, self.x + 70, self.y + 20))
        if box:
            avoid.append(box)
        self.names = place_names(self.view, avoid, cities=6, countries=3,
                                 seas=1 if kind in ("EQ", "VO") else 0)

        fact = report._digest_fact(event)
        where = " · ".join(p for p in (place, report._digest_dates(event)) if p)
        # A flood's GDACS point is the centroid of the basin that raised the
        # alert and can sit a hundred kilometres from the water. Said on
        # screen, since the marker otherwise claims a precision it lacks.
        note = ("The marker is the GDACS alert point, not the flooded area."
                if kind == "FL" else "")
        self.card = card(natcat.GDACS_PERILS[kind], _alert(event), title,
                         [(where, 30),
                          (f"{emphasise(fact)} · GDACS" if fact else "", 26)],
                         self.colour, note)

    def _callout(self, place: str) -> tuple:
        """The key figure written beside the event, and the box it takes.

        A figure carries its source on the same label (H15). Floods get
        none: GDACS gives them no figure, and their point is not the flood.
        """
        kind, event = self.kind, self.event
        fact = report._digest_fact(event)
        lines = None
        if kind == "EQ" and event.get("severity"):
            depth = re.search(r"depth (\d+) km", fact)
            lines = (f"M {float(event['severity']):.1f}",
                     f"{depth.group(1)} km deep · GDACS" if depth else "GDACS")
        elif kind == "WF":
            area = re.search(r"\d[\d,]*\s?ha", fact)
            lines = (area.group(0), "fire area · GDACS") if area else None
        elif kind == "VO":
            lines = (report._event_name(event) or "Volcano", place)
        if not lines:
            return Layer(np.zeros((1, 1, 4), np.float32)), None

        gap = self.CALLOUT_GAP[kind]
        width = max(font(26, True).getlength(lines[0]),
                    font(17).getlength(lines[1] or "")) + 6
        right = self.x + gap + width < W - MARGIN / 2
        x = self.x + gap if right else self.x - gap
        anchor = "ls" if right else "rs"
        image = blank()
        text(image, (x, self.y - 2), lines[0], 26, INK, bold=True, anchor=anchor,
             halo="#FFFFFF")
        if lines[1]:
            text(image, (x, self.y + 20), lines[1], 17, INK, anchor=anchor,
                 halo="#FFFFFF")
        left = x if right else x - width
        return Layer(np.asarray(image)), (left, self.y - 26, left + width, self.y + 26)

    def _shock(self, t: float) -> float:
        if t < self.SHOCK_START:
            return 0.0
        return math.exp(-2.8 * ((t - self.SHOCK_START) % self.SHOCK_PERIOD))

    def map(self, t: float) -> np.ndarray:
        frame = self.base.copy()
        self.names.over(frame, ramp(t, 0.3, 1.1))
        appear = ramp(t, 0.15, 0.5)
        kind, x, y = self.kind, self.x, self.y

        if kind == "EQ":
            # Two wavefronts per shock, the second a beat behind: P and S.
            latest = int((t - self.SHOCK_START) // self.SHOCK_PERIOD)
            for k in (latest - 1, latest):
                for delay in (0.0, 0.25):
                    age = (t - self.SHOCK_START - k * self.SHOCK_PERIOD - delay) / 1.6
                    if k >= 0 and 0 < age < 1:
                        ring(frame, x, y, 30 + self.reach * age, 3.0, self.colour,
                             0.8 * (1 - age) ** 1.2)
            shock = self._shock(t)
            stamp(frame, quake_glyph(self.colour, t, shock),
                  x + 3.2 * shock * math.sin(t * 70), y + 1.8 * shock * math.cos(t * 55),
                  appear)
        elif kind == "FL":
            for offset in (0.0, 1.2):
                if t > 0.5 + offset:
                    phase = ((t - 0.5 - offset) / 2.4) % 1.0
                    ring(frame, x, y, 30 + self.reach * 0.8 * phase, 2.5,
                         self.colour, 0.55 * (1 - phase) ** 1.3)
            stamp(frame, flood_glyph(self.colour, t), x, y, appear)
        elif kind == "VO":
            stamp(frame, volcano_glyph(self.colour, t), x, y, appear)
        elif kind == "WF":
            stamp(frame, fire_glyph(self.colour, t), x, y, appear)
        else:
            paste(frame, cyclone_glyph(self.colour).rotate(
                t * 300.0 * (1 if self.lat >= 0 else -1),
                resample=Image.Resampling.BICUBIC), x, y, appear)
        self.callout.over(frame, ramp(t, 0.9, 1.5))
        return frame

    def decorate(self, frame: np.ndarray, t: float):
        alpha, dy = card_alpha(t, self.duration)
        self.card.over(frame, alpha, dy=dy)


def _probe(path: str) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe not found; install ffmpeg in this environment")
    result = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", path],
        capture_output=True, text=True, check=True)
    info = json.loads(result.stdout)
    stream = info["streams"][0]
    return {"width": int(stream["width"]), "height": int(stream["height"]),
            "duration": float(info["format"]["duration"])}


class ClipScene(Scene):
    """A clip the user supplied, played after its event with the source on it.

    The clip is fitted inside the map area over a blurred copy of itself,
    silent, with the source burned in underneath: most LinkedIn video plays
    muted, so a credit that is only spoken is not a credit.
    """

    def __init__(self, pick: dict, after: Scene):
        self.pick, self.after = pick, after
        self.chapter = after.chapter
        self.view = after.view
        info = _probe(pick["clip"])
        begin = pick["from"] or 0.0
        finish = min(pick["to"] or info["duration"], info["duration"])
        self.begin, self.length = begin, max(0.5, finish - begin)
        self.duration = self.length
        scale = min((W - 80) / info["width"], (SAFE_BOTTOM - SAFE_TOP - 120) / info["height"])
        self.size = (int(info["width"] * scale) // 2 * 2,
                     int(info["height"] * scale) // 2 * 2)
        self.left = (W - self.size[0]) // 2
        self.top = int((SAFE_TOP + SAFE_BOTTOM) / 2 - self.size[1] / 2)

        credit = blank()
        text(credit, (self.left, self.top + self.size[1] + 40),
             f"Video: {pick['source']}", 24, "#FFFFFF", bold=True, halo=INK)
        title, _ = _where(after.event, {})
        text(credit, (self.left, self.top - 22),
             f"{natcat.GDACS_PERILS[after.event['event_type']].upper()} · {title}",
             24, "#FFFFFF", bold=True, halo=INK)
        self.credit = Layer(np.asarray(credit))
        self.leaving = after.last()

    def frames(self):
        ffmpeg = shutil.which("ffmpeg")
        w, h = self.size
        process = subprocess.Popen(
            [ffmpeg, "-v", "error", "-ss", f"{self.begin}", "-i", self.pick["clip"],
             "-t", f"{self.length}", "-vf", f"fps={FPS},scale={w}:{h}",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE)
        total = int(round(self.length * FPS))
        count = 0
        for i in range(total):
            raw = process.stdout.read(w * h * 3)
            if len(raw) < w * h * 3:
                break
            clip = np.frombuffer(raw, np.uint8).reshape(h, w, 3)
            t = i / FPS
            mix = min(ramp(t, 0.0, 0.35), 1 - ramp(t, self.length - 0.35, self.length))
            count += 1
            yield self._compose(clip) * mix + self.leaving * (1 - mix)
        # ffmpeg can round one frame more than was asked for; drained rather
        # than cut off, since a closed pipe would make it exit with an error.
        process.stdout.read()
        process.stdout.close()
        failed = process.wait() != 0 and count < total
        if failed or count == 0:
            raise RuntimeError(f"ffmpeg could not read the clip {self.pick['clip']}")

    def _compose(self, clip: np.ndarray) -> np.ndarray:
        image = Image.fromarray(clip)
        cover = max(W / image.width, H / image.height)
        small = image.resize((max(1, int(image.width * cover / 12)),
                              max(1, int(image.height * cover / 12))),
                             Image.Resampling.BILINEAR)
        small = small.filter(ImageFilter.GaussianBlur(3))
        back = small.resize((int(image.width * cover), int(image.height * cover)),
                            Image.Resampling.BILINEAR)
        left, top = (back.width - W) // 2, (back.height - H) // 2
        back = back.crop((left, top, left + W, top + H))
        frame = np.asarray(back, np.float32) / 255 * 0.45
        frame[self.top:self.top + clip.shape[0],
              self.left:self.left + clip.shape[1]] = clip.astype(np.float32) / 255
        self.credit.over(frame)
        return frame

    def last(self) -> np.ndarray:
        return self.leaving


class WorldScene(Scene):
    """The whole world: markers popping in at the start, everything at the end."""

    def __init__(self, view: View, base: np.ndarray, events: list,
                 closing: bool, droughts: list, start: date, end: date,
                 regions: dict):
        self.view, self.base, self.closing = view, base, closing
        self.chapter = None
        self.markers = []
        tracks = []
        for number, (event, scene) in enumerate(events, 1):
            colour = carto.PERIL_COLOURS[PERIL_KEY[event["event_type"]]]
            if isinstance(scene, TrackScene):
                lons = scene.lons + (near(scene.lons[-1], view.lon) - scene.lons[-1])
                tracks.append((lons, scene.lats))
                lon, lat = lons[-1], scene.lats[-1]
            else:
                lon, lat = near(event["lon"], view.lon), event["lat"]
            x, y = (float(v) for v in view.px(lon, lat))
            self.markers.append((x, y, colour, number))

        def draw_tracks(ax):
            for lons, lats in tracks:
                ax.plot(mx(lons), my(lats), color="#FFFFFF", lw=4.5, alpha=0.9,
                        solid_capstyle="round")
                ax.plot(mx(lons), my(lats), color=carto.PERIL_COLOURS["storm"],
                        lw=2.4, solid_capstyle="round")
        self.tracks = overlay(view, draw_tracks)
        self.taken = [(x - 17, y - 17, x + 17, y + 17)
                      for x, y, _, _ in self.markers] + [OWNER_BOX]
        self.droughts = [self._drought(d, i, view) for i, d in enumerate(droughts)]
        self.duration = (INTRO_SECONDS if not closing else
                         0.6 + DROUGHT_STAGGER * len(self.droughts) + 1.2 + OUTRO_HOLD)

        shown = [event for event, _ in events]
        perils = {}
        for event in shown + droughts:
            perils.setdefault(natcat.GDACS_PERILS[event["event_type"]],
                              carto.PERIL_COLOURS[PERIL_KEY[event["event_type"]]])
        if closing:
            count = f"**{len(shown)} event{'s' if len(shown) != 1 else ''}**"
            if droughts:
                count += (f" and **{len(droughts)} drought alert"
                          f"{'s' if len(droughts) != 1 else ''}**")
            # Each peril in its own colour, the colour its marker carried: the
            # line doubles as the legend of the map above it.
            legend = []
            for i, (name, colour) in enumerate(perils.items()):
                if i:
                    legend.append(("  ·  ", FAINT, False))
                legend.append((name, colour, True))
            self.card = card("The week", None, "Natural catastrophes",
                             [(count, 30), (legend, 26)], INK)
        else:
            self.card = card("This week", None, "Natural catastrophes",
                             [(report._date_span(start, end), 30),
                              ("The week's GDACS alerts, one by one", 26)], INK)

    def _drought(self, event: dict, index: int, view: View) -> dict:
        countries = natural_earth("admin_0_countries", "50m")
        wanted = set(event.get("countries_iso3") or [])
        rows = countries[countries["ADM0_A3"].isin(wanted)
                         | countries["ISO_A3"].isin(wanted)]
        pieces = [g for _, g in clipped(rows, view, pad=0.0)]
        colour = carto.PERIL_COLOURS["drought"]
        fill = overlay(view, lambda ax: _fill(ax, pieces, facecolor=colour,
                                              alpha=0.5, edgecolor="none"))
        edge = overlay(view, lambda ax: _draw_lines(ax, pieces, colors=colour,
                                                    linewidths=1.6))
        # The label goes on the countries themselves. The GDACS point for a
        # drought is the centroid of its polygon, which for "Europe" sits in
        # Bavaria and for a coastal alert can sit at sea.
        import shapely

        if pieces:
            centre = shapely.union_all(pieces).representative_point()
            x, y = (float(v) for v in view.px(math.degrees(centre.x / R),
                                              float(lat_of(centre.y))))
        else:
            x, y = (float(v) for v in view.px(near(event["lon"], view.lon),
                                              event["lat"]))
        sweep = None
        if not edge.empty:
            h, w = edge.image.shape[:2]
            yy, xx = np.mgrid[0:h, 0:w]
            angle = np.arctan2(xx + edge.x0 - x, -(yy + edge.y0 - y))
            sweep = ((angle % (2 * np.pi)) / (2 * np.pi)).astype(np.float32)

        region = _drought_region(event) or report._digest_country(event["country"])
        began = event["from_date"]
        since = f"since {began.day} {report.MONTHS[began.month - 1][:3]} {began.year}"
        width = max(font(19, True).getlength(region), font(16).getlength(since)) + 8
        # Several alerts can share a region (two over East Africa this year),
        # so a label that would sit on another moves until it is clear.
        spots = [(0, 0), (0, -44), (0, 44), (-width * 0.6, 0), (width * 0.6, 0),
                 (0, -88), (0, 88), (-width * 0.6, -44), (width * 0.6, 44)]
        for ox, oy in spots:
            # Pulled back inside the frame first: a country on the map's edge
            # still gets a label that can be read whole.
            cx = float(np.clip(x + ox, MARGIN / 2 + width / 2,
                               W - MARGIN / 2 - width / 2))
            cy = float(np.clip(y + oy, LABEL_TOP + 22, SAFE_BOTTOM - 22))
            box = (cx - width / 2, cy - 22, cx + width / 2, cy + 22)
            if all(box[2] < o[0] or box[0] > o[2] or box[3] < o[1]
                   or box[1] > o[3] for o in self.taken):
                break
        self.taken.append(box)
        label = blank()
        text(label, (cx, cy - 3), region, 19, "#5C4206", bold=True, anchor="ms",
             halo="#FFFFFF")
        text(label, (cx, cy + 17), since, 16, "#5C4206", anchor="ms",
             halo="#FFFFFF")
        return {"fill": fill, "edge": edge, "sweep": sweep,
                "label": Layer(np.asarray(label)),
                "start": 0.5 + DROUGHT_STAGGER * index}

    def map(self, t: float) -> np.ndarray:
        frame = self.base.copy()
        if self.closing:
            # Every fill and border first, every label after: a country in two
            # alerts is filled twice, and the second fill used to cover the
            # first alert's label.
            for d in self.droughts:
                s = t - d["start"]
                if s <= 0:
                    continue
                d["fill"].over(frame, 0.9 * ramp(s, 0.6, 1.2))
                if d["sweep"] is not None:
                    reach = ramp(s, 0.0, 0.9) * 1.02
                    d["edge"].over(frame, 1.0,
                                   mask=np.clip((reach - d["sweep"]) * 40, 0, 1))
            for d in self.droughts:
                d["label"].over(frame, ramp(t - d["start"], 0.9, 1.3))
            self.tracks.over(frame)
            for x, y, colour, number in self.markers:
                paste(frame, marker(colour, number, 30), x, y)
        else:
            self.tracks.over(frame, ramp(t, 0.2, 0.9))
            for i, (x, y, colour, number) in enumerate(self.markers):
                grow = ramp(t, 0.25 + 0.14 * i, 0.55 + 0.14 * i)
                if grow > 0:
                    overshoot = 1 + 0.25 * math.sin(math.pi * grow)
                    size = max(2, int(30 * grow * overshoot) // 2 * 2)
                    paste(frame, marker(colour, number, size), x, y, min(1, grow * 2))
        return frame

    def decorate(self, frame: np.ndarray, t: float):
        if self.closing:
            alpha = ramp(t, 0.3, 0.9)
        else:
            alpha = ramp(t, 0.0, 0.3) * (1 - ramp(t, self.duration - 0.4, self.duration))
        self.card.over(frame, alpha)


class Flight:
    """The camera between two scenes, over the world map and both frozen ends."""

    chapter = None

    def __init__(self, a: Scene, b: Scene, world: Source):
        self.a, self.b, self.world = a, b, world
        self.chapter = b.chapter
        self.duration = flight_seconds(a.view, b.view)

    def frames(self):
        start = Source(self.a.last(), self.a.view, feather=0.06)
        finish = Source(self.b.first(), self.b.view, feather=0.06)
        n = int(round(self.duration * FPS))
        for i in range(n):
            p = (i + 1) / (n + 1)
            view = camera(self.a.view, self.b.view, p)
            frame = np.empty((H, W, 3), np.float32)
            frame[:] = PAPER
            for turn in range(-2, 3):
                self.world.draw(frame, view, shift=turn * WORLD)
            # Each end stays on screen as long as it is sharp; the world map
            # under them is magnified and only carries the middle of the trip.
            start.draw(frame, view, 1 - ramp(p, 0.2, 0.55))
            finish.draw(frame, view, ramp(p, 0.45, 0.85))
            yield frame


class EndCard:
    """Paper, the mark, the week, the sources and the disclaimer."""

    chapter = None

    def __init__(self, start: date, end: date, credits: list, leaving: np.ndarray):
        image = Image.new("RGBA", (W, H), _rgba(carto.THEME["background"]))
        mark = brand(290)
        image.alpha_composite(mark, dest=((W - mark.width) // 2, 250))
        text(image, (W / 2, 665), "WEEKLY REPORT", 28, FAINT, bold=True, anchor="ms")
        text(image, (W / 2, 730), report._date_span(start, end), 46, INK,
             bold=True, anchor="ms")
        text(image, (W / 2, 785), OWNER, 28, INK, anchor="ms")

        y = 980
        locked = report.locked_phrases()
        lines = [locked["L-SRC-GDACS"]] + credits
        for block, size, colour in ((" ".join(lines), 21, FAINT),
                                    (locked["L-DISC-FEED"], 21, INK)):
            for line in _wrap(block, size, W - 2 * MARGIN):
                text(image, (MARGIN, y), line, size, colour)
                y += size + 11
            y += 22
        self.image = np.asarray(image.convert("RGB"), np.float32) / 255
        self.leaving = leaving
        self.duration = END_SECONDS

    def frames(self):
        for i in range(int(round(self.duration * FPS))):
            mix = ramp(i / FPS, 0.0, 0.6)
            yield self.image * mix + self.leaving * (1 - mix)


def _wrap(words: str, size: int, width: float) -> list:
    face = font(size)
    lines, current = [], ""
    for word in words.split():
        trial = f"{current} {word}".strip()
        if current and face.getlength(trial) > width:
            lines.append(current)
            current = word
        else:
            current = trial
    return lines + ([current] if current else [])


# ---------------------------------------------------------------------------
# Timeline and encoding
# ---------------------------------------------------------------------------

def build(monday, picks_path=None) -> dict:
    """Everything the video needs, from the picks file, ready to render."""
    monday, start, end = week_of(monday)
    paths = _paths(monday)
    if not paths["candidates"].exists():
        write_picks(candidates(monday))
    found = json.loads(paths["candidates"].read_text(encoding="utf-8"))
    records = {c["key"]: c for c in found["scenes"] + found["droughts"]}
    picks, drought_keys = read_picks(picks_path or paths["picks"])

    missing = [p["key"] for p in picks if p["key"] not in records]
    missing += [k for k in drought_keys if k not in records]
    if missing:
        raise KeyError(f"Not among this week's candidates: {', '.join(missing)}. "
                       f"Run `video.py candidates {monday}` again.")
    events = [_load_event(records[p["key"]]) for p in picks]
    droughts = [_load_event(records[k]) for k in drought_keys]
    regions = {e["event_id"]: records[key_of(e)].get("region", "")
               for e in events + droughts}

    lons = [e["lon"] for e in events + droughts]
    centre = gap_centre(lons)
    print(f"World map, centred on {centre:.0f} degrees")
    # Rendered once, whole and large, for the camera to fly over; the world
    # views at either end are crops of it.
    whole = world_view(centre, whole=True)
    world = Source(keyframe(whole, WORLD_SCALE, lats=WORLD_LATS), whole)

    def world_base(view):
        frame = np.empty((H, W, 3), np.float32)
        frame[:] = PAPER
        for turn in range(-2, 3):
            world.draw(frame, view, shift=turn * WORLD)
        return frame

    scenes, anchor = [], centre
    for number, (pick, event) in enumerate(zip(picks, events)):
        label = records[pick["key"]]["label"]
        print(f"Scene {number + 1}: {label}")
        scene = None
        if event["event_type"] == "TC":
            track = natcat.cyclone_track(event)
            if len(track["fixes"]) >= 2:
                scene = TrackScene(event, regions, anchor, start, end,
                                   track["fixes"])
        if scene is None:
            scene = PointScene(event, regions, anchor)
        scene.chapter = number
        anchor = scene.view.lon
        scenes.append((pick, event, scene))

    pairs = [(event, scene) for _, event, scene in scenes]
    opening = world_view(centre, lons)
    ending = world_view(near(centre, anchor), lons)
    intro = WorldScene(opening, world_base(opening), pairs, False, [], start,
                       end, regions)
    outro = WorldScene(ending, world_base(ending), pairs, True, droughts, start,
                       end, regions)

    timeline, previous = [intro], intro
    for pick, event, scene in scenes:
        timeline += [Flight(previous, scene, world), scene]
        if pick["clip"]:
            timeline.append(ClipScene(pick, scene))
        previous = scene
    timeline.append(Flight(previous, outro, world))
    timeline.append(outro)

    colours = [carto.PERIL_COLOURS[PERIL_KEY[e["event_type"]]] for e in events]
    tracks = any(isinstance(scene, TrackScene) for _, _, scene in scenes)
    credits = (([TRACK_CREDIT] if tracks else []) + [MAP_CREDIT]
               + [f"Video: {p['source']}." for p, _, _ in scenes if p["clip"]])
    return {"timeline": timeline, "start": start, "end": end,
            "colours": colours, "paths": paths, "outro": outro,
            "tracks": tracks, "credits": credits}


class Encoder:
    """Raw frames piped into ffmpeg: H.264, yuv420p, plus an audio track.

    `audio_path` is a pre-mixed track from `build_audio`, already the right
    length; without one (or without ffmpeg cues at all) the track is silence,
    kept only so LinkedIn's player shows normal playback controls.
    """

    def __init__(self, path: Path, audio_path: Path | None = None):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg not found; run through `conda run -n climada_env`")
        path.parent.mkdir(parents=True, exist_ok=True)
        audio_input = (["-i", str(audio_path)] if audio_path else
                      ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"])
        self.process = subprocess.Popen(
            [ffmpeg, "-y", "-v", "error",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
             "-r", str(FPS), "-i", "-",
             *audio_input,
             "-map", "0:v", "-map", "1:a", "-shortest",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
             "-movflags", "+faststart", str(path)],
            stdin=subprocess.PIPE)
        self.count = 0

    def write(self, frame: np.ndarray):
        """Takes ownership of `frame`: it is converted in place."""
        np.clip(frame, 0, 1, out=frame)
        frame *= 255
        frame += 0.5
        self.process.stdin.write(frame.astype(np.uint8).tobytes())
        self.count += 1

    def close(self):
        self.process.stdin.close()
        if self.process.wait() != 0:
            raise RuntimeError("ffmpeg failed while encoding the video")


def _target_peak_db(name: str) -> float:
    """The peak, in dB, a cue's sound file should be normalised to.

    The whoosh is the exception, quieter on purpose (see `TRANSITION_PEAK_DB`)
    so a transition never competes with the hazard it is leaving or arriving.
    """
    return TRANSITION_PEAK_DB if name == "transition_whoosh.mp3" else TARGET_PEAK_DB


@lru_cache(maxsize=None)
def _peak_gain_db(path: str, target: float) -> float:
    """The gain, in dB, that brings this file's true peak to `target`.

    Peak, not mean: a rumble or wind bed carries roughly constant energy, so
    its mean is close to what it sounds like, but a crackle or a shock is
    mostly silence between short peaks. Levelling those by their mean would
    ask for a huge boost and turn up their noise floor with it; matching the
    peaks they already have does not.
    """
    ffmpeg = shutil.which("ffmpeg")
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True)
    match = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB", result.stderr)
    peak = float(match.group(1)) if match else 0.0
    return target - peak


def sound_file(name: str) -> Path:
    """A cached local copy of one of `SOUND_SOURCES`, downloading it once."""
    path = SOUND_DIR / name
    if path.exists():
        return path
    request = urllib.request.Request(SOUND_SOURCES[name],
                                     headers={"User-Agent": "video"})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    SOUND_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def audio_cues(timeline: list) -> list:
    """`(file, start second, trim seconds or None)` for every sound.

    A trimmed cue is a bed under a scene, faded in and out at its edges so the
    hard trim point never clicks. An untrimmed one is a short one-shot
    (a whoosh, a shock, an eruption burst) played to its own natural end,
    which every source here already does cleanly. Level is not decided here:
    every cue is peak-normalised the same way in `build_audio`.
    """
    cues, t = [], 0.0
    for item in timeline:
        if isinstance(item, Flight):
            trim = max(0.6, min(item.duration - 0.1, 2.6))
            cues.append(("transition_whoosh.mp3", t, trim))
        elif isinstance(item, TrackScene):
            cues.append(("cyclone_wind.mp3", t, item.duration))
        elif isinstance(item, PointScene):
            bed = BED_SOUND.get(item.kind)
            if bed:
                cues.append((bed, t, item.duration))
            if item.kind == "EQ":
                shock = item.SHOCK_START
                while shock < item.duration:
                    cues.append(("earthquake_shock.mp3", t + shock, None))
                    shock += item.SHOCK_PERIOD
            elif item.kind == "VO":
                cues.append(("volcano_burst.mp3", t + 0.25, None))
        t += item.duration
    return cues


def build_audio(timeline: list, total_duration: float, path: Path):
    """Every cue mixed into one track, `total_duration` long, at `path`.

    Each input is resampled to the same format first: `adelay` (positioning
    in time) takes a channel count it must match, and the source clips are
    not all the same. A silent bed the length of the whole video is mixed in
    too, so the result is always exactly `total_duration` even where nothing
    plays. `alimiter` is the only thing standing between overlapping cues and
    clipping — there is no full loudness pass (see `BED_GAIN`'s note).
    """
    ffmpeg = shutil.which("ffmpeg")
    cues = audio_cues(timeline)
    # `-t` on the input, not `anullsrc`'s own `d` option: this ffmpeg build
    # (4.3.1) does not have it.
    inputs, chains, labels = ["-f", "lavfi", "-t", f"{total_duration:.3f}", "-i",
                              "anullsrc=channel_layout=stereo:sample_rate=44100"], [], ["0:a"]
    for i, (name, start, trim) in enumerate(cues, start=1):
        file = str(sound_file(name))
        inputs += ["-i", file]
        gain = _peak_gain_db(file, _target_peak_db(name))
        steps = ["aformat=sample_rates=44100:channel_layouts=stereo"]
        if trim is not None:
            fade = min(BED_FADE, trim / 2)
            steps += [f"atrim=0:{trim:.3f}",
                     f"afade=t=in:st=0:d={fade:.3f}",
                     f"afade=t=out:st={trim - fade:.3f}:d={fade:.3f}"]
        else:
            steps.append("afade=t=in:st=0:d=0.01")
        steps += [f"volume={gain:.2f}dB",
                 f"adelay={round(start * 1000)}|{round(start * 1000)}"]
        chains.append(f"[{i}:a]{','.join(steps)}[a{i}]")
        labels.append(f"a{i}")
    mix = "".join(f"[{label}]" for label in labels)
    filter_complex = ";".join(chains + [
        f"{mix}amix=inputs={len(labels)}:duration=first:dropout_transition=0,"
        f"alimiter=limit=0.9[mix]"])
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-y", "-v", "error", *inputs,
                   "-filter_complex", filter_complex, "-map", "[mix]",
                   "-t", f"{total_duration:.3f}", str(path)], check=True)


def render(monday, picks_path=None) -> dict:
    """Render the week's video and a cover image. Returns their paths."""
    began = time.time()
    plan = build(monday, picks_path)
    timeline, paths = plan["timeline"], plan["paths"]
    frame_chrome = Chrome(plan["start"], plan["end"], plan["tracks"])
    total = len(plan["colours"])
    strips = {None: Layer(np.zeros((1, 1, 4), np.float32))}
    for chapter in range(total):
        strips[chapter] = chapters(total, chapter, plan["colours"])

    # The last frame of the closing world view is also the cover image, the
    # still LinkedIn shows before the video plays.
    outro = plan["outro"]
    cover = outro.last()
    frame_chrome.over(cover)
    outro.decorate(cover, outro.duration - 0.01)
    Image.fromarray((np.clip(cover, 0, 1) * 255 + 0.5).astype(np.uint8)).save(paths["cover"])
    timeline.append(EndCard(plan["start"], plan["end"], plan["credits"], cover))

    total_duration = sum(item.duration for item in timeline)
    audio_path = paths["video"].with_suffix(".wav")
    build_audio(timeline, total_duration, audio_path)

    encoder = Encoder(paths["video"], audio_path)
    try:
        # Map, then the chrome, then the card: the card's text belongs on top
        # of the fixed paper band.
        for item in timeline:
            dress = not isinstance(item, EndCard)
            decorate = getattr(item, "decorate", None)
            for i, frame in enumerate(item.frames()):
                if dress:
                    frame_chrome.over(frame)
                    if decorate:
                        decorate(frame, i / FPS)
                    strips[item.chapter].over(frame)
                encoder.write(frame)
    finally:
        encoder.close()
    audio_path.unlink(missing_ok=True)

    seconds = encoder.count / FPS
    print(f"{paths['video']}  {seconds:.1f} s, {encoder.count} frames, "
          f"rendered in {time.time() - began:.0f} s")
    return {"video": paths["video"], "cover": paths["cover"], "seconds": seconds}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text_ in (("candidates", "list the week's events and write the picks file"),
                        ("render", "render the video from the picks file")):
        command = sub.add_parser(name, help=text_)
        command.add_argument("monday", help="publication Monday, YYYY-MM-DD")
        if name == "render":
            command.add_argument("--picks", help="another picks file")
    args = parser.parse_args(argv)
    # Place names come from every language; a Windows console that cannot
    # print one should not stop the run.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(errors="replace")

    if args.command == "candidates":
        found = candidates(args.monday)
        paths = write_picks(found)
        print(paths["picks"].read_text(encoding="utf-8"))
        print(f"Edit {paths['picks']}, then run: python video.py render {args.monday}")
    else:
        render(args.monday, args.picks)


if __name__ == "__main__":
    main()
