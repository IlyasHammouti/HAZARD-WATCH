"""Footprints drawn by hand, and the provenance that makes them publishable.

Copernicus GFM covers routine flooding on flat ground. It produces nothing
usable for a mountain torrent, for a flash flood that has drained before the
next pass, or for a storm over one department that no authority ever asked to
have mapped. Those are the events where the analyst has to read the imagery
and draw the outline.

That is a legitimate method: Copernicus EMS Rapid Mapping operators do exactly
this, and their products are labelled `det_method: Photo-interpretation`. It
is only legitimate under one condition, which this module enforces rather than
recommends: **a hand-drawn outline is published with the imagery it was drawn
from.** Without that, an outline is an opinion in the shape of a measurement,
and there is no way for a reader to tell the two apart.

So `load_footprint` refuses a file whose provenance is incomplete. It raises
instead of warning, because the whole point of drawing by hand is that nothing
downstream can check the result: the guards can test a radar footprint against
its own exclusion mask, and they have no equivalent test here. The provenance
block is the only thing standing between an observation and an invention.

    from manual import load_footprint
    drawn = load_footprint("data/manual/valdemarne_2026-08-27.geojson")

The return value is shaped like `natcat.ems_activation`, so it drops straight
into `natcat.aoi_mask` and into the rest of the chain.
"""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import numpy as np
from shapely.geometry import shape as shapely_shape
from shapely.ops import unary_union

# Every one of these has to be present and non-empty. They are not metadata
# niceties: each answers a question a reader is entitled to ask of a line
# somebody drew by hand.
REQUIRED = {
    "operator": "who drew it",
    "drawn_on": "when, as an ISO date",
    "method": "how, e.g. photo-interpretation",
    "imagery": "what it was drawn from, one entry per scene",
    "coverage": "share of the area of interest the imagery covered, 0 to 1",
    "assessable": "share of that imagery the operator could actually read",
    "limitations": "what the operator could not see, in plain words",
}

REQUIRED_IMAGERY = ("sensor", "scene_id", "acquired", "resolution_m")

# A footprint drawn from imagery taken before the event is not a footprint of
# the event. This is the one provenance error that produces a plausible-looking
# and completely wrong result, so it is checked rather than trusted.
def _check_acquisition_dates(imagery: list, event_date: str | None) -> list:
    if not event_date:
        return []
    event_day = date.fromisoformat(event_date[:10])
    stale = [
        scene for scene in imagery
        if date.fromisoformat(scene["acquired"][:10]) < event_day
    ]
    return stale


def load_footprint(path, event_date: str | None = None) -> dict:
    """Read a hand-drawn footprint, refusing anything it cannot vouch for.

    Parameters
    ----------
    path : GeoJSON FeatureCollection with a top-level `provenance` object.
    event_date : the event date, ISO. When given, every scene the outline was
        drawn from must have been acquired on or after it.

    Returns
    -------
    Dictionary shaped like `natcat.ems_activation`: `aois`, `union`, `bounds`,
    `area_km2`, plus `provenance` and `source="manual"`.
    """
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError(
            f"{path.name} has no top-level `provenance` object. A hand-drawn "
            f"footprint is not publishable without one; see "
            f"docs/MANUAL_DELINEATION.md."
        )

    missing = [f"{k} ({why})" for k, why in REQUIRED.items()
               if provenance.get(k) in (None, "", [], {})]
    if missing:
        raise ValueError(f"{path.name} provenance is incomplete. Missing: "
                         + "; ".join(missing))

    imagery = provenance["imagery"]
    if not isinstance(imagery, list):
        raise ValueError(f"{path.name}: `imagery` must be a list of scenes.")
    for scene in imagery:
        gaps = [k for k in REQUIRED_IMAGERY if not scene.get(k)]
        if gaps:
            raise ValueError(f"{path.name}: imagery entry {scene} is missing "
                             + ", ".join(gaps))

    stale = _check_acquisition_dates(imagery, event_date)
    if stale:
        raise ValueError(
            f"{path.name}: every scene predates the event of {event_date}. "
            f"An outline drawn from before-imagery is not an observation of "
            f"this event: "
            + ", ".join(f"{s['sensor']} {s['acquired']}" for s in stale)
        )

    for share in ("coverage", "assessable"):
        value = provenance[share]
        if not 0.0 < float(value) <= 1.0:
            raise ValueError(f"{path.name}: `{share}` is {value}, expected a "
                             f"share between 0 and 1.")

    features = payload.get("features") or []
    if not features:
        raise ValueError(f"{path.name} contains no features.")

    areas = [
        {"name": (f.get("properties") or {}).get("name", f"part {i + 1}"),
         "geometry": shapely_shape(f["geometry"])}
        for i, f in enumerate(features)
    ]

    union = unary_union([a["geometry"] for a in areas])
    bounds = union.bounds
    mid_lat = math.radians((bounds[1] + bounds[3]) / 2)
    km2 = union.area * (111.32 ** 2) * math.cos(mid_lat)

    return {
        "code": provenance.get("event_code", path.stem),
        "name": provenance.get("event_name", path.stem),
        "event_time": provenance.get("event_time", event_date),
        "countries": provenance.get("countries", []),
        "aois": areas,
        "union": union,
        "bounds": tuple(round(b, 4) for b in bounds),
        "area_km2": float(km2),
        "provenance": provenance,
        "source": "manual",
    }


def grid_for(aoi: tuple, resolution_m: float = 20.0) -> tuple:
    """A metre-based grid over an area, for footprints with no source raster.

    The GFM path inherits its grid from the product it downloads. A drawn
    outline has no such raster behind it, so the grid is built here: local UTM,
    and the same 20 m the GFM ensemble product uses, which keeps areas and
    exposure totals comparable between a detected and a drawn footprint.
    """
    import rasterio.transform
    import rasterio.warp
    from rasterio.crs import CRS

    lon_c, lat_c = (aoi[0] + aoi[2]) / 2, (aoi[1] + aoi[3]) / 2
    zone = int((lon_c + 180) // 6) + 1
    epsg = (32600 if lat_c >= 0 else 32700) + zone

    left, bottom, right, top = rasterio.warp.transform_bounds(
        "EPSG:4326", f"EPSG:{epsg}", *aoi)
    width = max(1, math.ceil((right - left) / resolution_m))
    height = max(1, math.ceil((top - bottom) / resolution_m))

    profile = {
        "crs": CRS.from_epsg(epsg),
        "transform": rasterio.transform.from_origin(left, top,
                                                    resolution_m, resolution_m),
        "resolution": resolution_m,
    }
    return profile, (height, width)


def credit_values(activation: dict) -> dict:
    """Placeholder values for `L-SRC-MANUAL`, filled from the provenance.

    The wording itself lives in `docs/EDITORIAL_RULES.md` with every other
    locked string, so it cannot drift between posts. Only the facts come from
    here, and the sensor and date are the part that matters: they let a reader
    go and look at the same picture.
    """
    p = activation["provenance"]
    return {
        "OPERATOR": p["operator"],
        "DRAWN_ON": p["drawn_on"],
        "METHOD": p["method"],
        "IMAGERY": "; ".join(
            f"{s['sensor']} {s['acquired'][:10]} at {s['resolution_m']} m"
            for s in p["imagery"]
        ),
        "DRAWN_LIMITATIONS": p["limitations"],
    }


# ---------------------------------------------------------------------------
# The upstream half: getting the pictures onto the screen
#
# Drawing by hand needs something to draw on. This part fetches the scenes,
# applies the band combinations an interpreter actually uses, writes them as
# GeoTIFFs QGIS opens directly, and records what it fetched so the provenance
# block is filled from the catalogue rather than from memory.
#
#     from manual import prepare_imagery
#     prepare_imagery((84.90, 28.10, 85.10, 28.25), "2026-08-26",
#                     out_dir="data/manual/EMSR927", emsr_code="EMSR927")
#
# Then: open the folder in QGIS, draw, save the vector next to it, paste the
# provenance skeleton from `manifest.json` into the GeoJSON, and run the chain.
# ---------------------------------------------------------------------------

S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"

# Linear power rather than the decibel product. `_ee_to_grid` recombines tiles
# with a maximum, and zero outside a tile would then win against any negative
# decibel value. Power is non-negative, so the recombination is exact and the
# conversion to decibels happens here instead.
S1_COLLECTION = "COPERNICUS/S1_GRD_FLOAT"

# A drawing area is a valley or a town, not a province. Above this the download
# runs for an hour and the imagery is too coarse on screen to draw from anyway.
MAX_DRAW_PIXELS = 40_000_000


def _stamp(millis) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(millis / 1000, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _pick_s2(box, start: str, end: str, max_cloud: float):
    """Least-cloudy Sentinel-2 date in a window, mosaicked over that date.

    One dated scene, not a composite over the window. A composite has no
    acquisition time, so it cannot go in a provenance block, and a maximum
    over many dates is what produced the false positives recorded in
    docs/DECISIONS.md.
    """
    import ee

    pool = (ee.ImageCollection(S2_COLLECTION).filterBounds(box)
            .filterDate(start, end)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud))
            .sort("CLOUDY_PIXEL_PERCENTAGE"))
    if pool.size().getInfo() == 0:
        return None, None, None

    best = ee.Image(pool.first())
    meta = best.toDictionary(["CLOUDY_PIXEL_PERCENTAGE"]).getInfo()
    scene_id = best.get("system:index").getInfo()
    when = _stamp(best.get("system:time_start").getInfo())

    # Every scene of the same day, so a drawing area straddling two tiles is
    # not cut in half.
    day = ee.Date(when[:10])
    same_day = (ee.ImageCollection(S2_COLLECTION).filterBounds(box)
                .filterDate(day, day.advance(1, "day")))
    mosaic = same_day.mosaic()

    # Scene classification: 3 shadow, 8 and 9 cloud, 10 cirrus. Kept as its own
    # layer rather than applied, because the true-colour and false-colour
    # composites are more useful with the cloud left visible — the operator can
    # see what is hiding the ground — while any index difference computed
    # across cloud is nonsense and has to be blanked.
    scl = mosaic.select("SCL")
    clear = (scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10))
             .rename("clear"))

    return mosaic, clear, {
        "sensor": "Sentinel-2",
        "scene_id": scene_id,
        "acquired": when,
        "resolution_m": 10,
        "cloud_percent": round(meta.get("CLOUDY_PIXEL_PERCENTAGE", -1), 1),
    }


def _pick_s1(box, start: str, end: str, newest: bool = False,
             orbit: int | None = None, direction: str | None = None):
    """One Sentinel-1 acquisition, optionally locked to a track.

    The before and after images have to come from the same relative orbit and
    the same pass direction. A different incidence angle changes backscatter on
    unchanged ground, which manufactures a flood signal where there is none —
    the reason `docs/DECISIONS.md` records six days rather than one as the
    revisit that governs change detection.
    """
    import ee

    pool = (ee.ImageCollection(S1_COLLECTION).filterBounds(box)
            .filterDate(start, end)
            .filter(ee.Filter.eq("instrumentMode", "IW")))
    if direction:
        pool = pool.filter(ee.Filter.eq("orbitProperties_pass", direction))
    if orbit is not None:
        pool = pool.filter(ee.Filter.eq("relativeOrbitNumber_start", orbit))

    pool = pool.sort("system:time_start", not newest)
    if pool.size().getInfo() == 0:
        return None, None

    scene = ee.Image(pool.first())
    info = scene.toDictionary(
        ["relativeOrbitNumber_start", "orbitProperties_pass",
         "platform_number"]).getInfo()
    when = _stamp(scene.get("system:time_start").getInfo())

    return scene, {
        "sensor": f"Sentinel-1{info.get('platform_number', '')}",
        "scene_id": scene.get("system:index").getInfo(),
        "acquired": when,
        "resolution_m": 10,
        "track": int(info["relativeOrbitNumber_start"]),
        "direction": info["orbitProperties_pass"],
    }


def _write_tif(path, bands: list, profile: dict, descriptions: list,
               nodata: float = 0.0):
    """Write a stack of arrays as a GeoTIFF QGIS can open without help.

    `nodata` is a parameter because a difference layer has to distinguish "no
    change" from "could not be measured", and zero means the first.
    """
    import rasterio

    data = np.stack(bands).astype("float32")
    with rasterio.open(
        path, "w", driver="GTiff", height=data.shape[1], width=data.shape[2],
        count=data.shape[0], dtype="float32", crs=profile["crs"],
        transform=profile["transform"], nodata=nodata,
        compress="deflate", tiled=True,
    ) as dst:
        dst.write(data)
        for index, name in enumerate(descriptions, start=1):
            dst.set_band_description(index, name)
    return path


def _ems_orthos(code: str) -> list:
    """Very high resolution orthos Copernicus EMS published for an activation.

    These are tasked commercial scenes, typically 30 to 50 cm, delivered within
    about 48 hours and open. Where they exist they are better than anything
    Sentinel can offer, and they are the imagery EMS operators drew their own
    products from. Returned as `/vsicurl/` paths so QGIS opens them remotely
    without downloading a whole scene.
    """
    import urllib.request

    api = ("https://rapidmapping.emergency.copernicus.eu/backend/"
           "dashboard-api/public-activations/?code=" + code)
    bucket = "https://rapidmapping-viewer.s3.eu-west-1.amazonaws.com/"

    try:
        with urllib.request.urlopen(api, timeout=90) as response:
            payload = json.loads(response.read())
        activation = payload["results"][0]
    except Exception as error:                      # noqa: BLE001
        return [{"error": f"{type(error).__name__}: {error}"}]

    orthos = []
    for area in activation.get("aois", []):
        for product in area.get("products", []):
            for layer in product.get("layers", []):
                if layer.get("format") != "cog":
                    continue
                orthos.append({
                    "aoi": area.get("name"),
                    "product": product.get("type"),
                    "url": "/vsicurl/" + bucket + layer["name"],
                    "sensors": [image.get("sensorName")
                                for image in product.get("images", [])],
                    "acquired": [image.get("acquisitionTime")
                                 for image in product.get("images", [])],
                })
    return orthos


def prepare_imagery(aoi: tuple, event_date: str, out_dir, days_before: int = 24,
                    days_after: int = 10, resolution_m: float = 10.0,
                    max_cloud: float = 80.0, emsr_code: str | None = None) -> dict:
    """Fetch and process the imagery a hand delineation is drawn from.

    Writes into `out_dir`, one GeoTIFF per product, plus `manifest.json`
    carrying a provenance skeleton with the scene identifiers already filled.

    Layers written, where the scenes exist:

    | File | What it is for |
    |---|---|
    | `s2_<when>_truecolour.tif` | What the ground looks like |
    | `s2_<when>_falsecolour.tif` | Near infrared: water reads near black, vegetation bright |
    | `s2_<when>_mndwi.tif` | Green minus shortwave infrared; separates water from built-up |
    | `s1_<when>_vv_db.tif` | Radar backscatter; flat water reads dark whatever the cloud |
    | `s1_change_vv_db.tif` | After minus before, same track. Negative is new smooth surface |

    The Sentinel-1 pair is locked to one relative orbit. Cloud is not filtered
    out of the post-event Sentinel-2 scene: a partly clouded scene is often the
    only one there is, and deciding what is readable is the operator's job, not
    a threshold's.
    """
    from datetime import date, timedelta

    import ee

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    profile, shape = grid_for(aoi, resolution_m)
    if shape[0] * shape[1] > MAX_DRAW_PIXELS:
        raise ValueError(
            f"{shape[1]} by {shape[0]} pixels at {resolution_m:.0f} m is more "
            f"than {MAX_DRAW_PIXELS:,} and will not finish in a usable time. "
            f"Draw on a smaller area, or pass a coarser resolution_m."
        )

    import natcat

    day = date.fromisoformat(event_date[:10])
    before = (day - timedelta(days=days_before)).isoformat()
    after = (day + timedelta(days=days_after)).isoformat()
    box = ee.Geometry.Rectangle(list(aoi))

    manifest = {
        "aoi": list(aoi),
        "event_date": event_date,
        "resolution_m": resolution_m,
        "grid": {"width": shape[1], "height": shape[0],
                 "crs": str(profile["crs"])},
        "used": [],
        "rejected": [],
        "files": [],
    }

    def grid(image):
        return natcat._ee_to_grid(image, aoi, profile, shape,
                                  scale=int(resolution_m))

    # ---- Sentinel-2, before and after -------------------------------------
    indices = {}
    for label, window in (("pre", (before, event_date[:10])),
                          ("post", (event_date[:10], after))):
        image, clear, meta = _pick_s2(box, window[0], window[1], max_cloud)
        if image is None:
            manifest["rejected"].append(
                {"sensor": "Sentinel-2", "window": list(window),
                 "reason": f"no scene under {max_cloud:.0f} per cent cloud"})
            continue

        meta["role"] = label
        manifest["used"].append(meta)
        stem = f"s2_{label}_{meta['acquired'][:10]}"

        true_colour = [grid(image.select(band).divide(10000))
                       for band in ("B4", "B3", "B2")]
        manifest["files"].append(str(_write_tif(
            out_dir / f"{stem}_truecolour.tif", true_colour, profile,
            ["red B4", "green B3", "blue B2"])))

        false_colour = [grid(image.select(band).divide(10000))
                        for band in ("B8", "B4", "B3")]
        manifest["files"].append(str(_write_tif(
            out_dir / f"{stem}_falsecolour.tif", false_colour, profile,
            ["near infrared B8", "red B4", "green B3"])))

        # Shifted to stay positive: the tile recombination in `_ee_to_grid`
        # takes a maximum, and a negative value would lose to the zero outside
        # its own tile. Subtracting the shift back restores the true index.
        mndwi = grid(image.normalizedDifference(["B3", "B11"]).add(2)) - 2
        ndvi = grid(image.normalizedDifference(["B8", "B4"]).add(2)) - 2
        readable = grid(clear) > 0.5
        indices[label] = {"mndwi": mndwi, "ndvi": ndvi, "clear": readable,
                          "meta": meta}
        meta["clear_share"] = round(float(readable.mean()), 3)

        manifest["files"].append(str(_write_tif(
            out_dir / f"{stem}_mndwi.tif", [mndwi], profile,
            ["MNDWI, water above 0.2"])))
        manifest["files"].append(str(_write_tif(
            out_dir / f"{stem}_ndvi.tif", [ndvi], profile,
            ["NDVI, vegetation above 0.3"])))

    # ---- What changed, which is where to look -----------------------------
    # The operator's problem is not reading imagery, it is knowing where in
    # 20 km of valley to start. A difference between the same index before and
    # after answers that directly, and for a debris flow it answers it better
    # than either scene alone: water may have drained by the time of the pass,
    # but stripped vegetation and fresh deposit do not grow back in two days.
    if {"pre", "post"} <= set(indices):
        pre, post = indices["pre"], indices["post"]
        pair = f"{pre['meta']['acquired'][:10]}_to_{post['meta']['acquired'][:10]}"

        # Only where both scenes actually saw the ground. Without this the
        # layer measures cloud: on the first Rasuwa run, 90 km2 of a 183 km2
        # box showed an NDVI drop below -0.4, which was the 78.5 % cloud of
        # the post-event scene and not one square metre of debris.
        usable = pre["clear"] & post["clear"]
        d_ndvi = np.where(usable, post["ndvi"] - pre["ndvi"], np.nan)
        d_mndwi = np.where(usable, post["mndwi"] - pre["mndwi"], np.nan)

        manifest["files"].append(str(_write_tif(
            out_dir / f"s2_change_ndvi_{pair}.tif", [d_ndvi], profile,
            ["NDVI after minus before, cloud-free in both. Strongly negative "
             "is vegetation removed"], nodata=float("nan"))))
        manifest["files"].append(str(_write_tif(
            out_dir / f"s2_change_mndwi_{pair}.tif", [d_mndwi], profile,
            ["MNDWI after minus before, cloud-free in both. Strongly positive "
             "is new water"], nodata=float("nan"))))

        # One layer to open first: how far this pixel moved on either index,
        # whichever direction. It points at ground worth inspecting, and it is
        # not a result — a shadow moving between two dates moves it too.
        manifest["files"].append(str(_write_tif(
            out_dir / f"s2_change_magnitude_{pair}.tif",
            [np.fmax(np.abs(d_ndvi), np.abs(d_mndwi))], profile,
            ["Largest absolute index change. A search layer, not a result"],
            nodata=float("nan"))))

        manifest["change_pair"] = pair
        manifest["change_usable_share"] = round(float(usable.mean()), 3)
        strong = usable & (d_ndvi < -0.2)
        manifest["change_flagged_km2"] = round(
            float(strong.sum()) * (resolution_m ** 2) / 1e6, 2)

    # ---- Sentinel-1, one track, before and after --------------------------
    post, post_meta = _pick_s1(box, event_date[:10], after)
    if post is None:
        manifest["rejected"].append(
            {"sensor": "Sentinel-1", "window": [event_date[:10], after],
             "reason": "no acquisition since the event"})
    else:
        post_meta["role"] = "post"
        manifest["used"].append(post_meta)
        post_db = grid(post.select("VV"))
        post_db = 10 * np.log10(np.where(post_db > 0, post_db, np.nan))
        manifest["files"].append(str(_write_tif(
            out_dir / f"s1_post_{post_meta['acquired'][:10]}_vv_db.tif",
            [np.nan_to_num(post_db)], profile,
            [f"VV dB, track {post_meta['track']} {post_meta['direction']}"])))

        pre, pre_meta = _pick_s1(box, before, event_date[:10], newest=True,
                                 orbit=post_meta["track"],
                                 direction=post_meta["direction"])
        if pre is None:
            manifest["rejected"].append(
                {"sensor": "Sentinel-1", "window": [before, event_date[:10]],
                 "reason": f"no acquisition on track {post_meta['track']} "
                           f"before the event; a different track would change "
                           f"the incidence angle and manufacture a signal"})
        else:
            pre_meta["role"] = "pre"
            manifest["used"].append(pre_meta)
            pre_db = grid(pre.select("VV"))
            pre_db = 10 * np.log10(np.where(pre_db > 0, pre_db, np.nan))
            manifest["files"].append(str(_write_tif(
                out_dir / f"s1_pre_{pre_meta['acquired'][:10]}_vv_db.tif",
                [np.nan_to_num(pre_db)], profile,
                [f"VV dB, track {pre_meta['track']} {pre_meta['direction']}"])))
            manifest["files"].append(str(_write_tif(
                out_dir / "s1_change_vv_db.tif",
                [np.nan_to_num(post_db - pre_db)], profile,
                ["after minus before, dB. Negative is a new smooth surface"])))

    # ---- Anything Copernicus EMS already published ------------------------
    if emsr_code:
        manifest["ems_orthos"] = _ems_orthos(emsr_code)

    # ---- The provenance skeleton, with the catalogue already filled in ----
    manifest["provenance_skeleton"] = {
        "event_code": emsr_code or "REPLACE",
        "event_name": "REPLACE",
        "event_time": event_date,
        "operator": "REPLACE",
        "drawn_on": date.today().isoformat(),
        "method": "photo-interpretation",
        "scale": f"1:{int(resolution_m) * 1000}",
        "imagery": [{k: v for k, v in scene.items()
                     if k in REQUIRED_IMAGERY} for scene in manifest["used"]],
        "rejected": manifest["rejected"],
        "coverage": 1.0,
        "assessable": "REPLACE with the share you could actually read",
        "limitations": "REPLACE. Published verbatim inside L-DRAWN.",
    }

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")

    # One path per line, in the order they are worth looking at. QGIS opens a
    # `/vsicurl/` path as a remote layer without downloading the scene, which
    # matters when the best imagery is a 50 cm ortho of several hundred
    # megabytes.
    lines = ["# Drag these into QGIS. Best imagery first.", ""]
    for ortho in manifest.get("ems_orthos", []):
        if ortho.get("url"):
            lines.append(f"{ortho['url']}    # {ortho.get('aoi')}, "
                         f"{'/'.join(filter(None, ortho.get('sensors', [])))}")
    lines += [""] + [str(Path(f).resolve()) for f in manifest["files"]]
    (out_dir / "layers.txt").write_text("\n".join(lines) + "\n",
                                        encoding="utf-8")
    return manifest


def _self_check() -> None:
    """Run: conda run -n climada_env python manual.py"""
    import tempfile

    good = {
        "type": "FeatureCollection",
        "provenance": {
            "operator": "I. Hammouti",
            "drawn_on": "2026-08-28",
            "method": "photo-interpretation",
            "imagery": [{"sensor": "Sentinel-2", "scene_id": "T31UDP",
                         "acquired": "2026-08-27T10:57:00Z", "resolution_m": 10}],
            "coverage": 0.9,
            "assessable": 0.4,
            "limitations": "72 per cent cloud over the northern third.",
        },
        "features": [{
            "type": "Feature", "properties": {"name": "test"},
            "geometry": {"type": "Polygon", "coordinates":
                         [[[2.4, 48.7], [2.5, 48.7], [2.5, 48.8], [2.4, 48.8],
                           [2.4, 48.7]]]},
        }],
    }

    def write(payload):
        handle = tempfile.NamedTemporaryFile("w", suffix=".geojson",
                                             delete=False, encoding="utf-8")
        json.dump(payload, handle)
        handle.close()
        return handle.name

    drawn = load_footprint(write(good), event_date="2026-08-27")
    assert drawn["source"] == "manual"
    assert 60 < drawn["area_km2"] < 100, drawn["area_km2"]
    assert "Sentinel-2" in credit_values(drawn)["IMAGERY"]
    print("ok  a complete footprint loads")

    for label, mutate in (
        ("no provenance", lambda p: p.pop("provenance")),
        ("no operator", lambda p: p["provenance"].update(operator="")),
        ("no limitations", lambda p: p["provenance"].pop("limitations")),
        ("imagery missing a scene id",
         lambda p: p["provenance"]["imagery"][0].update(scene_id="")),
        ("assessable out of range",
         lambda p: p["provenance"].update(assessable=40)),
    ):
        payload = json.loads(json.dumps(good))
        mutate(payload)
        try:
            load_footprint(write(payload), event_date="2026-08-27")
        except ValueError:
            print(f"ok  refused: {label}")
        else:
            raise AssertionError(f"accepted a footprint with {label}")

    payload = json.loads(json.dumps(good))
    payload["provenance"]["imagery"][0]["acquired"] = "2026-08-25T10:00:00Z"
    try:
        load_footprint(write(payload), event_date="2026-08-27")
    except ValueError as error:
        assert "predates" in str(error)
        print("ok  refused: imagery older than the event")
    else:
        raise AssertionError("accepted an outline drawn from before-imagery")

    print("\n7 checks passed")


if __name__ == "__main__":
    _self_check()
