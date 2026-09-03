"""Re-verify every claim this project makes about a live service.

`docs/DECISIONS.md` mixes two kinds of statement. Measurements — 63.5 % of
built-up area inside the exclusion mask, 59 % of the ground above 20 degrees —
stay true. Statements about the state of a catalogue do not: "No Landsat 8 or
9 scenes at all" was written about Rasuwa and was wrong, and the ReliefWeb API
this project nearly adopted answers 410 Gone.

So the catalogue claims come out of the document and become the output of this
script. Run it before trusting anything in the documentation that begins with
"there is" or "there is no".

    conda run -n climada_env python check_sources.py

Every check prints what it measured, not just whether it passed, because a
service that answers but answers something stale is the failure mode that
matters.
"""

from __future__ import annotations

import json
import sys
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

AGENT = {"User-Agent": "natcat"}
RESULTS = []


def check(name):
    """Register a check. It returns a message, or raises to fail."""
    def wrap(function):
        RESULTS.append((name, function))
        return function
    return wrap


def _get(url, timeout=60, body=None):
    request = urllib.request.Request(
        url, data=json.dumps(body).encode() if body else None,
        headers={**AGENT, **({"Content-Type": "application/json"} if body else {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw) if raw else None


@check("GDACS event feed")
def _gdacs():
    payload = _get("https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
                   "?eventlist=FL&alertlevel=Orange;Red"
                   "&fromdate=2026-08-01&todate=2026-08-30")
    n = len((payload or {}).get("features", []))
    assert n, "no features returned"
    return f"{n} flood events in a one-month window (hard cap is 100)"


@check("Copernicus GFM catalogue, EODC STAC")
def _gfm():
    payload = _get("https://stac.eodc.eu/api/v1/search", body={
        "collections": ["GFM"], "bbox": [11.3, 44.0, 12.5, 44.6],
        "datetime": "2023-05-17T00:00:00Z/2023-05-20T00:00:00Z", "limit": 3})
    n = len((payload or {}).get("features", []))
    assert n, "GFM returned nothing for the reference case"
    return f"{n} scenes for the EMSR664 reference window, no account needed"


@check("Copernicus EMS dashboard")
def _ems_api():
    import ems

    known = ems.activation("EMSR927")
    assert known, "EMSR927 no longer resolves"
    clock = ems.timings(known)
    return (f"EMSR927 reads; activation at "
            f"+{clock['activation_hours']:.0f} h, first product at "
            f"+{clock['first_product_hours']:.0f} h")


@check("EMS activation discovery by walking the code")
def _ems_walk():
    import ems

    # The mechanism the whole early calendar depends on: an unissued code must
    # refuse, or discovery would run forever and invent activations.
    assert ems.activation("EMSR999") is None, "an unissued code now answers"
    return "an unissued code refuses, so counting forward terminates"


@check("ESA acquisition plans are current")
def _plans():
    import plan

    files = plan.plan_files("sentinel-1") + plan.plan_files("sentinel-2")
    assert files, "no plan files listed"
    latest = max(f["end"] for f in files)
    ahead = (latest - datetime.now(timezone.utc).replace(tzinfo=None)).days
    assert ahead > 0, f"every published plan ended {-ahead} days ago"
    fresh = [f for f in files if f["end"] > datetime.now(timezone.utc).replace(tzinfo=None)]
    return (f"{len(fresh)} satellites planned to {latest:%Y-%m-%d}, "
            f"{ahead} days ahead")


@check("STAC catalogues carry the newest scenes")
def _stac():
    import catalog

    recent = catalog.scenes((85.30, 28.13, 85.40, 28.30),
                            (datetime.now(timezone.utc) - timedelta(days=20))
                            .date().isoformat(),
                            datetime.now(timezone.utc).date().isoformat())
    assert recent, "no scenes at all in the last 20 days"
    sensors = sorted({s["sensor"] for s in recent})
    newest = max(s["when"] for s in recent if s["when"])
    lag = (datetime.now(timezone.utc) - newest).total_seconds() / 3600
    return (f"{len(recent)} scenes, sensors {sensors}, newest "
            f"{lag:.0f} h old")


@check("Landsat is reachable, the claim that was wrong")
def _landsat():
    import catalog

    scenes = catalog.scenes((85.30, 28.13, 85.40, 28.30),
                            "2026-08-20", "2026-09-01", sensors=("landsat",))
    assert scenes, "no Landsat scenes, which is what DECISIONS.md once claimed"
    clearest = min((s for s in scenes if s["cloud"] is not None),
                   key=lambda s: s["cloud"])
    return (f"{len(scenes)} Landsat scenes over Rasuwa, clearest "
            f"{clearest['cloud']:.0f}% cloud on {clearest['when']:%Y-%m-%d}")


@check("Copernicus Data Space catalogue")
def _cdse():
    payload = _get("https://catalogue.dataspace.copernicus.eu/odata/v1/"
                   "Products?$top=1")
    assert (payload or {}).get("value"), "OData returned nothing"
    return "OData answers without an account"


@check("Earth Engine datasets the pipeline names")
def _earth_engine():
    import ee

    ee.Initialize(project="zeta-bonfire-478712-n9")
    missing = []
    for asset in ("JRC/GHSL/P2023A/GHS_BUILT_S", "JRC/GHSL/P2023A/GHS_POP",
                  "projects/sat-io/open-datasets/FABDEM",
                  "COPERNICUS/S2_SR_HARMONIZED", "COPERNICUS/S1_GRD",
                  "COPERNICUS/S1_GRD_FLOAT", "JRC/GSW1_4/GlobalSurfaceWater",
                  "FAO/GAUL/2015/level0", "FAO/GAUL/2015/level1"):
        # An Earth Engine asset is a collection, a table or a single image, and
        # the name alone does not say which. Trying all three is the only way
        # to ask "does this exist" rather than "is this the type I assumed".
        for reader in (lambda a: ee.ImageCollection(a).limit(1).size(),
                       lambda a: ee.FeatureCollection(a).limit(1).size(),
                       lambda a: ee.Image(a).bandNames()):
            try:
                reader(asset).getInfo()
                break
            except Exception:                                  # noqa: BLE001
                continue
        else:
            missing.append(asset)
    assert not missing, f"missing: {missing}"
    return "all nine named assets resolve"


@check("Earth Engine lag against the open catalogues")
def _ee_lag():
    import ee

    import catalog

    ee.Initialize(project="zeta-bonfire-478712-n9")
    box = ee.Geometry.Rectangle([85.30, 28.13, 85.40, 28.30])
    start = (datetime.now(timezone.utc) - timedelta(days=25)).date().isoformat()
    stamps = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(box)
              .filterDate(start, datetime.now(timezone.utc).date().isoformat())
              .aggregate_array("system:time_start").getInfo())
    if not stamps:
        return "Earth Engine holds no Sentinel-1 over the test area at all"
    engine = datetime.fromtimestamp(max(stamps) / 1000, timezone.utc)

    open_scenes = [s for s in catalog.scenes((85.30, 28.13, 85.40, 28.30), start,
                                             datetime.now(timezone.utc).date()
                                             .isoformat(),
                                             sensors=("sentinel-1",))
                   if s["when"]]
    if not open_scenes:
        return f"Earth Engine newest {engine:%Y-%m-%d}, open catalogues empty"
    newest = max(s["when"] for s in open_scenes)
    lag = (newest - engine).total_seconds() / 3600
    return (f"Earth Engine newest {engine:%Y-%m-%d %H:%M}, open catalogues "
            f"{newest:%Y-%m-%d %H:%M}, lag {lag:.0f} h")


def main() -> int:
    stamp = datetime.now(timezone.utc)
    print(f"Source checks, {stamp:%Y-%m-%d %H:%M} UTC\n")

    failures = 0
    for name, function in RESULTS:
        try:
            message = function()
            print(f"  ok    {name}\n        {message}")
        except AssertionError as error:
            failures += 1
            print(f"  STALE {name}\n        {error}")
        except Exception as error:                             # noqa: BLE001
            failures += 1
            print(f"  BROKE {name}\n        {type(error).__name__}: {error}")
            if "-v" in sys.argv:
                traceback.print_exc()

    print(f"\n{len(RESULTS) - failures} of {len(RESULTS)} checks passed")
    if failures:
        print("A failure here means a statement in docs/ is no longer true. "
              "Fix the document, not the check.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
