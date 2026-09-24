"""One question, every catalogue: what has actually been imaged over here?

The chain used to ask Earth Engine, and only Earth Engine. Measured over the
Bhote Koshi valley on 2026-08-28: Earth Engine held nothing after 24 August
while the Copernicus Data Space, Earth Search and the Planetary Computer all
held the 28 August Sentinel-1 acquisition. Four days of lag on the one scene
that mattered.

Earth Engine stays for global gridded data — GHSL, FABDEM, LitPop, GAUL —
where there is no latency question because the data does not change. Scenes of
a live event come from STAC, read straight as cloud-optimised GeoTIFFs.

    from catalog import scenes, first_look
    first_look((85.30, 28.13, 85.40, 28.30), "2026-08-25")

Two endpoints, neither needing an account. Landsat comes with the Planetary
Computer, which is the point: it crosses the equator half an hour before
Sentinel-2 on an unrelated cycle, so on a monsoon day the two have independent
chances of a gap in the cloud. Measured on Rasuwa, Landsat 9 on 26 August at
47.5 % cloud against Sentinel-2 on the 27th at 78.5 %.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timedelta, timezone

CATALOGUES = {
    "earth-search": "https://earth-search.aws.element84.com/v1",
    "planetary-computer": "https://planetarycomputer.microsoft.com/api/stac/v1",
}

# Collection names differ between catalogues for the same data. Ordered by
# how useful the sensor is for reading a flood footprint by eye.
COLLECTIONS = {
    "sentinel-2": {"earth-search": "sentinel-2-l2a",
                   "planetary-computer": "sentinel-2-l2a"},
    "sentinel-1": {"earth-search": "sentinel-1-grd",
                   "planetary-computer": "sentinel-1-grd"},
    "landsat": {"planetary-computer": "landsat-c2-l2"},
}

SAS = "https://planetarycomputer.microsoft.com/api/sas/v1/token/{collection}"

_tokens: dict[str, str] = {}


def _sas_token(collection: str) -> str:
    """A Planetary Computer read token. Free, anonymous, cached per session."""
    if collection not in _tokens:
        request = urllib.request.Request(SAS.format(collection=collection),
                                         headers={"User-Agent": "natcat"})
        with urllib.request.urlopen(request, timeout=60) as response:
            _tokens[collection] = json.loads(response.read())["token"]
    return _tokens[collection]


def sign(href: str, collection: str, source: str) -> str:
    """Make an asset href readable. Only the Planetary Computer needs it."""
    if source != "planetary-computer" or "?" in href:
        return href
    return f"{href}?{_sas_token(collection)}"


def scenes(aoi: tuple, start: str, end: str, sensors=("sentinel-2", "sentinel-1",
                                                      "landsat"),
           max_cloud: float | None = None, limit: int = 40) -> list[dict]:
    """Every scene covering an area in a window, from every catalogue that has it.

    Returns one dictionary per scene, oldest first: sensor, source, id, when,
    cloud where the sensor reports it, platform, and the raw STAC item so the
    assets can be read without asking again.

    Duplicates are collapsed on the granule identity rather than on the STAC
    id, because the same acquisition carries different ids in each catalogue.
    """
    from pystac_client import Client

    found = {}
    for sensor in sensors:
        for source, collection in COLLECTIONS.get(sensor, {}).items():
            try:
                client = Client.open(CATALOGUES[source])
                search = client.search(collections=[collection], bbox=list(aoi),
                                       datetime=f"{start}/{end}", limit=limit)
                items = list(search.items())
            except Exception:                                  # noqa: BLE001
                continue

            for item in items:
                cloud = item.properties.get("eo:cloud_cover")
                if max_cloud is not None and cloud is not None and cloud > max_cloud:
                    continue
                when = item.datetime
                if when and when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)

                # Same acquisition, two catalogues: keep one, prefer the one
                # that needs no token.
                key = (sensor, when.replace(microsecond=0) if when else item.id)
                entry = {
                    "sensor": sensor,
                    "source": source,
                    "collection": collection,
                    "id": item.id,
                    "when": when,
                    "cloud": cloud,
                    "platform": item.properties.get("platform"),
                    "item": item,
                }
                if key not in found or source == "earth-search":
                    found[key] = entry

    return sorted(found.values(), key=lambda s: (s["when"] or datetime.max
                                                 .replace(tzinfo=timezone.utc)))


def first_look(aoi: tuple, event_date: str, days: int = 14,
               max_cloud: float = 95.0) -> dict:
    """The first post-event scene from each sensor, and the first of all.

    Nothing is rejected for cloud below `max_cloud`: a partly clouded scene is
    often the only one there is, and deciding what is readable is the
    operator's job rather than a threshold's. The cloud figure travels with the
    scene so that judgement can be made.
    """
    day = datetime.fromisoformat(event_date[:10]).replace(tzinfo=timezone.utc)
    end = (day + timedelta(days=days)).date().isoformat()

    after = [s for s in scenes(aoi, day.date().isoformat(), end,
                               max_cloud=max_cloud)
             if s["when"] and s["when"] >= day]

    per_sensor = {}
    for entry in after:
        per_sensor.setdefault(entry["sensor"], entry)

    def hours(entry):
        return (entry["when"] - day).total_seconds() / 3600

    return {
        "event": day,
        "first": after[0] if after else None,
        "first_hours": hours(after[0]) if after else None,
        "per_sensor": per_sensor,
        "clearest": min((s for s in after if s["cloud"] is not None),
                        key=lambda s: s["cloud"], default=None),
        "all": after,
    }


def describe(entry: dict) -> str:
    """One line naming a scene the way a post has to name it."""
    if not entry:
        return "no scene"
    cloud = f", {entry['cloud']:.0f}% cloud" if entry["cloud"] is not None else ""
    platform = entry.get("platform") or entry["sensor"]
    return (f"{platform} {entry['when']:%Y-%m-%d %H:%M} UTC{cloud} "
            f"({entry['source']})")


def _self_check() -> None:
    """Run: conda run -n climada_env python catalog.py"""
    valley = (85.303, 28.129, 85.401, 28.300)

    look = first_look(valley, "2026-08-25", days=8)
    assert look["first"], "no post-event scene found over Rasuwa"
    print(f"ok  first post-event scene: {describe(look['first'])} "
          f"at +{look['first_hours']:.0f} h")

    for sensor, entry in sorted(look["per_sensor"].items()):
        print(f"      {sensor:<11} {describe(entry)}")

    sensors = set(look["per_sensor"])
    assert {"sentinel-1", "sentinel-2"} <= sensors, sensors
    assert "landsat" in sensors, "Landsat was missing from the search"

    clearest = look["clearest"]
    assert clearest and clearest["cloud"] < 60, describe(clearest)
    print(f"ok  clearest optical scene: {describe(clearest)}")

    href = next(iter(look["per_sensor"]["landsat"]["item"].assets.values())).href
    signed = sign(href, "landsat-c2-l2", "planetary-computer")
    assert signed != href and "?" in signed
    print("ok  Planetary Computer assets sign anonymously")

    print("\nchecks passed")


if __name__ == "__main__":
    _self_check()
