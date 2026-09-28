"""Self-check for the video digest's logic.

Run: conda run -n climada_env python test_video.py

No network. These cover what decides where things land and what gets shown:
the camera, the picks file, the cyclone track matching and the compositing.
"""

import math
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np

import natcat
import video


def test_longitudes_are_unwrapped_towards_the_camera():
    """Japan to Hawaii crosses 180 degrees and must keep going, not jump back."""
    assert video.near(-155, 140) == 205
    assert video.near(170, -175) == -190
    assert video.near(10, 0) == 10


def test_world_is_cut_where_nothing_happened():
    centre = video.gap_centre([0, 10])
    assert 4 <= centre <= 6, centre
    # A Pacific week: events either side of 180 stay in one piece.
    centre = video.gap_centre([170, -170, 150])
    assert all(abs(video.near(lon, centre) - centre) < 60
               for lon in (170, -170, 150)), centre
    assert video.gap_centre([42]) == 42
    assert video.gap_centre([]) == 10.0


def test_world_view_crops_only_the_empty_part():
    small = video.world_view(0, [10, -20])
    assert math.isclose(small.width, video.WORLD * 0.8)
    spread = video.world_view(0, [170, -60])
    assert spread.width > small.width
    assert math.isclose(video.world_view(0, whole=True).width, video.WORLD)


def test_camera_starts_and_ends_exactly_on_the_two_views():
    a = video.point_view(10, 45, 900)
    b = video.point_view(140, 35, 900)
    start, end = video.camera(a, b, 0.0), video.camera(a, b, 1.0)
    assert math.isclose(start.cx, a.cx) and math.isclose(start.width, a.width)
    assert math.isclose(end.cx, b.cx) and math.isclose(end.width, b.width)
    # Far apart, the camera pulls back to show both on the way.
    middle = video.camera(a, b, 0.5)
    assert middle.width > 3 * max(a.width, b.width)


def test_a_point_lands_on_the_focus():
    view = video.point_view(-175.2, -18.1, 900)
    x, y = view.px(-175.2, -18.1)
    assert abs(x - video.W / 2) < 0.5
    assert abs(y - video.FOCUS_Y * video.H) < 0.5


def test_a_fitted_track_stays_inside_the_safe_area():
    lons, lats = [120.0, 128.0, 134.0, 139.0], [12.0, 17.0, 24.0, 33.0]
    view = video.fit_view(lons, lats)
    xs, ys = view.px(np.array(lons), np.array(lats))
    assert xs.min() > video.MARGIN and xs.max() < video.W - video.MARGIN
    assert ys.min() > video.SAFE_TOP and ys.max() < video.SAFE_BOTTOM


def _picks(text: str) -> Path:
    path = Path(tempfile.mkdtemp()) / "picks.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_picks_file_keeps_order_options_and_droughts():
    clip = Path(tempfile.mkdtemp()) / "clip.mp4"
    clip.write_bytes(b"")
    path = _picks(
        "# comment\n"
        "EQ-2   Earthquake, Tonga - Green\n"
        "# TC-9   not picked\n"
        f"TC-1   Tropical cyclone POLO-26 | clip={clip} | source=Reuters "
        "| from=2 | to=11.5\n"
        "\n"
        "DR-5   Drought, Europe\n")
    scenes, droughts = video.read_picks(path)
    assert [s["key"] for s in scenes] == ["EQ-2", "TC-1"]
    assert scenes[1]["clip"] == str(clip) and scenes[1]["source"] == "Reuters"
    assert scenes[1]["from"] == 2.0 and scenes[1]["to"] == 11.5
    assert scenes[0]["clip"] is None
    assert droughts == ["DR-5"]


def test_a_clip_without_its_source_is_refused():
    clip = Path(tempfile.mkdtemp()) / "clip.mp4"
    clip.write_bytes(b"")
    try:
        video.read_picks(_picks(f"TC-1 | clip={clip}\n"))
    except ValueError as error:
        assert "source" in str(error)
    else:
        raise AssertionError("a clip with no source was accepted")


def test_a_mistyped_key_is_refused():
    try:
        video.read_picks(_picks("TC1001325 Tropical cyclone\n"))
    except ValueError:
        pass
    else:
        raise AssertionError("a malformed key was accepted")


def test_a_category_five_outranks_an_orange_tropical_storm():
    """GDACS lists a storm at the level of its latest advisory. POLO-26 was
    Green by the time the week closed, after peaking at Category 5."""
    polo = {"event_type": "TC", "alert_level": "Green", "alert_score": 1,
            "severity": "0", "from_date": datetime(2026, 9, 21),
            "week_peak": {"wind_kt": 155, "category": 5}}
    one = {"event_type": "TC", "alert_level": "Orange", "alert_score": 2,
           "severity": "0", "from_date": datetime(2026, 9, 22),
           "week_peak": {"wind_kt": 45, "category": 0}}
    weak = {**polo, "week_peak": {"wind_kt": 70, "category": 1}}
    assert video._serious(polo) and video._serious(one)
    assert not video._serious(weak)
    assert video._significance(polo) > video._significance(one)


def test_drought_region_drops_the_year_slug():
    assert video._drought_region({"event_name": "East Africa-2026"}) == "East Africa"
    assert video._drought_region({"event_name": "Uganda, Kenya-2026"}) == "Uganda, Kenya"
    assert video._drought_region({"event_name": ""}) == ""


def test_saffir_simpson_thresholds():
    assert natcat.saffir_simpson(None) is None
    assert natcat.saffir_simpson(30) == -1
    assert natcat.saffir_simpson(34) == 0
    assert natcat.saffir_simpson(64) == 1
    assert natcat.saffir_simpson(112) == 3
    assert natcat.saffir_simpson(155) == 5


def _circle(lon, lat, key, issued="2026-09-25T15:00:00"):
    ring = [[lon + 0.01 * math.cos(a), lat + 0.01 * math.sin(a)]
            for a in np.linspace(0, 2 * math.pi, 12)]
    return {"geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"featuretype": "PointRadii", "key": key,
                           "polygondate": issued}}


def _event(**over):
    base = {"event_type": "TC", "event_id": 1, "episode_id": 1,
            "event_name": "POLO-26", "lat": 17.0, "lon": -108.0,
            "from_date": datetime(2026, 9, 21), "to_date": datetime(2026, 9, 25)}
    return {**base, **over}


def test_gdacs_track_drops_forecast_positions():
    original = natcat.gdacs_geometry
    natcat.gdacs_geometry = lambda event: [
        _circle(-104.6, 15.1, "09210300"), _circle(-103.8, 15.5, "09210900"),
        _circle(-106.5, 30.4, "09301200")]            # 30 Sep: a forecast
    try:
        fixes = natcat._gdacs_track(_event())
    finally:
        natcat.gdacs_geometry = original
    assert [f["time"] for f in fixes] == [datetime(2026, 9, 21, 3),
                                          datetime(2026, 9, 21, 9)]
    assert abs(fixes[0]["lon"] + 104.6) < 0.02


def test_cyclone_matched_by_name_then_by_position_then_extended():
    fix = lambda day, lon, wind: {"time": datetime(2026, 9, day), "lat": 16.0,
                                  "lon": lon, "wind_kt": wind, "category": None}
    storms = {
        "A": {"sid": "A", "name": "POLO", "season": 2026, "basin": "EP",
              "fixes": [fix(21, -104.0, 60), fix(22, -105.0, 100)]},
        "B": {"sid": "B", "name": "UNNAMED", "season": 2026, "basin": "NI",
              "fixes": [fix(22, 84.0, 35), fix(23, 83.5, 40)]},
    }
    original = (natcat.ibtracs_active, natcat.gdacs_geometry)
    natcat.ibtracs_active = lambda: storms
    natcat.gdacs_geometry = lambda event: [_circle(-106.0, 16.5, "09230000")]
    try:
        named = natcat.cyclone_track(_event())
        unnamed = natcat.cyclone_track(_event(event_name="ONE-26", lat=16.2,
                                              lon=83.8))
    finally:
        natcat.ibtracs_active, natcat.gdacs_geometry = original
    assert named["sid"] == "A"
    assert [f["category"] for f in named["fixes"][:2]] == [0, 3]     # 60, 100 kt
    # IBTrACS stops on the 22nd; GDACS's later position is appended, windless.
    assert named["source"] == "IBTrACS + GDACS"
    assert named["fixes"][-1]["wind_kt"] is None
    assert unnamed["sid"] == "B"


def test_marker_numbers_sit_in_the_middle_of_their_disc():
    """The digits' own ink is centred in the disc, within half a pixel."""
    for number in range(1, 10):
        image = np.asarray(video.marker("#1B7F79", number, 30), np.float32)
        white = (image[..., :3].min(axis=2) > 200) & (image[..., 3] > 200)
        # Only the digit: the white rim is the outer ring, so keep the inside.
        yy, xx = np.mgrid[0:30, 0:30]
        inside = np.hypot(xx - 14.5, yy - 14.5) < 10
        ys, xs = np.nonzero(white & inside)
        centre_x = (xs.min() + xs.max()) / 2
        centre_y = (ys.min() + ys.max()) / 2
        assert abs(centre_x - 14.5) <= 0.5 and abs(centre_y - 14.5) <= 0.5, \
            (number, centre_x, centre_y)


def test_figures_in_a_card_line_are_set_bold():
    line = video.emphasise("Forest fire over 20,000 ha")
    assert line == "Forest fire over **20,000 ha**"
    assert video.emphasise("Magnitude 6.5, depth 98 km") == \
        "**Magnitude 6.5**, depth **98 km**"
    assert video.emphasise("since 21 September 2026") == "since 21 September 2026"
    runs = video.runs("over **20,000 ha**")
    assert [bold for _, _, bold in runs] == [False, True]


def _flight(duration):
    item = object.__new__(video.Flight)
    item.duration, item.chapter = duration, None
    return item


def _track(duration):
    item = object.__new__(video.TrackScene)
    item.duration, item.chapter = duration, 0
    return item


def _point(kind, duration):
    item = object.__new__(video.PointScene)
    item.kind, item.duration, item.chapter = kind, duration, 0
    return item


def test_audio_cues_are_timed_against_the_running_clock():
    """Each cue starts when its scene starts, not at its own index."""
    timeline = [_flight(1.8), _track(6.0), _flight(2.0), _point("FL", 4.0)]
    cues = video.audio_cues(timeline)
    files = [c[0] for c in cues]
    starts = [round(c[1], 3) for c in cues]
    assert files == ["transition_whoosh.mp3", "cyclone_wind.mp3",
                     "transition_whoosh.mp3", "flood_water.mp3"]
    assert starts == [0.0, 1.8, 7.8, 9.8]


def test_a_bed_is_trimmed_to_its_scene_and_a_whoosh_never_outlasts_its_flight():
    cues = video.audio_cues([_track(6.0), _flight(1.6)])
    assert cues[0][2] == 6.0                    # bed trimmed to the scene
    assert cues[1][2] <= 1.6 - 0.1 + 1e-9        # whoosh trimmed inside the flight


def test_earthquake_gets_a_bed_and_one_shock_per_period_inside_the_scene():
    cues = video.audio_cues([_point("EQ", 5.0)])
    shocks = [c for c in cues if c[0] == "earthquake_shock.mp3"]
    beds = [c for c in cues if c[0] == "earthquake_rumble.mp3"]
    assert len(beds) == 1 and beds[0][1] == 0.0 and beds[0][2] == 5.0
    # SHOCK_START=0.45, SHOCK_PERIOD=1.9: shocks at 0.45, 2.35, 4.25 — three
    # inside a 5s scene, none of them past its end.
    assert [round(s[1], 2) for s in shocks] == [0.45, 2.35, 4.25]
    assert all(s[1] < 5.0 for s in shocks)


def test_volcano_gets_one_burst_near_the_start_no_shocks():
    cues = video.audio_cues([_point("VO", 5.0)])
    assert [c[0] for c in cues] == ["volcano_rumble.mp3", "volcano_burst.mp3"]
    assert abs(cues[1][1] - 0.25) < 1e-9


def test_wildfire_and_flood_get_only_their_bed():
    for kind, bed in (("WF", "wildfire_crackle.mp3"), ("FL", "flood_water.mp3")):
        cues = video.audio_cues([_point(kind, 4.0)])
        assert [c[0] for c in cues] == [bed]


def test_peak_gain_corrects_a_quiet_file_more_than_a_loud_one():
    """Not an absolute level (ffmpeg's `sine` source isn't full-scale to start
    with) — just that a file made much quieter needs a much bigger boost than
    one made much louder, which is the whole point of peak-normalising."""
    quiet = Path(tempfile.mkdtemp()) / "quiet.wav"
    loud = Path(tempfile.mkdtemp()) / "loud.wav"
    ffmpeg = shutil.which("ffmpeg")
    for path, gain in ((quiet, 0.05), (loud, 6.0)):
        subprocess.run([ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i",
                        f"sine=frequency=440:duration=0.5,volume={gain}",
                        str(path)], check=True)
    video._peak_gain_db.cache_clear()
    quiet_gain = video._peak_gain_db(str(quiet))
    loud_gain = video._peak_gain_db(str(loud))
    video._peak_gain_db.cache_clear()
    assert quiet_gain > loud_gain + 20


def test_sound_file_downloads_once_then_reuses_the_cache():
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            calls.append(1)
            return b"fake mp3 bytes"

    original_urlopen = video.urllib.request.urlopen
    video.urllib.request.urlopen = lambda *a, **k: FakeResponse()
    original_dir = video.SOUND_DIR
    video.SOUND_DIR = Path(tempfile.mkdtemp())
    try:
        name = next(iter(video.SOUND_SOURCES))
        path = video.sound_file(name)
        assert path.read_bytes() == b"fake mp3 bytes"
        assert len(calls) == 1
        video.sound_file(name)               # cached: no second download
        assert len(calls) == 1
    finally:
        video.urllib.request.urlopen = original_urlopen
        video.SOUND_DIR = original_dir


def test_layer_composites_premultiplied_and_respects_the_mask():
    frame = np.zeros((4, 4, 3), np.float32)
    rgba = np.zeros((4, 4, 4), np.float32)
    rgba[1:3, 1:3] = [1.0, 0.0, 0.0, 0.5]
    layer = video.Layer(rgba)
    assert (layer.y0, layer.x0) == (1, 1) and layer.image.shape[:2] == (2, 2)
    mask = np.array([[1.0, 0.0], [1.0, 0.0]], np.float32)
    layer.over(frame, mask=mask)
    assert math.isclose(frame[1, 1, 0], 0.5)
    assert frame[1, 2, 0] == 0.0


if __name__ == "__main__":
    checks = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for check in checks:
        check()
        print(f"ok  {check.__name__}")
    print(f"\n{len(checks)} checks passed")
