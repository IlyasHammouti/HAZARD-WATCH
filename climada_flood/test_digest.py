"""Self-check for the weekly digest helpers.

Run: conda run -n climada_env python test_digest.py

No network. These are the pieces that turn a raw feed record into a published
sentence, and each one of them was wrong on the first pass.
"""

from datetime import datetime

import report


def event(**over):
    base = {
        "event_type": "FL",
        "country": "Nepal",
        "severity": "0.0",
        "severity_text": "Magnitude 0 ",
        "from_date": datetime(2026, 8, 26, 1, 0),
        "to_date": datetime(2026, 8, 28, 1, 0),
        "is_current": True,
        "name": "Flood in Nepal",
        "event_name": "",
        "alert_level": "Orange",
        "is_new": False,
        "event_id": 1,
    }
    return {**base, **over}


def test_two_significant_figures():
    assert report._two_sig(1487749) == "1,500,000"
    assert report._two_sig(18310) == "18,000"
    assert report._two_sig(0) == "0"


def test_flood_has_no_magnitude():
    """GDACS returns `Magnitude 0` for every flood. It is not a measurement."""
    assert report._digest_fact(event()) == ""


def test_earthquake_magnitude_is_not_millions():
    fact = report._digest_fact(event(event_type="EQ", severity="5.0",
                                     severity_text="Magnitude 5M, Depth:10km"))
    assert fact == "Magnitude 5.0, depth 10 km", fact


def test_alert_level_is_not_repeated_inside_the_clause():
    fact = report._digest_fact(event(
        event_type="WF", severity="1",
        severity_text="Orange impact for forestfire in 18310 ha"))
    assert fact == "Forest fire over 18,000 ha", fact


def test_no_event_is_printed_as_ended():
    """`to_date` advances with the data, so it is never printed as an end.

    Measured on the Madagascar drought: `todate` moved from 26 to 27 August
    between two pulls a day apart, `datemodified` was that morning, and
    `iscurrent` was false throughout. None of those three says the drought
    stopped.
    """
    assert report._digest_dates(event()) == "since 26 August 2026"
    drought = event(is_current=False, from_date=datetime(2025, 11, 21),
                    to_date=datetime(2026, 8, 27))
    assert report._digest_dates(drought) == "since 21 November 2025"
    instant = event(event_type="EQ", from_date=datetime(2026, 8, 28, 5, 13),
                    to_date=datetime(2026, 8, 28, 5, 13))
    assert report._digest_dates(instant) == "28 August 2026"


def test_region_only_where_the_point_is_the_event():
    """A flood point is a basin centroid and must not become a location."""
    quake = event(event_type="EQ", country="China", event_id=1)
    assert report._digest_place(quake, {1: "Sichuan Sheng"}) == "Sichuan Sheng, China"
    flood = event(event_id=2)
    assert report._digest_place(flood, {}) == "Nepal"


def test_long_country_lists_are_counted_not_listed():
    many = "Albania, Austria, Bosnia, Belgium, Bulgaria, "
    assert report._digest_country(many) == "Albania, Austria and 3 other countries"
    assert report._digest_country("Japan, China") == "Japan, China"


def test_peril_carries_the_name_the_feed_gives():
    """A volcano without its name is a category: Indonesia has 127."""
    assert report._digest_peril(event()) == "Flood"
    volcano = event(event_type="VO", country="Indonesia",
                    event_name="Krakatau", name="Eruption  Krakatau")
    assert report._digest_peril(volcano) == "Volcano Krakatau"
    cyclone = event(event_type="TC", event_name="SAUDEL-26",
                    name="Tropical Cyclone SAUDEL-26")
    assert report._digest_peril(cyclone) == "Tropical cyclone SAUDEL-26"

    # GDACS fills eventname for droughts too, with an alert slug that printed
    # as "Madagascar-2026, Madagascar" the first time it reached the figure.
    drought = event(event_type="DR", country="Madagascar",
                    event_name="Madagascar-2026")
    assert report._digest_peril(drought) == "Drought"
    assert report._digest_row(drought, {}) == "Madagascar"


def test_figure_row_carries_the_name_too():
    """The table heading says VOLCANO, so the row is the only place left."""
    volcano = event(event_type="VO", country="Indonesia", event_id=9,
                    event_name="Krakatau")
    assert report._digest_row(volcano, {9: "Lampung"}) ==         "Krakatau, Lampung, Indonesia"
    assert report._digest_row(event(), {}) == "Nepal"


def test_text_lists_only_what_the_figure_cannot_carry():
    """The bullets and the figure held the same eight lines."""
    fresh = event(event_id=1, is_new=True)
    red = event(event_id=2, alert_level="Red")
    old = event(event_id=3)
    listed, dropped = report._digest_selection([fresh, red, old], 8)
    assert [e["event_id"] for e in listed] == [1, 2]
    assert [e["event_id"] for e in dropped] == [3]

    # The cap still binds, and whatever it cuts moves to the figure.
    many = [event(event_id=i, is_new=True) for i in range(10)]
    listed, dropped = report._digest_selection(many, 8)
    assert len(listed) == 8 and len(dropped) == 2


def test_filter_unfeatured_drops_previously_shown_events():
    """A Red alert is never hidden, however long it has run or repeated."""
    history = {"3": {"first_shown": "2026-09-07", "name": "Flood in China"}}
    fresh = event(event_id=1)
    shown_before = event(event_id=3)
    red_shown_before = event(event_id=3, alert_level="Red")
    assert [e["event_id"] for e in
            report._filter_unfeatured([fresh, shown_before], history)] == [1]
    assert [e["event_id"] for e in
            report._filter_unfeatured([red_shown_before], history)] == [3]


def test_headline_prefers_new_then_red_then_green_topup_then_continuing():
    new_event = event(event_id=1, is_new=True)
    red = event(event_id=2, alert_level="Red")
    topup = {**event(event_id=3, event_type="EQ"), "green_topup": True}
    old = event(event_id=4)
    history = {}

    assert report._pick_headline([new_event], [red], [topup], history)["event_id"] == 1
    assert report._pick_headline([], [red, old], [topup], history)["event_id"] == 2
    assert report._pick_headline([], [old], [topup], history)["event_id"] == 3
    assert report._pick_headline([], [old], [], history)["event_id"] == 4
    assert report._pick_headline([], [], [], history) is None


def test_headline_skips_a_suppressed_continuing_event_when_nothing_else_exists():
    """The whole point: an old event shown once must not headline again,
    even with no fresh Green pick to replace it — unless it is the only
    event left in the world, the true last-resort safety net."""
    history = {"9": {"first_shown": "2026-09-07", "name": "Flood in China"}}
    suppressed = event(event_id=9)
    assert report._pick_headline([], [suppressed], [], history) is not None
    assert report._pick_headline([], [suppressed], [], history)["event_id"] == 9

    other = event(event_id=10)
    assert report._pick_headline(
        [], [suppressed, other], [], history)["event_id"] == 10


def test_digest_selection_always_lists_a_green_topup():
    """A Green top-up must appear as a bullet even when it is not `is_new` -
    otherwise it silently falls to the figure and the whole point (giving
    each risk type an explicit line) is lost."""
    continuing_topup = {**event(event_id=5, is_new=False, alert_level="Green"),
                        "green_topup": True}
    old = event(event_id=6)
    listed, dropped = report._digest_selection([continuing_topup, old], 8)
    assert [e["event_id"] for e in listed] == [5]
    assert [e["event_id"] for e in dropped] == [6]


def test_remainder_counts_the_perils_it_leaves_to_the_figure():
    rest = [event(event_id=1, event_type="DR",
                  from_date=datetime(2025, 11, 21)),
            event(event_id=2, event_type="DR",
                  from_date=datetime(2026, 4, 21)),
            event(event_id=3, event_type="FL",
                  from_date=datetime(2026, 7, 31))]
    line = report._digest_remainder(rest)
    assert "3 more" in line, line
    assert "2 droughts and 1 flood" in line, line
    assert "21 November 2025" in line, line
    assert report._digest_remainder([]) == ""


def test_red_statement_names_what_it_counts():
    """A bare "1 reached Red." counts nothing the reader can see."""
    assert report._red_statement([]) == "No event reached Red."
    assert report._red_statement([event()]) == "1 event reached Red."
    assert report._red_statement([event(), event()]) == "2 events reached Red."


def test_plain_text_keeps_the_title_and_unwraps_prose():
    plain = report.to_plain_text(
        "# Natural catastrophes, week of 24 August\n\n"
        "Two events entered the list this week; ten\nwere already running.\n\n"
        "## Events\n\n- Flood, Nepal. Alert Orange.\n- Flood, China. Alert Orange.\n"
    )
    assert plain.startswith("Natural catastrophes, week of 24 August")
    assert "this week; ten were already running." in plain, plain
    assert "#" not in plain and "**" not in plain
    assert "- Flood, Nepal. Alert Orange.\n- Flood, China." in plain


def test_credit_follows_the_sensor_that_produced_the_extent():
    """EMSR927 was 0.05 per cent radar and still credited Sentinel-1."""
    class _Event:
        event_date = "2026-08-25"

    radar = {"extent_km2": 22.8, "radar_km2": 16.9, "optical_scenes": 22,
             "timeline": [{"datetime": "2023-05-17T05:11:00", "area_km2": 5.0}],
             "event": _Event(), "source": "gfm"}
    optical = {"extent_km2": 0.87, "radar_km2": 0.0004, "optical_scenes": 1,
               "optical_dates": ["2026-08-27"], "timeline": [],
               "event": _Event(), "source": "gfm"}

    assert "Global Flood Monitoring" in report._extent_credit(radar)
    assert report._sensor(radar).startswith("Sentinel-1")

    assert "Sentinel-2" in report._extent_credit(optical)
    assert "Global Flood Monitoring" not in report._extent_credit(optical).split(
        "over ground")[0]
    assert report._sensor(optical) == "Sentinel-2"
    assert "2 days after the event" in report._latency_statement(optical)

    # No optical date recorded means a slot a human fills, never a guess.
    assert report._latency_statement({**optical, "optical_dates": []}) == "[TO WRITE]"


def test_every_locked_string_a_template_asks_for_exists():
    """A locked id that does not parse fails at publication, not before.

    The parser wants the identifier and the colon on one line. `L-DISC-GRADED`
    was written over two and silently did not exist, which surfaced as a
    KeyError while drafting rather than as a missing sentence in a post.
    """
    import re
    from pathlib import Path

    import report

    known = set(report.locked_phrases())
    assert known, "no locked strings parsed at all"

    missing = {}
    for path in sorted(Path("templates").glob("*.md")):
        wanted = set(re.findall(r"\{\{LOCKED:([A-Z0-9-]+)\}\}",
                                path.read_text(encoding="utf-8")))
        if wanted - known:
            missing[path.name] = sorted(wanted - known)
    assert not missing, missing

    # And the ones the code reaches for by name, which templates never mention.
    for name in ("L-DISC-GRADED", "L-DISC-FULL", "L-SRC-SENTINEL",
                 "L-REPORTED", "L-SRC-EMS-GRADING", "L-SRC-OPTICAL",
                 "L-SRC-GFM", "L-SRC-MANUAL", "L-PASS", "L-AWAITING-PRODUCT"):
        assert name in known, name


def test_graded_loss_prices_what_was_observed():
    """No assumed depth, no borrowed curve: the grade is the measurement."""
    import numpy as np
    import rasterio.transform
    from rasterio.crs import CRS
    from shapely.geometry import Point

    import natcat

    # Two cells of 100 m, side by side, worth 1000 each.
    profile = {"crs": CRS.from_epsg(4326),
               "transform": rasterio.transform.from_origin(0.0, 1.0, 0.001, 0.001),
               "resolution": 0.001}
    value = np.array([[1000.0, 1000.0]])

    def building(lon, grade):
        return {"geometry": Point(lon, 0.9995), "properties": {"damage_gra": grade},
                "aoi": "A"}

    # Three buildings in the left cell, one in the right.
    buildings = [building(0.0005, "Destroyed"), building(0.0006, "Destroyed"),
                 building(0.0007, "Damaged"), building(0.0015, "Possibly damaged")]

    out = natcat.graded_loss(buildings, value, profile)
    assert out["graded"] == 4 and out["unplaced"] == 0
    # Left cell splits 1000 three ways, right cell gives its 1000 to one.
    assert abs(out["exposed"] - 2000.0) < 1e-6, out["exposed"]

    third = 1000.0 / 3.0
    # Destroyed costs replacement at both bounds; only the lower grades move.
    assert abs(out["loss_low"] - (2 * third + third * 0.30 + 1000 * 0.05)) < 1e-6
    assert abs(out["loss_high"] - (2 * third + third * 0.60 + 1000 * 0.20)) < 1e-6
    assert out["loss_low"] < out["loss"] < out["loss_high"]
    assert out["method"] == "graded"
    assert out["grades"]["Destroyed"] == 2

    # A building outside the grid carries no value and is counted as such.
    far = natcat.graded_loss([building(9.0, "Destroyed")], value, profile)
    assert far["unplaced"] == 1 and far["exposed"] == 0.0


def test_terrain_and_mechanism_do_not_block_an_observed_grade():
    """They are questions about a depth-damage curve. None is used here."""
    import guards

    graded = {"timeline": [1], "extent_km2": 8.5, "detected_km2": 0.0,
              "radar_km2": 0.0, "coverage": 1.0, "assessable": 0.92,
              "exposed_usd": 1.3e8, "damage_ratio": 0.6, "source": "ems",
              "method": "graded", "graded_buildings": 3207,
              "grades": {"Destroyed": 2521, "Damaged": 285},
              "loss_low_usd": 8e7, "loss_high_usd": 1.0e8}

    verdict = guards.assess(graded, mechanism="glof", steep_share=0.59)
    codes = {f.code for f in verdict.findings}
    assert "MECHANISM" not in codes and "TERRAIN" not in codes, codes
    assert "GRADED" in codes
    assert verdict.tier == 1, verdict.report()

    # The depth route still refuses exactly as before.
    depth = {**graded, "method": "depth"}
    assert guards.assess(depth, mechanism="glof", steep_share=0.59).tier == 2


def test_the_event_carries_two_clocks():
    """Local time for the reader, UTC for the data, never the author's zone."""
    result = {
        "event": type("E", (), {"event_date": "2026-08-25"})(),
        "activation": {"event_time": "2026-08-25T22:00:00",
                       "bounds": (85.30, 28.13, 85.40, 28.30)},
    }
    text = report._event_time(result)
    assert "03:45 local time" in text, text          # Kathmandu is UTC+5:45
    assert "2026-08-25 22:00 UTC" in text, text
    assert "26 August 2026" in text, text            # local date, not the UTC one

    # No activation time means no invented clock.
    assert report._event_time({"event": result["event"], "activation": {}}) \
        == "2026-08-25"


def test_swath_clip_keeps_the_centre():
    import natcat

    wide = (83.9194, 26.9191, 86.5726, 29.3207)      # GDACS Nepal flood polygon
    clipped = natcat.clip_aoi(wide, max_km=100.0)
    assert clipped[0] > wide[0] and clipped[2] < wide[2]
    assert abs((clipped[0] + clipped[2]) / 2 - (wide[0] + wide[2]) / 2) < 1e-9
    assert (clipped[3] - clipped[1]) * 111.32 <= 100.5
    # A box already inside one swath is left alone.
    small = (84.4054, 27.6821, 85.3806, 28.2799)     # EMSR927 activation
    assert natcat.clip_aoi(small, max_km=100.0) == small


def test_legend_dashes_end_on_a_gap():
    """The map pattern left a two-point stub dash at the end of the handle."""
    import carto

    for cycles in (2, 3, 4):
        offset, (dash, gap) = carto.legend_dashes(carto.STUDY_AREA_DASH,
                                                  cycles=cycles)
        handle = carto.LEGEND_HANDLE_LENGTH * carto.TYPE["legend"]
        assert offset == 0
        # A whole number of cycles across the handle, so it ends on a gap.
        assert abs((dash + gap) * cycles - handle) < 1e-9
        # And the ratio the map uses is untouched.
        assert abs(dash / gap - carto.STUDY_AREA_DASH[0]
                   / carto.STUDY_AREA_DASH[1]) < 1e-9


def test_ems_summary_counts_what_the_responders_mapped():
    """Needs the network; the published GeoJSON is fetched and cached."""
    import ems

    layers = ems.vectors("EMSR927")
    if not layers:
        print("ok  (skipped, EMSR927 vectors unavailable)")
        return
    summary = ems.damage_summary(layers)
    assert summary["buildings"] == sum(summary["building_grades"].values())
    assert summary["observed_km2"] > 0
    assert summary["roads_destroyed_km"] <= summary["roads_km"]
    assert all(f["grade"] for f in summary["facilities"])


def test_the_tier_never_suppresses_a_reported_figure():
    """The V1 failure: no figure published while EMS had counted 2 521."""
    import guards

    official = {"buildings": 3207, "building_grades": {"Destroyed": 2521,
                                                       "Damaged": 285},
                "observed_km2": 8.33, "mechanisms": ["Landslide"],
                "roads_km": 21.3, "roads_destroyed_km": 15.7,
                "named_destroyed": ["Rasuwagadhi Hydropower Dam"]}
    blocked = {"timeline": [1], "extent_km2": 0.87, "detected_km2": 0.87,
               "radar_km2": 0.0004, "coverage": 1.0, "assessable": 0.05,
               "exposed_usd": 1.4e7, "damage_ratio": 0.49, "source": "gfm"}

    verdict = guards.assess(blocked, mechanism="glof", steep_share=0.59,
                            ems=official)
    assert verdict.tier == 2, verdict.tier
    assert verdict.reported["buildings_destroyed"] == 2521
    assert "Copernicus EMS" in verdict.reported["source"]

    statement = guards.tier_statement(verdict)
    assert "modelled" in statement.lower()
    assert "reported as published" in statement

    # And with no other source, the block simply does not exist.
    assert guards.assess(blocked, mechanism="glof", steep_share=0.59).reported == {}


def test_own_detection_is_measured_against_the_official_map():
    import guards

    finding = guards.check_against_official(0.87, {"observed_km2": 8.33})
    assert finding.level == "warn" and "10%" in finding.message
    assert guards.check_against_official(7.0, {"observed_km2": 8.33}).level == "ok"
    assert guards.check_against_official(0.87, None).level == "ok"


def test_pick_top_unexcluded_ranks_by_alert_score_and_skips_excluded():
    import natcat

    low = {"event_id": 1, "alert_score": 1}
    high = {"event_id": 2, "alert_score": 5}
    mid = {"event_id": 3, "alert_score": 3}
    no_score = {"event_id": 4, "alert_score": None}

    assert natcat._pick_top_unexcluded([low, high, mid], frozenset())["event_id"] == 2
    # The highest-scoring one is excluded: falls through to the next.
    assert natcat._pick_top_unexcluded([low, high, mid], {"2"})["event_id"] == 3
    # Every candidate excluded: nothing to return, never a stretch pick.
    assert natcat._pick_top_unexcluded([low], {"1"}) is None
    assert natcat._pick_top_unexcluded([], frozenset()) is None
    # A missing/None alert_score ranks as 0, never crashes the comparison.
    assert natcat._pick_top_unexcluded([no_score, low], frozenset())["event_id"] == 1


if __name__ == "__main__":
    checks = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for check in checks:
        check()
        print(f"ok  {check.__name__}")
    print(f"\n{len(checks)} checks passed")
