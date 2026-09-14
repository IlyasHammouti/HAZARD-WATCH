"""Assemble the whole chain into one call.

Everything else in this project is a component. This is the part that runs
them in order for one event and writes the two things a post needs: the map,
and the fact sheet with every number already filled in.

    from report import make_post
    make_post(FloodEvent(ems_code="EMSR664", ...))

The split is deliberate. The chain produces facts and graphics; it never
produces the analysis. Placeholders that call for judgement are left visible
in the output so they cannot be published unnoticed.
"""

from __future__ import annotations

import json
import pickle
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rasterio.transform
import rasterio.warp
from rasterio.features import rasterize
from scipy import ndimage
from shapely.geometry import mapping, shape as shapely_shape

import carto
import ems
import guards
import natcat
import plan

ROOT = Path(__file__).parent
CACHE = ROOT / "data" / "cache"
OUTPUT = ROOT / "output"
TEMPLATES = ROOT / "templates"
FEATURED_HISTORY_PATH = CACHE / "digest_featured.json"

# Conversion applied only where a figure is republished in a second currency.
# The source currency and base year always travel with the number.
USD_TO_EUR_2023 = 0.924

# Fragments smaller than this are speckle, not flooding. Measured on EMSR664:
# dropping them costs 4 % of area but 36 % of exposed value, because the noise
# sits in built-up land.
MIN_FRAGMENT_PIXELS = 5


@dataclass
class FloodEvent:
    """Everything the chain needs to know about one flood."""

    ems_code: str
    country: str
    region: str
    event_date: str
    hazard_start: str
    hazard_end: str
    optical_start: str
    optical_end: str
    seas: dict = field(default_factory=dict)
    depth_m: float = 1.0
    sector: str = "residential"
    crosscheck_figure: str = ""
    crosscheck_source: str = ""
    peril: str = "flood"
    # How the water damages things. Only riverine, coastal and pluvial
    # flooding are what the JRC depth-damage curves were built for.
    mechanism: str = "riverine"
    # JRC continent the damage curve is read from. The curves are calibrated
    # per continent, and the default is Europe: an Asian or African event left
    # on the default is read from the wrong curve and nothing complains.
    curve_region: str = "Europe"
    # Path to a hand-drawn footprint, for events the automated products cannot
    # see. Set it and the chain takes the outline from the file instead of
    # from GFM. See manual.py and docs/MANUAL_DELINEATION.md.
    footprint_path: str = ""
    # Whether to run our own radar and optical detection at all. Off is the
    # right answer whenever Copernicus EMS has already graded the event: they
    # mapped the same ground by hand at 50 cm, the run costs twenty-five
    # minutes, and its only output would be a worse outline nobody publishes.
    # Left on for events EMS delineated but did not grade, and for events it
    # never touched, where the detection is the only extent there is.
    detect: bool = True


def _despeckle(mask: np.ndarray, min_pixels: int = MIN_FRAGMENT_PIXELS):
    labels, count = ndimage.label(mask)
    if count == 0:
        return mask
    sizes = ndimage.sum(mask, labels, range(1, count + 1))
    keep = np.where(sizes >= min_pixels)[0] + 1
    return np.isin(labels, keep) & mask


def _building_count_check(official: dict) -> str:
    """Is 79 % destroyed a share of everything, or of a small graded sample?

    A grading product's own denominator is however many buildings its
    operators looked at, which need not be every building on the ground. This
    checks it against an independent global footprint dataset, queried inside
    the exact polygons Copernicus mapped, rather than assuming either that the
    grading is complete or that it is partial.
    """
    observed = official.get("observed")
    graded = official.get("buildings")
    if not observed or not graded:
        return ""

    try:
        import json as _json

        import ee
        from shapely.ops import unary_union

        union = unary_union([g for g in observed if g and not g.is_empty])
        geom = ee.Geometry(_json.loads(_json.dumps(union.__geo_interface__)))
        count = (ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons")
                 .filterBounds(geom).size().getInfo())
    except Exception:                                          # noqa: BLE001
        return ""
    if not count:
        return ""

    # The two counts need not agree, and both directions are informative. In
    # mountainous ground a global automated footprint layer misses structures
    # a person reading 50 cm imagery does not, so Copernicus grading more than
    # the independent count is not an error — checked on EMSR927, where it
    # graded 4 485 against 4 346 found independently. The one thing that
    # needs saying either way is the sentence a caller reads it for: does the
    # destroyed share sit on nearly everything, or on a small sample.
    if graded >= count:
        return (f"An independent footprint count (Google Open Buildings) "
                f"finds {_thousands(count)} structures inside the same "
                f"polygons. Copernicus graded {_thousands(graded)}, at least "
                f"as many; the destroyed share above is not read against a "
                f"small sample.")
    share = graded / count
    return (f"An independent footprint count (Google Open Buildings) finds "
            f"{_thousands(count)} structures inside the same polygons, of "
            f"which Copernicus graded {share * 100:.0f}%. The destroyed share "
            f"above is read against nearly the full count, not a sample of it.")


def _calendar_values(result: dict, clock: dict | None) -> dict:
    """Fields the activation and official-figures posts need.

    These describe the response rather than the hazard: when the activation
    opened, what was tasked at it, when the product is due. They are the whole
    content of the posts published before anything has been measured.
    """
    activation = result.get("activation") or {}
    areas = activation.get("aois") or []
    official = result.get("ems") or {}
    detected = result.get("detected_km2", 0.0)
    mapped = official.get("observed_km2") or 0.0

    tasked, expected = [], []
    for product in (clock or {}).get("products", []):
        sensors = ", ".join(s for s in product.get("sensors") or [] if s)
        acquired = [a for a in product.get("acquired") or [] if a]
        when = (f", acquired {min(acquired):%d %B %Y %H:%M} UTC"
                if acquired else "")
        tasked.append(f"- {product['aoi']}: {sensors or 'sensor not stated'}{when}")
        if not product.get("delivered") and product.get("expected"):
            expected.append(f"{product['aoi']} is expected "
                            f"{product['expected']:%d %B %Y at %H:%M} UTC")

    if expected:
        delivery = ("Copernicus states an expected delivery for each area. "
                    + "; ".join(expected) + ".")
    elif clock and clock.get("first_product_hours") is not None:
        delivery = (f"The first product was delivered "
                    f"{clock['first_product_hours']:.0f} hours after the event.")
    else:
        delivery = "[TO WRITE]"

    headline = "[TO WRITE]"
    grades = official.get("building_grades") or {}
    if grades.get("Destroyed"):
        event = result["event"]
        hours = (clock or {}).get("first_product_hours")
        graded = _thousands(official["buildings"])
        destroyed = _thousands(grades["Destroyed"])
        when = (f", from imagery read {hours:.0f} hours after the event"
                if hours else "")
        headline = (f"Copernicus EMS operators graded {graded} buildings in "
                    f"{event.region}, {event.country}, and recorded "
                    f"{destroyed} of them destroyed{when}.")

    # The share is already on its own line above where a detection ran, so
    # this says only what the bullets cannot: whose footprint the money sits
    # on. Saying it twice cost fifty words and taught the reader nothing.
    caveat = ("Those figures are this project's, computed on the footprint "
              "Copernicus mapped rather than on one of our own."
              if mapped else "")

    completeness = _building_count_check(official)
    if completeness:
        caveat = f"{caveat} {completeness}".strip()

    return {
        "ACTIVATION_HOURS": (f"{clock['activation_hours']:.0f}"
                             if clock and clock.get("activation_hours") is not None
                             else "[TO WRITE]"),
        "AREA_COUNT": str(len(areas)) if areas else "[TO WRITE]",
        "MAPPED_AREA": (f"{official['mapped_km2']:.0f}" if official.get("mapped_km2")
                        else f"{activation.get('area_km2', 0):.0f}"),
        "TASKED_LINES": "\n".join(tasked) or "[TO WRITE]",
        "EXPECTED_DELIVERY": delivery,
        "HEADLINE_COUNT": headline,
        "DETECTED_AREA": f"{detected:.1f}",
        "DETECTED_SHARE": (f"{detected / mapped * 100:.0f}%" if mapped
                           else "no official map to compare against"),
        "OWN_LAYER_CAVEAT": caveat,
    }


def _reported_values(verdict, clock: dict | None) -> dict:
    """Placeholders for figures a named source published, not ones we computed.

    Kept in its own block so a reader never has to work out which number came
    from where, and so the tier that suppresses our modelled figures leaves
    these alone.
    """
    reported = getattr(verdict, "reported", {}) or {}
    if not reported:
        # Nothing reported means the section disappears, heading and all.
        return {"REPORTED_BODY": "", "REPORTED_SOURCE": ""}

    lines = []
    if reported.get("buildings_mapped"):
        lines.append(
            f"- Buildings graded: {_thousands(reported['buildings_mapped'])}, "
            f"of which {_thousands(reported['buildings_destroyed'])} destroyed "
            f"and {_thousands(reported['buildings_damaged'])} damaged")
    if reported.get("observed_km2"):
        mechanism = ", ".join(reported.get("mechanisms") or []) or "not stated"
        lines.append(f"- Area mapped as affected: "
                     f"{reported['observed_km2']:.1f} km2, typed {mechanism}")
    if reported.get("roads_km"):
        bridges = reported.get("bridges_destroyed") or 0
        bridge_note = (f", including {bridges} bridge"
                       f"{'s' if bridges != 1 else ''}" if bridges else "")
        lines.append(f"- Roads: {reported['roads_destroyed_km']:.1f} km destroyed "
                     f"of {reported['roads_km']:.1f} km graded{bridge_note}")
    for name in (reported.get("named_destroyed") or [])[:3]:
        lines.append(f"- Destroyed and named in the product: {name}")

    speed = ""
    if clock and clock.get("activation_hours") is not None:
        speed = (f"The activation opened "
                 f"{clock['activation_hours']:.0f} hours after the event")
        if clock.get("first_product_hours") is not None:
            speed += (f" and the first graded product was delivered "
                      f"{clock['first_product_hours']:.0f} hours after it")
        speed += "."

    locked = locked_phrases()
    source = reported.get("source", "")
    # The full grading credit lives in the sources block. Repeating it under
    # the figures said the same thing twice in fifty words, and `L-REPORTED`
    # above already names who counted them.
    body = [locked["L-REPORTED"].replace("{{REPORTED_SOURCE}}", source), ""]
    body += lines
    if speed:
        body += ["", speed]

    return {"REPORTED_BODY": "\n".join(body), "REPORTED_SOURCE": source}


def _loss(event: FloodEvent, official: dict | None, footprint, value,
          profile: dict) -> dict:
    """Vulnerability, from observation where it exists and from a curve where
    it does not.

    Two routes, and the better one is chosen automatically:

    * **Graded.** Copernicus EMS has looked at every building in 50 cm imagery
      and recorded whether it is standing. There is nothing left to assume
      about hazard intensity, nothing to borrow from another continent, and no
      mechanism to worry about: a building destroyed by debris is destroyed
      exactly as much as one destroyed by standing water. This removes the two
      largest sources of error in the project at once.
    * **Depth-damage.** The V1 route, for everywhere EMS has not graded. An
      assumed uniform depth through a JRC curve, on a 100 m grid.
    """
    graded = (official or {}).get("buildings_features")
    if graded:
        return natcat.graded_loss(graded, value, profile)

    depth = np.where(footprint, event.depth_m, 0.0).astype("float32")
    result = natcat.flood_loss(depth, value, profile, sector=event.sector,
                               region=event.curve_region)
    result["method"] = "depth"
    return result


def _damage_layers(ax, crs, features: dict, extent: tuple) -> dict:
    """Draw what the responders counted, on top of what they mapped.

    A grading product is the only place a reader gets the damage object by
    object, and drawing the outline while omitting the objects wastes the part
    that took people days. Buildings by grade, roads that were carried away,
    and critical facilities, which are what a reinsurance reader looks for
    first: a destroyed dam is not one more damaged building.
    """
    drawn = {}

    def project(geometry):
        return rasterio.warp.transform_geom("EPSG:4326", crs, mapping(geometry))

    def visible(x, y):
        return (extent[0] <= x <= extent[2]) and (extent[1] <= y <= extent[3])

    # Roads under the buildings, and every layer at the order the identity
    # fixes: what a reader must not lose sits highest.
    for feature in features.get("transportationL", []):
        if feature["properties"].get("damage_gra") != "Destroyed":
            continue
        geometry = feature["geometry"]
        for line in (geometry.geoms if hasattr(geometry, "geoms") else [geometry]):
            drawn_geom = project(line)
            arr = np.asarray(drawn_geom["coordinates"])
            if arr.ndim == 2 and len(arr) >= 2:
                ax.plot(arr[:, 0], arr[:, 1], color=carto.ROAD_CUT, lw=2.0,
                        solid_capstyle="round",
                        zorder=carto.LAYER_ORDER["road"], alpha=0.9)
                drawn["roads"] = drawn.get("roads", 0) + 1

    for grade in carto.DAMAGE_GRADES_ORDER:
        points = []
        for feature in features.get("builtUpP", []):
            if feature["properties"].get("damage_gra") != grade:
                continue
            drawn_geom = project(feature["geometry"])
            x, y = drawn_geom["coordinates"][:2]
            if visible(x, y):
                points.append((x, y))
        if points:
            xs, ys = zip(*points)
            ax.scatter(xs, ys, s=11, c=carto.DAMAGE_COLOURS[grade],
                       edgecolors="none", alpha=0.9,
                       zorder=carto.LAYER_ORDER[grade])
            drawn[grade] = len(points)

    facilities = (features.get("facilitiesA", []) + features.get("facilitiesL", []))
    width = extent[2] - extent[0]
    for feature in facilities:
        if feature["properties"].get("damage_gra") == "No visible damage":
            continue
        centre = project(feature["geometry"].centroid)
        x, y = centre["coordinates"][:2]
        if not visible(x, y):
            continue
        # A white ring, back by request after seeing it on the sheet: over
        # dark hillshade the purple loses its edge against the terrain, and
        # the marker has to read as a symbol rather than as a dark patch.
        ax.scatter([x], [y], s=95, marker="^", c=carto.FACILITY,
                   edgecolors="#FFFFFF", linewidths=1.1,
                   zorder=carto.LAYER_ORDER["facility"])
        drawn["facilities"] = drawn.get("facilities", 0) + 1
        # The triangle is the marker; the label's own dot would sit on top of
        # it and read as a second, different thing.

        # Wrapped over as many lines as the name needs. Trimming to an ellipsis
        # threw away the half that identifies the place: "Langtang Khola
        # Hydroelect…" names nothing.
        name = feature["properties"].get("name") or ""
        if name and name != "Unknown":
            left_side = (extent[2] - x) < width * 0.3
            carto.place_label(ax, x, y, _wrap_label(name), kind="city",
                              offset=-width * 0.012 if left_side else width * 0.012,
                              align="right" if left_side else "left", dot=False)
    return drawn


def _wrap_label(name: str, width: int = 18) -> str:
    """Break a place name onto as many lines as it needs, on word boundaries."""
    import textwrap

    return "\n".join(textwrap.wrap(name, width=width) or [name])


def _official_assessable(official: dict, activation: dict) -> float:
    """Share of the mapped ground the EMS operators could actually read.

    They publish what they could not read, as `notAnalysedA`. The denominator
    is their own area of interest where the product ships one, and the
    activation's area otherwise: the vector-tile export does not always carry
    `areaOfInterestA`, and falling back to 100 % assessable would credit them
    with reading ground they said they could not.
    """
    unread = (official or {}).get("not_analysed_km2") or 0.0
    if not unread:
        return 1.0

    # Three candidate denominators, most specific first. `areaOfInterestA` is
    # what the operators were asked to map, but the vector-tile export does
    # not always carry it — on EMSR927 it is absent, `mapped_km2` is 0, and
    # falling through to a bare 1.0 made the post claim EMS had marked nothing
    # unreadable when it had marked 0.14 km2. The mapped event's own area is
    # the honest fallback: it is real ground the operators did read.
    mapped = ((official or {}).get("mapped_km2")
              or (official or {}).get("observed_km2")
              or (activation or {}).get("area_km2") or 0.0)
    if not mapped:
        return 1.0
    return max(0.0, min(1.0, 1.0 - unread / (mapped + unread)))


def _rasterise(geometries: list, profile: dict, shape: tuple) -> np.ndarray:
    """Burn lon/lat polygons onto the pipeline grid."""
    from shapely.ops import unary_union

    union = unary_union([g for g in geometries if g and not g.is_empty])
    if union.is_empty:
        return np.zeros(shape, dtype=bool)
    drawn = rasterio.warp.transform_geom("EPSG:4326", profile["crs"],
                                         mapping(union))
    return rasterize([(drawn, 1)], out_shape=shape,
                     transform=profile["transform"], fill=0,
                     dtype="uint8").astype(bool)


def _expected_look(aoi: tuple, event: FloodEvent) -> dict:
    """When the ground is next planned to be imaged, from the published plan.

    Replaces the empirical guess. `plan.next_look` reads the acquisition
    segments ESA publishes two to three weeks ahead, so this is a schedule
    rather than a projection of what happened last month.
    """
    from datetime import datetime, timezone

    try:
        after = datetime.fromisoformat(event.event_date[:10]).replace(
            tzinfo=timezone.utc)
        answer = plan.next_look(aoi, after=max(after, datetime.now(timezone.utc)))
    except Exception:                                          # noqa: BLE001
        return {"awaiting_pass": None, "planned_looks": {}}

    soonest = answer.get("soonest")
    return {
        "awaiting_pass": soonest["start"].date() if soonest else None,
        "awaiting_satellite": soonest["satellite"] if soonest else None,
        "planned_looks": {s: e["start"] for s, e in
                          answer.get("per_satellite", {}).items()},
    }


def _compute_on_official(event: FloodEvent, activation: dict,
                         official: dict) -> dict:
    """Run the chain on the footprint Copernicus EMS mapped, with no detection.

    The case V1 could not handle: radar has seen nothing usable, and EMS has
    already published a hand-mapped outline. V1 returned a pending note. There
    is nothing pending about it — the footprint exists, it is better than ours
    would have been, and every step after the extent is unchanged.
    """
    import manual

    aoi = activation["bounds"]
    profile, shape = manual.grid_for(aoi, resolution_m=20.0)

    footprint = _rasterise(official["observed"], profile, shape)
    exposure = natcat.exposure(aoi, event.country, profile, shape)
    people = natcat.population(aoi, profile, shape)
    value = exposure["value"]

    loss = _loss(event, official, footprint, value, profile)
    pixel_km2 = profile["resolution"] ** 2 / 1e6
    return {
        "event": event,
        "activation": activation,
        "ems": official,
        "profile": profile,
        "footprint": footprint,
        "detected": np.zeros(shape, dtype=bool),
        "mask": footprint,
        "value": value,
        "radar_only": np.zeros(shape, dtype=bool),
        "extent_km2": float(footprint.sum() * pixel_km2),
        "detected_km2": 0.0,
        "radar_km2": 0.0,
        "optical_gain_km2": 0.0,
        # EMS states the ground it could not read; that is the honest coverage.
        "coverage": 1.0,
        "assessable": _official_assessable(official, activation),
        "unseen_share": 1.0 - _official_assessable(official, activation),
        "timeline": [{"datetime": activation.get("event_time") or "",
                      "area_km2": float(footprint.sum() * pixel_km2)}],
        "optical_scenes": 0,
        "optical_dates": [],
        "exposed_usd": loss["exposed"],
        "loss_usd": loss["loss"],
        "loss_low_usd": loss.get("loss_low"),
        "loss_high_usd": loss.get("loss_high"),
        "damage_ratio": loss["damage_ratio"],
        "impact_function": loss.get("impact_function", ""),
        "method": loss.get("method", "depth"),
        "graded_buildings": loss.get("graded"),
        "grades": loss.get("grades", {}),
        "currency": exposure["currency"],
        "built_km2": exposure["built_km2"],
        "affected_population": float(people[footprint].sum()),
        "steep_share": _steep_share(aoi),
        "source": "ems",
    }


def _compute_drawn(event: FloodEvent) -> dict:
    """Run the chain on a footprint an operator drew, rather than on GFM.

    Everything after the extent is identical, which is the point: exposure,
    the damage curve and the guards do not care how the outline was obtained,
    only that it is honest about what it is. Coverage and assessable share
    come from the provenance block because only the operator knows how much of
    the area they could actually see.
    """
    import manual

    activation = manual.load_footprint(event.footprint_path,
                                       event_date=event.event_date)
    aoi = activation["bounds"]
    profile, shape = manual.grid_for(aoi)

    footprint = natcat.aoi_mask(activation, profile, shape)
    exposure = natcat.exposure(aoi, event.country, profile, shape)
    people = natcat.population(aoi, profile, shape)
    value = exposure["value"]

    depth = np.where(footprint, event.depth_m, 0.0).astype("float32")
    loss = natcat.flood_loss(depth, value, profile, sector=event.sector,
                             region=event.curve_region)

    p = activation["provenance"]
    pixel_km2 = profile["resolution"] ** 2 / 1e6
    # One timeline entry per scene the operator read, so the imagery guard sees
    # what the operator saw rather than counting GFM scenes that do not exist.
    timeline = [
        {"datetime": scene["acquired"], "sensor": scene["sensor"],
         "scene_id": scene["scene_id"], "area_km2": float(footprint.sum() * pixel_km2)}
        for scene in p["imagery"]
    ]

    return {
        "event": event,
        "activation": activation,
        "profile": profile,
        "footprint": footprint,
        "mask": footprint,
        "value": value,
        "radar_only": np.zeros_like(footprint),
        "extent_km2": float(footprint.sum() * pixel_km2),
        "radar_km2": 0.0,
        "optical_gain_km2": 0.0,
        "coverage": float(p["coverage"]),
        "assessable": float(p["assessable"]),
        "unseen_share": 1.0 - float(p["assessable"]),
        "timeline": timeline,
        "optical_scenes": len(p["imagery"]),
        "exposed_usd": loss["exposed"],
        "loss_usd": loss["loss"],
        "damage_ratio": loss["damage_ratio"],
        "impact_function": loss.get("impact_function", ""),
        "currency": exposure["currency"],
        "built_km2": exposure["built_km2"],
        "affected_population": float(people[footprint].sum()),
        "steep_share": _steep_share(aoi),
        "source": "manual",
        "provenance": p,
    }


def _official_fingerprint(official: dict | None) -> str:
    """A short tag that changes whenever the official data actually does.

    An activation an event's `compute()` result is cached under grows over
    days: EMSR927 went from 3 delivered areas to 4, and one of those areas was
    itself re-graded in a later monitoring round. A cache keyed on the event
    code alone cannot tell that apart from nothing having changed, and it
    silently served a three-area result for days after a fourth had landed —
    the same failure the round-aware fix in `ems.py`'s vector cache exists to
    prevent, one layer up.
    """
    if not official or not official.get("buildings"):
        return "noems"
    return (f"b{official['buildings']}"
           f"a{len(official.get('areas') or [])}"
           f"o{official.get('observed_km2', 0):.1f}")


def compute(event: FloodEvent, use_cache: bool = True) -> dict:
    """Run the measurement chain and return every figure the post will quote.

    Results are cached per event: the satellite reads and Earth Engine
    downloads take minutes, and nothing about a past event changes — except
    the Copernicus EMS grading behind an event this project did not detect
    itself, which can and does change as an activation grows. See
    `_official_fingerprint`.
    """
    CACHE.mkdir(parents=True, exist_ok=True)

    if event.footprint_path:
        path = CACHE / f"{event.ems_code}_result.pkl"
        if use_cache and path.exists():
            with open(path, "rb") as handle:
                return pickle.load(handle)
        result = _compute_drawn(event)
        with open(path, "wb") as handle:
            pickle.dump(result, handle)
        return result

    record = ems.activation(event.ems_code)
    activation = ems.study_area(event.ems_code, record)
    aoi = activation["bounds"]

    # Copernicus EMS first. Where its operators have mapped the event by hand
    # from very high resolution imagery, that footprint is better than anything
    # this chain can detect, and V2 runs the loss chain on it rather than on a
    # worse outline of our own. Our detection is still computed where it can
    # be, because the comparison between the two is the honest part.
    layers = ems.vectors(event.ems_code, record) if record else {}
    official = ems.damage_summary(layers) if layers else None

    path = CACHE / f"{event.ems_code}_{_official_fingerprint(official)}_result.pkl"
    if use_cache and path.exists():
        with open(path, "rb") as handle:
            return pickle.load(handle)

    # An event with no post-event imagery is a normal state for a reactive
    # chain, not a failure. Return what is known — the area, and when the
    # satellite is due back — and let the guards call it tier 0.
    has_official = bool(official and official.get("observed"))
    if not event.detect and has_official:
        result = _compute_on_official(event, activation, official)
        with open(path, "wb") as handle:
            pickle.dump(result, handle)
        return result

    try:
        radar = natcat.flood_extent(aoi, event.hazard_start, event.hazard_end)
    except ValueError:
        radar = None

    if radar is None and official and official.get("observed"):
        return _compute_on_official(event, activation, official)

    if radar is None:
        return {
            "event": event,
            "activation": activation,
            "ems": official,
            "timeline": [],
            "extent_km2": 0.0,
            "detected_km2": 0.0,
            "coverage": 0.0,
            "assessable": 0.0,
            "exposed_usd": 0.0,
            "loss_usd": 0.0,
            "damage_ratio": 0.0,
            "unseen_share": 1.0,
            "impact_function": "",
            "steep_share": _steep_share(aoi),
            "source": "none",
            **_expected_look(aoi, event),
        }

    profile, shape = radar["profile"], radar["flooded"].shape

    optical = natcat.optical_water(aoi, event.optical_start, event.optical_end,
                                   profile, shape)
    merged = natcat.merge_extents(radar, optical)
    mask = natcat.aoi_mask(activation, profile, shape)

    detected = _despeckle(merged["flooded"] & mask)

    # The source ladder. An outline mapped by hand from 50 cm imagery beats a
    # detection from 10 m every time, so where EMS has one the chain runs on
    # it and our detection becomes the comparison rather than the input.
    footprint, source = detected, "gfm"
    coverage, assessable = radar["coverage"], radar["assessable"]
    if official and official.get("observed"):
        official_mask = _rasterise(official["observed"], profile, shape)
        if official_mask.any():
            footprint, source = official_mask, "ems"
            # Coverage and assessable describe the footprint's own provenance.
            # Once the outline comes from 50 cm optical, what radar could or
            # could not judge says nothing about it, and leaving the radar
            # figures in place would block a currency figure for a weakness
            # the footprint no longer has. EMS states the ground its operators
            # could not read, and that is the honest replacement.
            coverage = 1.0
            assessable = _official_assessable(official, activation)

    exposure = natcat.exposure(aoi, event.country, profile, shape)
    people = natcat.population(aoi, profile, shape)
    value = exposure["value"] * mask

    loss = _loss(event, official, footprint, value, profile)

    steep_share = _steep_share(aoi)

    pixel_km2 = profile["resolution"] ** 2 / 1e6
    result = {
        "steep_share": steep_share,
        "event": event,
        "activation": activation,
        "profile": profile,
        "footprint": footprint,
        "detected": detected,
        "mask": mask,
        "value": value,
        "ems": official,
        "radar_only": _despeckle(radar["flooded"] & mask),
        "extent_km2": float(footprint.sum() * pixel_km2),
        "detected_km2": float(detected.sum() * pixel_km2),
        "radar_km2": float((radar["flooded"] & mask).sum() * pixel_km2),
        "optical_gain_km2": float(merged.get("filled_km2", 0.0)),
        "coverage": coverage,
        "assessable": assessable,
        "unseen_share": 1.0 - assessable,
        "radar_assessable": radar["assessable"],
        "timeline": radar["timeline"],
        "optical_scenes": optical["scenes"],
        "optical_dates": optical.get("dates", []),
        "exposed_usd": loss["exposed"],
        "loss_usd": loss["loss"],
        "loss_low_usd": loss.get("loss_low"),
        "loss_high_usd": loss.get("loss_high"),
        "damage_ratio": loss["damage_ratio"],
        "impact_function": loss.get("impact_function", ""),
        "method": loss.get("method", "depth"),
        "graded_buildings": loss.get("graded"),
        "grades": loss.get("grades", {}),
        "currency": exposure["currency"],
        "built_km2": exposure["built_km2"],
        "affected_population": float(people[footprint].sum()),
        "source": source,
    }

    with open(path, "wb") as handle:
        pickle.dump(result, handle)
    return result


def _steep_share(aoi: tuple) -> float | None:
    """Share of the area steeper than 20 degrees.

    Depth-damage curves assume standing water on a floodplain. This is the
    single cheapest measurement that says whether that assumption holds, and it
    separates Emilia-Romagna (5 %) from Rasuwa (59 %) immediately.
    """
    import ee

    try:
        dem = (ee.ImageCollection("projects/sat-io/open-datasets/FABDEM")
               .mosaic().select("b1")
               .reproject(crs="EPSG:4326", scale=90))
        steep = ee.Terrain.slope(dem).gt(20)
        return float(steep.reduceRegion(
            ee.Reducer.mean(), ee.Geometry.Rectangle(list(aoi)),
            scale=200, maxPixels=1e9).getInfo()["slope"])
    except Exception:
        return None


def _money(value_usd: float, currency: str = "EUR") -> str:
    """Format a figure, converting only when asked and never silently."""
    amount = value_usd * (USD_TO_EUR_2023 if currency == "EUR" else 1.0)
    symbol = "€" if currency == "EUR" else "$"
    if abs(amount) >= 1e9:
        return f"{symbol}{amount / 1e9:.2f}bn"
    return f"{symbol}{amount / 1e6:.0f}M"


def _radar_share(result: dict) -> float:
    extent = result.get("extent_km2") or 0.0
    return (result.get("radar_km2", 0.0) / extent) if extent else 0.0


def _sensor(result: dict) -> str:
    """Which instrument produced the extent, named rather than implied.

    On EMSR927 radar contributed 0.0004 km² of a 0.87 km² extent, and the
    draft still opened with "from the Sentinel-1 pass". That credits the wrong
    instrument (A25) and it is the same failure the INFILL guard exists to
    name, so the sentence is decided by the same threshold.
    """
    if result.get("source") == "manual":
        return ", ".join(sorted({s["sensor"]
                                 for s in result["provenance"]["imagery"]}))
    if _radar_share(result) < guards.MIN_RADAR_SHARE:
        return "Sentinel-2"
    return ("Sentinel-1, with Sentinel-2 infill" if result.get("optical_scenes")
            else "Sentinel-1")


def _first_pass(result: dict) -> str:
    """When the extent was observed, by whichever sensor actually produced it."""
    if _radar_share(result) < guards.MIN_RADAR_SHARE and result.get("source") != "manual":
        dates = result.get("optical_dates") or []
        # No dates recorded means the result predates them being kept; a slot
        # a human has to fill is the correct output, never an invented date.
        return _date_list(dates) if dates else "[TO WRITE]"

    usable = [s["datetime"] for s in (result.get("timeline") or [])
              if s.get("area_km2", 0) > 0]
    if not usable:
        return "[TO WRITE]"
    stamp = min(usable).replace("Z", "").replace("T", " ")
    return f"{stamp[:16]} UTC"


def _latency_statement(result: dict) -> str:
    """How long the picture took, measured against the picture that was used.

    Quoting the radar latency in hours next to an extent Sentinel-2 produced
    describes an acquisition the figure does not rest on. Optical dates are
    known to the day, so the optical case is stated in days rather than
    dressed up in hours it cannot support.
    """
    from datetime import date as _date

    if _radar_share(result) >= guards.MIN_RADAR_SHARE:
        hours = latency_hours(result)
        return (f"The first usable pass came {hours:.0f} hours after the event."
                if hours else "[TO WRITE]")

    dates = result.get("optical_dates") or []
    if not dates:
        return "[TO WRITE]"
    event_day = _date.fromisoformat(result["event"].event_date[:10])
    days = (_date.fromisoformat(dates[0][:10]) - event_day).days
    unit = "day" if abs(days) == 1 else "days"
    return (f"Radar saw nothing usable here, and the first readable image came "
            f"{days} {unit} after the event, from Sentinel-2.")


def _extent_credit(result: dict) -> str:
    """Credit the instrument that produced the footprint, not the expected one."""
    locked = locked_phrases()
    if result.get("source") == "manual":
        return locked["L-SRC-MANUAL"]
    if _radar_share(result) >= guards.MIN_RADAR_SHARE:
        return locked["L-SRC-GFM"]
    return locked["L-SRC-OPTICAL"]


def _date_list(dates: list) -> str:
    """`27 August 2026`, or `26 and 27 August 2026` for a short run."""
    from datetime import date as _date

    days = [_date.fromisoformat(d[:10]) for d in dates]
    if len(days) == 1:
        return _prose_date(days[0])
    if len(days) == 2:
        return f"{days[0].day} and {_prose_date(days[1])}"
    return f"{_date_span(min(days), max(days))}, {len(days)} scenes"


def _unknowns(result: dict) -> str:
    """Block 6, built from what the run actually could not settle.

    Two sentences at most, and every clause traceable to a state of the data
    rather than to a hedge. Rules section 7: uncertainty is stated in plain
    declaratives, never with "results may vary".
    """
    official = result.get("ems") or {}
    activation = result.get("activation") or {}

    lines = []

    # Areas the responders were asked to map and have not delivered yet.
    mapped = set(official.get("areas") or [])
    asked = [a["name"] for a in activation.get("aois") or []]
    waiting = [name for name in asked if name not in mapped]
    if waiting:
        which = ", ".join(waiting)
        lines.append(
            f"{which} {'is' if len(waiting) == 1 else 'are'} inside the "
            f"activation and {'has' if len(waiting) == 1 else 'have'} not been "
            f"graded yet, so nothing here counts {'it' if len(waiting) == 1 else 'them'}."
        )

    if result.get("method") == "graded":
        lines.append(
            "What each building is worth comes from an aggregated national "
            "exposure dataset rather than from any local valuation. At the two "
            "lower damage grades, the share of that value lost is assumed."
        )

    lines.append("No official or industry cost figure has been published for "
                 "this event.")
    return " ".join(lines[:3])


def _method_summary(result: dict, latency: str, tier: int) -> str:
    """One paragraph naming where each part of the figure came from.

    The extent sentence follows the source ladder. Crediting Copernicus Global
    Flood Monitoring for an outline EMS operators drew by hand is the same
    class of error as crediting Sentinel-1 for a Sentinel-2 detection.
    """
    source = result.get("source", "gfm")
    if source == "ems":
        extent = ("Extent mapped by Copernicus EMS operators from very high "
                  "resolution imagery, by photo-interpretation.")
    elif source == "manual":
        extent = "Extent drawn by hand from the imagery listed in the sources."
    else:
        extent = (f"Extent observed {latency}, from Copernicus Global Flood "
                  f"Monitoring at 20 m, merged with Sentinel-2 where radar is "
                  f"blind.")

    # The vulnerability sentence follows the route. CLIMADA and the JRC curves
    # are not touched when the damage was graded building by building, and
    # naming them would credit a method the figure does not rest on.
    if tier != 1:
        vulnerability = ""
    elif result.get("method") == "graded":
        vulnerability = (" Loss is the replacement share of each building's "
                         "recorded damage grade, summed. No water depth is "
                         "assumed and no depth-damage curve is used.")
    else:
        vulnerability = " Loss computed with CLIMADA."

    return f"{extent} Exposure from GHSL and LitPop.{vulnerability}"


def _event_time(result: dict) -> str:
    """When the event happened, local first and UTC alongside.

    Two clocks, because they answer different questions. A reader wants to
    know it was the middle of the night; the data wants a timestamp that does
    not move. Neither is the author's own time zone, which would be wrong for
    both.

    Verified before adopting: Copernicus EMS timestamps are UTC. The
    WorldView-3 scene over Rasuwa is stamped 05:05, which is 10:50 in
    Kathmandu, exactly where a sun-synchronous optical satellite crosses. Had
    the field been local, every latency in this project would have been out by
    5 hours 45.
    """
    from datetime import datetime, timezone

    activation = result.get("activation") or {}
    stamp = activation.get("event_time")
    if not stamp:
        return result["event"].event_date

    utc = datetime.fromisoformat(str(stamp)[:19]).replace(tzinfo=timezone.utc)
    prose = f"{utc.day} {MONTHS[utc.month - 1]} {utc.year}"

    try:
        from zoneinfo import ZoneInfo

        from timezonefinder import TimezoneFinder

        bounds = activation["bounds"]
        zone = TimezoneFinder().timezone_at(lat=(bounds[1] + bounds[3]) / 2,
                                            lng=(bounds[0] + bounds[2]) / 2)
        local = utc.astimezone(ZoneInfo(zone))
    except Exception:                                          # noqa: BLE001
        return f"{prose} at {utc:%H:%M} UTC"

    local_prose = f"{local.day} {MONTHS[local.month - 1]} {local.year}"
    return (f"{local_prose} at {local:%H:%M} local time "
            f"({utc:%Y-%m-%d %H:%M} UTC)")


def _coverage_statement(result: dict) -> str:
    """What share of the area the extent's own source could read, and why not.

    The reason changes with the source and so does the sentence. Radar is
    blinded by the double bounce in built-up land; an EMS operator is blinded
    by what the tasked scene did not cover, and publishes that as its own
    layer.
    """
    unseen = result.get("unseen_share", 0.0)
    assessed = 1.0 - unseen
    source = result.get("source", "gfm")

    if source == "ems":
        # "No part" only when there is genuinely no `notAnalysedA` polygon at
        # all. A small share is still a share: rounding 0.14 km2 down to a
        # claim that everything was readable is the kind of quiet overstatement
        # the whole rule set exists to stop, and it costs one clause to avoid.
        unread_km2 = (result.get("ems") or {}).get("not_analysed_km2") or 0.0
        if not unread_km2:
            return ("Copernicus EMS marked no part of the areas it mapped as "
                    "unreadable, so the figures below cover all of it.")
        return (f"Copernicus EMS marks {unread_km2:.2f} km2 of the ground it "
                f"was asked to map as not analysed, {unseen * 100:.1f}% of the "
                f"total. Nothing inside it is counted, by them or here.")
    if source == "manual":
        return (f"The outline covers {assessed * 100:.0f}% of the area. The "
                f"operator could not read the remaining {unseen * 100:.0f}%, "
                f"and drew no boundary across it.")
    return (f"The estimate covers {assessed * 100:.0f}% of the exposed value. "
            f"The remaining {unseen * 100:.0f}% falls in areas radar could not "
            f"assess, chiefly built-up land.")


def _thousands(number: float) -> str:
    """`3 207`, grouped with an ordinary space.

    A space groups the digits without a comma, which reads as a decimal point
    to half of Europe and is the one separator that can change a figure's
    meaning. An ordinary space, not the typographically correct narrow
    no-break one: that character is missing from fonts a feed may render
    with, and a number arriving as `3?207` is worse than one that wraps.
    """
    return f"{int(round(number)):,}".replace(",", " ")


def _people(count: float | None) -> str:
    """Affected population, at the precision the rules allow.

    Section 6: rounded to the nearest thousand above 10 000. Below that the
    nearest hundred, because a gridded population product does not know who
    lives in which building and a bare count would say it does.
    """
    if count is None:
        return "[TO WRITE]"
    return _thousands(round(count, -3 if count >= 10_000 else -2))


def latency_hours(result: dict) -> float | None:
    """Hours between the event and the first usable satellite observation."""
    from datetime import datetime

    if not result["timeline"]:
        return None
    event_day = datetime.fromisoformat(result["event"].event_date)
    first = min(
        datetime.fromisoformat(scene["datetime"].replace("Z", "")).replace(tzinfo=None)
        for scene in result["timeline"] if scene["area_km2"] > 0
    )
    return round((first - event_day).total_seconds() / 3600, 1)


def fact_sheet(result: dict, currency: str = "EUR", tier: int = 1) -> dict:
    """Every value the template needs, keyed by its placeholder name.

    Slots that require judgement are filled with a visible marker rather than
    with a guess, so an unreviewed draft is obvious at a glance.
    """
    event = result["event"]
    todo = "[TO WRITE]"

    hours = latency_hours(result) if result.get("timeline") else None
    if hours:
        latency = f"{hours:.0f} hours after the event"
    elif result.get("awaiting_pass"):
        latency = (f"not yet observed; next Sentinel-1 pass expected "
                   f"{result['awaiting_pass']}")
    else:
        latency = "not yet observed"

    return {
        "PERIL": event.peril.capitalize(),
        "REGION": event.region,
        "COUNTRY": event.country,
        "EVENT_DATE": event.event_date,
        "EVENT_TIME": _event_time(result),
        # Why it happened, quoted from the activation request rather than
        # written here. It is the requester's account, and it is the only
        # place in the chain a mechanism or a measured water level appears.
        "EVENT_CAUSE": (result.get("activation") or {}).get("reason") or todo,
        "CURRENCY": currency,
        "BASE_YEAR": "2014" if currency == "USD" else "2014, converted at 2023 rates",
        "LOSS_FIGURE": _money(result["loss_usd"], currency),
        # A range where the method produces one, because a single figure with
        # no range is what docs/DECISIONS.md calls indefensible. The graded
        # route brackets it tightly; the depth route brackets it by a factor.
        "LOSS_RANGE": (
            f"{_money(result['loss_low_usd'], currency)} to "
            f"{_money(result['loss_high_usd'], currency)}"
            if result.get("loss_low_usd") is not None
            else _money(result["loss_usd"], currency)),
        # Only where a detection of our own actually ran. Where Copernicus
        # graded the event and the detector was left off, there is nothing to
        # compare and no line.
        "DETECTION_LINE": (
            f"- Our own detection found: {result['detected_km2']:.1f} km2, "
            f"{result['detected_km2'] / (result.get('ems') or {}).get('observed_km2', 1) * 100:.0f}% "
            f"of what Copernicus mapped"
            if result.get("detected_km2") and (result.get("ems") or {}).get("observed_km2")
            else ""),
        "EXPOSED_VALUE": _money(result["exposed_usd"], currency),
        "LOSS_SHARE": f"{result['damage_ratio'] * 100:.1f}%",
        "EXTENT_AREA": f"{result['extent_km2']:.0f}",
        "PRODUCT_RESOLUTION": "20 m",
        # Template 03 asks who saw it and when. Both are in the timeline
        # already; leaving them as placeholders made the extent post the only
        # one that could not be published (H8).
        "SENSOR": _sensor(result),
        "PASS_TIMESTAMP": _first_pass(result),
        "LATENCY_STATEMENT": _latency_statement(result),
        "EXTENT_CREDIT": _extent_credit(result),
        "POPULATION": _people(result.get("affected_population")),
        # What could not be assessed, and by whom. Saying "radar could not
        # assess" under an outline drawn from 50 cm optical names the wrong
        # instrument and the wrong weakness.
        "COVERAGE_STATEMENT": _coverage_statement(result),
        "EXCLUSION_STATEMENT": (
            "Public infrastructure, agriculture and vehicles are outside the "
            "model. Only private built assets are counted."
        ),
        "ASSUMPTION_DEPTH": (
            f"Water depth is assumed uniform at {event.depth_m:.1f} m. It was "
            f"not measured: the footprint is too fragmented for depth to be "
            f"derived from terrain."
        ),
        "ASSUMPTION_EXPOSURE": (
            "Exposure is GHSL built-up surface at 100 m, anchored to the "
            "LitPop national total for produced capital."
        ),
        "ASSUMPTION_CURVE": (
            f"Damage curve: {result['impact_function']} (JRC, Huizinga et al., "
            f"2017)."
        ),
        "ASSUMPTION_OTHER": (
            f"Extent merges Copernicus GFM radar with Sentinel-2 optical infill "
            f"over the radar blind spot; fragments below "
            f"{MIN_FRAGMENT_PIXELS} pixels are discarded as speckle."
        ),
        "DOMINANT_ASSUMPTION_STATEMENT": (
            "Assumed water depth dominates the result. At 0.5 m the loss would "
            "be roughly 40% lower, at 2 m roughly 50% higher."
        ),
        # Names the source the extent actually came from, and mentions CLIMADA
        # only in a post that publishes a loss. At tier 2 it credited an engine
        # whose output the same post refuses to print.
        "METHOD_SUMMARY": _method_summary(result, latency, tier),
        # Sentinel is credited only where a Sentinel scene entered the
        # figures. With the detector off and the extent mapped by EMS from
        # commercial imagery, none did.
        "SENTINEL_CREDIT": (
            "" if result.get("source") == "ems" and not result.get("detected_km2")
            else locked_phrases()["L-SRC-SENTINEL"].replace(
                "{{YEAR}}", event.event_date[:4])),
        "DISCLAIMER": locked_phrases()[
            "L-DISC-GRADED" if result.get("method") == "graded"
            else "L-DISC-FULL"],
        "CROSSCHECK_FIGURE": event.crosscheck_figure or todo,
        "CROSSCHECK_SOURCE": event.crosscheck_source or todo,
        "EVENT_SUMMARY": todo,
        "UNKNOWNS": _unknowns(result),
        # Zero is an acceptable and common choice, rules section 3.
        "HASHTAGS": "",
        "EMSR_CODE": event.ems_code,
        "YEAR": event.event_date[:4],
        # Pending-case fields, used by the alert template when nothing has
        # been observed yet.
        "PASS_DATE": str(result.get("awaiting_pass") or todo),
        "REVISIT_DAYS": str(result.get("cycle_days") or todo),
        "PASS_CAVEAT": (
            "The estimate is empirical, measured from what Sentinel-1 actually "
            "did over this exact area in recent weeks. Cloud does not affect "
            "radar, but steep terrain does: in this valley much of the ground "
            "sits in radar shadow."
        ),
        "ALERT_LEVEL": todo,
        "FACT": todo,
        "SOURCE": todo,
        "TIMESTAMP": todo,
        "ADDITIONAL_UNKNOWNS": todo,
    }


def locked_phrases() -> dict:
    """The fixed wordings, read from the editorial rules.

    These sentences are quoted from `docs/EDITORIAL_RULES.md` rather than
    retyped here. A caveat that drifts between posts is a caveat that no longer
    means the same thing, and one copy is the only way to guarantee it does not.
    """
    text = (ROOT / "docs" / "EDITORIAL_RULES.md").read_text(encoding="utf-8")
    phrases = {}

    # Long wordings are written as block quotes under their identifier
    for match in re.finditer(
        r"`(L-[A-Z0-9-]+)`[^\n]*:\s*\n\s*\n((?:> ?[^\n]*\n)+)", text
    ):
        body = "\n".join(line.lstrip("> ").rstrip()
                         for line in match.group(2).strip().split("\n"))
        phrases[match.group(1)] = body.strip()

    # Short ones, chiefly source credits, live in a two-column table
    for match in re.finditer(r"^\|\s*`(L-[A-Z0-9-]+)`\s*\|\s*(.+?)\s*\|\s*$",
                             text, flags=re.MULTILINE):
        phrases.setdefault(match.group(1), match.group(2).strip())

    return phrases


# Values that are the same on every post, whatever the event.
GLOBALS = {
    "REPO_URL": "https://github.com/ihammouti/hazard-watch",
    "EMSR_CODE": "",
    "YEAR": "",
}


def fill_template(kind: str, values: dict) -> str:
    """Fill a post template, leaving unfilled placeholders visible.

    Locked phrasings are resolved first, then have their own placeholders
    filled, so a fixed sentence can still quote a figure without being
    rewritten.
    """
    text = (TEMPLATES / kind).read_text(encoding="utf-8")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    for key, phrase in locked_phrases().items():
        text = text.replace(f"{{{{LOCKED:{key}}}}}", phrase)

    # Twice, because a value can itself be a resolved locked string carrying
    # its own placeholder: L-SRC-EMS-GRADING arrives inside REPORTED_BODY with
    # {{EMSR_CODE}} still in it, and dictionary order decides nothing.
    for _ in range(2):
        for key, value in {**GLOBALS, **values}.items():
            text = text.replace(f"{{{{{key}}}}}", str(value))

    missing = sorted(set(re.findall(r"\{\{LOCKED:([A-Z0-9-]+)\}\}", text)))
    if missing:
        text += ("\n\n> Unresolved locked phrasings, check "
                 f"docs/EDITORIAL_RULES.md: {', '.join(missing)}\n")

    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"



def _smooth_dem(dem, source_scale: float, page_scale: float):
    """Blur the terrain by however much it was enlarged.

    FABDEM is 30 m. A sheet covering five kilometres asks about 4 m a pixel,
    so the hillshade renders the source grid rather than the relief and the
    page comes out looking like graph paper. The blur is sized to the
    enlargement, so a wide sheet that needed no upsampling is left alone.
    """
    ratio = source_scale / max(page_scale, 1e-9)
    if ratio <= 1.5:
        return dem
    return ndimage.gaussian_filter(dem, sigma=min(ratio / 2.5, 6.0))


def _country_borders(point: tuple, radius_km: float = 3000.0) -> list:
    """Country outlines around a point, as lon/lat segments, cached on disk.

    Read from FAO GAUL level 0, the same source the map already credits for
    its place names. Simplified to 20 km, which is finer than a 3 000 km
    locator can show and keeps the cached file small. An empty list on failure:
    a missing political line is not a reason to lose the map.
    """
    lon, lat = round(point[0], 1), round(point[1], 1)
    cache = CACHE / f"borders_{lon}_{lat}_{int(radius_km)}.pkl"
    if cache.exists():
        with open(cache, "rb") as handle:
            return pickle.load(handle)

    try:
        import ee

        span = radius_km / 111.0 * 1.25
        window = ee.Geometry.Rectangle(
            [lon - span, max(lat - span, -85.0),
             lon + span, min(lat + span, 85.0)], None, False)
        collection = (ee.FeatureCollection("FAO/GAUL/2015/level0")
                      .filterBounds(window)
                      .map(lambda f: ee.Feature(f.geometry().simplify(20000))))
        features = collection.getInfo()["features"]
    except Exception:                                          # noqa: BLE001
        return []

    segments = []
    for feature in features:
        geometry = shapely_shape(feature["geometry"])
        parts = geometry.geoms if hasattr(geometry, "geoms") else [geometry]
        for part in parts:
            if part.geom_type != "Polygon":
                continue
            for ring in [part.exterior, *part.interiors]:
                arr = np.asarray(ring.coords)
                if len(arr) >= 2:
                    segments.append((arr[:, 0], arr[:, 1]))

    CACHE.mkdir(parents=True, exist_ok=True)
    with open(cache, "wb") as handle:
        pickle.dump(segments, handle)
    return segments


def draw_map(result: dict, path: Path, verdict=None, ems: dict | None = None,
             area: dict | None = None, features: dict | None = None,
             fill_share: float = 0.80, published=None,
             number: int | None = None) -> Path:
    """The main map for this event, in the project's visual identity.

    `verdict` is not optional in practice. The map is a second publication
    surface and the tier that suppresses a currency figure in the text has to
    reach it too: the first Rasuwa map printed a modelled loss of €6M above a
    post that refused to publish one.

    `ems` is the Copernicus EMS grading summary, where the products have been
    downloaded. It is drawn as a reference outline and quoted as a count; it
    never enters the loss chain.

    `area` frames the sheet on one mapped area instead of on the whole
    footprint. An activation covering four valleys 60 km apart cannot be shown
    on one sheet at a scale where a 0.9 km2 outline is visible: framing on the
    footprint put Bidur on the page and left Syapru Besi and Timure, where the
    two named hydropower stations were destroyed, off it entirely.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    import ee

    event = result["event"]
    activation = result["activation"]
    profile = result["profile"]
    footprint = result["footprint"]
    crs = profile["crs"]

    if area is not None:
        target = rasterio.warp.transform_bounds("EPSG:4326", crs,
                                                *area["geometry"].bounds)
    else:
        rows, cols = np.where(footprint)
        xs, ys = rasterio.transform.xy(profile["transform"], rows, cols)
        target = (float(np.min(xs)), float(np.min(ys)),
                  float(np.max(xs)), float(np.max(ys)))
    extent = carto.frame_extent(target, carto.PORTRAIT, fill=fill_share)

    lon0, lat0, lon1, lat1 = rasterio.warp.transform_bounds(
        crs, "EPSG:4326", extent[0], extent[1], extent[2], extent[3])
    page = {
        "crs": crs,
        "transform": rasterio.transform.from_bounds(
            extent[0], extent[1], extent[2], extent[3], 1080, 1350),
        "resolution": (extent[2] - extent[0]) / 1080,
    }
    # Fetch the terrain at roughly the page's own resolution, never finer than
    # FABDEM's native 30 m. Asking for 90 m over a five kilometre sheet meant
    # a twentyfold upsample, and the hillshade came out as a moiré of tile
    # seams rather than as relief.
    dem_scale = int(min(90, max(30, page["resolution"])))
    dem = natcat._ee_to_grid(
        ee.ImageCollection("projects/sat-io/open-datasets/FABDEM")
        .mosaic().select("b1"),
        (lon0, lat0, lon1, lat1), page, (1350, 1080), scale=dem_scale)
    dem = _smooth_dem(dem, dem_scale, page["resolution"])

    study = rasterio.warp.transform_geom("EPSG:4326", crs,
                                         mapping(activation["union"]))

    cities, countries = _context_labels(event.ems_code, (lon0, lat0, lon1, lat1))
    with open(CACHE / "world_outline.pkl", "rb") as handle:
        silhouette = pickle.load(handle)

    accent = carto.PERIL_COLOURS[event.peril]
    legend_anchor = (0.655, 0.200)

    occupancy = _canvas_occupancy(footprint, [
        (carto.LOCATOR_XY, carto.LOCATOR_SIZE),
        (legend_anchor, (0.29, 0.09)),
    ])
    spots = carto.place_boxes(occupancy, [
        carto.circle_slot(carto.BUBBLE_PRIMARY_R),
        carto.circle_slot(carto.BUBBLE_SECONDARY_R),
    ])

    carto.apply()
    fig = carto.canvas(carto.PORTRAIT)
    ax = fig.add_axes([0, 0, 1, 1], zorder=0)
    # No white wash outside the study area. The dashed outline already says
    # where it is, and washing the rest out threw away the terrain that
    # explains the event: a gorge reads as a gorge only if the ridges either
    # side of it are visible.
    backdrop = carto.draw_basemap(
        ax, dem, extent=(extent[0], extent[2], extent[1], extent[3]))
    ax.set_xlim(extent[0], extent[2])
    ax.set_ylim(extent[1], extent[3])
    ax.axis("off")

    rings = (study["coordinates"] if study["type"] == "MultiPolygon"
             else [study["coordinates"]])
    for polygon in rings:
        ring = np.array(polygon[0])
        ax.plot(ring[:, 0], ring[:, 1], color=carto.STUDY_AREA, lw=2.1,
                ls=(0, carto.STUDY_AREA_DASH), zorder=3, alpha=0.95)

    # The outline of what the responders mapped, drawn only when the filled
    # area is somebody else's: once the fill is the EMS footprint the outline
    # traces the same geometry twice.
    for feature in ([] if result.get("source") == "ems"
                    else (ems or {}).get("observed", [])):
        drawn = rasterio.warp.transform_geom("EPSG:4326", crs, mapping(feature))
        parts = (drawn["coordinates"] if drawn["type"] == "MultiPolygon"
                 else [drawn["coordinates"]])
        for polygon in parts:
            ring = np.array(polygon[0])
            ax.plot(ring[:, 0], ring[:, 1], color=carto.OBSERVED_EVENT,
                    lw=1.6, ls=(0, carto.OBSERVED_EVENT_DASH), zorder=5,
                    alpha=0.95)

    transform = profile["transform"]
    bounds = (transform.c, transform.c + footprint.shape[1] * transform.a,
              transform.f + footprint.shape[0] * transform.e, transform.f)

    def fill(mask, colour, zorder):
        ax.imshow(np.ma.masked_where(~mask, mask), extent=bounds,
                  origin="upper",
                  cmap=matplotlib.colors.ListedColormap([colour]),
                  interpolation="nearest", zorder=zorder)

    # What the filled area is depends on which source produced it. Labelling
    # the EMS footprint "detected extent" contradicted the bubble beside it
    # saying our detector saw none of that ground.
    #
    # Where the responders mapped the event, the sheet shows what they mapped
    # and what they counted, and stops showing our own outline entirely. Two
    # overlapping detections of the same ground is a comparison for the text;
    # on the sheet it spends the reader's attention on the weaker one.
    from_ems = result.get("source") == "ems"
    if from_ems:
        # Hatched, not filled. A solid navy river swamped the damage points
        # that are the reason the sheet exists, and it read as a permanent
        # water body rather than as the flooded surface.
        for feature in (ems or {}).get("observed", []):
            drawn_geom = rasterio.warp.transform_geom("EPSG:4326", crs,
                                                      mapping(feature))
            parts = (drawn_geom["coordinates"]
                     if drawn_geom["type"] == "MultiPolygon"
                     else [drawn_geom["coordinates"]])
            for polygon in parts:
                ax.add_patch(plt.Polygon(
                    np.array(polygon[0]), closed=True, facecolor="none",
                    edgecolor=carto.OBSERVED_EVENT, lw=1.3, hatch="////",
                    alpha=0.85, zorder=4))
    else:
        fill(footprint, accent, 4)
    own_shown = False

    drawn_layers = _damage_layers(ax, crs, features, extent) if features else {}

    reserved = [
        (carto.LOCATOR_XY[0] - 0.02, carto.LOCATOR_XY[1] - 0.02,
         carto.LOCATOR_SIZE[0] + 0.04, carto.LOCATOR_SIZE[1] + 0.04),
        (legend_anchor[0] - 0.02, legend_anchor[1] - 0.02, 0.33, 0.13),
        (0.0, 0.0, 1.0, carto.CANVAS["bottom"] + 0.02),
        (0.0, carto.CANVAS["top"] - 0.02, 1.0, 0.30),
    ]
    nudge = (extent[2] - extent[0]) * 0.011

    def to_map(lon, lat):
        tx, ty = rasterio.warp.transform("EPSG:4326", crs, [lon], [lat])
        return tx[0], ty[0]

    for name, lon, lat in countries:
        xy = to_map(lon, lat)
        if carto.label_is_clear(xy, extent, reserved):
            carto.place_label(ax, xy[0], xy[1], name.upper(), kind="country")
    for name, (lon, lat) in event.seas.items():
        xy = to_map(lon, lat)
        if carto.label_is_clear(xy, extent, reserved):
            carto.place_label(ax, xy[0], xy[1], name, kind="water")
    for name, lon, lat in cities:
        xy = to_map(lon, lat)
        if carto.label_is_clear(xy, extent, reserved):
            carto.place_label(ax, xy[0], xy[1], name, offset=nudge, kind="city")

    carto.fade(fig)

    tier = getattr(verdict, "tier", 1)

    # What this project detected, which is not the same as the footprint the
    # figures were computed on once the ladder has picked EMS. Comparing the
    # EMS extent against the EMS extent returns 102 % and says nothing.
    shown = (result.get("detected_km2", 0.0) if result.get("source") == "ems"
             else result["extent_km2"])
    if area is not None and result.get("detected") is not None:
        # On a per-area sheet the detection has to be the detection inside
        # that area, or it is compared against a denominator it does not
        # belong to.
        here = _rasterise([area["geometry"]], profile, footprint.shape)
        pixel_km2 = profile["resolution"] ** 2 / 1e6
        source_mask = (result["detected"] if result.get("source") == "ems"
                       else footprint)
        shown = float((source_mask & here).sum() * pixel_km2)
    extent_text = f"{shown:.1f} km²" if shown < 10 else f"{shown:.0f} km²"

    # Numbered notes are built alongside the labels that carry them, so a
    # superscript never points at a note that was not written.
    marks = "¹²³"
    notes = []

    def note(text: str) -> str:
        notes.append(f"{len(notes) + 1}. {text}")
        return marks[len(notes) - 1]

    graded_method = result.get("method") == "graded"

    # A sheet for one valley must carry that valley's figures. The activation
    # total on a page headed Syapru Besi is the same misreading the per-area
    # counts were split to prevent.
    money = {"loss": result.get("loss_usd", 0.0),
             "exposed": result.get("exposed_usd", 0.0)}
    if area is not None and graded_method and features and features.get("builtUpP"):
        local_loss = natcat.graded_loss(features["builtUpP"],
                                        result["value"], profile)
        money = {"loss": local_loss["loss"], "exposed": local_loss["exposed"]}

    if tier != 1:
        loss_mark = ""
    elif graded_method:
        loss_mark = note("Priced from the damage grade Copernicus EMS "
                         "recorded for each building, not from an assumed "
                         "water depth.")
    else:
        loss_mark = note(f"Residential built assets, {event.depth_m:.0f} m "
                         f"water depth assumed.")

    if ems and ems.get("observed_km2"):
        share = shown / ems["observed_km2"]
        extent_note = f"{share * 100:.0f}% of the EMS mapped event"
    else:
        extent_note = (f"{result['unseen_share'] * 100:.0f}% unseen "
                       + note("Share of the area neither radar nor optical "
                              "imagery could assess."))

    # A share rather than a count: 79 % destroyed says how bad it was, where
    # 2 521 only says how big the place is.
    destroyed = (ems or {}).get("building_grades", {}).get("Destroyed")
    buildings = None
    if destroyed and (ems or {}).get("buildings"):
        buildings = (f"{destroyed / ems['buildings'] * 100:.0f}%",
                     "Buildings destroyed",
                     f"{_thousands(destroyed)} of "
                     f"{_thousands(ems['buildings'])} graded by EMS")

    if tier == 1:
        primary = (_money(money["loss"]), f"Modelled loss {loss_mark}",
                   f"{_money(money['exposed'])} exposed")
        secondary = buildings or (extent_text, "Flood extent", extent_note)
    elif buildings:
        # Where the responders graded the damage, that is the measurement on
        # the sheet. Our own detection is a comparison for the text and has no
        # business taking a bubble, least of all to report a zero.
        primary = buildings
        secondary = (_money(money["exposed"]), "Exposed value",
                     f"in the {ems['observed_km2']:.1f} km² EMS mapped")
    else:
        # No currency figure the evidence cannot support, on the graphic any
        # more than in the text.
        primary = (extent_text, "Detected extent", extent_note)
        secondary = (_money(money["exposed"]), "Exposed value",
                     "no loss figure at this tier")

    carto.bubble(fig, backdrop,
                 carto.slot_centre(spots[0], carto.BUBBLE_PRIMARY_R),
                 carto.BUBBLE_PRIMARY_R, *primary, peril=event.peril)
    carto.bubble(fig, backdrop,
                 carto.slot_centre(spots[1], carto.BUBBLE_SECONDARY_R),
                 carto.BUBBLE_SECONDARY_R, *secondary, peril=event.peril)

    centre = ((activation["bounds"][0] + activation["bounds"][2]) / 2,
              (activation["bounds"][1] + activation["bounds"][3]) / 2)
    carto.locator(fig, centre, silhouette, xy=carto.LOCATOR_XY,
                  borders=_country_borders(centre))

    keys = []
    if from_ems:
        # "Mapped by EMS operators" said nothing: a reader could not tell the
        # river from the flood. The legend names the thing, not the process.
        keys.append(Patch(facecolor="none", edgecolor=carto.OBSERVED_EVENT,
                          hatch="////", lw=1.3,
                          label="Flooded surface, mapped by EMS"))
    else:
        keys.append(Line2D([], [], marker="s", ls="", ms=10, color=accent,
                           label="Detected extent"))
    for grade in carto.DAMAGE_GRADES_ORDER:
        if drawn_layers.get(grade):
            keys.append(Line2D([], [], marker="o", ls="", ms=8,
                               markeredgecolor="none",
                               color=carto.DAMAGE_COLOURS[grade],
                               label=f"Buildings {grade.lower()}"))
    if drawn_layers.get("facilities"):
        keys.append(Line2D([], [], marker="^", ls="", ms=9,
                           markeredgecolor="#FFFFFF", markeredgewidth=1.1,
                           color=carto.FACILITY,
                           label="Critical facility hit"))
    if drawn_layers.get("roads"):
        keys.append(Line2D([], [], ls="-", lw=2.4, color=carto.ROAD_CUT,
                           label="Road destroyed"))
    keys.append(Line2D(
        [], [], ls=carto.legend_dashes(carto.STUDY_AREA_DASH, cycles=3),
        lw=2.1, color=carto.STUDY_AREA, label="EMS study area"))
    carto.legend_panel(fig, backdrop, keys, legend_anchor)

    byline_top = 0.128
    byline_h = carto.TYPE["byline"] / 72 * carto.DPI / carto.PORTRAIT[1]
    carto.byline_furniture(fig, ax, bottom=byline_top - byline_h)

    # The number the overview gave this area. The carousel is read in order
    # and the sheets are titled by place name, so without it a reader has to
    # match "Phosretar" back to a dot on the first card by memory.
    where = f"{area['name']}, {event.region}" if area else event.region
    if area and number:
        where = f"{number}. {where}"
    when = (f"Graded {published:%d %B %Y}" if published
            else f"{event.event_date}")
    carto.header(fig, f"{where} {event.peril}",
                 f"{when}  ·  Copernicus EMS {event.ems_code}  ·  "
                 f"{event.country}",
                 peril=event.peril)
    # Only what was actually used. On the graded route no depth-damage curve
    # is read and CLIMADA is not called, so crediting either would name a
    # method the figure does not rest on.
    sources = "Sources: "
    if from_ems:
        sources += "Copernicus EMS Rapid Mapping grading products"
    else:
        sources += ("Copernicus EMS / Global Flood Monitoring · Sentinel-1, "
                    "Sentinel-2")
    sources += " · JRC GHSL · FABDEM"
    if tier == 1 and not graded_method:
        sources += (" · CLIMADA (ETH Zurich) · JRC depth-damage functions "
                    "(Huizinga et al., 2017)")
    sources += " · Administrative boundaries: FAO GAUL"

    # The standing disclaimer opens on "Modelled estimate". Below tier 1 the
    # sheet carries no modelled estimate, so the first two words are the only
    # part that changes; everything the disclaimer actually disclaims stands.
    disclaimer = carto.DISCLAIMER
    if tier != 1:
        disclaimer = disclaimer.replace("Modelled estimate", "Observed extent")

    carto.footer(fig, sources, byline="Ilyas Hammouti",
                 notes=" ".join(notes), disclaimer=disclaimer)

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=carto.THEME["background"])
    plt.close(fig)
    return path


def _canvas_occupancy(footprint: np.ndarray, reserved: list,
                      rows: int = 260, cols: int = 220) -> np.ndarray:
    """Where the canvas is already busy, for the placement solver."""
    grid = np.zeros((rows, cols), bool)
    sub = footprint[::max(1, footprint.shape[0] // rows),
                    ::max(1, footprint.shape[1] // cols)]
    grid[:min(rows, sub.shape[0]), :min(cols, sub.shape[1])] = sub[:rows, :cols]

    width = carto.CANVAS["right"] - carto.CANVAS["left"]
    height = carto.CANVAS["top"] - carto.CANVAS["bottom"]
    for (fx, fy), (fw, fh) in reserved:
        c0 = int(np.clip((fx - carto.CANVAS["left"]) / width, 0, 1) * cols)
        c1 = int(np.clip((fx + fw - carto.CANVAS["left"]) / width, 0, 1) * cols)
        r0 = int((1 - np.clip((fy + fh - carto.CANVAS["bottom"]) / height, 0, 1)) * rows)
        r1 = int((1 - np.clip((fy - carto.CANVAS["bottom"]) / height, 0, 1)) * rows)
        grid[r0:r1, c0:c1] = True
    return grid


def _overview_occupancy(ordered: list, extent: tuple, crs, reserved: list,
                        rows: int = 260, cols: int = 220) -> np.ndarray:
    """Where the overview sheet is already busy, for the placement solver.

    The per-area sheets can hand `place_boxes` a raster of the flooded
    footprint and be done. This sheet has no raster: it has a handful of
    outlines that are a few pixels wide, and a label beside each. Passing an
    empty grid told the solver the page was free everywhere, which is how a
    bubble ended up on top of two labels and why the positions here were
    hard-coded afterwards. This builds the grid the solver was missing.
    """
    grid = np.zeros((rows, cols), bool)
    span_x = extent[2] - extent[0]
    span_y = extent[3] - extent[1]
    width = carto.CANVAS["right"] - carto.CANVAS["left"]
    height = carto.CANVAS["top"] - carto.CANVAS["bottom"]

    def mark(fx: float, fy: float, half_c: int = 2, half_r: int = 2):
        """Mark a cell, and its neighbours, from a figure-fraction point."""
        c = int((fx - carto.CANVAS["left"]) / width * cols)
        r = int((1 - (fy - carto.CANVAS["bottom"]) / height) * rows)
        grid[max(0, r - half_r):min(rows, r + half_r + 1),
             max(0, c - half_c):min(cols, c + half_c + 1)] = True

    for area in ordered:
        drawn = rasterio.warp.transform_geom("EPSG:4326", crs,
                                             mapping(area["geometry"]))
        parts = (drawn["coordinates"] if drawn["type"] == "MultiPolygon"
                 else [drawn["coordinates"]])
        ring_points = []
        for polygon in parts:
            ring = np.array(polygon[0])
            for x, y in ring:
                fx, fy = (x - extent[0]) / span_x, (y - extent[1]) / span_y
                mark(fx, fy)
                ring_points.append((fx, fy))
        if not ring_points:
            continue
        # The label sits beside the centroid and is the widest thing on the
        # page after the areas themselves. Which side it goes on follows the
        # same rule the drawing uses, so the reserved strip is on the side
        # the text will actually occupy.
        cx = float(np.mean([q[0] for q in ring_points]))
        cy = float(np.mean([q[1] for q in ring_points]))
        left_side = (1 - cx) < 0.22
        for step in np.linspace(0, 0.16, 24):
            mark(cx - step if left_side else cx + step, cy, half_r=3)

    for (fx, fy), (fw, fh) in reserved:
        c0 = int(np.clip((fx - carto.CANVAS["left"]) / width, 0, 1) * cols)
        c1 = int(np.clip((fx + fw - carto.CANVAS["left"]) / width, 0, 1) * cols)
        r0 = int((1 - np.clip((fy + fh - carto.CANVAS["bottom"]) / height, 0, 1)) * rows)
        r1 = int((1 - np.clip((fy - carto.CANVAS["bottom"]) / height, 0, 1)) * rows)
        grid[r0:r1, c0:c1] = True

    return grid


def _spot_flips(fx: float) -> bool:
    """Whether a spot height near the right margin must label leftwards."""
    return fx > 0.62


def _spot_heights(ax, dem: np.ndarray, extent: tuple, occupancy: np.ndarray,
                  taken: list) -> int:
    """Highest, lowest and mid-altitude points, in whatever room is left.

    Optional by construction. Each point is only drawn where the sheet is
    genuinely empty there — not on an area, a place name, a bubble or the
    furniture — so on a crowded page some or all of them are simply skipped.
    A spot height is relief annotation: worth having when there is space for
    it, never worth pushing anything else aside for.
    """
    rows, cols = occupancy.shape
    span_x, span_y = extent[2] - extent[0], extent[3] - extent[1]
    width = carto.CANVAS["right"] - carto.CANVAS["left"]
    height = carto.CANVAS["top"] - carto.CANVAS["bottom"]

    busy = occupancy.copy()
    for (bx, by, bw, bh) in taken:
        c0 = int(np.clip((bx - carto.CANVAS["left"]) / width, 0, 1) * cols)
        c1 = int(np.clip((bx + bw - carto.CANVAS["left"]) / width, 0, 1) * cols)
        r0 = int((1 - np.clip((by + bh - carto.CANVAS["bottom"]) / height, 0, 1)) * rows)
        r1 = int((1 - np.clip((by - carto.CANVAS["bottom"]) / height, 0, 1)) * rows)
        busy[r0:r1, c0:c1] = True

    def free(fx: float, fy: float) -> bool:
        """Is this figure-fraction point clear, with room for its label?

        The metres sit beside the dot, so the window checked is the one the
        text will actually occupy — to the right normally, to the left near
        the right margin, which is also the side the label is then drawn on.
        """
        if not (0.08 < fx < 0.93):
            return False
        if not (carto.CANVAS["bottom"] + 0.03 < fy < carto.CANVAS["top"] - 0.03):
            return False
        c = int((fx - carto.CANVAS["left"]) / width * cols)
        r = int((1 - (fy - carto.CANVAS["bottom"]) / height) * rows)
        if _spot_flips(fx):
            patch = busy[max(0, r - 6):r + 7, max(0, c - 34):c + 5]
        else:
            patch = busy[max(0, r - 6):r + 7, max(0, c - 4):c + 34]
        return patch.size > 0 and not patch.any()

    finite = np.isfinite(dem)
    if finite.sum() < 100:
        return 0
    values = np.where(finite, dem, np.nan)
    targets = [("high", np.nanmax(values)), ("low", np.nanmin(values)),
               ("mid", float(np.nanmean(values)))]

    drawn = 0
    for _, target in targets:
        # Closest pixel to the wanted altitude, then outwards through the
        # next-closest ones until one lands somewhere there is room.
        order = np.argsort(np.abs(values - target), axis=None)
        for flat in order[:40000]:
            r, c = np.unravel_index(flat, values.shape)
            if not np.isfinite(values[r, c]):
                continue
            fx, fy = (c + 0.5) / values.shape[1], 1 - (r + 0.5) / values.shape[0]
            if not free(fx, fy):
                continue
            x = extent[0] + fx * span_x
            y = extent[1] + fy * span_y
            flip = _spot_flips(fx)
            carto.place_label(ax, x, y, f"{_thousands(values[r, c])} m",
                              kind="spot",
                              offset=span_x * (-0.008 if flip else 0.008),
                              align="right" if flip else "left")
            # Block the ground this one just took, so the next spot height
            # does not land on its label.
            gc = int((fx - carto.CANVAS["left"]) / width * cols)
            gr = int((1 - (fy - carto.CANVAS["bottom"]) / height) * rows)
            if flip:
                busy[max(0, gr - 10):gr + 11, max(0, gc - 40):gc + 9] = True
            else:
                busy[max(0, gr - 10):gr + 11, max(0, gc - 8):gc + 40] = True
            drawn += 1
            break
    return drawn


def _context_labels(code: str, view: tuple):
    """Provincial capitals and countries in view, from FAO GAUL."""
    import ee

    path = CACHE / f"context_{code}.pkl"
    if path.exists():
        with open(path, "rb") as handle:
            return pickle.load(handle)

    lon0, lat0, lon1, lat1 = view
    window = ee.Geometry.Rectangle([lon0, lat0, lon1, lat1])

    # GAUL writes a trailing apostrophe where the source had a grave accent,
    # and inserts a placeholder row where it has no name at all.
    accented = {"Forli'": "Forlì", "Cesena'": "Cesena"}

    cities = []
    for feature in (ee.FeatureCollection("FAO/GAUL/2015/level2")
                    .filterBounds(window).limit(60).getInfo()["features"]):
        raw = feature["properties"]["ADM2_NAME"]
        if not raw or "not available" in raw.lower():
            continue
        geometry = shapely_shape(feature["geometry"])
        point = geometry.representative_point()
        if lon0 < point.x < lon1 and lat0 < point.y < lat1:
            cities.append((accented.get(raw, raw.rstrip("'")),
                           point.x, point.y, geometry.area))
    cities.sort(key=lambda item: -item[3])
    cities = [(name, x, y) for name, x, y, _ in cities[:9]]

    countries, seen = [], set()
    for feature in (ee.FeatureCollection("FAO/GAUL/2015/level1")
                    .filterBounds(window).limit(40).getInfo()["features"]):
        name = feature["properties"]["ADM0_NAME"]
        if name in seen:
            continue
        seen.add(name)
        point = shapely_shape(feature["geometry"]).representative_point()
        countries.append((name, point.x, point.y))

    with open(path, "wb") as handle:
        pickle.dump((cities, countries), handle)
    return cities, countries


def make_post(event: FloodEvent, kind: str | None = None,
              use_cache: bool = True, update_note: str = "") -> dict:
    """Produce everything a post needs for one event.

    The guards run before anything is written, and the tier they return picks
    the template. An event that cannot support a currency figure still gets a
    post; it just gets a different one.

    Writes the map, the filled draft, and the raw figures as JSON. The draft
    still carries [TO WRITE] wherever a human has to decide something.

    `update_note` is empty by default, and stays empty on every ordinary run:
    nothing here should claim to be a follow-up unless one actually
    published earlier. Pass one sentence saying what changed and why when
    this run genuinely does supersede a post that already went out — the
    editorial rules require exactly that, plainly, rather than a silent
    replacement.
    """
    result = compute(event, use_cache=use_cache)
    official = result.get("ems")

    # The activation clock, which is what the early posts are made of and what
    # the reported block quotes for latency.
    record = ems.activation(event.ems_code)
    clock = ems.timings(record) if record else None

    verdict = guards.assess(
        result,
        mechanism=event.mechanism,
        steep_share=result.get("steep_share"),
        next_pass=result.get("awaiting_pass"),
        ems=official,
        timings=clock,
    )

    values = fact_sheet(result, tier=verdict.tier)
    if result.get("source") == "manual":
        import manual

        # Fills L-SRC-MANUAL and L-DRAWN. Without these the post cannot be
        # published at all (H13), so they are added before anything is written.
        values.update(manual.credit_values(result["activation"]))
    values.update(_reported_values(verdict, clock))
    values.update(_calendar_values(result, clock))
    values["UPDATE_NOTE"] = update_note
    values["TIER_STATEMENT"] = guards.tier_statement(verdict)
    if verdict.tier != 1:
        # Never leave a currency figure in a draft the evidence cannot support
        values["LOSS_FIGURE"] = "not published at this tier"
        values["LOSS_SHARE"] = "not published at this tier"

    template = kind or guards.choose_template(verdict, result)
    stem = OUTPUT / event.ems_code
    stem.mkdir(parents=True, exist_ok=True)

    sheet_path = stem / f"{event.ems_code}_draft.md"
    body = _drop_empty_sections(fill_template(template, values))
    sheet_path.write_text(
        body + "\n\n---\n\n## Automatic checks\n\n```\n"
        + verdict.report() + "\n```\n",
        encoding="utf-8",
    )

    # What actually gets pasted. Written here rather than left as a step to
    # remember, because the draft is Markdown and the feed renders none of it:
    # a post published from the draft arrives with its hashes and asterisks
    # showing, which is the clearest possible sign of pasted generated text.
    post_path = stem / f"{event.ems_code}_post.txt"
    post_path.write_text(to_plain_text(body), encoding="utf-8")

    maps = []
    if verdict.tier > 0 or result.get("source") == "ems":
        maps = draw_maps(result, stem, verdict, official, clock, record)
    map_path = maps[0] if maps else None

    numbers = {k: v for k, v in result.items()
               if isinstance(v, (int, float, str))}
    numbers["tier"] = verdict.tier
    numbers["findings"] = [str(f) for f in verdict.findings]
    facts_path = stem / f"{event.ems_code}_figures.json"
    facts_path.write_text(json.dumps(numbers, indent=2), encoding="utf-8")

    return {
        "map": map_path,
        "maps": maps,
        "draft": sheet_path,
        "post": post_path,
        "figures": facts_path,
        "verdict": verdict,
        # Slots left for a human **in the text that was written**, not in the
        # whole fact sheet: most of its fields belong to other post types and
        # counting them made every draft look unfinished.
        "to_write": body.count("[TO WRITE]"),
        "result": result,
    }


def draw_overview(result: dict, path: Path, ordered: list, ems: dict | None = None,
                  verdict=None, clock: dict | None = None):
    """Where the mapped areas are, and how far apart, on one sheet.

    The first card of the carousel. Every sheet after it is a valley at 1 km
    across, and without this one a reader has no way to know that Timure and
    Bidur are forty kilometres apart on the same river.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    import ee

    if len(ordered) < 2:
        return None

    event = result["event"]
    activation = result["activation"]
    profile = result["profile"]
    crs = profile["crs"]

    bounds = activation["union"].bounds
    target = rasterio.warp.transform_bounds("EPSG:4326", crs, *bounds)
    extent = carto.frame_extent(target, carto.PORTRAIT, fill=1.0)
    lon0, lat0, lon1, lat1 = rasterio.warp.transform_bounds(
        crs, "EPSG:4326", *extent)

    page = {"crs": crs,
            "transform": rasterio.transform.from_bounds(*extent, 1080, 1350),
            "resolution": (extent[2] - extent[0]) / 1080}
    dem_scale = int(min(90, max(30, page["resolution"])))
    dem = natcat._ee_to_grid(
        ee.ImageCollection("projects/sat-io/open-datasets/FABDEM")
        .mosaic().select("b1"), (lon0, lat0, lon1, lat1), page, (1350, 1080),
        scale=dem_scale)
    dem = _smooth_dem(dem, dem_scale, page["resolution"])

    with open(CACHE / "world_outline.pkl", "rb") as handle:
        silhouette = pickle.load(handle)

    carto.apply()
    fig = carto.canvas(carto.PORTRAIT)
    ax = fig.add_axes([0, 0, 1, 1], zorder=0)
    backdrop = carto.draw_basemap(ax, dem,
                                  extent=(extent[0], extent[2],
                                          extent[1], extent[3]))
    ax.set_xlim(extent[0], extent[2])
    ax.set_ylim(extent[1], extent[3])
    ax.axis("off")

    for index, area in enumerate(ordered, start=1):
        drawn = rasterio.warp.transform_geom("EPSG:4326", crs,
                                             mapping(area["geometry"]))
        parts = (drawn["coordinates"] if drawn["type"] == "MultiPolygon"
                 else [drawn["coordinates"]])
        for polygon in parts:
            ring = np.array(polygon[0])
            ax.plot(ring[:, 0], ring[:, 1], color=carto.STUDY_AREA, lw=2.4,
                    zorder=carto.LAYER_ORDER["study_area"])
        centre = area["geometry"].centroid
        point = rasterio.warp.transform("EPSG:4326", crs, [centre.x], [centre.y])
        x, y = point[0][0], point[1][0]
        # Flip the label to the left of its dot near the right margin, or it
        # runs off the sheet, which is where "1. Syapru Be" came from.
        width = extent[2] - extent[0]
        left_side = (extent[2] - x) < width * 0.22
        carto.place_label(ax, x, y, f"{index}. {area['name']}", kind="city",
                          offset=-width * 0.010 if left_side else width * 0.010,
                          align="right" if left_side else "left")

    carto.fade(fig)

    # The totals for the whole event. Without them this sheet was a picture of
    # four rectangles: it said where, and nothing about what happened there.
    # It opens the carousel, so it is the one page a reader may see alone.
    grades = (ems or {}).get("building_grades") or {}
    if grades.get("Destroyed") and (ems or {}).get("buildings"):
        cards = []
        # Where the areas, their labels and the fixed furniture are, so the
        # solver puts each bubble on the emptiest ground left rather than on
        # a place name. Four cards no longer fit down one margin, which is
        # what the hard-coded pair here used to do.
        share = grades["Destroyed"] / ems["buildings"]
        cards.append((carto.BUBBLE_PRIMARY_R,
                      (f"{share * 100:.0f}%", "Buildings destroyed",
                       f"{_thousands(grades['Destroyed'])} of "
                       f"{_thousands(ems['buildings'])} graded by EMS")))

        tier = getattr(verdict, "tier", None)
        if tier == 1 and result.get("loss_low_usd") is not None:
            cards.append((carto.BUBBLE_SECONDARY_R,
                          (f"{_money(result['loss_low_usd'])} to "
                           f"{_money(result['loss_high_usd'])}", "Modelled loss",
                           f"{_money(result['exposed_usd'])} exposed")))
        else:
            cards.append((carto.BUBBLE_SECONDARY_R,
                          (f"{ems['observed_km2']:.1f} km²", "Flooded surface",
                           f"across {len(ordered)} mapped areas")))

        # People and lifelines. The two figures a reader asks for after the
        # count and the cost, and the ones the per-area sheets have no room
        # for: population is a whole-event number and a severed road matters
        # for the valley behind it, not for the frame it happens to cross.
        people = result.get("affected_population")
        if people:
            cards.append((carto.BUBBLE_TERTIARY_R,
                          (_thousands(people), "People in the mapped area",
                           "GHSL population grid, 2020")))

        road_km = ems.get("roads_destroyed_km") or 0.0
        if road_km:
            bridges = ems.get("bridges_destroyed") or 0
            note = (f"including {bridges} bridge{'s' if bridges != 1 else ''}"
                    if bridges else
                    f"of {ems['roads_km']:.0f} km graded")
            cards.append((carto.BUBBLE_TERTIARY_R,
                          (f"{road_km:.0f} km", "Road destroyed", note)))

        reserved = [
            (carto.LOCATOR_XY, carto.LOCATOR_SIZE),
            ((0.0, 0.0), (1.0, carto.CANVAS["bottom"] + 0.02)),
            ((0.0, carto.CANVAS["top"] - 0.02), (1.0, 0.30)),
        ]
        occupancy = _overview_occupancy(ordered, extent, crs, reserved)
        spots = carto.place_boxes(occupancy,
                                  [carto.circle_slot(r) for r, _ in cards])

        for (radius, texts), spot in zip(cards, spots):
            carto.bubble(fig, backdrop, carto.slot_centre(spot, radius),
                         radius, *texts, peril=event.peril)

        # Last, and only into what is genuinely left over: the relief's own
        # annotation, which explains why the flood behaved as it did without
        # taking room from anything that carries a figure.
        _spot_heights(ax, dem, extent, occupancy,
                      [(x, y) + carto.circle_slot(r)
                       for (r, _), (x, y) in zip(cards, spots)])

    # The same furniture the per-area sheets carry. A locator without a scale
    # is the one map where a reader genuinely cannot tell forty kilometres
    # from four hundred.
    byline_top = 0.128
    byline_h = carto.TYPE["byline"] / 72 * carto.DPI / carto.PORTRAIT[1]
    carto.byline_furniture(fig, ax, bottom=byline_top - byline_h)

    # The event's own clock on the overview, and the product date on each area
    # sheet: this page is about when it happened, those are about when it was
    # seen.
    # The same world locator the area sheets carry. Without it a reader who
    # opens the carousel on this card has a valley and no continent.
    centre = ((activation["bounds"][0] + activation["bounds"][2]) / 2,
              (activation["bounds"][1] + activation["bounds"][3]) / 2)
    carto.locator(fig, centre, silhouette, xy=carto.LOCATOR_XY,
                  borders=_country_borders(centre))

    # Two lines, so the subtitle stops short of the locator instead of running
    # under it.
    subtitle = (f"{_event_time(result)}\n"
                f"{len(ordered)} areas mapped by Copernicus EMS "
                f"{event.ems_code}")
    carto.header(fig, f"{event.region}, {event.country}", subtitle,
                 peril=event.peril)
    carto.footer(
        fig,
        "Sources: Copernicus EMS Rapid Mapping · FABDEM · "
        "Administrative boundaries: FAO GAUL",
        byline="Ilyas Hammouti",
        notes="Numbered in the order the areas were imaged and graded. "
              "Building values come from an aggregated national capital "
              "dataset, which covers more than buildings alone, so the loss "
              "is more likely high than low.",
        disclaimer="Damage counts by Copernicus EMS. The loss is modelled "
                   "here from those counts and is not an official assessment.")

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=carto.THEME["background"])
    plt.close(fig)
    return path


def draw_maps(result: dict, stem: Path, verdict=None,
              official: dict | None = None, clock: dict | None = None,
              record: dict | None = None) -> list:
    """One sheet per mapped area, in the order the responders worked.

    A carousel rather than a single sheet, because an activation covering four
    valleys sixty kilometres apart has no scale at which one page shows both
    the extent of the event and the width of a river.

    The order is chronological on the imagery each area was mapped from, which
    is also the order the products were delivered. It is the order the event
    was understood in, and it is the only ordering that means anything to a
    reader who was not there.
    """
    activation = result.get("activation") or {}
    areas = activation.get("aois") or []
    code = result["event"].ems_code

    # When each area's imagery was taken, from the activation clock. Areas
    # with no product yet sort last rather than being dropped: they are part
    # of the event, they are simply not mapped yet.
    when = {}
    for product in (clock or {}).get("products", []):
        acquired = [a for a in product.get("acquired") or [] if a]
        if acquired:
            when.setdefault(product["aoi"], min(acquired))

    if len(areas) <= 1:
        return [draw_map(result, stem / f"{code}_map.png", verdict=verdict,
                         ems=official)]

    from datetime import datetime as _dt

    ordered = sorted(areas, key=lambda a: when.get(a["name"], _dt.max))

    # The overview numbers every area in this order, delivered or not. The
    # sheets have to carry the same numbers, so they are taken from here
    # rather than from a counter over the sheets that actually get drawn:
    # those skip the undelivered areas and would renumber everything after
    # the first gap.
    numbers = {a["name"]: i for i, a in enumerate(ordered, start=1)}

    # Counts for the area on the sheet, not for the activation. A page headed
    # Syapru Besi carrying the whole event's 2 521 destroyed buildings invites
    # exactly the misreading the source labels exist to prevent.
    # The caller already holds the activation record. Re-fetching it here
    # meant a second call to the dashboard for something already in memory,
    # and a run that had computed everything died on it when the network
    # dropped for a moment.
    layers = ems.vectors(code, record) if official else {}

    profile = result.get("profile")
    detected = result.get("detected")
    pixel_km2 = profile["resolution"] ** 2 / 1e6 if profile else 0.0

    paths = []
    index = 0
    for area in ordered:
        local = (ems.damage_summary(layers, area=area["name"])
                 if layers else None)
        if local and not local.get("observed"):
            local = None            # nothing mapped here yet

        here = 0.0
        if profile is not None and detected is not None:
            mask = _rasterise([area["geometry"]], profile, detected.shape)
            here = float((detected & mask).sum() * pixel_km2)

        # An area with no product and nothing detected has nothing on it. A
        # sheet showing two zeros is not a publication, and saying so in the
        # text is more honest than drawing an empty page.
        if local is None and here <= 0.0:
            continue

        index += 1
        name = re.sub(r"[^a-z0-9]+", "-", area["name"].lower()).strip("-")
        here_features = {layer: [f for f in feats if f["aoi"] == area["name"]]
                         for layer, feats in layers.items()} if layers else None
        delivered = next((p["delivered"] for p in (clock or {}).get("products", [])
                          if p["aoi"] == area["name"] and p.get("delivered")),
                         None)
        paths.append(draw_map(
            result, stem / f"{code}_{index:02d}_{name}.png",
            verdict=verdict, ems=local, area=area, features=here_features,
            published=delivered, number=numbers.get(area["name"]),
            # Fill the canvas box the layout defines: a small lateral
            # margin, under the title, above the byline. `frame_extent`
            # already solves for that box, so 0.98 puts the outline against
            # its edges without stretching the map.
            fill_share=0.98))

    # The carousel opens on where these places are. Three narrow valleys
    # forty kilometres apart mean nothing to a reader who has not been told
    # they are the same river.
    overview = draw_overview(result, stem / f"{code}_00_sites.png", ordered,
                             ems=official, verdict=verdict, clock=clock)
    return [overview] + paths if overview else paths


# ---------------------------------------------------------------------------
# Weekly digest, post type 1
#
# The one format that carries no loss figure, so nothing in it can be wrong
# about money. It is assembled here rather than in the notebook because the
# notebook produces facts and this file produces posts.
# ---------------------------------------------------------------------------

DIGEST_TEMPLATE = "01-weekly-digest.md"
DIGEST_MAX_BULLETS = 8          # rules section 3, bullets per list

MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")


def _prose_date(day) -> str:
    """`26 August 2026`, the date format the rules fix for prose."""
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"


def _two_sig(number: float) -> str:
    """Round to two significant figures and group the thousands.

    Rules section 6: areas carry two significant figures. GDACS reports an
    agricultural drought over `1487749 km2`, a precision nothing about the
    measurement supports.
    """
    if number == 0:
        return "0"
    from math import floor, log10

    magnitude = floor(log10(abs(number)))
    rounded = round(number, -(magnitude - 1))
    return f"{int(rounded):,}"


def _tidy_units(text: str) -> str:
    """Put the feed's own wording into the units and precision of the rules.

    Three things are corrected and nothing else, so the clause stays the
    feed's claim rather than becoming ours: the alert level is stripped where
    the feed repeats it inside the sentence (it already stands on the same
    line), `forestfire` is spelled as two words, and areas are cut to two
    significant figures.
    """
    text = re.sub(r"^(Orange|Red|Green|Extreme|High|Medium|Low)\s+impact\s+for\s+",
                  "", text, flags=re.IGNORECASE)
    text = text.replace("forestfire", "forest fire")
    text = re.sub(r"\bin\s+(\d[\d\s]*(?:ha|km2))\b", r"over \1", text)
    text = re.sub(r"(\d+)\s*(ha|km2)\b",
                  lambda m: f"{_two_sig(float(m.group(1)))} {m.group(2)}", text)
    text = re.sub(r"\s*\(maximum wind speed of ([^)]+)\)",
                  r", maximum wind speed \1", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" .,")
    return text[:1].upper() + text[1:] if text else text


def _digest_fact(event: dict) -> str:
    """One factual clause from the feed, or nothing at all.

    GDACS carries no magnitude for a flood and returns the literal string
    `Magnitude 0`. Publishing that is publishing a fabricated value (H11), so
    an empty clause is the correct output and the bullet simply ends earlier.
    """
    text = (event.get("severity_text") or "").strip()
    if not text or re.fullmatch(r"Magnitude\s*0\.?0?\s*", text):
        return ""

    # Earthquakes are rebuilt from the structured fields. `Magnitude 5M` reads
    # as five million; the unit belongs to the scale, not to the number.
    if event["event_type"] == "EQ":
        clause = f"Magnitude {float(event['severity']):.1f}"
        depth = re.search(r"Depth:\s*(\d+)\s*km", text)
        return f"{clause}, depth {depth.group(1)} km" if depth else clause

    return _tidy_units(text)


def _digest_country(name: str) -> str:
    """Countries as a readable clause.

    The GDACS drought entries list every country the polygon touches, up to 27
    of them, and the field ends in a stray comma. A 27-name list would take a
    third of the post's word budget.
    """
    names = [part.strip() for part in (name or "").split(",") if part.strip()]
    if len(names) <= 3:
        return ", ".join(names)
    return f"{names[0]}, {names[1]} and {len(names) - 2} other countries"


def _digest_place(event: dict, regions: dict) -> str:
    """Where it happened, as precisely as the source actually supports.

    A region is added only for the perils whose reported point is the event
    itself. The feed offers no location below that level: GAUL's second
    administrative level comes back as `Name Unknown` too often to publish,
    and for a flood the point is a basin centroid that can sit a hundred
    kilometres from the damage.
    """
    country = _digest_country(event["country"])
    region = regions.get(event["event_id"])
    return f"{region}, {country}" if region else country


def _digest_row(event: dict, regions: dict) -> str:
    """The figure's location cell, carrying the event's name where it has one.

    The table groups by peril, so the heading above the row already says
    VOLCANO and the name has nowhere else to go: the cell read "Lampung,
    Indonesia" and Krakatau appeared nowhere on the sheet. The text names it
    through `_digest_peril`, which the figure does not use.
    """
    place = _digest_place(event, regions)
    name = _event_name(event)
    return f"{name}, {place}" if name else place


def _digest_dates(event: dict) -> str:
    """The start date, and never an end date.

    GDACS `to_date` advances with the data rather than with the event. Checked
    on the Madagascar drought: `todate` moved from 26 to 27 August between two
    pulls a day apart, `datemodified` was that same morning, and `iscurrent`
    was nonetheless false. It is the last day of data, not the day the drought
    stopped, and printing it as the second half of a range asserts an end
    nobody has declared (H14).

    An event with identical start and end is instantaneous, an earthquake
    among them, and prints as a single date.
    """
    start, finish = event["from_date"].date(), event["to_date"].date()
    if start == finish:
        return _prose_date(start)
    return f"since {_prose_date(start)}"


def _red_statement(reds: list) -> str:
    """A week with no Red alert is a fact about the week, so it is printed.

    The count carries its noun: "1 reached Red." leaves the reader to guess
    what was counted, and the sentence sits directly under two other counts.
    """
    if not reds:
        return "No event reached Red."
    return f"{len(reds)} event{'s' if len(reds) != 1 else ''} reached Red."


def _date_span(start, finish) -> str:
    """`24 to 30 August 2026`, contracted only when the month is shared."""
    if start == finish:
        return _prose_date(start)
    if (start.month, start.year) == (finish.month, finish.year):
        return f"{start.day} to {_prose_date(finish)}"
    return f"{_prose_date(start)} to {_prose_date(finish)}"


# Perils GDACS gives a real name to. It fills `eventname` for every peril, but
# for a drought the value is an alert identifier — `Madagascar-2026`,
# `Europe-2026` — which is a slug for the record, not the name of a thing. It
# printed as "Madagascar-2026, Madagascar" the first time it was published to
# the figure.
NAMED_PERILS = ("TC", "VO")


def _event_name(event: dict) -> str:
    """The event's own name, where GDACS publishes one worth printing."""
    if event["event_type"] not in NAMED_PERILS:
        return ""
    return (event.get("event_name") or "").strip()


def _digest_peril(event: dict) -> str:
    """Peril, carrying the name the feed gives the event.

    A named cyclone is how the insurance audience indexes the event, and a
    volcano without its name is a category rather than a place: Indonesia has
    127 of them, so "Volcano, Indonesia" tells a reader nothing they could
    look up. GDACS carries both in `eventname` and leaves it empty for the
    perils it does not name, which is floods and droughts.

    This used to read the cyclone name out of the title with a regular
    expression while the volcano name sat unused one field away. Checked on
    the same feed: `eventname` is `SAUDEL-26` for the cyclone and `Krakatau`
    for the volcano, so one field serves both.
    """
    peril = natcat.GDACS_PERILS.get(event["event_type"], event["event_type"])
    name = _event_name(event)
    return f"{peril} {name}" if name else peril


def _digest_line(event: dict, regions: dict | None = None) -> str:
    """A Green top-up can carry no country at all: an open-ocean cyclone GDACS
    tracks by lat/long alone, no coastline for `_digest_place` to name. Omit
    the place clause entirely rather than print the empty string and leave a
    bare double comma behind.
    """
    place = _digest_place(event, regions or {})
    place_clause = f"{place}, " if place else ""
    line = (f"- {_digest_peril(event)}, "
            f"{place_clause}"
            f"{_digest_dates(event)}. Alert {event['alert_level']}.")
    fact = _digest_fact(event)
    return f"{line} {fact}." if fact else line


def _filter_unfeatured(events: list, history: dict) -> list:
    """Events still eligible to be headlined or listed by name this week.

    A Red alert is always eligible, however long it has run or however many
    times it has already been shown: rules section 5, a Red alert is never
    hidden. Anything else drops out once its `event_id` has appeared, by
    name, in a previously published digest.
    """
    return [e for e in events
            if e["alert_level"] == "Red" or str(e["event_id"]) not in history]


def _eligible_history(history: dict, monday) -> dict:
    """`history`, minus this function's own picks from an earlier same-day
    run for this same `monday`.

    A same-day re-run (this project's own testing already did this more
    than once) must not see its own earlier run's picks as "prior weeks
    already covered" - otherwise a re-run behaves as if those events had
    been featured in some real past week, and they stay suppressed forever.
    Only entries this function itself wrote, tagged with
    `generated_for_monday`, are excluded here; a manually-seeded real entry
    has no such tag, so date equality with `monday` alone can never be
    mistaken for "this run wrote it" - which is what let a manually-seeded
    entry whose `first_shown` happened to equal `monday` get wrongly
    un-suppressed.
    """
    return {k: v for k, v in history.items()
            if v.get("generated_for_monday") != str(monday)}


def _pick_headline(new: list, continuing: list, green_topups: list,
                    history: dict) -> dict | None:
    """The week's headline, in priority order: new, Red, this week's Green
    top-up, then whatever else is still running.

    `continuing` is the raw, unfiltered list. Without this function, the
    only thing keeping an old continuing event from resurfacing was chance
    of it also being the one with the most recent start date among a thin
    set - that is exactly how a month-old flood ended up "Most recent" two
    weeks running. Red and the Green top-ups are checked first, and a
    suppressed continuing event is skipped as long as anything else is
    available; it is used only as the very last resort, so a quiet week
    with nothing else in the world never publishes an empty headline line.
    """
    reds = [e for e in continuing if e["alert_level"] == "Red"]
    eligible_continuing = _filter_unfeatured(continuing, history)
    for group in (new, reds, green_topups, eligible_continuing, continuing):
        if group:
            return group[0]
    return None


def _digest_selection(ordered: list, max_bullets: int) -> tuple:
    """Split the week into what the text lists and what only the figure holds.

    Listed: what entered the week, and whatever reached Red however long it
    has been running. A Red alert is the one thing worth a sentence even on
    an event the reader has seen before, because the level is what changed.

    Everything else is a row in the figure's table. A drought open since last
    November does not need a bullet repeating a line the reader can see.

    A Green top-up is always listed regardless of `is_new` - it was chosen
    specifically to represent its risk type this week, and silently folding it
    into the figure instead would defeat the reason it was picked.
    """
    listed = [e for e in ordered
              if e["is_new"] or e["alert_level"] == "Red"
              or e.get("green_topup")][:max_bullets]
    shown = {e["event_id"] for e in listed}
    return listed, [e for e in ordered if e["event_id"] not in shown]


def _digest_remainder(rest: list) -> str:
    """One sentence for the events the figure carries and the text does not.

    The bullets and the figure used to hold the same eight lines, so half the
    post was a caption for the image beside it. The figure keeps the full week
    because a table is what it is good at; the text keeps what entered the
    week and what reached Red, and accounts for the rest here rather than
    letting the reader wonder whether the list was cut.
    """
    if not rest:
        return ""

    counts = {}
    for event in rest:
        peril = natcat.GDACS_PERILS.get(event["event_type"], event["event_type"])
        counts[peril.lower()] = counts.get(peril.lower(), 0) + 1

    parts = [f"{n} {peril}{'s' if n > 1 else ''}"
             for peril, n in sorted(counts.items(), key=lambda kv: -kv[1])]
    listed = (parts[0] if len(parts) == 1
              else ", ".join(parts[:-1]) + " and " + parts[-1])
    oldest = min(e["from_date"] for e in rest).date()

    return (f"The figure carries {len(rest)} more, every one of them already "
            f"running when the week opened: {listed}. The oldest has been "
            f"open since {_prose_date(oldest)}.")


def _headline_sentence(event: dict | None, regions: dict | None = None) -> str:
    """The most recent event, as one sentence.

    One sentence rather than three short declaratives, which would read as
    generated (A28).
    """
    if not event:
        return ""
    fact = _digest_fact(event)
    when = _digest_dates(event)
    when = when if when.startswith("since") else f"on {when}"
    clause = f", {fact[:1].lower()}{fact[1:]}" if fact else ""
    return (f"{_digest_peril(event)} in "
            f"{_digest_place(event, regions or {})} "
            f"{when}{clause}, at GDACS alert level {event['alert_level']}.")


def _digest_pending(cases: list, locked: dict) -> str:
    """One entry per pending event, each carrying L-PASS verbatim.

    The locked string is filled here rather than by `fill_template`, because a
    single global substitution cannot give two events two different pass
    dates. Entries with no measurable revisit cycle are dropped: L-PASS quotes
    a cycle, and there is no honest way to write it without one.
    """
    lines = []
    for case in cases:
        peril = natcat.GDACS_PERILS.get(case["event"]["event_type"], "Event")
        where = f"{peril}, {_digest_country(case['event']['country'])}. "

        if case.get("state") == "awaiting_product" and case.get("last_pass"):
            lines.append(where + locked["L-AWAITING-PRODUCT"].replace(
                "{{LAST_PASS}}", _prose_date(case["last_pass"])))
            continue

        if not case.get("next_pass") or not case.get("cycle_days"):
            continue
        lines.append(where + locked["L-PASS"]
                     .replace("{{PASS_DATE}}", _prose_date(case["next_pass"]))
                     .replace("{{REVISIT_DAYS}}", str(case["cycle_days"])))
    return "\n\n".join(lines)


def _drop_empty_sections(text: str) -> str:
    """Remove a heading whose section has no content.

    Rules section 2: a block with nothing to say is omitted entirely, never
    filled with a sentence saying it is empty.
    """
    return re.sub(r"^##[^\n]*\n\s*(?=(##|---|\Z))", "", text, flags=re.MULTILINE)


def _load_featured_history(path: Path = FEATURED_HISTORY_PATH) -> dict:
    """`event_id` (string) -> `{"first_shown": iso date, "name": ...}`.

    Empty when the file does not exist yet - the first run after this
    feature ships starts with nothing suppressed, which is why Task 4 seeds
    it once by hand for the events already published by name.
    """
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_featured_history(history: dict,
                           path: Path = FEATURED_HISTORY_PATH) -> None:
    """Persist the full history dict, creating the cache folder if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2, sort_keys=True),
                    encoding="utf-8")


def weekly_digest(monday=None, alert_levels: tuple = ("Orange", "Red"),
                  max_bullets: int = DIGEST_MAX_BULLETS,
                  write: bool = True) -> dict:
    """Build the Monday digest for the week that just ended.

    `monday` is the publication date. The window is the seven days before it,
    so a digest published on Monday 31 August covers 24 to 30 August. Passing
    an earlier Monday rebuilds that week exactly as it stood, provided GDACS
    still serves it.
    """
    from datetime import date, datetime, timedelta, timezone

    monday = monday or datetime.now(timezone.utc).date()
    if isinstance(monday, str):
        monday = date.fromisoformat(monday)
    week_end = monday - timedelta(days=1)
    week_start = monday - timedelta(days=7)

    events = natcat.gdacs_events(days=7, alert_levels=alert_levels, end=week_end)
    cases = natcat.pending_cases(events, end=week_end)

    new = [e for e in events if e["is_new"]]
    continuing = [e for e in events if not e["is_new"]]

    # A risk type gets a Green top-up only when nothing of its own is
    # eligible at Orange/Red this week - "eligible" excludes whatever has
    # already been shown by name in a previous digest, Red alerts excepted.
    history = _load_featured_history()
    # See `_eligible_history`: excludes only this function's own picks from
    # an earlier same-day run for this same `monday`. The full `history` -
    # untouched - is still what gets merged and saved at the end, so real
    # prior weeks (and manually-seeded entries) stay suppressed.
    eligible_history = _eligible_history(history, monday)
    covered_types = {e["event_type"]
                     for e in _filter_unfeatured(events, eligible_history)}
    missing_types = [t for t in natcat.GDACS_TYPES if t not in covered_types]

    green_topups = []
    if missing_types:
        picks = natcat.top_green_per_type(missing_types, days=7, end=week_end,
                                          exclude_ids=set(eligible_history))
        green_topups = [{**e, "green_topup": True} for e in picks]
        # Most severe first, so a headline that falls through to the Green
        # top-ups (nothing new, nothing Red) picks the single most
        # significant one across every filled-in type, not just whichever
        # peril happens to sort first.
        green_topups.sort(key=lambda e: e.get("alert_score") or 0, reverse=True)

    # New events first, then the continuing ones (both raw - the figure and
    # the overflow sentence account for every event regardless of whether it
    # is eligible to be named), then this week's Green top-ups.
    ordered = new + continuing + green_topups

    listed, dropped = _digest_selection(ordered, max_bullets)

    headline = _pick_headline(new, continuing, green_topups, eligible_history)
    locked = locked_phrases()

    overflow = _digest_remainder(dropped)

    unknowns = []
    if any(c.get("state") == "awaiting_pass" for c in cases):
        unknowns.append("No post-event imagery covers the pending areas yet.")
    unknowns.append(
        "GDACS reports events of international significance, so a storm "
        "damaging a single department or county appears in no line above."
    )
    if continuing:
        unknowns.append(
            "None of the running events has a published end date: the feed "
            "advances its last day of data, which is not the day the event "
            "stopped."
        )

    plural_new = "s" if len(new) != 1 else ""
    was_were = "were" if len(continuing) != 1 else "was"

    # Region names, where the reported point is the event itself. Green
    # top-ups are included: they are exactly the EQ/WF/VO events this was
    # built to name a region for, and `events` alone is the raw Orange/Red
    # pull that mostly does not include them. Fails soft: the digest
    # otherwise runs on plain HTTP and losing a region name is not a reason
    # to lose the week's post.
    regions = natcat.event_regions(events + green_topups)

    reds = [e for e in events if e["alert_level"] == "Red"]

    # GDACS's own hard cap (see `gdacs_events`'s docstring) means a Green-level
    # query is a truncated sample, not the full week: the pick is the most
    # severe *of what came back*, not provably the most severe Green event of
    # the week, so the note must not claim the superlative (H9). Counted
    # against `listed`, not `green_topups`, because the bullet cap can cut a
    # top-up before it reaches the reader.
    shown_green = [e for e in listed if e.get("green_topup")]

    values = {
        "WEEK_START": _prose_date(week_start),
        "WEEK_END": _prose_date(week_end),
        "ALERT_FILTER": " or ".join(alert_levels),
        "NEW_COUNT": f"{len(new)} event{plural_new}",
        "CONTINUING_COUNT": f"{len(continuing)} {was_were}",
        "RED_STATEMENT": _red_statement(reds),
        "GREEN_NOTE": (
            f" The list also carries a Green-level event "
            f"for {len(shown_green)} risk type"
            f"{'s' if len(shown_green) != 1 else ''} with nothing more "
            f"severe this week."
        ) if shown_green else "",
        "DIGEST_TITLE": (f"Weekly natural catastrophe report, "
                         f"{_date_span(week_start, week_end)}"),
        "HEADLINE_LINE": _headline_sentence(headline, regions),
        "EVENT_LINES": "\n".join(_digest_line(e, regions) for e in listed),
        "EVENT_OVERFLOW": overflow,
        "PENDING_LINES": _digest_pending(cases, locked),
        "UNKNOWNS": " ".join(unknowns),
        "SENTINEL_CREDIT": (locked["L-SRC-SENTINEL"].replace(
            "{{YEAR}}", str(week_end.year)) if cases else ""),
        "PASS_METHOD": ("Satellite pass dates are estimated from the observed "
                        "Sentinel-1 revisit cycle over each area."
                        if cases else ""),
        "YEAR": str(week_end.year),
        # Two, the maximum rules section 3 allows, and fixed rather than
        # generated: they name the format and the discipline, which do not
        # change from week to week. A tag derived from the week's perils
        # would move every Monday and index nothing.
        "HASHTAGS": "#natcat #catastrophemodelling",
    }

    body = _drop_empty_sections(fill_template(DIGEST_TEMPLATE, values))
    plain = to_plain_text(body)

    paths = {}
    if write:
        folder = OUTPUT / "digests"
        folder.mkdir(parents=True, exist_ok=True)
        paths["draft_path"] = folder / f"{monday}-digest.md"
        paths["plain_path"] = folder / f"{monday}-digest.txt"
        paths["draft_path"].write_text(body, encoding="utf-8")
        paths["plain_path"].write_text(plain, encoding="utf-8")

        shown = listed + ([headline] if headline else [])
        # Only ids never before in the full (unfiltered) history: an id
        # already there — a Red alert shown again, or a same-day re-run's
        # own earlier pick — keeps its original `first_shown` rather than
        # having it quietly overwritten to today's date.
        newly_featured = {
            str(e["event_id"]): {"first_shown": str(monday), "name": e["name"],
                                 "generated_for_monday": str(monday)}
            for e in shown if str(e["event_id"]) not in history
        }
        if newly_featured:
            _save_featured_history({**history, **newly_featured})

    digest = {
        "monday": monday,
        "window": (week_start, week_end),
        # Green top-ups included: `digest_figure`'s own contract is every
        # event of the week, including the ones the text's bullet cap kept
        # out, and on a quiet week the top-ups are most of what the text
        # actually names.
        "events": events + green_topups,
        "listed": listed,
        "dropped": dropped,
        "pending": cases,
        "regions": regions,
        "title": values["DIGEST_TITLE"],
        "reds": reds,
        "body": body,
        "plain": plain,
        "words": len(plain.split()),
        **paths,
    }

    if write:
        # The figure carries the title, the dates and every event, including
        # the ones the eight-bullet cap kept out of the text.
        digest["figure_path"] = digest_figure(
            digest, OUTPUT / "digests" / f"{monday}-digest.png")

    return digest


# ---------------------------------------------------------------------------
# Plain text, rules section 3.1
# ---------------------------------------------------------------------------

def to_plain_text(markdown: str, drop_title: bool = False) -> str:
    """Convert a draft to what actually gets pasted into the feed.

    LinkedIn renders no Markdown. Hashes, asterisks and backticks appear
    literally and are the clearest possible signal that the text was pasted
    out of a generator. The conversion follows the table in section 3.1.

    `drop_title` removes the level 1 heading. There is no title field in a
    LinkedIn post, so a title occupies the 140-character preview with a label
    rather than with an event. The digest passes it and prints the title on
    the figure instead.
    """
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\2", markdown)
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"^\s*---\s*$", "", text, flags=re.MULTILINE)

    blocks = re.split(r"^(#{1,6} +.*)$", text, flags=re.MULTILINE)
    out, heading, level = [], None, 0
    for chunk in blocks:
        if re.match(r"^#{1,6} +", chunk or ""):
            level = len(chunk) - len(chunk.lstrip("#"))
            heading = re.sub(r"^#{1,6} +", "", chunk).strip()
            continue
        section = _unwrap(chunk or "")
        if heading is not None:
            # Below the title, a heading over two sentences of prose is noise:
            # the section is shorter than its own label. Lists keep theirs.
            sentences = len(re.findall(r"[.!?](?:\s|$)", section))
            if level == 1:
                keep = not drop_title
            else:
                keep = bool(section) and (sentences > 2
                                          or section.lstrip().startswith("-"))
            if keep:
                out.append(heading)
            heading = None
        if section:
            out.append(section)

    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(out)).strip() + "\n"


def _unwrap(text: str) -> str:
    """Undo the template's line wrapping.

    The templates are wrapped at 79 characters because they are source files.
    Those line breaks are real in a LinkedIn post, and they cut sentences in
    half. Bullets keep one line each; prose paragraphs become one line.
    """
    out = []
    for para in re.split(r"\n\s*\n", text.strip()):
        lines = [line.strip() for line in para.splitlines() if line.strip()]
        if not lines:
            continue
        if any(line.startswith("- ") for line in lines):
            out.append("\n".join(lines))
        else:
            out.append(" ".join(lines))
    return "\n\n".join(out)


# ---------------------------------------------------------------------------
# The digest figure
#
# The post text is capped at eight bullets and about 320 words, so a week with
# twelve alerts loses four of them. A table has no such limit: the figure
# carries every event, grouped by peril, and it also carries the title and the
# dates, which is why the text no longer opens with a label.
# ---------------------------------------------------------------------------

DIGEST_PERIL_ORDER = ("Flood", "Tropical cyclone", "Earthquake", "Wildfire",
                      "Drought", "Volcano")

# Right edge of the alert column. Leaves room for the longest date clause a
# drought produces, `11 December 2025 to 26 August 2026`, right-aligned at the
# margin.
ALERT_COLUMN = 0.685


def _peril_key(name: str) -> str:
    """Map a GDACS peril name onto the identity's colour keys."""
    lowered = name.lower()
    if lowered.startswith("tropical"):
        return "storm"
    return lowered if lowered in carto.PERIL_COLOURS else "flood"


def digest_figure(digest: dict, path) -> "Path":
    """One graphic for the weekly digest: title, dates, every event.

    Deliberately a table and not a map. The week has no single geography, and
    a world map with twelve dots says less than twelve rows that each carry a
    place, a date, an alert level and what the feed measured.
    """
    import matplotlib.pyplot as plt

    carto.apply()
    fig = carto.canvas(carto.PORTRAIT)

    events = digest["events"]
    regions = digest.get("regions", {})
    peril_of = lambda e: natcat.GDACS_PERILS.get(e["event_type"], e["event_type"])

    groups = {}
    for event in events:
        groups.setdefault(peril_of(event), []).append(event)
    ordered = sorted(groups, key=lambda p: (DIGEST_PERIL_ORDER.index(p)
                                            if p in DIGEST_PERIL_ORDER else 99))

    top, bottom = carto.CANVAS["top"], carto.CANVAS["bottom"]
    left, right = carto.CANVAS["left"], carto.CANVAS["right"]

    # ---- Header, written here rather than through carto.header -------------
    # No peril icon: a weekly report covers six perils and one icon would name
    # the wrong one. The dates are set at title weight because the format is
    # the point of the graphic, and "Natural catastrophes" alone says neither
    # that it is weekly nor which week.
    start, end = digest["window"]
    carto.brand_mark(fig, xy=(right, 0.930))
    fig.text(left, 0.930, "WEEKLY REPORT", fontsize=carto.TYPE["brand"],
             fontweight="bold", color=carto.THEME["faint"], va="center",
             ha="left", zorder=6)
    fig.text(left, 0.905, "Natural catastrophes", fontsize=carto.TYPE["title"],
             fontweight="bold", color=carto.THEME["text"], va="top",
             ha="left", zorder=6)
    fig.text(left, 0.868, _date_span(start, end), fontsize=22,
             fontweight="bold", color=carto.THEME["faint"], va="top",
             ha="left", zorder=6)
    reds = len(digest.get("reds", []))
    # `events` now also carries this week's Green top-ups (finding 1): counted
    # separately here so the header keeps claiming only what is actually at
    # Orange or Red, never folding a Green pick into that count.
    orange_red_count = len([e for e in events if not e.get("green_topup")])
    fig.text(right, 0.872,
             f"{orange_red_count} events at GDACS Orange and Red · "
             + (f"{reds} at Red" if reds else "none at Red"),
             fontsize=carto.TYPE["caption"], color=carto.THEME["faint"],
             va="top", ha="right", zorder=6)

    # ---- Height budget, then the table centred in what is left -------------
    # The unit counts match exactly what the loop below draws: a peril heading
    # advances 1.05 rows, an event 1, a fact line 0.62. A mismatch here does
    # not overflow the page, it leaves the table hanging from the top with all
    # the slack piled underneath.
    facts = {id(e): _digest_fact(e) for e in events}
    units = (len(ordered) * 1.05
             + len(events)
             + sum(0.62 for e in events if facts[id(e)]))

    HEADING_ROW = 0.019          # space the column headings need above the table
    band_top, band_bottom = top - HEADING_ROW, bottom - 0.025
    step = min(0.034, (band_top - band_bottom) / max(units, 1))
    slack = max(0.0, (band_top - band_bottom) - units * step)

    y = band_top - slack / 2

    # ---- Column headings, sitting on the table wherever it ended up --------
    for x, label, align in ((left, "LOCATION", "left"),
                            (ALERT_COLUMN, "ALERT", "right"),
                            (right, "DATES", "right")):
        fig.text(x, y + HEADING_ROW, label, fontsize=carto.TYPE["credit"],
                 fontweight="bold", color=carto.THEME["faint"], va="top",
                 ha=align, zorder=6)

    for peril in ordered:
        colour = carto.PERIL_COLOURS[_peril_key(peril)]
        fig.text(left, y, peril.upper(), fontsize=carto.TYPE["legend"],
                 fontweight="bold", color=colour, va="top", ha="left",
                 zorder=6)
        fig.lines.append(plt.Line2D([left, right], [y - step * 0.58] * 2,
                                    transform=fig.transFigure,
                                    color=carto.THEME["rule"], lw=0.8,
                                    zorder=5))
        y -= step * 1.05

        for event in groups[peril]:
            fig.text(left, y, _digest_row(event, regions),
                     fontsize=carto.TYPE["place"], color=carto.THEME["text"],
                     va="top", ha="left", zorder=6)

            # Both columns are right-aligned and they do not share a boundary:
            # a drought range runs to thirty-odd characters and would sit on
            # top of a left-aligned alert level.
            alert = event["alert_level"]
            fig.text(ALERT_COLUMN, y, alert, fontsize=carto.TYPE["caption"],
                     fontweight="bold",
                     color=carto.ALERT_COLOURS.get(alert, carto.THEME["text"]),
                     va="top", ha="right", zorder=6)
            fig.text(right, y, _digest_dates(event),
                     fontsize=carto.TYPE["caption"], color=carto.THEME["faint"],
                     va="top", ha="right", zorder=6)
            y -= step

            fact = facts[id(event)]
            if fact:
                fig.text(left, y + step * 0.34, fact,
                         fontsize=carto.TYPE["credit"],
                         color=carto.THEME["faint"], va="top", ha="left",
                         zorder=6)
                y -= step * 0.62

    pending = digest["pending"]
    notes = ""
    if pending:
        first = pending[0]
        where = _digest_country(first["event"]["country"])
        if first.get("state") == "awaiting_product":
            notes = (f"{where}: imaged "
                     f"{_prose_date(first['last_pass'])}, no flood extent "
                     f"product published from that acquisition yet.")
        elif first.get("next_pass"):
            notes = (f"{where}: awaiting a satellite pass, next Sentinel-1 "
                     f"pass estimated {_prose_date(first['next_pass'])}.")

    sources = "Sources: GDACS (European Commission, United Nations)"
    if pending:
        sources += (" · Satellite pass dates measured from the Copernicus "
                    "Data Space catalogue, Sentinel-1")

    carto.footer(
        fig,
        sources,
        byline="Ilyas Hammouti",
        notes=notes,
        # Same locked sentence as the post body, read from the rules rather
        # than retyped, so the graphic and the text cannot drift apart.
        disclaimer=locked_phrases()["L-DISC-FEED"],
    )

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=carto.THEME["background"])
    plt.close(fig)
    return path
