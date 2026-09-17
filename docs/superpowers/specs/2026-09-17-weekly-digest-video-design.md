# Weekly digest: video instead of list

Status: proposed. Written 2026-09-17.

## Problem / goal

Type 1 (weekly digest) is currently a static PNG figure + plain text
(`report.weekly_digest`, `report.py:2622`). It carries the whole week as a
table and reads well, but it does not show *what happened* — a flood extent,
a cyclone track, an eruption plume are all reduced to a name and an alert
level.

Goal: replace the Type 1 post with a short animated video that walks through
the week's events in chronological order, on a world map, with each
event's own geometry animating (cyclone track drawing itself, epicentre
pulsing, country border filling in for drought), then a final wide shot
with everything from the week overlaid at once.

This replaces the digest entirely — no more list-format Monday post.
Selection logic (which events qualify, GDACS alert-level filtering,
Green top-ups) is unaffected; what changes is the *rendering* of the
already-selected events, plus a second selection layer described below.

Phase 1 (this spec's implementation target): **cyclone only**, via IBTrACS.
Earthquake, volcano, tsunami, drought, flood, wildfire are designed here for
architectural consistency but not built until the cyclone pipeline is
validated end to end.

## Hazard categories

Not every GDACS event type gets the same treatment. Three categories,
decided by what geometry is reliably available on Monday morning, not by
severity:

### Category A — dedicated scene (zoom + animate)

Cyclone, earthquake, volcano, tsunami, flood, wildfire.

All six have a point or line geometry that is available without waiting on
a satellite pass: GNSS epicentre, volcano coordinates, IBTrACS track, or
(for flood/wildfire) the GDACS event centroid — no footprint polygon
required. This is what makes them eligible for a scene even before any
polygon exists for the week.

Two overlay types cover all six:

- **Track** (cyclone only): the IBTrACS points for the week, coloured by
  Saffir-Simpson category, drawn progressively along the animation.
- **Point pulse** (earthquake, volcano, tsunami, flood, wildfire): a single
  coordinate, animated as an expanding ring scaled by the event's existing
  `alert_score` (already computed by `natcat.py` for every GDACS event —
  no new severity metric to build). Flood/wildfire get this treatment, not
  a polygon reveal: no footprint animation in v1, regardless of publication
  day (see "Publication day" below).

### Category B — final wide shot only, no dedicated scene

Drought.

Not point/line-shaped and not visually dynamic enough to justify a zoom-in
scene. Shown only in the video's closing wide shot: for each drought-hit
country, the national border animates in (draw-on, then fill), followed by
the country name and the drought's start date in fade-in text. Uses Natural
Earth admin-0 boundaries — the same source already feeding the country/water
labels drawn by `carto.place_label` — so no new data dependency.

### Publication day

Stays Monday, fixed. The alternative (publish Wednesday, wait for
flood/wildfire footprint polygons) was considered and rejected: it would
only benefit 2 of 6 hazard types, breaks the "Monday digest" promise, and
adds a dependency on satellite timing to the editorial calendar — the kind
of fragility `HANDOVER.md` has already had to fix elsewhere (GDACS
timeouts, Earth Engine initialisation). Flood/wildfire are Category A with
point-only geometry, unconditionally — not contingent on whether a polygon
happens to be ready.

## Event selection: human picks, not an automatic cap

No automatic ranking/cap algorithm. The pipeline proposes; the user
decides — consistent with the automation boundary already stated in
`POST_TYPES.md` ("Human: choosing the event... checking that the figure is
plausible... approving before publication").

1. `list_candidate_events(week_start, week_end)` returns every Category A
   event for the week (peril, region, `alert_score`, an estimated scene
   duration), for the user to read.
2. The user picks a subset and an order — to control geographic variety and
   avoid over-representing one region, which is a judgement call the code
   has no basis to make.
3. `build_video_timeline(selected_events)` turns the picks into the scene
   list the renderer consumes.

Category B (drought) is not part of this manual pick — every drought-hit
country of the week appears automatically in the closing wide shot, since
it costs one extra element on an already-planned scene, not a new one.

### External clip insert

Alongside the picked event list, the user may attach a clip per event:
`{clip: <file path>, source: "<attribution text>"}`. Rights and sourcing
are the user's responsibility before the file is ever handed to the
pipeline — nothing here searches for, fetches, or downloads third-party
video. (Automated cross-platform video search/download was considered and
rejected: no platform except YouTube exposes a usable free search API, and
downloading footage does not confer the right to republish it — a real risk
for a portfolio channel a recruiter will actually watch.)

When present, the clip becomes a fourth scene type, inserted immediately
after that event's Category A scene and before the transition to the next
one. The source is burned into the clip as on-screen text (same typographic
treatment as `carto.footer`'s disclaimer strip) — required because 79-92%
of LinkedIn video plays muted, so an attribution that is only spoken is
effectively invisible. Clip duration: native length by default; trimming is
a manual, per-clip decision (no fixed cap in code).

## Rendering architecture

Three layers. The one rule that drives all three: **Cartopy renders a
keyframe once per geographic zone, never once per video frame.**
`carto.py`'s basemap draw (`draw_basemap`) and the rest of its chrome
(header, footer, locator, legend) are comparatively expensive; re-running
them 24-30 times/second for a transition would cost minutes of render time
for an effect a viewer cannot distinguish from a cheap affine pan on a
pre-rendered image.

1. **Keyframe raster** — one Cartopy render per zone (world, and one per
   selected Category A event's extent), slightly oversized versus the final
   crop to leave pan headroom. Uses `carto.frame_extent` for the bounding
   box and the existing basemap/label/chrome functions as-is — no new
   cartography code.
2. **Overlay animation** — PIL/OpenCV compositing on top of the frozen
   keyframe raster, not matplotlib: the progressing track line, the
   expanding pulse ring, the border draw-and-fill, label fade-ins. Pure
   pixel compositing is fast and frame-accurate without re-invoking Cartopy.
3. **Transition between zones** — moviepy's own `resize(lambda t: ...)`
   / `set_position(lambda t: ...)` / `crossfadein`, applied to the two
   already-rendered keyframe rasters. No custom per-frame reprojection, no
   raw ffmpeg filtergraphs (harder to maintain and explain than the moviepy
   Python API). If the angular distance between two consecutive zones is
   large enough that a straight pan would look like it's crossing an
   impossible arc (e.g. Pacific to Atlantic), use a hard cut with crossfade
   instead of a pan — a simple threshold check on the two extents' centres.

Cyclone track interpolation uses **MovingPandas** (`Trajectory.get_position_at`
et al.) on the week's IBTrACS points, rather than hand-written interpolation
— it turns irregular 3h/6h track fixes into a smooth position at any point
in the animation's timeline for free.

Considered and rejected for the animation engine itself:

- **QGIS Temporal Controller** — mature animation tooling the user already
  knows, but each week's geometry differs (different storms, different
  zones), so it would need reconfiguring by hand every Monday or scripted
  via PyQGIS — a second full GIS runtime alongside the conda stack already
  planned (CLIMADA, Cartopy, GeoPandas), for a data volume (a handful of
  zoomed scenes a week) that doesn't need it.
- **kepler.gl / deck.gl `TripsLayer`** — the most capable trajectory-drawing
  engine available, but it means adding a JS/headless-browser runtime to a
  Python-only pipeline for GPU-scale trail rendering this project will
  never approach.
- **Flourish** — no-code animated-map templates including hurricane
  tracks, but it's an external SaaS: breaks the local, reproducible,
  scriptable pipeline the rest of the project is built on, and would need
  the project's own conventions (peril colour coding, disclaimer,
  locator) re-implemented inside someone else's template constraints.

## Data pipeline — phase 1 (cyclone)

- **Source**: IBTrACS.ACTIVE (NOAA), re-downloaded each Monday. Small CSV,
  no need for the heavier caching pattern already used for scene data in
  `data/cache/`.
- **Join to the week's GDACS selection**: GDACS and IBTrACS share no common
  ID. Join by storm name + basin + a time window overlapping the digest
  week. Flagged as an empirical risk to validate during implementation, not
  a blocker to this design.
- **Intensity per point**: max wind → Saffir-Simpson category, colours the
  track segment-by-segment. Consistent with the peril-colour system already
  in `carto.PERIL_COLOURS`.
- **Zoom extent**: bounding box of the week's track plus margin, through
  the existing `carto.frame_extent`.
- **Toponyms**: the same label source already used by `place_label` /
  `label_is_clear` for the current digest figure, filtered to the scene's
  bounding box and a rank threshold scaled to zoom level.

Extending to earthquake/volcano/tsunami/flood/wildfire/drought later needs
no new engine — only a new overlay spec (point pulse, or the border
draw-and-fill for Category B) and a new data source per hazard (USGS or
GDACS coordinates for quake/tsunami, Smithsonian GVP for volcano, GDACS
centroid for flood/wildfire). The scene builder, keyframe renderer and
transition logic are unchanged by adding a hazard type.

## Format

Portrait 1080×1350 (`carto.PORTRAIT`) — reused as-is from every other post
type, and confirmed by research as the right choice independent of that
reuse: LinkedIn's own B2B video guidance measures a lift in click-through
for vertical formats on mobile feeds, where most LinkedIn video is watched.

Total video length is not a fixed target — it follows from how many
Category A events the user picks and how long each scene needs, not the
reverse. This was an open question earlier in the design (a hard 30-45s
budget was assumed at first) and is now resolved by data: LinkedIn's actual
engagement rate is flat (~5.6-5.8%) from 0-90s and *peaks at 6.6% in the
120-180s window*, only dropping past three minutes (Socialinsider,
aggregate LinkedIn video benchmarks). There is no engagement penalty for
letting the video run as long as the picked events need, up to roughly
2-3 minutes.

Every scene, and the video as a whole, carries burned-in text (titles,
dates, source attribution, drought/flood/wildfire labels in the closing
shot) — not optional styling but a direct response to sourced data: 79-92%
of LinkedIn video plays with sound off.

Sources for the format decisions above:
- [Best practices for video ads | LinkedIn Ad Tips](https://business.linkedin.com/marketing-solutions/success/best-practices/video-ad-tips)
- [B2B Video on LinkedIn: 13 Best Practices](https://www.linkedin.com/business/marketing/blog/content-marketing/13-top-tips-for-compelling-b2b-video-content-on-linkedin)
- [Social Media Video Statistics 2026: Engagement & Views — Socialinsider](https://www.socialinsider.io/social-media-benchmarks/social-media-video-statistics)

## Video assembly

moviepy assembles the final file from the scene list `build_video_timeline`
produces, in order:

1. World intro keyframe (no risk layers), held static for a few seconds.
2. For each selected event, in the user's chosen order: its keyframe +
   overlay animation, immediately followed by its external clip scene if
   one was attached, then a transition (pan or cut, per the threshold rule
   above) to the next event's keyframe.
3. World outro keyframe, transitioned into from the last event, holding
   every selected event's static layer plus every Category B (drought)
   country's border/fill/label animation.

Each scene in the list is a plain data structure (extent, overlay type,
overlay data, duration, optional clip path/source) — moviepy, the PIL
overlay compositor and the Cartopy keyframe renderer each consume this list
once, independently. Nothing in the assembly step needs to know where an
event came from (GDACS, IBTrACS, a user-picked clip) — only what kind of
scene it is.

## Integration point

A new function alongside the existing `weekly_digest` machinery in
`report.py`:

- `list_candidate_events(week_start, week_end)` — read-only, surfaces
  Category A candidates for the user to pick from. Built on the same
  `natcat.gdacs_events` / IBTrACS join already described, not a new
  selection pipeline.
- `build_video_timeline(selected_events, clips=None)` — takes the user's
  picks (and optional clip attachments) and returns the ordered scene list
  described above.
- The rendering/compositing/assembly steps consume that scene list and
  produce the final MP4. `weekly_digest`'s existing event-gathering,
  Green top-up and featured-history logic (`report.py:2622` onward) is
  reused unchanged as the source of *which events exist*; only the output
  stage (currently the PNG figure + plain text) is replaced.

## Open items for implementation time, not blocking this design

- Exact GDACS↔IBTrACS join key reliability (flagged above).
- Whether `alert_score` scales the point-pulse animation linearly or needs
  a perceptual curve (e.g. log) so a magnitude-9 quake doesn't dwarf a
  magnitude-6 one into invisibility.
- Cartopy render time per keyframe, to confirm the "keyframes only, never
  per-frame" budget actually holds at video frame rates once built.
