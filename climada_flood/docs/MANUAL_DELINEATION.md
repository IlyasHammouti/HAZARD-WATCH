# Drawing the affected area by hand

Written 2026-08-28.

Copernicus Global Flood Monitoring covers routine flooding on flat, open
ground. It covers nothing else, and the events it misses are not a marginal
category: a torrent in a valley, a flash flood that has drained before the
next radar pass, a storm over one department that no national authority asked
to have mapped. For those, somebody has to read the imagery and draw the
outline.

This is a recognised method, not a workaround. Copernicus EMS Rapid Mapping
operators produce their delineation and grading products exactly this way, and
their own vector attributes record it: `det_method: Photo-interpretation`.
Their outlines carry weight because every product ships with the scene it was
drawn from, its sensor, its acquisition time and its resolution.

That is the whole condition. **A drawn outline is published together with the
imagery it was drawn from, or it is not published.** A reader cannot tell a
drawn line from a detected one by looking at it, so the post has to say which
it is, and hand over enough for the reader to go and look at the same picture.
`manual.py` enforces this by refusing to load a file whose provenance is
incomplete, and `guards.check_provenance` puts the disclosure into the draft.

---

## When this applies

Draw by hand only when all three hold.

1. The automated products return nothing usable, and the reason is known and
   can be written in one sentence.
2. Post-event imagery exists, covers a usable share of the area, and can be
   named.
3. What is visible in that imagery is the thing being drawn.

Point 3 is the one that fails most often, and it is the one that matters. A
polygon over a satellite image that shows nothing is not an observation. It is
an opinion drawn at the right map scale, and publishing it would undo the
entire reason `guards.py` exists.

**If post-event imagery does not exist yet, the answer is the pending-case
note, not a drawing.** The next-pass date is already published in the weekly
digest, and waiting is a defensible editorial position. Drawing is not.

---

## What may be drawn

| Drawn | Not drawn |
|---|---|
| Water visible in a post-event scene | Water inferred from where a river usually floods |
| Debris fields, scour, changed channels | Damage assumed from the shape of the terrain |
| Buildings visible as destroyed or damaged | Buildings assumed affected because they are inside the outline |
| The boundary of what the operator could see | The boundary of the administrative unit |

The last row is the trap for local events. A department boundary is not a
hazard footprint, and a list of communes recognised under a natural-catastrophe
decree is an administrative record rather than an observation. Both are usable
and both are citable, but they are a different claim and they belong in a
different sentence.

---

## Procedure

**1. Fetch and process the imagery.** One call. It selects the scenes, applies
the band combinations, writes GeoTIFFs, and records what it used and what it
rejected.

```bash
conda run -n climada_env python -c "import ee; ee.Initialize(project='zeta-bonfire-478712-n9'); import manual; manual.prepare_imagery((85.303,28.129,85.401,28.300), '2026-08-26', out_dir='data/manual/EMSR927', emsr_code='EMSR927')"
```

What lands in the folder:

| File | What it is for |
|---|---|
| `s2_pre_<date>_truecolour.tif` | The ground before, for comparison |
| `s2_post_<date>_truecolour.tif` | What it looks like now |
| `s2_*_falsecolour.tif` | Near infrared. Water reads near black, vegetation bright red. The fastest way to see a water edge |
| `s2_*_mndwi.tif` | Green minus shortwave infrared. Above 0.2 is water; the threshold is calibrated in `DECISIONS.md` |
| `s1_post_<date>_vv_db.tif` | Radar backscatter. Flat water reads dark through any cloud |
| `s1_pre_<date>_vv_db.tif` | Same relative orbit as the post scene, never a different one |
| `s1_change_vv_db.tif` | After minus before. Strongly negative is a new smooth surface, which is usually water |
| `layers.txt` | Every layer path, best first, ready to drag into QGIS |
| `manifest.json` | Scenes used, scenes rejected, and a provenance skeleton already filled from the catalogue |

Two behaviours are deliberate. The Sentinel-1 pair is locked to one relative
orbit, because a different incidence angle changes backscatter on unchanged
ground and manufactures a flood signal. And the post-event Sentinel-2 scene is
**not** rejected for cloud: a partly clouded scene is often the only one there
is, and deciding what is readable is the operator's job rather than a
threshold's.

Where the event has a Copernicus EMS activation, `layers.txt` also lists the
very high resolution orthos EMS published, as `/vsicurl/` paths. QGIS opens
those remotely without downloading the scene. They are typically 30 to 50 cm
and they are better than anything Sentinel can offer.

**2. Load from `layers.txt`, never from a basemap.** A satellite basemap in
QGIS is a mosaic of undated scenes and it is the fastest way to draw an
outline from a picture taken two years before the event.

**3. Draw at a fixed scale.** Pick one scale, note it, and stay at it. An
outline drawn at 1:5 000 in one place and 1:50 000 in another has two
different meanings and no way to tell them apart afterwards.

**4. Draw the visible extent only.** Where cloud, shadow or terrain hides the
ground, stop the polygon and record the gap under `limitations`. Do not close
a polygon across an area that was not seen. A hole in the outline is
information; a smooth outline over an unseen area is not.

**5. Save as GeoJSON in EPSG:4326**, into the same folder, named
`<event>_<date>.geojson`. One feature per distinct area, each with a `name`.

**6. Paste the provenance block.** It is already written for you in
`manifest.json` under `provenance_skeleton`, with the scene identifiers,
acquisition times and resolutions filled from the catalogue. Copy it to the
top level of the GeoJSON, next to `features`, and replace the fields marked
`REPLACE`: who drew it, the share you could actually read, and what you could
not see. `data/manual/TEMPLATE.geojson` shows the finished shape.

**7. Load it and let it be refused.** `manual.load_footprint` raises on a
missing field rather than warning, because nothing downstream can catch the
error later.

```bash
conda run -n climada_env python -c "import manual; print(manual.load_footprint('data/manual/TEMPLATE.geojson', event_date='2026-08-27')['area_km2'])"
```

**8. Run the chain.** Set `footprint_path` on the `FloodEvent` and call
`make_post` as usual. Exposure, the damage curve and the guards are the same
code as for a GFM footprint; only the extent came from somewhere else.

---

## The provenance block, field by field

Every field is required. Each one answers a question a reader is entitled to
ask of a line somebody drew.

| Field | Answers |
|---|---|
| `operator` | Who drew it |
| `drawn_on` | When, ISO date. A footprint redrawn after more imagery arrived is a new file, not an edit |
| `method` | How. `photo-interpretation` for visual reading; anything else is spelled out |
| `imagery` | One entry per scene: `sensor`, `scene_id`, `acquired`, `resolution_m`. The scene identifier matters more than the sensor name, because it is what makes the work repeatable |
| `coverage` | Share of the area of interest the imagery covered at all, 0 to 1 |
| `assessable` | Share of that imagery the operator could actually read. Cloud, shadow and radar layover come off here |
| `limitations` | What the operator could not see, in plain words. This sentence is published verbatim inside `L-DRAWN` |
| `scale` | Optional, the drawing scale, e.g. `1:10000` |
| `rejected` | Optional, scenes considered and not used, with the reason |

`load_footprint` also refuses a file whose scenes all predate the event. That
is the one provenance error that produces a plausible, entirely wrong result,
so it is checked rather than trusted.

---

## What the guards do with it

`check_provenance` never blocks a drawn footprint and never approves it
either. It returns a warning, always, whose text names the operator and the
scenes, and that warning travels into the draft. The other guards are
unchanged: terrain, mechanism, extent, assessable share and damage ratio apply
exactly as they do to a GFM footprint, and a drawn outline over 59 per cent
steep ground is refused a currency figure for the same reason a detected one
is.

A drawn footprint is therefore allowed to reach tier 1. It is not allowed to
reach it quietly.

## What the post must say

Two locked strings, both mandatory, both hard fails if missing (H13):

- `L-SRC-MANUAL` in the sources, naming operator, date, method and scenes.
- `L-DRAWN` in the body, carrying the operator's own `limitations` sentence.

Neither is a disclaimer in the legal sense. They are the difference between a
measurement and an assertion.

---

## The two live cases, as of 28 August 2026

**EMSR927, Nepal, Rasuwa.** Prepared and ready to draw. Measured on the Bhote
Koshi valley, (85.303, 28.129, 85.401, 28.300):

| Source | State on 28 August 2026 |
|---|---|
| EMS ortho, WorldView-3 | Syapru Besi, 27 August 05:05, **0.5 m, three bands, opens remotely**. The best imagery available |
| EMS ortho, Legion | Timure, 27 August 05:05 |
| Sentinel-2 post | 27 August, 78.5 per cent cloud. Written out anyway; the operator judges what is readable |
| Sentinel-2 pre | 12 August, 18.7 per cent cloud. Clean reference |
| Sentinel-1 | **Imaged 28 August, full coverage**, in the Copernicus Data Space catalogue. Not yet in Earth Engine, so no radar layer was written |
| Copernicus GFM | No scene over the valley at all since the event |

Draw on the WorldView-3 ortho where it covers the ground, and on the
Sentinel-2 pair outside it. EMS has published its own graded product for
Syapru Besi and Timure; an outline drawn here is a second reading of the same
imagery, so say which areas it overlaps and compare the two rather than
presenting it as new coverage.

The mechanism is already settled by the source: EMS classifies the observed
event at Syapru Besi as `6-Mass Movement`, a landslide. The official mapper
reaches the same conclusion as the `MECHANISM` guard, from imagery rather than
from a threshold, so no depth-damage curve applies whatever the outline shows.

The Sentinel-1 gap is an ingestion lag rather than an absence, and it is worth
knowing which catalogue is being asked. Earth Engine held nothing over the
valley after 24 August; the Copernicus Data Space held a full-coverage
acquisition on 28 August. Rerun `prepare_imagery` once Earth Engine catches up
and the radar layers appear.

**Storm over Val-de-Marne, 26 to 27 August 2026.** There is nothing to draw
from yet, and this is measured rather than assumed. Sentinel-1 covered the
department fully on 20, 23, 24 and 26 August; the 26 August acquisition was at
17:39 UTC, and nothing has passed since. Sentinel-2 passed on 25 August at 27
per cent cloud, before the event, and on 27 August at 72 and 100 per cent
cloud. Satellite rainfall over the department gives about 15 mm on 27 August
and under 1 mm on 26 August, which is an ordinary wet day rather than evidence
of a damaging storm; a short convective cell is exactly what a 10 km hourly
rainfall product smooths away, so this is a limit of the instrument and not a
finding about the storm.

An outline drawn today over Val-de-Marne would be drawn over imagery showing
nothing. The honest routes are to wait for the next Sentinel-1 pass, or to
build the affected area from the French administrative record, which is a
different and clearly labelled claim.
