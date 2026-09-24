"""When the satellite will actually look, read from the published plan.

The pipeline used to answer "when is the next pass?" by measuring what
Sentinel-1 did over an area in the recent past and projecting it forward. That
is an extrapolation, and it was wrong in both directions: it returned a 12-day
cycle over Rasuwa where the true interval was 4 days, and it silently ignored
that a satellite only produces an image where the mission plan says the
instrument is on.

ESA publishes the plan. One KML per satellite, updated every few days, holding
every planned acquisition segment with its start, its end, its orbit and its
ground footprint, two to three weeks ahead. Reading it is not a forecast, it
is a schedule, and it removes the guesswork entirely.

    from plan import next_look
    next_look((85.30, 28.13, 85.40, 28.30))

Source: Sentinel Online, Acquisition Plans. Free, no account.
"""

from __future__ import annotations

import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import Polygon, box

ROOT = Path(__file__).parent
PLAN_CACHE = ROOT / "data" / "cache" / "plans"

BASE = "https://sentinels.copernicus.eu"
AGENT = {"User-Agent": "Mozilla/5.0 natcat"}

# One page per mission, each listing the KML for every satellite in it.
PLAN_PAGES = {
    "sentinel-1": "/copernicus/sentinel-1/acquisition-plans",
    "sentinel-2": "/copernicus/sentinel-2/acquisition-plans",
}

# The file names carry the satellite and the window they cover, which is how
# the newest plan is picked without opening anything.
PLAN_NAME = re.compile(
    r"(?P<sat>s[12][a-d])_mp_(?:user|acq__kml)_"
    r"(?P<start>\d{8})t\d{6}_(?P<end>\d{8})t\d{6}"
)

KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}


def _fetch(url: str, timeout: int = 180) -> bytes:
    request = urllib.request.Request(url, headers=AGENT)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def plan_files(mission: str) -> list[dict]:
    """Every plan file listed for a mission, newest window last.

    The page is HTML and the links have no extension, so the satellite and the
    window are read from the file name rather than from the markup.
    """
    html = _fetch(BASE + PLAN_PAGES[mission]).decode("utf-8", "ignore")

    found = {}
    for href in re.findall(r'href="(/documents/d/sentinel/[^"]+)"', html):
        match = PLAN_NAME.search(href)
        if not match:
            continue
        satellite = match.group("sat").upper()
        entry = {
            "satellite": satellite,
            "url": BASE + href,
            "name": href.rsplit("/", 1)[-1],
            "start": datetime.strptime(match.group("start"), "%Y%m%d"),
            "end": datetime.strptime(match.group("end"), "%Y%m%d"),
        }
        # Several plans overlap; the one issued last covers the future best.
        if satellite not in found or entry["end"] > found[satellite]["end"]:
            found[satellite] = entry
    return sorted(found.values(), key=lambda e: e["satellite"])


def _cached(entry: dict) -> bytes:
    PLAN_CACHE.mkdir(parents=True, exist_ok=True)
    path = PLAN_CACHE / f"{entry['name']}.kml"
    if not path.exists():
        path.write_bytes(_fetch(entry["url"]))
    return path.read_bytes()


def load_plan(entry: dict) -> list[dict]:
    """Parse one plan file into acquisition segments.

    Returns one dictionary per segment: satellite, mode, relative orbit, start
    and end in UTC, and the ground footprint as a shapely polygon.
    """
    root = ET.fromstring(_cached(entry))
    segments = []

    for placemark in root.iter(f"{{{KML_NS['kml']}}}Placemark"):
        span = placemark.find("kml:TimeSpan", KML_NS)
        ring = placemark.find(".//kml:coordinates", KML_NS)
        if span is None or ring is None or not (ring.text or "").strip():
            continue

        points = []
        for triple in ring.text.split():
            parts = triple.split(",")
            if len(parts) >= 2:
                points.append((float(parts[0]), float(parts[1])))
        if len(points) < 4:
            continue

        data = {}
        for item in placemark.iter(f"{{{KML_NS['kml']}}}Data"):
            value = item.find("kml:value", KML_NS)
            if value is not None:
                data[item.get("name")] = (value.text or "").strip()

        begin = span.findtext("kml:begin", "", KML_NS)
        end = span.findtext("kml:end", "", KML_NS)
        if not begin:
            continue

        segments.append({
            "satellite": data.get("SatelliteId", entry["satellite"]),
            "mode": data.get("Mode", ""),
            "orbit": data.get("OrbitRelative", ""),
            "start": datetime.fromisoformat(begin).replace(tzinfo=timezone.utc),
            "end": (datetime.fromisoformat(end).replace(tzinfo=timezone.utc)
                    if end else None),
            # A footprint that crosses the antimeridian comes back folded; a
            # buffer of zero repairs the self-intersection it produces.
            "footprint": Polygon(points).buffer(0),
        })
    return segments


def planned_acquisitions(aoi: tuple, missions=("sentinel-1", "sentinel-2"),
                         after=None, limit: int = 40) -> list[dict]:
    """Planned acquisitions covering an area, soonest first.

    `aoi` is (min_lon, min_lat, max_lon, max_lat). Only segments whose
    footprint actually intersects the area are returned, so this answers "when
    will this ground be imaged" rather than "when will a satellite go past".
    """
    after = after or datetime.now(timezone.utc)
    if after.tzinfo is None:
        after = after.replace(tzinfo=timezone.utc)
    area = box(*aoi)

    hits = []
    for mission in missions:
        for entry in plan_files(mission):
            for segment in load_plan(entry):
                if segment["start"] < after:
                    continue
                if not segment["footprint"].intersects(area):
                    continue
                covered = segment["footprint"].intersection(area).area
                hits.append({**segment, "mission": mission,
                             "share": covered / area.area if area.area else 0.0})

    hits.sort(key=lambda s: s["start"])
    return hits[:limit]


def landsat_look(aoi: tuple, after=None) -> dict | None:
    """The next Landsat acquisition, projected from its own fixed cycle.

    USGS publishes no footprint plan, and it does not need one. Landsat has no
    tasking: the instrument is on and the orbit repeats every 16 days per
    satellite, offset so that 8 and 9 together return every 8. Measured over
    the Bhote Koshi valley: gaps of 8, 8, 8, 8, 8, 8, 8, 8, 16 days, the last
    being one missed acquisition. So the cycle *is* the plan, and the last
    acquisition plus the measured interval is the next look.

    Returned in the same shape as a Sentinel segment so a caller does not have
    to know which mission answered.
    """
    import statistics
    from datetime import timedelta

    import catalog

    after = after or datetime.now(timezone.utc)
    if after.tzinfo is None:
        after = after.replace(tzinfo=timezone.utc)

    window_start = (after - timedelta(days=90)).date().isoformat()
    try:
        scenes = catalog.scenes(aoi, window_start, after.date().isoformat(),
                                sensors=("landsat",))
    except Exception:                                          # noqa: BLE001
        return None

    stamps = sorted({s["when"] for s in scenes if s["when"]})
    if len(stamps) < 2:
        return None

    gaps = [(b - a).days for a, b in zip(stamps, stamps[1:]) if (b - a).days]
    cycle = int(statistics.median_low(gaps)) if gaps else 8

    when = stamps[-1] + timedelta(days=cycle)
    while when <= after:
        when += timedelta(days=cycle)

    return {
        "satellite": "Landsat 8/9",
        "mission": "landsat",
        "mode": "OLI",
        "orbit": "",
        "start": when,
        "end": when,
        "footprint": None,
        # The cycle repeats the same ground track, so a scene that covered the
        # area before covers it again. Projected rather than read, and said so.
        "share": 1.0,
        "projected": True,
        "cycle_days": cycle,
    }


def next_look(aoi: tuple, after=None, min_share: float = 0.9,
              include_landsat: bool = True) -> dict:
    """The next planned acquisition per satellite, and the soonest overall.

    `min_share` is the fraction of the area a single segment has to cover to
    count. A swath clipping one corner is not a look at the event.
    """
    acquisitions = planned_acquisitions(aoi, after=after, limit=400)
    usable = [a for a in acquisitions if a["share"] >= min_share]

    if include_landsat:
        landsat = landsat_look(aoi, after=after)
        if landsat:
            usable.append(landsat)
            usable.sort(key=lambda s: s["start"])

    per_satellite = {}
    for entry in usable:
        per_satellite.setdefault(entry["satellite"], entry)

    return {
        "soonest": usable[0] if usable else None,
        "per_satellite": per_satellite,
        "partial": [a for a in acquisitions if a["share"] < min_share][:5],
        "checked": datetime.now(timezone.utc),
    }


def _self_check() -> None:
    """Run: conda run -n climada_env python plan.py"""
    valley = (85.303, 28.129, 85.401, 28.300)          # Bhote Koshi, Rasuwa
    marne = (2.32, 48.68, 2.62, 48.86)                 # Val-de-Marne

    files = plan_files("sentinel-1") + plan_files("sentinel-2")
    assert files, "no acquisition plan files listed"
    print(f"ok  {len(files)} plan files listed")
    for entry in files:
        print(f"      {entry['satellite']}  covers to {entry['end']:%Y-%m-%d}")

    segments = load_plan(files[0])
    assert segments, "plan parsed to nothing"
    assert segments[0]["footprint"].is_valid
    print(f"ok  {files[0]['satellite']} plan parses to {len(segments)} segments")

    for label, aoi in (("Rasuwa", valley), ("Val-de-Marne", marne)):
        answer = next_look(aoi)
        soonest = answer["soonest"]
        assert soonest is not None, f"no planned acquisition over {label}"
        assert soonest["start"] > datetime.now(timezone.utc)
        print(f"ok  {label}: next full look {soonest['start']:%Y-%m-%d %H:%M} UTC "
              f"by {soonest['satellite']} ({soonest['mode']})")
        for satellite, entry in sorted(answer["per_satellite"].items()):
            how = " projected from the repeat cycle" if entry.get("projected") else ""
            print(f"      {satellite}  {entry['start']:%Y-%m-%d %H:%M} UTC  "
                  f"{entry['share']:.0%} of the area{how}")
        assert any(e.get("projected") for e in answer["per_satellite"].values()), \
            f"Landsat missing from the answer over {label}"

    print("\nchecks passed")


if __name__ == "__main__":
    _self_check()
