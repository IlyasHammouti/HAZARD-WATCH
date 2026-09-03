"""Watch for new activations and say which post is due.

Run it on a schedule. It walks the Copernicus EMS activation numbering
forward, records what it finds, places every open activation on the
publication calendar, and drafts the post that is due.

    conda run -n climada_env python watch.py            # report only
    conda run -n climada_env python watch.py --draft    # and write the drafts

**It never publishes.** Section 11 of the editorial rules refuses to publish
anything without a human plausibility sign-off, and that rule is the reason
this project can put figures in public at all. What is automated is the
watching, the timing and the drafting; the decision stays with a person.

State lives in `data/watch_state.json`: the highest activation code seen, and
which post type has already been drafted for each event, so a scheduled run
does not redraft what it drafted an hour ago.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import ems

ROOT = Path(__file__).parent
STATE = ROOT / "data" / "watch_state.json"

# The publication calendar, in hours since the event. A post becomes due when
# the clock passes its hour and its content actually exists.
CALENDAR = (
    ("alert", 0, "02-alert.md"),
    ("activation", 6, "07-activation.md"),
    ("extent", 30, "03-observed-extent.md"),
    ("official", 40, "08-official-figures.md"),
)

# The loss post is deliberately absent from the calendar above. Whether one
# can be written is not a question of the hour: it is whether the guards
# return tier 1, and only running the chain answers that. A watcher announcing
# "loss estimate due" for an event whose mechanism refuses a damage curve
# would be announcing a post that cannot exist.

# Events older than this are history, not news; the watcher stops offering
# posts for them and a retrospective is a deliberate decision.
STALE_HOURS = 21 * 24

# What the chain can actually model. Everything else is still watched and
# still reported — an activation is worth knowing about whatever the peril —
# but the watcher says plainly that no loss chain exists behind it.
COVERED_PERILS = {"flood"}


def _load() -> dict:
    if STATE.exists():
        state = json.loads(STATE.read_text(encoding="utf-8"))
        state.setdefault("open", {})
        state.setdefault("drafted", {})
        return state
    return {"last_code": "EMSR920", "open": {}, "drafted": {}}


def _save(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def due(clock: dict, has_counts: bool, has_extent: bool) -> tuple:
    """Which post the calendar and the evidence together say is due.

    The hour alone does not decide it. A post is due when its hour has passed
    **and** the thing it is about exists: there is no official-figures post
    before anybody has counted anything, however late it is.
    """
    event = clock.get("event")
    if not event:
        return None, None
    hours = (datetime.now(timezone.utc)
             - event.replace(tzinfo=timezone.utc)).total_seconds() / 3600
    if hours > STALE_HOURS:
        return None, hours

    ready = {
        "alert": True,
        "activation": clock.get("activation_hours") is not None,
        "extent": has_extent,
        "official": has_counts,
    }
    # The latest post whose hour has passed and whose content exists. Later
    # posts supersede earlier ones: there is no point drafting an alert for an
    # event that has already been graded.
    chosen = None
    for name, hour, template in CALENDAR:
        if hours >= hour and ready.get(name):
            chosen = (name, template)
    return chosen, hours


def scan(draft: bool = False, look_ahead: int = 6) -> list:
    """Walk the numbering forward, place each activation, report what is due."""
    state = _load()
    found = ems.discover(state["last_code"], look_ahead=look_ahead)

    if found:
        state["last_code"] = max(r["code"] for r in found)

    # Everything still open, not only what is new. An activation discovered
    # yesterday reaches its official-figures hour today, and a watcher that
    # forgot it the moment it stopped being new would never draft that post.
    for record in found:
        state["open"][record["code"]] = record.get("eventTime") or ""

    now = datetime.now(timezone.utc)
    for code, when in list(state["open"].items()):
        try:
            age = (now - datetime.fromisoformat(when).replace(
                tzinfo=timezone.utc)).total_seconds() / 3600
        except Exception:                                      # noqa: BLE001
            continue
        if age > STALE_HOURS:
            del state["open"][code]

    report = []
    for code in sorted(state["open"]):
        record = ems.activation(code)
        if not record:
            continue
        clock = ems.timings(record)

        layers = ems.vectors(code, record)
        counts = ems.damage_summary(layers) if layers else {}
        has_counts = bool(counts.get("buildings"))
        has_extent = bool(counts.get("observed"))

        chosen, hours = due(clock, has_counts, has_extent)
        entry = {
            "code": code,
            "name": record.get("name"),
            "category": record.get("category") or record.get("subCategory") or "",
            "covered": (record.get("category") or "").lower() in COVERED_PERILS,
            "hours": round(hours, 1) if hours is not None else None,
            "activation_hours": clock.get("activation_hours"),
            "first_product_hours": clock.get("first_product_hours"),
            "buildings": counts.get("buildings", 0),
            "due": chosen[0] if chosen else None,
            "template": chosen[1] if chosen else None,
            "already_drafted": state.get("drafted", {}).get(code),
        }

        if draft and chosen and entry["already_drafted"] != chosen[0]:
            entry["drafted"] = _draft(code, record, chosen[1])
            if entry["drafted"]:
                state.setdefault("drafted", {})[code] = chosen[0]

        report.append(entry)

    _save(state)
    return report


def _draft(code: str, record: dict, template: str):
    """Write the draft for one activation, if the chain can build the event.

    An activation this project has no `FloodEvent` for cannot be run: the
    chain needs the hazard windows and the sector, which are judgement. The
    watcher says so rather than inventing them.
    """
    try:
        import events as catalogue
        import report as reporting
    except Exception:                                          # noqa: BLE001
        return None

    event = next((v for k, v in vars(catalogue).items()
                  if getattr(v, "ems_code", None) == code), None)
    if event is None:
        return f"no event definition for {code}; add one to events.py"

    try:
        import ee

        ee.Initialize(project="zeta-bonfire-478712-n9")
        out = reporting.make_post(event, kind=template)
        return str(out["draft"])
    except Exception as error:                                 # noqa: BLE001
        return f"{type(error).__name__}: {error}"


def main() -> int:
    draft = "--draft" in sys.argv
    rows = scan(draft=draft)

    stamp = datetime.now(timezone.utc)
    print(f"Activation watch, {stamp:%Y-%m-%d %H:%M} UTC\n")
    if not rows:
        print("  Nothing open and nothing new.")
        return 0

    for row in rows:
        age = f"+{row['hours']:.0f} h" if row["hours"] is not None else "unknown"
        mark = "" if row["covered"] else "   [no loss chain for this peril]"
        print(f"  {row['code']}  {row['name']}{mark}")
        print(f"        event {age}"
              + (f", activation +{row['activation_hours']:.0f} h"
                 if row["activation_hours"] is not None else "")
              + (f", first product +{row['first_product_hours']:.0f} h"
                 if row["first_product_hours"] is not None else ""))
        if row["buildings"]:
            print(f"        {row['buildings']} buildings graded")
        if row["due"]:
            done = (" (already drafted)"
                    if row["already_drafted"] == row["due"] else "")
            print(f"        due: {row['due']}, {row['template']}{done}")
        else:
            print("        due: nothing yet")
        if row.get("drafted"):
            print(f"        drafted: {row['drafted']}")

    print("\nNothing here is published. A human signs off before anything goes "
          "out, which is rule 11 and not an oversight.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
