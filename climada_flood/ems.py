"""Copernicus EMS Rapid Mapping: activations, timings and mapped damage.

EMS is the source this project spent months not using, and it is the one that
covers the pipeline's own blind spot. When Sentinel fails — steep ground,
cloud, a flash flood that drains before the radar returns — EMS tasks
commercial very high resolution imagery and its operators map the damage
building by building.

Measured on EMSR927, Rasuwa, against an event at 2026-08-25 22:00 UTC:

    +11 h 53   activation opened
    +31 h      WorldView-3 and Legion acquire
    +45 h      first graded product delivered, 433 buildings
    +62 h      first Sentinel-1 acquisition over the valley
    +80 h      Copernicus GFM finally publishes an extent

EMS beat this project's own chain by 35 hours with an incomparably better
product. That is the fact V2 is built around.

Three things live here:

* discovery, because there is no public endpoint listing activations
* timings, which are what the early posts in the calendar are made of
* the mapped damage itself, read from the published vector layers

Everything is open and needs no account.
"""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parent
VECTOR_CACHE = ROOT / "data" / "ems"

DASHBOARD = ("https://rapidmapping.emergency.copernicus.eu/backend/"
             "dashboard-api/public-activations/?code={code}")
BUCKET = "https://rapidmapping-viewer.s3.eu-west-1.amazonaws.com/"
AGENT = {"User-Agent": "natcat"}

# Vector layers worth reading, matched on the stem because every product
# carries a version suffix that changes between areas of one activation.
LAYERS = (
    "observedEventA",     # what the operator mapped as the event itself
    "builtUpP",           # buildings, one point each, with a damage grade
    "facilitiesA",        # named critical facilities
    "facilitiesL",
    "transportationL",    # roads, with a damage grade
    "areaOfInterestA",    # the area the operator was asked to map
    "imageFootprintA",    # the ground the imagery actually covered
    "notAnalysedA",       # ground inside the area that could not be read
)

# Where the GeoPackages land when they are downloaded by hand instead.
LOCAL_DIRS = (ROOT.parent / "EMSR", ROOT / "data" / "ems_reference")

DAMAGE_GRADES = ("Destroyed", "Damaged", "Possibly damaged", "No visible damage")


def _get(url: str, timeout: int = 90):
    request = urllib.request.Request(url, headers=AGENT)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw) if raw else None


def activation(code: str) -> dict | None:
    """Activation metadata, or None when the code does not exist yet.

    The service answers 403 rather than 404 for a code it has not created, so
    both are treated as "not yet".
    """
    try:
        payload = _get(DASHBOARD.format(code=code))
    except urllib.error.HTTPError as error:
        if error.code in (403, 404):
            return None
        raise
    results = (payload or {}).get("results") or []
    return results[0] if results else None


def discover(after: str, look_ahead: int = 6) -> list[dict]:
    """Activations opened since a known code, by walking the numbering forward.

    There is no public endpoint listing activations: the dashboard API demands
    a code and refuses `/activations/` outright. The codes are sequential, and
    an unissued code answers 403, so counting upward from the last one seen is
    the discovery mechanism. Verified on EMSR924 to EMSR933: four exist, the
    rest refuse.

    `look_ahead` is how many consecutive misses end the walk, which covers a
    code reserved and not yet published.
    """
    prefix = "".join(c for c in after if c.isalpha())
    number = int("".join(c for c in after if c.isdigit()))

    found, misses = [], 0
    while misses < look_ahead:
        number += 1
        record = activation(f"{prefix}{number}")
        if record is None:
            misses += 1
            continue
        misses = 0
        found.append(record)
    return found


def timings(record: dict) -> dict:
    """The event clock: when each thing happened, and how late it was.

    These are the facts the first two posts of the publication calendar are
    made of, and nobody else puts them next to an alert.
    """
    def when(value):
        return datetime.fromisoformat(value) if value else None

    event = when(record.get("eventTime"))
    opened = when(record.get("activationTime"))

    products = []
    for area in record.get("aois", []):
        for product in area.get("products", []):
            version = product.get("version") or {}
            delivered = when((version.get("deliveryTime") or "")[:19] or None)
            products.append({
                "aoi": area.get("name"),
                "type": product.get("type"),
                "status": version.get("statusCode"),
                "delivered": delivered,
                "expected": when(product.get("expectedDelivery")),
                "sensors": [i.get("sensorName") for i in product.get("images", [])],
                "acquired": [when(i.get("acquisitionTime"))
                             for i in product.get("images", [])],
                "hours": ((delivered - event).total_seconds() / 3600
                          if delivered and event else None),
            })

    delivered = [p for p in products if p["delivered"]]
    return {
        "code": record.get("code"),
        "name": record.get("name"),
        "event": event,
        "opened": opened,
        "activation_hours": ((opened - event).total_seconds() / 3600
                             if opened and event else None),
        "products": products,
        "first_product": min((p["delivered"] for p in delivered), default=None),
        "first_product_hours": min((p["hours"] for p in delivered), default=None),
        "pending": [p for p in products if not p["delivered"]],
        "closed": record.get("closed"),
    }


def _latest_product(area: dict):
    """The one product per area whose layers should actually be read.

    An area can carry more than one delivered product: EMS re-grades the same
    footprint as a monitoring round when better imagery arrives, under a
    `monitoringNumber` that increases with each round. Confirmed on EMSR927
    AOI03 Bidur, where `GRA_PRODUCT` (round 0, delivered 2026-08-29) and
    `GRA_MONIT01` (round 1, delivered 2026-08-31, from different sensors) both
    grade the same buildings.

    Reading every product's layers, as this once did, does not add coverage —
    it counts the same buildings twice. The later round supersedes the
    earlier one for the same ground, exactly as a revised estimate supersedes
    an earlier one elsewhere in this project, so only the latest delivered
    product is kept.
    """
    delivered = [p for p in area.get("products", [])
                if (p.get("version") or {}).get("deliveryTime")]
    if not delivered:
        return None
    return max(delivered, key=lambda p: (
        p.get("monitoringNumber") or 0,
        (p.get("version") or {}).get("deliveryTime"),
    ))


def vector_urls(record: dict) -> list[dict]:
    """Published GeoJSON layers for an activation, straight from the bucket.

    The dashboard lists a `json` URL beside every vector tile layer. They are
    open, so the products no longer have to be downloaded by hand. Only the
    latest delivered product per area is read; see `_latest_product`.
    """
    urls = []
    for area in record.get("aois", []):
        product = _latest_product(area)
        if not product:
            continue
        for layer in product.get("layers", []):
            if layer.get("format") != "vt" or not layer.get("json"):
                continue
            stem = layer["name"].rsplit("/", 1)[-1]
            stem = stem.removesuffix("_VT").rsplit("_v", 1)[0]
            stem = stem.split("_")[-1]
            if stem in LAYERS:
                version = product.get("version") or {}
                urls.append({
                    "aoi": area.get("name"), "layer": stem,
                    "url": layer["json"], "product": product.get("type"),
                    # Identifies which delivered round this came from, so a
                    # cache keyed on it cannot go on serving round 0 once
                    # round 1 has been delivered under the same file name.
                    "round": (f"m{product.get('monitoringNumber') or 0}"
                             f"-{(version.get('deliveryTime') or '')[:10]}"),
                })
    return urls


def _from_bucket(code: str, record: dict) -> dict:
    """Download the published GeoJSON layers, caching each file once.

    Old files from a superseded round are left on disk rather than deleted:
    harmless, since the cache key now carries the round and nothing reads them
    by the old name any more.
    """
    from shapely.geometry import shape as shapely_shape

    folder = VECTOR_CACHE / code
    folder.mkdir(parents=True, exist_ok=True)

    layers = {}
    for item in vector_urls(record):
        path = folder / f"{item['aoi']}_{item['layer']}_{item['round']}.json"
        if not path.exists():
            try:
                request = urllib.request.Request(item["url"], headers=AGENT)
                with urllib.request.urlopen(request, timeout=120) as response:
                    path.write_bytes(response.read())
            except Exception:                                  # noqa: BLE001
                continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:                                      # noqa: BLE001
            continue
        for feature in payload.get("features", []):
            # Attribute-only rows exist in these exports; a feature with no
            # geometry is a table entry, not something on the ground.
            if not feature.get("geometry"):
                continue
            layers.setdefault(item["layer"], []).append({
                "geometry": shapely_shape(feature["geometry"]),
                "properties": dict(feature.get("properties") or {}),
                "aoi": item["aoi"],
            })
    return layers


def _from_geopackages(code: str) -> dict:
    """Fall back to GeoPackages downloaded by hand next to the repository."""
    import fiona
    from shapely.geometry import shape as shapely_shape

    files = sorted({p for d in LOCAL_DIRS if d.is_dir()
                    for p in d.glob(f"*{code}*.gpkg")})
    layers = {}
    for path in files:
        aoi = next((p for p in path.stem.split("_") if p.startswith("AOI")),
                   path.stem)
        for name in fiona.listlayers(str(path)):
            stem = name.rsplit("_v", 1)[0]
            if stem not in LAYERS:
                continue
            try:
                with fiona.open(str(path), layer=name) as src:
                    for feature in src:
                        if not feature.get("geometry"):
                            continue
                        layers.setdefault(stem, []).append({
                            "geometry": shapely_shape(feature["geometry"]),
                            "properties": dict(feature["properties"]),
                            "aoi": aoi,
                        })
            except Exception:                                  # noqa: BLE001
                continue
    return layers


def vectors(code: str, record: dict | None = None) -> dict:
    """Every mapped layer for an activation, keyed by layer stem.

    Prefers the published GeoJSON, because that needs nobody to remember to
    download anything. Falls back to local GeoPackages, which carry the same
    features and are what exists for an activation whose tiles are not up yet.
    """
    record = record if record is not None else activation(code)
    layers = _from_bucket(code, record) if record else {}
    if not layers:
        layers = _from_geopackages(code)
    return layers


def _area_km2(features: list) -> float:
    total = 0.0
    for feature in features:
        geometry = feature["geometry"]
        if geometry.is_empty:
            continue
        mid_lat = math.radians(geometry.centroid.y)
        total += geometry.area * (111.32 ** 2) * math.cos(mid_lat)
    return total


def _length_km(features: list) -> float:
    total = 0.0
    for feature in features:
        geometry = feature["geometry"]
        if geometry.is_empty:
            continue
        mid_lat = math.radians(geometry.centroid.y)
        for line in (geometry.geoms if hasattr(geometry, "geoms") else [geometry]):
            coords = np.asarray(line.coords)
            if len(coords) < 2:
                continue
            dx = np.diff(coords[:, 0]) * 111.32 * math.cos(mid_lat)
            dy = np.diff(coords[:, 1]) * 111.32
            total += float(np.hypot(dx, dy).sum())
    return total


def damage_summary(layers: dict, area: str | None = None) -> dict:
    """What the responders counted, from the features rather than the dashboard.

    The dashboard publishes rounded totals. These are the objects themselves,
    so they break down by grade and by area, and the named facilities come out
    with their names.

    `area` restricts the count to one mapped area. A sheet headed Syapru Besi
    must not carry the whole activation's total, and a per-area carousel is
    the only place the distinction shows.
    """
    if area:
        layers = {name: [f for f in features if f["aoi"] == area]
                  for name, features in layers.items()}

    def grades(features):
        return Counter(f["properties"].get("damage_gra") for f in features
                       if f["properties"].get("damage_gra"))

    buildings = layers.get("builtUpP", [])
    roads = layers.get("transportationL", [])
    facilities = layers.get("facilitiesA", []) + layers.get("facilitiesL", [])
    destroyed_roads = [f for f in roads
                       if f["properties"].get("damage_gra") == "Destroyed"]

    return {
        "areas": sorted({f["aoi"] for layer in layers.values() for f in layer}),
        "observed": [f["geometry"] for f in layers.get("observedEventA", [])],
        # The graded buildings themselves, not only their count. This is what
        # lets the loss chain price observed damage instead of assuming a
        # water depth, so it travels with the summary rather than being
        # re-read downstream.
        "buildings_features": buildings,
        "features": layers,
        "observed_km2": _area_km2(layers.get("observedEventA", [])),
        "observed_parts": len(layers.get("observedEventA", [])),
        "mechanisms": sorted({f["properties"].get("obj_desc")
                              for f in layers.get("observedEventA", [])
                              if f["properties"].get("obj_desc")}),
        "buildings": len(buildings),
        "building_grades": grades(buildings),
        "roads_km": _length_km(roads),
        "roads_destroyed_km": _length_km(destroyed_roads),
        "road_grades": grades(roads),
        "facilities": [
            {"name": f["properties"].get("name"),
             "kind": f["properties"].get("simplified"),
             "grade": f["properties"].get("damage_gra"),
             "aoi": f["aoi"]}
            for f in facilities
        ],
        "named_destroyed": sorted(
            {f["properties"].get("name") for f in facilities
             if f["properties"].get("damage_gra") == "Destroyed"
             and (f["properties"].get("name") or "Unknown") != "Unknown"}
        ),
        "not_analysed_km2": _area_km2(layers.get("notAnalysedA", [])),
        "mapped_km2": _area_km2(layers.get("areaOfInterestA", [])),
    }


def study_area(code: str, record: dict | None = None) -> dict:
    """The official areas of an activation, shaped like a study area.

    Replaces the geometry half of the old `natcat.ems_activation`: same
    contract, same keys, so `natcat.aoi_mask` and the rest of the chain do not
    change.
    """
    from shapely import wkt
    from shapely.ops import unary_union

    record = record if record is not None else activation(code)
    if not record:
        raise ValueError(f"No EMS activation found for {code}")

    areas = [{"name": entry.get("name", ""), "geometry": wkt.loads(entry["extent"])}
             for entry in record.get("aois", []) if entry.get("extent")]
    if not areas:
        raise ValueError(f"Activation {code} has no area geometry")

    union = unary_union([a["geometry"] for a in areas])
    bounds = union.bounds
    mid_lat = math.radians((bounds[1] + bounds[3]) / 2)

    return {
        "code": record["code"],
        "name": record.get("name", ""),
        "event_time": record.get("eventTime"),
        "countries": [c["name"] for c in record.get("countries", [])],
        "aois": areas,
        "union": union,
        "bounds": tuple(round(b, 4) for b in bounds),
        "area_km2": float(union.area * (111.32 ** 2) * math.cos(mid_lat)),
        "source": "ems",
        # Why the activation was requested, in the requester's own words. It
        # carries the mechanism and sometimes a measurement nothing else in
        # the chain has: for EMSR927 it names the glacial lake outburst and a
        # water level of 7 m recorded by monitoring stations, against the 1 m
        # this pipeline was assuming.
        "reason": record.get("reason", ""),
        "category": record.get("category", ""),
        "sub_category": record.get("subCategory", ""),
        "stats": record.get("stats") or {},
        "charter": record.get("charterUrl") or "",
        "product_types": sorted({p.get("type") for a in record.get("aois", [])
                                 for p in a.get("products", []) if p.get("type")}),
    }


def _self_check() -> None:
    """Run: conda run -n climada_env python ems.py"""
    record = activation("EMSR927")
    assert record and record["code"] == "EMSR927"
    print("ok  activation reads")

    assert activation("EMSR999") is None
    print("ok  an unissued code answers None rather than raising")

    clock = timings(record)
    assert 10 < clock["activation_hours"] < 14, clock["activation_hours"]
    assert clock["first_product_hours"] and clock["first_product_hours"] < 60
    print(f"ok  activation at +{clock['activation_hours']:.0f} h, "
          f"first product at +{clock['first_product_hours']:.0f} h")

    area = study_area("EMSR927", record)
    # At least the 4 zones this was first opened with, not exactly 4: a live
    # activation grows. EMSR927 itself went to 6 areas over the following
    # week, which is exactly the kind of fact this check exists to catch
    # rather than assume.
    assert len(area["aois"]) >= 4 and area["area_km2"] > 0
    print(f"ok  study area: {len(area['aois'])} zones, "
          f"{area['area_km2']:.0f} km2")

    layers = vectors("EMSR927", record)
    assert layers.get("builtUpP"), "no buildings read"
    summary = damage_summary(layers)
    assert summary["buildings"] == sum(summary["building_grades"].values())
    print(f"ok  {summary['buildings']} buildings, "
          f"{summary['building_grades'].get('Destroyed', 0)} destroyed, "
          f"{summary['observed_km2']:.2f} km2 observed, "
          f"mechanisms {summary['mechanisms']}")
    print(f"      named destroyed: {summary['named_destroyed']}")

    # Confirms the fix this run found: a monitoring round supersedes the
    # earlier one for the same ground rather than adding to it, so an area
    # with two delivered products is read once, not twice.
    monitored = next((a for a in record["aois"]
                      if sum(1 for p in a["products"]
                             if (p.get("version") or {}).get("deliveryTime")) > 1),
                     None)
    if monitored:
        chosen = _latest_product(monitored)
        assert chosen is not None
        rounds = {p.get("monitoringNumber") or 0 for p in monitored["products"]}
        assert (chosen.get("monitoringNumber") or 0) == max(rounds)
        print(f"ok  {monitored['name']} has {len(rounds)} delivered rounds; "
              f"the latest one is read, not all of them")

    print("\nchecks passed")


if __name__ == "__main__":
    _self_check()
