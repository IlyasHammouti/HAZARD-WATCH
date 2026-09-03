"""Shared functions for the natural catastrophe loss pipeline.

Import what you need from a notebook:

    from natcat import flood_extent

Each function does one thing and returns plain objects (numpy arrays,
dictionaries) rather than custom types, so results stay easy to inspect.

If you edit this file while a notebook is running, restart the kernel or put
these two lines at the top of the notebook, otherwise the old version stays in
memory:

    %load_ext autoreload
    %autoreload 2
"""

from __future__ import annotations

import json
import math
import statistics
import urllib.error
import urllib.parse
import urllib.request
import warnings
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import rasterio
import rasterio.transform
import rasterio.warp
from rasterio.windows import from_bounds

STAC_SEARCH = "https://stac.eodc.eu/api/v1/search"

# GFM pixel coding, from the product user manual
GFM_DRY = 0
GFM_FLOODED = 1
GFM_NODATA = 255


def gfm_scenes(aoi: tuple, start: str, end: str, limit: int = 50) -> list[dict]:
    """List Copernicus Global Flood Monitoring scenes covering an area and period.

    GFM is derived automatically from Sentinel-1 and published openly, with no
    account required. One scene corresponds to one satellite pass over one
    tile, so several scenes are usually needed to cover a single area.

    Parameters
    ----------
    aoi : (min_lon, min_lat, max_lon, max_lat) in degrees.
    start, end : ISO dates, e.g. "2023-05-17".

    Returns
    -------
    List of STAC items, most recent first.
    """
    body = {
        "collections": ["GFM"],
        "bbox": list(aoi),
        "datetime": f"{start}T00:00:00Z/{end}T00:00:00Z",
        "limit": limit,
    }
    request = urllib.request.Request(
        STAC_SEARCH,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        items = json.loads(response.read())["features"]

    return sorted(items, key=lambda i: i["properties"]["datetime"], reverse=True)


def _read_window(url: str, aoi: tuple) -> tuple[np.ndarray, dict]:
    """Read only the part of a remote GeoTIFF that covers the area of interest.

    GFM files are Cloud Optimized GeoTIFFs, so GDAL can fetch just the tiles it
    needs over HTTP. A full scene is 15000 x 15000 pixels; this avoids
    downloading it.
    """
    with rasterio.open("/vsicurl/" + url) as src:
        left, bottom, right, top = rasterio.warp.transform_bounds(
            "EPSG:4326", src.crs, *aoi
        )
        window = from_bounds(left, bottom, right, top, src.transform)
        data = src.read(1, window=window, boundless=True, fill_value=GFM_NODATA)
        profile = {
            "crs": src.crs,
            "transform": src.window_transform(window),
            "resolution": src.res[0],
        }
    return data, profile


def flood_extent(aoi: tuple, start: str, end: str) -> dict:
    """Maximum observed flood extent for an area and period, from GFM.

    Individual scenes only cover part of an area, and the flood itself moves:
    water rises, peaks, then recedes. Taking the most recent scene would report
    the situation after the water has partly drained.

    For damage estimation what matters is the **maximum** extent: a building
    flooded on the 22nd is damaged even if it is dry on the 23rd. So a pixel
    counts as flooded if *any* scene in the period saw water there.

    GFM also ships an exclusion mask marking pixels where its own detection is
    not reliable — chiefly built-up areas, where the double bounce between
    ground and walls keeps the radar return bright even when the street is
    under water. Those pixels are reported separately: they are not "dry", they
    are "unknown", and treating them as dry is what biases a loss estimate
    downwards exactly where value concentrates.

    Returns a dictionary with:
        flooded    : boolean array, True where water was seen at any point
        observed   : boolean array, True where any scene had valid data
        excluded   : boolean array, True where no scene could assess the pixel
        area_km2   : maximum flooded area over the period
        coverage   : share of the area actually observed, 0 to 1
        assessable : share of the observed area radar could actually judge
        timeline   : per-scene measurements, oldest first
        profile    : crs, transform and resolution, for export
    """
    scenes = gfm_scenes(aoi, start, end)
    if not scenes:
        raise ValueError(f"No GFM scene for {aoi} between {start} and {end}")

    flooded = None
    observed = None
    assessable = None
    profile = None
    timeline = []

    for item in scenes:
        data, prof = _read_window(item["assets"]["ensemble_flood_extent"]["href"], aoi)

        scene_observed = data != GFM_NODATA
        if not scene_observed.any():
            continue  # scene does not actually observe this area

        scene_flooded = data == GFM_FLOODED
        excl, _ = _read_window(item["assets"]["exclusion_mask"]["href"], aoi)
        scene_assessable = excl == 0  # 1 means excluded, confirmed empirically

        if flooded is None:
            flooded, observed, assessable = scene_flooded, scene_observed, scene_assessable
            profile = prof
        else:
            flooded |= scene_flooded
            observed |= scene_observed
            assessable |= scene_assessable

        pixel_km2 = prof["resolution"] ** 2 / 1e6
        timeline.append(
            {
                "datetime": item["properties"]["datetime"],
                "area_km2": float(scene_flooded.sum() * pixel_km2),
                "coverage": float(scene_observed.mean()),
                "id": item["id"],
            }
        )

    if flooded is None:
        raise ValueError("GFM scenes exist but none observes this area")

    excluded = observed & ~assessable
    pixel_area_km2 = profile["resolution"] ** 2 / 1e6
    timeline.sort(key=lambda s: s["datetime"])

    return {
        "flooded": flooded,
        "observed": observed,
        "excluded": excluded,
        "area_km2": float(flooded.sum() * pixel_area_km2),
        "coverage": float(observed.mean()),
        "assessable": float(assessable.sum() / max(observed.sum(), 1)),
        "timeline": timeline,
        "profile": profile,
    }


# ---------------------------------------------------------------------------
# Exposure
# ---------------------------------------------------------------------------


def _ee_to_grid(
    image, aoi: tuple, profile: dict, shape: tuple, scale: int, max_pixels: int = 3_000_000
):
    """Download an Earth Engine image and resample it onto a local target grid.

    Everything in the pipeline has to live on the same grid before it can be
    combined, and that grid is set by the hazard footprint. This fetches the
    area of interest from Earth Engine and reprojects it to match exactly.

    Large or computationally heavy requests are split into tiles. Earth Engine
    computes each download synchronously, so a wide area combined with a long
    image collection hits "User memory limit exceeded" — splitting keeps every
    single request inside the budget. Tiles do not overlap, so recombining them
    with a maximum is exact.
    """
    from rasterio.io import MemoryFile
    from rasterio.warp import Resampling, reproject

    import ee

    lon_min, lat_min, lon_max, lat_max = aoi
    mid_lat = math.radians((lat_min + lat_max) / 2)
    width_m = (lon_max - lon_min) * 111_320 * math.cos(mid_lat)
    height_m = (lat_max - lat_min) * 111_320
    estimated = (width_m / scale) * (height_m / scale)

    splits = max(1, math.ceil(math.sqrt(estimated / max_pixels)))
    lon_step = (lon_max - lon_min) / splits
    lat_step = (lat_max - lat_min) / splits

    destination = np.zeros(shape, dtype="float32")

    for i in range(splits):
        for j in range(splits):
            tile = (
                lon_min + i * lon_step,
                lat_min + j * lat_step,
                lon_min + (i + 1) * lon_step,
                lat_min + (j + 1) * lat_step,
            )
            url = image.getDownloadURL(
                {
                    "region": ee.Geometry.Rectangle(list(tile)),
                    "scale": scale,
                    "format": "GEO_TIFF",
                    "crs": "EPSG:4326",
                }
            )
            # Network here is intermittently flaky; a tile is cheap to retry
            # and losing a whole run to one dropped connection is not.
            raw = None
            for attempt in range(4):
                try:
                    with urllib.request.urlopen(url, timeout=300) as response:
                        raw = response.read()
                    break
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    if attempt == 3:
                        raise
                    warnings.warn(f"tile download retry {attempt + 1}: {exc}")

            patch = np.zeros(shape, dtype="float32")
            with MemoryFile(raw) as memfile, memfile.open() as src:
                reproject(
                    source=rasterio.band(src, 1),
                    destination=patch,
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=profile["transform"],
                    dst_crs=profile["crs"],
                    resampling=Resampling.average,
                )
            np.maximum(destination, np.nan_to_num(patch), out=destination)

    return destination


def _ghsl_built_fraction(aoi: tuple, profile: dict, shape: tuple) -> np.ndarray:
    """Built-up fraction per pixel, from GHSL, resampled onto a target grid.

    GHSL gives built-up surface in square metres per 100 m cell, so at most
    10000. Dividing by that turns it into a fraction between 0 and 1, which can
    be resampled safely — a quantity in square metres could not, since summing
    or averaging it across a change of resolution would not conserve the total.
    """
    import ee

    built = (
        ee.ImageCollection("JRC/GHSL/P2023A/GHS_BUILT_S")
        .filter(ee.Filter.eq("system:index", "2020"))
        .first()
        .select("built_surface")
        .divide(10000)  # square metres per 100 m cell -> fraction
    )
    return _ee_to_grid(built, aoi, profile, shape, scale=100)


# Perils whose reported point is the event itself. An earthquake epicentre and
# a fire cluster are located; a flood point is the centroid of an affected
# basin and a cyclone point is one position on a moving track. Measured: GDACS
# puts the Rasuwa flood at (85.365, 27.295), which resolves to Narayani, while
# the glacial lake outburst was in Bagmati, 100 km north.
LOCATABLE_PERILS = ("EQ", "WF", "VO")


def event_regions(events: list) -> dict:
    """First-level administrative region for events whose point is the event.

    Returns `{event_id: region name}`, and an empty dictionary if Earth Engine
    is unavailable. The digest runs on plain HTTP otherwise, and losing a
    region name is not a reason to lose the week's post.

    Only the first administrative level is used. GAUL's second level returns
    `Name Unknown` and `Administrative unit not available` often enough that it
    cannot be published without checking each one by hand.
    """
    wanted = [e for e in events
              if e["event_type"] in LOCATABLE_PERILS
              and "," not in (e.get("country") or "")]
    if not wanted:
        return {}

    try:
        import ee

        points = ee.FeatureCollection([
            ee.Feature(ee.Geometry.Point([e["lon"], e["lat"]]),
                       {"event_id": e["event_id"]})
            for e in wanted
        ])
        gaul = ee.FeatureCollection("FAO/GAUL/2015/level1")
        located = points.map(lambda f: f.set(
            gaul.filterBounds(f.geometry()).first().toDictionary(["ADM1_NAME"])))
        rows = located.getInfo()["features"]
    except Exception:                                          # noqa: BLE001
        return {}

    regions = {}
    for row in rows:
        name = (row["properties"] or {}).get("ADM1_NAME")
        if name and "unknown" not in name.lower() and "not available" not in name.lower():
            regions[row["properties"]["event_id"]] = name
    return regions


def population(aoi: tuple, profile: dict, shape: tuple) -> np.ndarray:
    """Residents per pixel, from GHSL population, on the pipeline grid.

    Tier 2 is defined in `docs/EDITORIAL_RULES.md` as *exposed value and
    affected population*, so a tier 2 post without a population figure does
    not deliver what its own locked sentence promises.

    GHS_POP counts people per 100 m cell. Dividing by the cell area gives a
    density, which resamples correctly onto a finer grid; a count would not,
    because resampling would duplicate people. Multiplying back by the target
    pixel area restores a count that sums to the same total.
    """
    import ee

    people = (
        ee.ImageCollection("JRC/GHSL/P2023A/GHS_POP")
        .filter(ee.Filter.eq("system:index", "2020"))
        .first()
        .select("population_count")
        .divide(100 * 100)          # people per 100 m cell -> people per m2
    )
    density = _ee_to_grid(people, aoi, profile, shape, scale=100)
    return density * (profile["resolution"] ** 2)


def _litpop(country: str):
    """LitPop exposure for a country, preferring the local copy.

    The CLIMADA data client checks its server for a newer version on every
    call, which stalls the whole pipeline whenever that server is slow. Once a
    country has been downloaded the file is on disk and does not change, so a
    failed check is no reason to give up: fall back to the cached file.
    """
    from climada.util.api_client import Client

    try:
        return Client().get_litpop(country)
    except Exception as exc:  # network or server-side failure, not a data error
        import pycountry
        from climada.entity import Exposures
        from climada.util.constants import SYSTEM_DIR

        iso3 = pycountry.countries.lookup(country).alpha_3
        matches = sorted(SYSTEM_DIR.glob(f"exposures/litpop/*{iso3}*/**/*.hdf5"))
        if not matches:
            raise RuntimeError(
                f"LitPop for {country} is neither reachable nor cached locally"
            ) from exc
        warnings.warn(f"LitPop server unreachable, using cached {matches[-1].name}")
        return Exposures.from_hdf5(matches[-1])


def exposure(aoi: tuple, country: str, profile: dict, shape: tuple) -> dict:
    """Exposed value per pixel, on the same grid as the hazard footprint.

    Two datasets, each used for what it does best.

    LitPop anchors the **total**: it distributes a published national figure for
    produced capital, so the sum over an area is macroeconomically grounded. Its
    weakness is resolution — roughly 4.6 km, far coarser than the narrow strips
    a river floods.

    GHSL provides the **spatial pattern** at 100 m: where the buildings actually
    are. It carries no monetary value of its own.

    Combining them keeps LitPop's anchoring and GHSL's detail: the LitPop total
    for the area is redistributed in proportion to built-up surface.

    Returns:
        value       : array of exposed value per pixel, same grid as the hazard
        total       : total exposed value over the area
        currency    : currency and base year of that total
        built_km2   : total built-up area
        litpop_cells: number of LitPop cells the total came from, for reference
    """
    litpop = _litpop(country)
    lon_min, lat_min, lon_max, lat_max = aoi
    local = litpop.gdf.cx[lon_min:lon_max, lat_min:lat_max]
    total = float(local["value"].sum())

    built = _ghsl_built_fraction(aoi, profile, shape)
    built_sum = built.sum()
    if built_sum == 0:
        raise ValueError("No built-up surface found in this area")

    pixel_m2 = profile["resolution"] ** 2

    return {
        "value": (built / built_sum) * total,
        "total": total,
        "currency": "USD, constant 2014 (LitPop produced capital)",
        "built_km2": float(built.sum() * pixel_m2 / 1e6),
        "litpop_cells": int(len(local)),
    }



def optical_water(
    aoi: tuple,
    start: str,
    end: str,
    profile: dict,
    shape: tuple,
    max_cloud: int = 60,
    threshold: float = 0.2,
) -> dict:
    """Water seen by Sentinel-2, used to fill the gaps radar cannot assess.

    Radar fails in built-up areas because walls bounce the signal back brightly
    even when the street is flooded. Optical imagery has the opposite profile:
    it sees standing water in a city perfectly well, but only through a clear
    sky — and floods come with clouds.

    The two are therefore complementary rather than competing, which is the
    approach recommended by UN-SPIDER (*Flood Mapping with Sentinel-1 and
    Sentinel-2 Imagery and Digital Terrain Models*).

    The index used is MNDWI, green minus shortwave infrared. Plain NDWI
    confuses water with built-up surfaces; MNDWI was designed specifically to
    separate the two, which is what this is for.

    The maximum over the period is kept, matching the maximum-extent rule used
    for radar. Permanent water is removed, so rivers and lakes are not counted
    as flooding.

    ``threshold`` matters more than it looks. The textbook value of 0 is far
    too permissive here: building shadows have low shortwave infrared, so they
    score high on MNDWI, and this function is deliberately pointed at built-up
    land. Measured on EMSR664, a threshold of 0 classified 8.3 % of all
    built-up area in the region as flooded, which is not credible; 0.2 brought
    that to 1.0 %, consistent with the radar footprint and with reported
    damage. Terrain filtering removes more of what remains.

    Returns:
        water     : boolean array, True where standing water was seen
        area_km2  : detected area
        scenes    : number of usable Sentinel-2 scenes
        usable    : share of the area that was cloud-free at least once
    """
    import ee

    region = ee.Geometry.Rectangle(list(aoi))
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(region)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud))
    )

    count = collection.size().getInfo()
    if count == 0:
        return {
            "water": np.zeros(shape, dtype=bool),
            "area_km2": 0.0,
            "scenes": 0,
            "dates": [],
            "usable": 0.0,
        }

    def drop_clouds(image):
        # Scene classification: 3 shadow, 8 and 9 cloud, 10 cirrus
        scl = image.select("SCL")
        clear = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10))
        return image.updateMask(clear)

    clear = collection.map(drop_clouds)
    mndwi = clear.map(lambda i: i.normalizedDifference(["B3", "B11"])).max()

    permanent = (
        ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").gt(50).unmask(0)
    )
    water_image = mndwi.gt(threshold).And(permanent.Not())

    # A pixel cloudy in every scene has no value at all; track that separately
    # so an absence of detection is not read as an absence of water.
    observed_image = mndwi.mask().gt(0)

    water = _ee_to_grid(water_image.unmask(0), aoi, profile, shape, scale=20) > 0.5
    observed = _ee_to_grid(observed_image.unmask(0), aoi, profile, shape, scale=20) > 0.5

    # The acquisition dates, because a post has to say which picture it is
    # quoting. Where the optical layer produces most of the extent, naming the
    # Sentinel-1 pass instead credits the wrong instrument.
    stamps = collection.aggregate_array("system:time_start").getInfo()
    dates = sorted({datetime.fromtimestamp(s / 1000, timezone.utc)
                    .strftime("%Y-%m-%d") for s in stamps})

    pixel_km2 = profile["resolution"] ** 2 / 1e6
    return {
        "water": water & observed,
        "area_km2": float((water & observed).sum() * pixel_km2),
        "scenes": int(count),
        "dates": dates,
        "usable": float(observed.mean()),
    }


def merge_extents(radar: dict, optical: dict) -> dict:
    """Combine radar and optical footprints, each where it is trustworthy.

    Radar keeps priority everywhere it could actually judge. Optical is only
    allowed to speak where radar declared itself unreliable — that is, inside
    the exclusion mask, which is mostly built-up land.

    This is deliberately conservative: it never lets optical contradict a valid
    radar reading, it only lets it fill a hole.

    Returns the same keys as ``flood_extent`` plus:
        filled_km2 : area recovered by optical inside the radar blind spot
        still_blind: share of exposed-area pixels neither sensor could assess
    """
    filled = radar["excluded"] & optical["water"]
    combined = radar["flooded"] | filled

    pixel_km2 = radar["profile"]["resolution"] ** 2 / 1e6
    blind = radar["excluded"] & ~optical["water"]

    merged = dict(radar)
    merged["flooded"] = combined
    merged["area_km2"] = float(combined.sum() * pixel_km2)
    merged["filled_km2"] = float(filled.sum() * pixel_km2)
    merged["still_blind"] = float(blind.sum() / max(radar["observed"].sum(), 1))
    return merged


# ---------------------------------------------------------------------------
# Watch — step 1 of the pipeline: which events deserve treatment
# ---------------------------------------------------------------------------

GDACS_EVENTS = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
GDACS_GEOMETRY = "https://www.gdacs.org/gdacsapi/api/polygons/getgeometry"
CDSE_PRODUCTS = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"

# GDACS returns at most this many events per query and gives no way to page
# past it. A query that comes back exactly full is almost certainly truncated.
GDACS_CAP = 100

# Perils GDACS publishes. Tsunami ("TS") exists as a code but is folded into
# the earthquake feed in practice, so it is not queried by default.
GDACS_PERILS = {
    "EQ": "Earthquake",
    "TC": "Tropical cyclone",
    "FL": "Flood",
    "VO": "Volcano",
    "WF": "Wildfire",
    "DR": "Drought",
}
GDACS_TYPES = tuple(GDACS_PERILS)

# Measured on EMSR664: event 2023-05-16, first GFM scene 2023-05-17 05:11 UTC.
GFM_LATENCY_HOURS = 19


def _get_json(url: str, params: dict | None = None, timeout: int = 90):
    """Fetch a URL and parse the JSON body, returning None when it is empty.

    GDACS answers a query with no matches using HTTP 204 and a zero-length
    body rather than an empty list, which would crash a plain `json.loads`.
    """
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "natcat"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw) if raw else None


def gdacs_events(
    days: int = 7,
    types: tuple = GDACS_TYPES,
    alert_levels: tuple = ("Orange", "Red"),
    end: date | None = None,
) -> list[dict]:
    """Significant natural catastrophes reported by GDACS over a time window.

    GDACS is the joint UN and European Commission alert system. It scores
    every event it detects as Green, Orange or Red, so the alert level is the
    severity filter: Orange and Red are the events worth covering, Green is
    the background noise of a planet that always has something happening.

    One query is sent per peril type. This is not a stylistic choice. The feed
    caps every response at 100 events with no way to page past it, so a single
    query covering all perils silently drops whatever does not fit. Splitting
    by type gives each peril its own 100-event budget. Any type that still
    comes back full raises a warning rather than quietly lying.

    The window filters on overlap, not on start date: a drought that began
    last November is returned in this week's window because it is still
    running. Each event therefore carries an `is_new` flag, True when it
    started inside the window, which is what separates "this happened this
    week" from "this is still going on".

    Parameters
    ----------
    days : length of the window, counting back from `end`.
    types : peril codes; see GDACS_TYPES.
    alert_levels : severity filter. Adding "Green" is possible but hits the
        100-event cap almost immediately and pushes the serious events out.
    end : last day of the window, defaults to today (UTC).

    Returns
    -------
    List of dictionaries, one per event, most severe and most recent first.
    """
    end = end or datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    level_filter = ";".join(alert_levels)

    events = []
    for event_type in types:
        payload = _get_json(
            GDACS_EVENTS,
            {
                "eventlist": event_type,
                "alertlevel": level_filter,
                "fromdate": start.isoformat(),
                "todate": end.isoformat(),
            },
        )
        features = (payload or {}).get("features", [])

        if len(features) >= GDACS_CAP:
            warnings.warn(
                f"GDACS returned {GDACS_CAP} {event_type} events, its hard cap. "
                f"The list is truncated - shorten the window below {days} days.",
                stacklevel=2,
            )

        for feature in features:
            events.append(_gdacs_event(feature, start))

    rank = {"Red": 0, "Orange": 1, "Green": 2}
    events.sort(
        key=lambda e: (rank.get(e["alert_level"], 9), -e["from_date"].toordinal())
    )
    return events


def _gdacs_event(feature: dict, window_start: date) -> dict:
    """Flatten one GDACS GeoJSON feature into a plain dictionary.

    The raw feature nests severity, geometry and links several levels deep.
    This keeps the fields a digest actually needs and drops the rest.
    """
    p = feature["properties"]
    severity = p.get("severitydata") or {}
    lon, lat = feature["geometry"]["coordinates"][:2]
    from_date = datetime.fromisoformat(p["fromdate"])

    return {
        "event_type": p["eventtype"],
        "event_id": p["eventid"],
        "episode_id": p["episodeid"],
        "name": p["name"],
        "country": p.get("country", ""),
        "iso3": p.get("iso3", ""),
        "alert_level": p["alertlevel"],
        "alert_score": p.get("alertscore"),
        "severity": severity.get("severity"),
        "severity_unit": severity.get("severityunit", ""),
        "severity_text": severity.get("severitytext", ""),
        "from_date": from_date,
        "to_date": datetime.fromisoformat(p["todate"]),
        "is_new": from_date.date() >= window_start,
        "is_current": str(p.get("iscurrent", "")).lower() == "true",
        "source": p.get("source", ""),
        "glide": p.get("glide", ""),
        "lat": lat,
        "lon": lon,
        "report_url": (p.get("url") or {}).get("report", ""),
    }


def _bbox_around(lon: float, lat: float, radius_km: float) -> tuple:
    """Square box of the given half-width around a point, in degrees.

    A degree of latitude is about 111.32 km everywhere; a degree of longitude
    shrinks towards the poles by the cosine of the latitude, so the two axes
    are converted separately.
    """
    d_lat = radius_km / 111.32
    d_lon = radius_km / (111.32 * max(math.cos(math.radians(lat)), 0.01))
    return (lon - d_lon, lat - d_lat, lon + d_lon, lat + d_lat)


# One Sentinel-1 IW acquisition is a strip about 250 km wide. An area wider
# than that can never be covered by a single pass, so asking "when is this area
# imaged in one go" over a wider box measures the rarity of favourable
# geometry, not the revisit cycle.
S1_SWATH_KM = 250.0
PASS_QUERY_MAX_KM = 100.0


def clip_aoi(aoi: tuple, max_km: float = PASS_QUERY_MAX_KM) -> tuple:
    """Shrink a box around its centre until one satellite pass can cover it.

    The GDACS affected-area polygon for a regional flood alert can span
    260 km, wider than a Sentinel-1 swath. Measuring a revisit cycle over such
    a box counts only the days when the geometry happened to be favourable,
    which returned 12 days for the Rasuwa flood where the true interval over
    the flooded valleys is 4. The centre is kept because that is where the
    event is; the edges are the part of the polygon the alert threw in.
    """
    lon_min, lat_min, lon_max, lat_max = aoi
    lat_c, lon_c = (lat_min + lat_max) / 2, (lon_min + lon_max) / 2

    max_lat = max_km / 2 / 111.32
    max_lon = max_km / 2 / (111.32 * max(math.cos(math.radians(lat_c)), 0.01))
    half_lat, half_lon = (lat_max - lat_min) / 2, (lon_max - lon_min) / 2

    if half_lat <= max_lat and half_lon <= max_lon:
        return aoi                    # already inside one swath, leave it alone

    half_lat, half_lon = min(half_lat, max_lat), min(half_lon, max_lon)
    return (lon_c - half_lon, lat_c - half_lat, lon_c + half_lon, lat_c + half_lat)


def gdacs_aoi(event: dict, radius_km: float = 25.0) -> tuple:
    """Area of interest for a GDACS event: (min_lon, min_lat, max_lon, max_lat).

    GDACS publishes several polygons per event. The one labelled as the
    affected area is the useful one; the "global area" polygon spans whole
    continents and would make any satellite question meaningless. Events with
    no polygon at all, most earthquakes among them, fall back to a box around
    the reported epicentre.

    The result is a bounding box rather than the polygon itself: every
    downstream service here takes a box, and a box never has to be repaired
    for self-intersections.
    """
    try:
        payload = _get_json(
            GDACS_GEOMETRY,
            {
                "eventtype": event["event_type"],
                "eventid": event["event_id"],
                "episodeid": event["episode_id"],
            },
            timeout=60,
        )
    except (urllib.error.URLError, TimeoutError):
        payload = None

    boxes = [
        f["bbox"]
        for f in (payload or {}).get("features", [])
        if f.get("bbox")
        and f["geometry"]["type"] != "Point"
        and f["properties"].get("Class") != "Poly_Global"
    ]

    if not boxes:
        return _bbox_around(event["lon"], event["lat"], radius_km)

    aoi = (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )
    # A polygon collapsed to a line or a point is unusable as a search area.
    if aoi[2] - aoi[0] < 1e-4 or aoi[3] - aoi[1] < 1e-4:
        return _bbox_around(event["lon"], event["lat"], radius_km)
    return aoi


def sentinel1_coverage(aoi: tuple, start: date, end: date) -> dict:
    """Share of an area that Sentinel-1 imaged, day by day.

    Read from the Copernicus Data Space catalogue, which is open and needs no
    account. Only IW GRDH products are counted, the wide-swath ground-range
    mode that flood mapping and the GFM product are built on.

    Asking only whether a satellite came near the area is not enough. One
    acquisition is a strip about 250 km wide, so a pass can clip a corner of
    an area and leave the flooded part unseen. Every acquisition footprint of
    the same day is therefore merged and measured against the area, which
    turns a vague "a satellite went past" into "this fraction of the area was
    actually imaged".

    This deliberately does not use the GFM catalogue, even though GFM is what
    the extent step consumes. GFM publishes on a fixed 300 km grid and tags
    each file with the footprint of the whole grid tile rather than the
    footprint of the satellite pass, so asking it which days covered a small
    area returns nearly every day and is wrong. The Sentinel-1 catalogue
    carries the true acquisition footprint.

    Returns {date: covered fraction between 0 and 1}, for days with imagery.
    """
    from shapely.geometry import box, shape
    from shapely.ops import unary_union

    min_lon, min_lat, max_lon, max_lat = aoi
    ring = ",".join(
        f"{x} {y}"
        for x, y in [
            (min_lon, min_lat),
            (max_lon, min_lat),
            (max_lon, max_lat),
            (min_lon, max_lat),
            (min_lon, min_lat),
        ]
    )
    query = (
        "Collection/Name eq 'SENTINEL-1' "
        f"and OData.CSC.Intersects(area=geography'SRID=4326;POLYGON(({ring}))') "
        "and contains(Name,'IW_GRDH') "
        f"and ContentDate/Start gt {start.isoformat()}T00:00:00.000Z "
        f"and ContentDate/Start lt {end.isoformat()}T23:59:59.999Z"
    )
    payload = _get_json(
        CDSE_PRODUCTS,
        {"$filter": query, "$orderby": "ContentDate/Start desc", "$top": 1000},
        timeout=120,
    )

    by_day: dict[date, list] = {}
    for product in (payload or {}).get("value", []):
        footprint = product.get("GeoFootprint")
        if not footprint:
            continue
        day = datetime.fromisoformat(product["ContentDate"]["Start"][:19]).date()
        by_day.setdefault(day, []).append(shape(footprint))

    # ponytail: areas compared in square degrees. Exact for the ratio of two
    # shapes inside one small box; switch to an equal-area projection if
    # areas of interest ever span more than a few degrees of latitude.
    area_of_interest = box(*aoi)
    return {
        day: unary_union(geoms).intersection(area_of_interest).area
        / area_of_interest.area
        for day, geoms in by_day.items()
    }


def sentinel1_passes(
    aoi: tuple, start: date, end: date, min_coverage: float = 0.9
) -> list[date]:
    """Days on which Sentinel-1 imaged enough of an area to be usable.

    A day counts as a pass when the merged acquisitions of that day cover at
    least `min_coverage` of the area. Lower the threshold for an area wider
    than a single 250 km swath, which no one pass can ever cover on its own.

    Returns dates, oldest first.
    """
    coverage = sentinel1_coverage(aoi, start, end)
    return sorted(day for day, share in coverage.items() if share >= min_coverage)


def _pass_cycle(pass_dates: list, today: date) -> tuple:
    """Revisit period and next expected pass, inferred from observed passes.

    Sentinel-1 repeats its ground track on a fixed cycle, so the interval
    between passes over one area is stable. The median gap is used rather
    than the mean because a single missed acquisition would otherwise stretch
    the estimate; the median ignores it.

    The estimate is then rolled forward until it lands in the future, which
    matters when the last known pass is already several cycles old.

    Returns (cycle_days, next_pass), or (None, None) when fewer than two
    passes are known and no interval can be measured.
    """
    dates = sorted(set(pass_dates))
    if len(dates) < 2:
        return None, None

    gaps = [(later - earlier).days for earlier, later in zip(dates, dates[1:])]
    cycle = int(statistics.median_low(gaps))

    next_pass = dates[-1] + timedelta(days=cycle)
    while next_pass <= today:
        next_pass += timedelta(days=cycle)
    return cycle, next_pass


def next_satellite_pass(
    aoi: tuple,
    lookback_days: int = 30,
    min_coverage: float = 0.9,
    end: date | None = None,
) -> dict:
    """When Sentinel-1 last covered an area, and when it is expected back.

    The prediction is empirical: it measures the revisit interval actually
    observed over this area in the recent past and projects it forward. No
    orbit propagation and no published acquisition plan, because those change,
    whereas what the satellite did last month over this exact box is a fact.

    Returns a dictionary with:
        last_pass    : date of the most recent qualifying pass, or None
        next_pass    : estimated date of the next one, or None
        cycle_days   : observed revisit interval, in days
        n_passes     : how many distinct pass days the estimate rests on
        passes       : the qualifying dates themselves
        best_coverage: largest share of the area imaged in one day over the
                       lookback period, which says whether the threshold is
                       reachable at all for an area this size
    """
    end = end or datetime.now(timezone.utc).date()
    coverage = sentinel1_coverage(aoi, end - timedelta(days=lookback_days), end)
    passes = sorted(day for day, share in coverage.items() if share >= min_coverage)
    best = max(coverage.values(), default=0.0)

    if coverage and not passes:
        warnings.warn(
            f"Sentinel-1 imaged this area on {len(coverage)} days but never more "
            f"than {best:.0%} of it in one day, short of the {min_coverage:.0%} "
            "asked for. The area is probably wider than one swath: lower "
            "min_coverage or split it.",
            stacklevel=2,
        )

    cycle, next_pass = _pass_cycle(passes, end)

    return {
        "last_pass": passes[-1] if passes else None,
        "next_pass": next_pass,
        "cycle_days": cycle,
        "n_passes": len(passes),
        "passes": passes,
        "best_coverage": best,
    }


def pending_cases(
    events: list[dict],
    types: tuple = ("FL",),
    radius_km: float = 25.0,
    lookback_days: int = 30,
    min_coverage: float = 0.9,
    end: date | None = None,
) -> list[dict]:
    """Events whose extent cannot be mapped yet, with the date that changes it.

    An event is pending when the satellite that would show its footprint has
    not covered the area since the event began. This is a normal and frequent
    state of a reactive chain, not a failure, and the expected pass date is
    the one piece of information nobody else publishes next to an alert.

    Only floods are checked by default, because only floods wait on a radar
    pass here. Wildfire extent comes from FIRMS, which is daily; earthquake
    intensity comes from a USGS ShakeMap, published within hours; tropical
    cyclone tracks come from the forecast itself. None of them queue behind an
    orbit.

    Each event costs two network calls, so pass a filtered event list rather
    than a whole month of them.

    Returns one dictionary per pending event, soonest expected pass first:
        event         : the original event dictionary
        aoi           : bounding box used
        next_pass     : estimated date of the next Sentinel-1 pass
        gfm_expected  : when the GFM flood product should follow
        cycle_days    : observed revisit interval over this area
        last_pass     : most recent pass, necessarily before the event
    """
    end = end or datetime.now(timezone.utc).date()
    pending = []

    for event in events:
        if event["event_type"] not in types:
            continue

        started = event["from_date"].date()
        aoi = clip_aoi(gdacs_aoi(event, radius_km=radius_km))
        # Look back far enough to measure a cycle even for a fresh event.
        window = max(lookback_days, (end - started).days + 1)
        passes = sentinel1_passes(
            aoi, end - timedelta(days=window), end, min_coverage=min_coverage
        )

        observed = [d for d in passes if d >= started]
        if observed:
            # A pass is not a product. GFM publishes an extent per acquisition
            # and does not cover every tile, so an area can be imaged and still
            # have no flood map: measured on Rasuwa, imaged 2026-08-28, no GFM
            # scene at all. Reporting that as "already observed" would tell a
            # reader the footprint is available when it is not.
            try:
                has_product = bool(gfm_scenes(
                    aoi, started.isoformat(),
                    (end + timedelta(days=1)).isoformat(), limit=1))
            except Exception:                                  # noqa: BLE001
                has_product = True     # never invent a pending state on error
            if has_product:
                continue
            pending.append({
                "event": event,
                "aoi": aoi,
                "state": "awaiting_product",
                "next_pass": None,
                "gfm_expected": None,
                "cycle_days": _pass_cycle(passes, end)[0],
                "last_pass": max(observed),
            })
            continue

        cycle, next_pass = _pass_cycle(passes, end)
        pending.append(
            {
                "event": event,
                "aoi": aoi,
                "state": "awaiting_pass",
                "next_pass": next_pass,
                "gfm_expected": (
                    datetime.combine(next_pass, datetime.min.time())
                    + timedelta(hours=GFM_LATENCY_HOURS)
                    if next_pass
                    else None
                ),
                "cycle_days": cycle,
                "last_pass": passes[-1] if passes else None,
            }
        )

    # Areas already imaged come first: their map is the nearest to existing.
    pending.sort(key=lambda c: (c["state"] != "awaiting_product",
                                c["next_pass"] is None,
                                c["next_pass"] or date.max))
    return pending


def _self_check() -> None:
    """Check the logic that has no business calling the network to be tested."""
    d = date(2026, 8, 1)

    # A clean 6-day cycle, projected past today.
    dates = [d, d + timedelta(days=6), d + timedelta(days=12)]
    cycle, nxt = _pass_cycle(dates, today=d + timedelta(days=13))
    assert cycle == 6, cycle
    assert nxt == d + timedelta(days=18), nxt

    # One missed acquisition must not stretch the estimate: gaps 6, 12, 6.
    dates = [d, d + timedelta(days=6), d + timedelta(days=18), d + timedelta(days=24)]
    cycle, _ = _pass_cycle(dates, today=d + timedelta(days=25))
    assert cycle == 6, cycle

    # Several acquisitions on one day collapse; one day alone yields nothing.
    assert _pass_cycle([d, d], today=d) == (None, None)
    assert _pass_cycle([], today=d) == (None, None)

    # Longitude spreads wider than latitude away from the equator.
    box = _bbox_around(lon=0.0, lat=60.0, radius_km=111.32)
    assert abs((box[3] - box[1]) - 2.0) < 1e-6, box
    assert (box[2] - box[0]) > 3.9, box

    print("natcat self-check passed")


if __name__ == "__main__":
    _self_check()


# ---------------------------------------------------------------------------
# Official reference areas
# ---------------------------------------------------------------------------

EMS_ACTIVATION = (
    "https://rapidmapping.emergency.copernicus.eu/backend"
    "/dashboard-api/public-activations/?code={code}"
)



def aoi_mask(activation: dict, profile: dict, shape: tuple) -> np.ndarray:
    """Boolean mask of the official areas, on the pipeline grid.

    The bounding box of several areas always contains land nobody mapped.
    Burning the actual polygons keeps totals honest: exposure outside the
    mapped areas is not exposure at risk in this event.
    """
    from rasterio.features import rasterize
    from shapely.geometry import mapping

    geometry = rasterio.warp.transform_geom(
        "EPSG:4326", profile["crs"], mapping(activation["union"])
    )

    burned = rasterize(
        [(geometry, 1)],
        out_shape=shape,
        transform=profile["transform"],
        fill=0,
        dtype="uint8",
    )
    return burned.astype(bool)


# ---------------------------------------------------------------------------
# Water depth and loss
# ---------------------------------------------------------------------------


def water_depth(
    flooded: np.ndarray, aoi: tuple, profile: dict, max_depth: float = 12.0
) -> np.ndarray:
    """Estimate water depth from a flood footprint and bare-earth terrain.

    A satellite footprint says where water is, not how deep it is. Damage
    functions need depth, and they are steep: assuming a flat metre everywhere
    is the single crudest approximation in the chain.

    This follows the published FwDET approach. Water in a floodplain has a
    roughly level surface, so the terrain elevation at the *edge* of the
    footprint is a good estimate of the water surface elevation nearby. For
    every flooded pixel, take the elevation of the nearest boundary pixel as
    the local water surface, subtract the ground elevation underneath, and what
    remains is depth.

    FABDEM is used rather than the Copernicus DEM. The latter is a surface
    model: it measures tree canopy and rooftops, sitting 1.7 to 3.8 m above the
    ground in forest and dense urban areas. Using it would place the ground too
    high exactly where the assets are, and so understate depth and loss.

    Depth is capped at ``max_depth``, matching the upper bound of the JRC damage
    curves, beyond which they carry no information anyway.
    """
    import ee
    from scipy import ndimage

    if not flooded.any():
        return np.zeros_like(flooded, dtype="float32")

    terrain = _ee_to_grid(
        ee.ImageCollection("projects/sat-io/open-datasets/FABDEM").mosaic().select("b1"),
        aoi,
        profile,
        flooded.shape,
        scale=30,
    )

    # Boundary of the footprint: flooded pixels touching a dry one
    interior = ndimage.binary_erosion(flooded, border_value=0)
    boundary = flooded & ~interior

    # Nearest boundary pixel for every pixel in the grid
    _, indices = ndimage.distance_transform_edt(~boundary, return_indices=True)
    water_surface = terrain[tuple(indices)]

    depth = np.where(flooded, water_surface - terrain, 0.0)
    depth = np.clip(depth, 0.0, max_depth)

    # A little smoothing: nearest-boundary sampling is noisy pixel to pixel
    depth = ndimage.uniform_filter(depth.astype("float32"), size=5)
    return np.where(flooded, depth, 0.0).astype("float32")


def flood_loss(
    depth: np.ndarray,
    value: np.ndarray,
    profile: dict,
    sector: str = "residential",
    region: str = "Europe",
) -> dict:
    """Modelled loss, by running depth and value through CLIMADA.

    The damage curve comes from the Joint Research Centre (Huizinga et al.,
    2017): published, peer-reviewed, calibrated per continent and per sector.
    Using it rather than inventing a curve is the whole reason CLIMADA is in
    this project.

    Only pixels with both water and value are passed to the engine. Dry ground
    contributes nothing to loss, and a 20-million-pixel grid would otherwise
    make the computation pointlessly heavy.

    Returns:
        loss          : modelled loss, in the currency of the exposure
        exposed       : value inside the footprint
        damage_ratio  : loss divided by exposed value
        mean_depth_m  : mean water depth where there is value at stake
        cells         : number of pixels actually evaluated
    """
    import geopandas as gpd
    from scipy import sparse
    from shapely.geometry import Point

    from climada.engine import ImpactCalc
    from climada.entity import Exposures, ImpactFuncSet
    from climada.hazard import Centroids, Hazard
    from climada_petals.entity.impact_funcs.river_flood import ImpfRiverFlood

    active = (depth > 0) & (value > 0)
    if not active.any():
        return {
            "loss": 0.0,
            "exposed": 0.0,
            "damage_ratio": 0.0,
            "mean_depth_m": 0.0,
            "cells": 0,
        }

    rows, cols = np.where(active)
    xs, ys = rasterio.transform.xy(profile["transform"], rows, cols)
    lon, lat = rasterio.warp.transform(profile["crs"], "EPSG:4326", xs, ys)

    impf = ImpfRiverFlood.from_jrc_region_sector(region, sector=sector)
    impf.check()

    exposures = Exposures(
        gpd.GeoDataFrame(
            {
                "value": value[active],
                "impf_RF": np.full(active.sum(), impf.id, dtype=int),
            },
            geometry=[Point(x, y) for x, y in zip(lon, lat)],
            crs="EPSG:4326",
        )
    )

    hazard = Hazard(
        haz_type="RF",
        intensity=sparse.csr_matrix(depth[active].reshape(1, -1)),
        centroids=Centroids(lat=np.array(lat), lon=np.array(lon)),
        event_id=np.array([1]),
        event_name=["observed"],
        frequency=np.array([1.0]),
        units="m",
    )
    hazard.check()

    impact = ImpactCalc(exposures, ImpactFuncSet([impf]), hazard).impact()
    exposed = float(value[active].sum())
    loss = float(impact.at_event[0])

    return {
        "loss": loss,
        "exposed": exposed,
        "damage_ratio": loss / exposed if exposed else 0.0,
        "mean_depth_m": float(depth[active].mean()),
        "cells": int(active.sum()),
        "impact_function": impf.name,
    }


# ---------------------------------------------------------------------------
# Loss from observed damage grades, rather than from assumed water depth
#
# The chain's whole vulnerability step exists to answer one question: given a
# hazard intensity, what fraction of a building's value is lost? A depth-damage
# curve answers it by assumption, from an assumed depth, on a 100 m grid, using
# a curve calibrated on a different continent.
#
# A Copernicus EMS grading product answers it by observation. An operator has
# looked at each building in 50 cm imagery and recorded whether it is standing.
# There is no hazard intensity to assume, no curve to borrow, and no mechanism
# to worry about: a building destroyed by debris is destroyed exactly as much
# as one destroyed by standing water.
#
# That removes the two largest sources of error in this project at once, and it
# is why an event the depth-damage path refuses can still carry a loss figure.
# What remains uncertain is narrower and is stated as a range.
# ---------------------------------------------------------------------------

# Share of replacement value lost at each grade, as a low and high bound.
#
# `Destroyed` is not an assumption: a destroyed building costs its replacement,
# which is what the word means. That matters more than it sounds here, because
# it is where the loss concentrates — 2 521 of the 3 207 buildings graded on
# EMSR927, 79 %.
#
# The two lower grades are the assumption, and Copernicus attaches no ratio to
# its own scale, so a range is used and the range is published rather than a
# point. The bounds bracket the values in common use in post-disaster needs
# assessments; anyone quoting a single number for "damaged" is choosing one.
GRADE_RATIOS = {
    "Destroyed": (1.00, 1.00),
    "Damaged": (0.30, 0.60),
    "Possibly damaged": (0.05, 0.20),
    "No visible damage": (0.00, 0.00),
}


def graded_loss(buildings: list, value: np.ndarray, profile: dict,
                ratios: dict | None = None) -> dict:
    """Loss from buildings an operator graded one by one.

    Each building takes a share of the value of the grid cell it stands in,
    split evenly between the buildings in that cell. The exposure grid says how
    much built capital sits in 100 m; the grading product says how many
    buildings that is and what happened to each. Neither alone gives a value
    per building.

    Parameters
    ----------
    buildings : EMS `builtUpP` features, each with a `damage_gra` property and
        a point geometry in EPSG:4326.
    value : exposure value per pixel, on `profile`'s grid.
    ratios : grade to (low, high) share of replacement value.

    Returns
    -------
    low, central and high loss, the exposed value of the graded buildings, the
    count per grade, and the share of buildings that fell outside the exposure
    grid and could therefore carry no value.
    """
    ratios = ratios or GRADE_RATIOS
    if not buildings:
        return {"loss_low": 0.0, "loss": 0.0, "loss_high": 0.0,
                "exposed": 0.0, "graded": 0, "unplaced": 0,
                "grades": {}, "method": "graded"}

    rows, cols, grades = [], [], []
    height, width = value.shape
    for feature in buildings:
        point = feature["geometry"]
        if point.is_empty:
            continue
        x, y = rasterio.warp.transform("EPSG:4326", profile["crs"],
                                       [point.x], [point.y])
        row, col = rasterio.transform.rowcol(profile["transform"], x[0], y[0])
        rows.append(row)
        cols.append(col)
        grades.append(feature["properties"].get("damage_gra"))

    rows = np.asarray(rows)
    cols = np.asarray(cols)
    inside = (rows >= 0) & (rows < height) & (cols >= 0) & (cols < width)

    # How many graded buildings share each cell, so a cell holding twenty
    # buildings does not hand its whole value to each of them.
    flat = rows[inside] * width + cols[inside]
    counts = np.bincount(flat, minlength=height * width)
    per_building = np.zeros(len(rows), dtype="float64")
    cell_value = value.reshape(-1)[flat]
    per_building[inside] = cell_value / np.maximum(counts[flat], 1)

    low = high = exposed = 0.0
    tally = {}
    for index, grade in enumerate(grades):
        if not inside[index]:
            continue
        share = per_building[index]
        exposed += share
        band = ratios.get(grade, (0.0, 0.0))
        low += share * band[0]
        high += share * band[1]
        tally[grade] = tally.get(grade, 0) + 1

    return {
        "loss_low": float(low),
        "loss": float((low + high) / 2),
        "loss_high": float(high),
        "exposed": float(exposed),
        "graded": int(inside.sum()),
        "unplaced": int((~inside).sum()),
        "grades": tally,
        "damage_ratio": float((low + high) / 2 / exposed) if exposed else 0.0,
        "method": "graded",
        "impact_function": "Copernicus EMS damage grades, replacement share",
    }
