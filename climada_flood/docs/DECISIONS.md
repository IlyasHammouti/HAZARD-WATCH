# Verified facts and settled decisions

Purpose: load this file at the start of any new working session so that
verified findings do not have to be re-derived.

**Two kinds of statement live here, and only one of them keeps.** A
measurement — 63.5 % of built-up area inside the exclusion mask, 59 % of the
ground above 20 degrees, a factor of 42 between radar-only and merged exposure
— stays true because the ground does not move. A statement about the state of
a service does not. "No Landsat 8 or 9 scenes at all" was written about Rasuwa
and was wrong; Landsat 9 imaged the valley the day after the event at 47.5 %
cloud, clearer than any Sentinel-2 scene. The ReliefWeb API this project
nearly adopted answers 410 Gone.

So catalogue claims are no longer written down as facts. **Run
`check_sources.py`**, which re-verifies every one of them against the live
service and prints what it measured. If this document and that script
disagree, the script is right and the document is stale.

    conda run -n climada_env python check_sources.py

Last verified: 2026-08-29.

## Data sources — verified working

| Source | Endpoint / ID | Auth | Notes |
|---|---|---|---|
| GDACS event feed | `gdacs.org/gdacsapi/api/events/geteventlist/SEARCH` | None | Hard cap of 100 results per query. No pagination parameter works (`pagesize`, `limit`, `pageSize`, `count` all ignored). Filter by `eventlist=<type>` and `alertlevel=` to stay under the cap. No rate limit observed. |
| GDACS press feed | `gdacsapi/api/emm/getemmnewsbykey` | None | Returns linked news articles (EMM, JRC). Working. |
| GFM flood extent | `stac.eodc.eu/api/v1/search`, collection `GFM` | **None** | Fully open. GeoTIFF download confirmed (HTTP 206, valid TIFF). GeoVille account **not required** for programmatic access. |
| Copernicus EMS activations | `rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/?code=<EMSR code>` | None | Returns AOI geometries, products, timeline. |
| USGS earthquakes | `earthquake.usgs.gov/fdsnws/event/1/query` | None | 15 events M5.5+ in a sample week, all with ShakeMap. |

## Copernicus EMS never publishes a monetary value — checked, not assumed

The `cd_value` field exists on every damage layer of every grading product.
Across four activations and **7 855 objects** it reads `Not Applicable`
without exception. The activation statistics are counts and areas: roads in
km, population, built-up hectares, buildings identified. There is no currency
anywhere in a Rapid Mapping product.

That is the gap this project fills, and it is the answer to "is my model still
worth running when EMS covers the event so well". **They publish what was
damaged. Nobody publishes what it cost.**

### Activations are wildly unequal, which decides when to run the detector

| Activation | Products | Vectors published | Statistics |
|---|---|---|---|
| EMSR927 Nepal | **GRA × 4** | 3 207 buildings graded, roads, facilities | complete |
| EMSR921 Aragon | DEL × 2, GRA, FEP | 3 736 objects | complete |
| EMSR924 Friuli | GRA, DEL × 2, FEP | 3 339 objects | partial |
| **EMSR926 Latvia** | **DEL × 9** | **none** | **every field `-`** |

Nepal got four grading products, the most detailed level, object by object.
Latvia got delineation only: an outline and nothing else.

The rule that follows, and `FloodEvent.detect` is how it is applied:

* **EMS graded it.** Turn the detector off. They mapped the same ground by
  hand at 50 cm; our run would spend twenty-five minutes producing a worse
  outline nobody publishes.
* **EMS delineated it only.** Run the detector. We are the only source of
  anything beyond the outline.
* **EMS never came.** Run the detector, or draw by hand. We are the only
  source at all.
* **Every case, without exception.** We are the only source of the money.

## Loss from observed damage, not from assumed depth

The largest change in the chain since V1, and it comes from taking the
grading product seriously.

A depth-damage curve answers "what fraction of value is lost" by assumption:
an assumed uniform depth, on a 100 m grid, through a curve calibrated on a
different continent. A grading product answers it by observation: an operator
looked at each building in 50 cm imagery and recorded whether it is standing.

So where EMS has graded, `natcat.graded_loss` prices the observed grade
instead. Each building takes a share of the value of the exposure cell it
stands in, split between the buildings in that cell, and the loss is the sum
over grades.

| Grade | Share of replacement value |
|---|---|
| Destroyed | **1.00**, definitional rather than assumed |
| Damaged | 0.30 to 0.60 |
| Possibly damaged | 0.05 to 0.20 |
| No visible damage | 0 |

**This removes the two largest error sources at once.** Water depth is gone
entirely — there is nothing to assume. And the mechanism no longer matters: a
building destroyed by debris is destroyed exactly as much as one destroyed by
standing water, which is why the `MECHANISM` and `TERRAIN` guards do not
apply on this route. They are questions about a depth-damage curve, and no
curve is used. Refusing a graded figure because a curve we did not use would
have been misapplied is refusing the wrong thing.

What remains uncertain is also much narrower, and concentrated where it
matters least: on EMSR927, **79 % of the graded buildings are Destroyed**, the
one grade that needs no assumption. The range is published rather than a
point, exactly as the depth range was.

### The activation request carries facts nothing else does

`reason` on the activation payload is the requester's own account. For
EMSR927:

> On the 26 August 2026, a flash flood reportedly triggered by a Glacial Lake
> Outburst Flood (GLOF) in Nepal has caused significant damage in Rasuwa
> District. **There is a 7 m-deep water level recorded by monitoring
> stations.**

Seven metres, measured on the ground. This pipeline was assuming one. The
field also carries the mechanism, and the activation payload carries the
International Charter number, 1052 for this event. It is now read into
`EVENT_CAUSE`.

## V2: what changed, and the measurement that forced it

The whole event clock for EMSR927, Rasuwa, against an event at
2026-08-25 22:00 UTC. Every line measured from the service that publishes it.

| Δ | What | Source |
|---|---|---|
| +3 h | GDACS alert | GDACS |
| **+12 h** | EMS activation opened | EMS dashboard |
| +30 h | Landsat 9, 47.5 % cloud | Planetary Computer |
| +31 h | WorldView-3, Legion, Sentinel-2 at 78.5 % cloud | EMS tasking, Copernicus |
| **+45 h** | **First graded product, 433 buildings** | EMS |
| +62 h | First post-event Sentinel-1 | Copernicus Data Space |
| +67 h, +77 h | Second and third graded products | EMS |
| ~+80 h | Copernicus GFM publishes an extent | EODC |

**Copernicus EMS beat this pipeline by 35 hours with an incomparably better
product.** V1 was structured as though Sentinel were the only source, so it
waited for a radar pass that took 62 hours, then reported a tier 0 pending
note for an event that had been mapped building by building a day and a half
earlier. Everything below follows from that.

Activation latency over four consecutive activations: EMSR924 wildfire 58 h,
EMSR925 wildfire 34 h, EMSR926 flood 19 h, EMSR927 flood 12 h.

### The five changes

**1. The tier governs modelled figures and nothing else.** A verdict now
carries `tier` and `reported` separately. The tier suppresses what this
pipeline computes; figures published by a named source go out with their
attribution whatever it says. Hard fails H15 and H16 in the editorial rules.

**2. Copernicus EMS is a first-rank extent source.** `report.compute` runs the
loss chain on the EMS hand-mapped footprint where one exists, and keeps our
own detection beside it as the comparison. On EMSR927 that moved the exposed
value from 14.1 M to 131.4 M USD and the population from 568 to 5 607, because
the footprint went from a tenth of the event to the whole of it.

Coverage and assessable share follow the footprint's own provenance. Once the
outline comes from 50 cm optical, what radar could judge says nothing about
it, and leaving the radar figure in place would block a currency figure for a
weakness the footprint no longer has.

**3. Satellite passes are read, not extrapolated.** ESA publishes the
acquisition plan as KML per satellite, two to three weeks ahead, with the
footprint of every planned segment. `plan.next_look` reads it.
`natcat.next_satellite_pass` remains for the weekly digest's pending block and
is no longer the basis of any published date.

**4. Scenes come from STAC, not only from Earth Engine.** `catalog.scenes`
queries Earth Search and the Planetary Computer, neither needing an account,
and returns Sentinel-1, Sentinel-2 and Landsat in one answer. Earth Engine
keeps the global gridded data — GHSL, FABDEM, LitPop, GAUL — where there is no
latency question because the data does not change.

The four-day Earth Engine lag measured on 28 August was a snapshot, not a
property: on 29 August the same check returned a lag of 0 h. That is the point
of measuring rather than asserting, and `check_sources.py` reports the lag
every run.

**5. Activations are discovered by walking the code.** There is no public
endpoint listing activations; the dashboard demands a code and `/activations/`
answers 403. Codes are sequential and an unissued code refuses, so counting
upward from the last one seen terminates and finds new activations within
minutes. `ems.discover`.

### The publication calendar

Six post types keyed to the event clock, set out in section 3.2 of the
editorial rules. The two new ones are type 7, the activation note at T+12 h,
and type 8, the official figures at T+45 h. Type 8 is the post V1 could not
produce, and it is the one carrying content that is open but absent from the
platforms this project publishes on.

### Where the detector is worth keeping, and where it is not

On EMSR927 the detector found **10 %** of what EMS mapped, and five reasons
each sufficed on their own: 59 % of the ground above 20 degrees, a debris
mechanism rather than standing water, 5 % of the ground assessable by radar, a
single optical scene at 78.5 % cloud, and an EMS operator already there with
50 cm imagery. In that valley the detector is not a tool that needs tuning, it
is the wrong tool.

**Broken down per area, the 10 % is worse than it reads**, and the breakdown
says something the average hides:

| Area | EMS mapped | Our detection |
|---|---|---|
| Bidur, where the valley opens out | 6.02 km² | 0.87 km², **15 %** |
| Syapru Besi, in the gorge | 1.13 km² | **0.00 km²** |
| Timure, in the gorge | 1.32 km² | **0.00 km²** |

Every square metre the detector found is in Bidur, forty kilometres
downstream, where the river leaves the mountains. In the two gorge sections —
where the Rasuwagadhi dam and the Langtang Khola power house were destroyed
and 695 buildings were graded — it found **nothing at all**. Not a weak
signal: zero pixels.

That is the sharp version of the limit. The detector works where a floodplain
exists and fails completely where one does not, and the failure is not
gradual. It also settles the per-area carousel: a sheet for Timure leads with
what EMS counted, and states our blank as the finding it is.

It is kept for two jobs. Events below the EMS activation threshold — a storm
over one French department is mapped by nobody — and as the methodological
demonstration the portfolio rests on. It is no longer the product. The product
is the loss chain applied to the best available footprint, whoever drew it.

## Earth Engine is not the fastest source, and it is not the only one

Measured 2026-08-28 and 2026-08-29 over the Bhote Koshi valley,
(85.303, 28.129, 85.401, 28.300), for the Rasuwa flash flood of 25 August.

| Catalogue | Latest Sentinel-1 over the valley | Account |
|---|---|---|
| Google Earth Engine | 2026-08-24 00:18, nothing after | project id |
| Copernicus Data Space | **2026-08-28 12:21, full coverage** | none for the catalogue |
| Earth Search, AWS, Element 84 | **2026-08-28 12:21**, same granule | **none** |
| Microsoft Planetary Computer | **2026-08-28 12:21**, same granule | none, free SAS token |
| Copernicus GFM, EODC | first scenes 2026-08-28 12:21, published within about 19 h | none |

Earth Engine was **four days behind** on the one acquisition that mattered.
The pipeline already reads two catalogues that were not behind — EODC for GFM,
the Copernicus Data Space for pass dates — so the lag only bites where the
chain uses Earth Engine for imagery rather than for gridded data.

Tested and confirmed readable with plain `rasterio`, no credentials:

* Earth Search Sentinel-2 L2A: `sentinel-cogs.s3.us-west-2.amazonaws.com`,
  10 980 × 10 980 at 10 m, EPSG:32645.
* Planetary Computer Landsat Collection 2 Level 2: 7 711 × 7 841 at 30 m,
  EPSG:32645, with a token fetched anonymously from
  `planetarycomputer.microsoft.com/api/sas/v1/token/landsat-c2-l2`.

Earth Engine stays for what it is good at: global gridded datasets — GHSL,
FABDEM, LitPop centroids, GAUL — where there is no latency question because
the data does not change. For scenes of a live event, a STAC search plus a
`/vsicurl` read is both faster and simpler.

### Landsat is worth adding, and the reason is cloud, not resolution

`docs/DECISIONS.md` previously recorded "No Landsat 8 or 9 scenes at all" for
Rasuwa. That was wrong. Planetary Computer returns two Landsat 9 scenes over
the valley on **2026-08-26**, the day after the event:

| Scene | Cloud |
|---|---|
| `LC09_L2SP_141040_20260826_02_T1` | **47.5 %** |
| `LC09_L2SP_141041_20260826_02_T1` | 67.8 % |

The best Sentinel-2 scene over the same area is 27 August at **78.5 %** cloud.
Landsat 9 was both earlier and clearer, and at 30 m it is coarse for a valley
but perfectly readable for a debris field several hundred metres wide.

That is the case for Landsat in one line: it is not better than Sentinel-2, it
is *elsewhere in the sky*. Landsat crosses at about 10:00 local and Sentinel-2
at about 10:30, on unrelated repeat cycles, so on any given monsoon day the two
have independent chances of a gap in the cloud. For a peril whose binding
constraint is cloud rather than pixel size, a second optical constellation
roughly doubles the number of chances.

Not adopted for flood extent as a primary source: 30 m is wider than most
inundated strips and the JRC exposure grid is 100 m, so a Landsat-derived
extent would be coarser than the product it feeds. Adopted as a gap-filler for
photo-interpretation and, later, for wildfire, where the thermal bands and the
1982 archive have no Sentinel equivalent.

## GFM product contents

One STAC item per Sentinel-1 pass. Assets include `ensemble_flood_extent`
(20 m, consensus of DLR / TUW / LIST algorithms), `reference_water_mask`
(permanent water), `exclusion_mask` (unreliable areas), `ensemble_likelihood`.

Latency measured on EMSR664: event 2023-05-16, first GFM scene
2023-05-17 05:11 UTC — roughly 19 hours. Faster than the EMS Rapid Mapping
activation (~26 h).

## Google Earth Engine datasets — all verified present

Elevation: `COPERNICUS/DEM/GLO30_2024_1`, `projects/sat-io/open-datasets/FABDEM`,
`MERIT/Hydro/v1_0_1`, `USGS/SRTMGL1_003`, `MERIT/DEM/v1_0_3`.

Exposure: `JRC/GHSL/P2023A/GHS_BUILT_S` (100 m), `JRC/GHSL/P2023A/GHS_POP`
(100 m), `GOOGLE/Research/open-buildings/v3/polygons`.

Flood: `COPERNICUS/S1_GRD`, `COPERNICUS/S2_SR_HARMONIZED`,
`JRC/GSW1_4/GlobalSurfaceWater`, `GLOBAL_FLOOD_DB/MODIS_EVENTS/V1`.

Fire: `FIRMS` (daily), `MODIS/061/MCD64A1`, `ESA/CCI/FireCCI/5_1`.

Land cover: `ESA/WorldCover/v200` (10 m), `GOOGLE/DYNAMICWORLD/V1` (10 m),
`COPERNICUS/CORINE/V20/100m/2018` (Europe).

Rainfall and soil: `JAXA/GPM_L3/GSMaP/v8/operational` (~13 h latency),
`NASA/GPM_L3/IMERG_V07` (~24 h), `NASA/SMAP/SPL4SMGP/007` (soil moisture),
`OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02`.

Deprecated, do not use: `NASA/GRACE/MASS_GRIDS/LAND` (use `MASS_GRIDS_V04`),
`COPERNICUS/DEM/GLO30` (use `GLO30_2024_1`).

## Copernicus DEM is a DSM, not a DTM — measured

Mean elevation difference, Copernicus DEM GLO-30 minus FABDEM:

| Area | Difference |
|---|---|
| Forest, Amazon | +3.48 m |
| Forest, Landes (FR) | +1.71 m |
| Dense urban, Paris | +3.82 m |
| Bare agricultural plain | +0.13 m |

Copernicus DEM measures tree canopy and rooftops. FABDEM (*Forest And
Buildings removed Copernicus DEM*) is the bare-earth version.

**Use FABDEM for water depth.** Using the DSM overestimates ground elevation
in built and forested areas, which underestimates depth and therefore loss —
precisely where the exposed value is concentrated.

## CLIMADA capabilities

Installed: `climada` 6.1.0 (conda-forge), `climada_petals` 6.2.0 (source,
editable install from `C:\Dev\INO RE\climada_petals`).

Ready-made impact functions, six families only: tropical cyclone, European
windstorm, river flood (JRC), wildfire, drought, relative crop yield.

Hazard modules without an impact function: landslide (`HAZ_TYPE = 'LS'`).
Absent entirely: earthquake, volcanic.

**The six families are not a hard limit.** Tested and confirmed: CLIMADA
accepts a user-defined `ImpactFunc`. A step function representing total
destruction returned exactly the expected loss (2 of 5 points in footprint,
1 M each, result 2 M). Perils without a published curve are therefore
reachable — the binding constraint is the availability of a credible
damage curve in the literature, not the software.

Deprecated: `Centroids.from_lat_lon` — use the constructor directly.

## Environment

Windows. Miniforge at `C:\Users\hammo\miniforge3`, environment `climada_env`.
Run through `conda run -n climada_env python ...`; calling `python.exe`
directly fails with a GDAL DLL error because activation sets the DLL path.
Jupyter kernel registered as `Python (climada_env)`.

GEE project id: `zeta-bonfire-478712-n9`. Authenticate with
`ee.Authenticate(auth_mode="localhost")` — the default mode requires pasting a
code into a Jupyter input box that does not accept keyboard input in VS Code.

PowerShell here is 5.1: `&&` is a syntax error. Chain with `;` or `if ($?)`.

## Settled decisions

**Perils in v1**: flood, wildfire, earthquake, tropical cyclone. European
windstorm comes almost free (CLIMADA support already complete).

**Exposure**: GHSL 100 m as primary, LitPop retained as a systematic
cross-check.

**Water depth**: derived from flood extent and FABDEM (FwDET approach),
replacing the uniform-depth assumption.

**Flood extent**: GFM as primary source. The hand-rolled Sentinel-1 threshold
is kept as a methodological demonstration and as a fallback for events GFM
misses.

### Urban under-detection — measured, and the three-level response

Radar amplitude fails in built-up areas: the double bounce between ground and
walls keeps the pixel bright even when the street is under water. Measured on
EMSR664: **63.5 % of built-up area falls inside GFM's own `exclusion_mask`**,
against 58.1 % of total surface. Built-up fraction under water averages 0.0008
versus 0.0253 elsewhere — a factor of 30.

Mask semantics confirmed empirically: 100 % of flood detections sit where
`exclusion_mask == 0`, so **1 means excluded**.

Consequence: any SAR-only loss estimate is biased low, and the bias falls
exactly where value concentrates. This affects every amplitude-based
estimator, not just this pipeline.

**Level 1 — always.** Never publish a loss figure without stating the share of
exposed value that could actually be assessed. "Estimate covers 36.5 % of
exposed value; 63.5 % not assessable by radar" is defensible; the bare figure
is not.

**Level 2 — implemented.** Optical infill with Sentinel-2 MNDWI, restricted to
pixels GFM marks as excluded. MNDWI (green minus SWIR) separates water from
built-up better than NDWI. Works only on cloud-free days, so typically after
the peak. Entirely within Earth Engine. Follows UN-SPIDER *Flood Mapping with
Sentinel-1 and Sentinel-2 Imagery and Digital Terrain Models*.

Threshold calibration matters and the textbook value is wrong for this use.
Measured on EMSR664:

| MNDWI threshold | Water detected | Share of all built-up flagged |
|---|---|---|
| > 0.0 (textbook) | 90.1 km² | 8.3 % — not credible |
| **> 0.2 (adopted)** | 26.0 km² | 1.0 % — consistent |
| radar reference | 16.8 km² | 0.0 % |

Building shadows have low shortwave infrared and therefore score high on
MNDWI, and the infill is pointed at built-up land by construction. Terrain
filtering should remove more of what remains.

Merged result on EMSR664: extent 22.8 km² (16.9 radar + 6.0 recovered in the
blind spot), exposed value inside the footprint **604 M USD** against 14 M for
radar alone — a factor of 42, because the blind spot is precisely where value
sits. 58 % of the observed area remained blind to both sensors, cloud being
the limit on the optical side.

This episode is the case for the human plausibility gate: the first run was
mechanically correct and factually absurd, and nothing in the code caught it.

**Level 3 — deferred, strongest differentiator.** Sentinel-1 interferometric
coherence, the published method for urban flood detection: a flooded city
changes phase correlation even when amplitude stays bright. Needs three SLC
scenes, two before and one after. **Not feasible in Earth Engine** —
`COPERNICUS/S1_SLC` does not exist, GEE holds GRD only, where phase is
discarded. Requires external processing (SNAP, or ASF HyP3 free on-demand
InSAR). Own limitation: coherence decorrelates over vegetation without any
real change, so it complements amplitude rather than replacing it. Reference:
UN-SPIDER *Flood Mapping with Sentinel-1 Interferometric Coherence*.

**MODIS**: no ready-made daily flood product in Earth Engine. Daily
reflectance is available (`MODIS/061/MOD09GQ` 250 m, `MOD09GA` 500 m, both
2-3 days behind), so MNDWI could be computed. Does **not** help with urban
detection — 250 m is wider than a city block, and optical is cloud-blocked.
Useful only to bridge the gap between Sentinel-1 passes on large rural
floods.

**Three output tiers**, always state which one was reached:
1. Modelled loss in currency — when a damage curve exists
2. Exposed value and affected population — always available
3. Physical extent only — last resort

**Currency**: report in the source currency and base year, stated explicitly
(LitPop `pc` is constant 2014 USD), with any conversion shown alongside its
rate and year. Never convert silently.

**Runoff modelling** (SCS Curve Number from rainfall, land cover, soil
moisture): deferred to v2, and framed as early warning only. It yields runoff
volume, not extent — converting volume to extent requires hydraulic routing.

**Licensing**: code AGPL-3.0, editorial content CC BY-SA 4.0. GEE is used
under its non-commercial tier, which is the real constraint on any future
commercialisation — CLIMADA's GPL-3 is not, since it has no network clause.

**Publication**: free, no monetisation. The portfolio artefact is the
pipeline itself, not any individual post. **Weekly digest goes out Monday
morning**: a recap of the week just ended reads naturally on a Monday, and the
insurance audience plans its week then.

**Wildfire and earthquake are deferred.** Both were researched and both are
ready to build; neither is being built now, because three water-driven events
are already waiting (Latvia EMSR926, Nepal EMSR927, and a local storm in
Val-de-Marne). Covering events beats adding perils.

*Wildfire (phase 5)* is the cheaper of the two: CLIMADA ingests FIRMS directly
through `WildFire.from_hist_fire_FIRMS`, and `ImpfWildfire.from_default_FIRMS`
supplies the damage function, so only the extent and vulnerability steps
change. FIRMS is daily, so no revisit wait.

*Earthquake (phase 6)* is researched in `docs/EARTHQUAKE_VULNERABILITY.md` and
carries two blockers that are not code problems. **ESRM20** (CC BY 4.0) is the
model to use; **GEM is CC BY-NC-SA**, whose ShareAlike clause on a
NonCommercial source would contaminate every derived figure and contradict the
CC BY-SA 4.0 settled above. And the real obstacle is exposure, not hazard:
ShakeMap supplies intensity readily, but GHSL and LitPop carry no building
class, while every seismic curve is indexed by typology. Starting point if
resumed: national typology fractions weighted by replacement cost, declared as
a national average building stock.

**Local events are invisible to the automated feeds.** Copernicus EMS activates
only on request from an authorised national body, and GDACS thresholds are set
for events of international significance. A damaging storm over one French
département appears in neither. Such events need the area of interest drawn by
hand, and that manual step is where the analyst's own work shows — which is
also true of the Nepal GLOF, where GFM will produce little of use.

**Guards decide the output tier, not the operator.** `guards.py` runs before
anything is written and returns a tier; the tier picks the template, and a
figure the evidence cannot support is replaced rather than left in place.
Thresholds and their measured justifications:

| Check | Threshold | Why that number |
|---|---|---|
| `ASSESSABLE` | ≥ 35 % | Below this a loss figure describes a minority of the exposure. EMSR664 sat at 57 % and already left 43 % unaccounted for. |
| `COVERAGE` | ≥ 60 % | Below this the footprint is a sample, not a map. |
| `TERRAIN` | ≤ 25 % steep | Depth-damage curves assume a floodplain. Measured: 5 % steep in Emilia-Romagna, 59 % in Rasuwa. |
| `EXTENT` | ≥ 0.5 km² | Smaller is inside the noise despeckling exists to remove. |
| `INFILL` | ≥ 25 % radar | Optical infill corrects the radar blind spot; it does not replace the measurement. EMSR664 had 74 % of its extent from radar. EMSR926 had 13 %, and 99.3 % of the exposed value behind its loss figure came from Sentinel-2 alone. |
| `DAMAGE_RATIO` | 2–85 % | Outside this the curve is being read far from calibration. |
| `MECHANISM` | riverine, coastal, pluvial | Anything else damages by force, debris or burial, not by standing water depth. |

A block on imagery or extent means nothing was observed and the output is a
pending-case note. A block on terrain, mechanism or radar coverage still
permits exposed value and affected population — tier 2 — but never a currency
figure.

**Language**: everything public in English — code, comments, function names,
documentation, posts.

## Known reference case

EMSR664, Emilia-Romagna flood, 16 May 2023.

**Study area must come from the activation, not from a hand-drawn box.** The
initial test rectangle (11.55, 44.05, 12.30, 44.45) was arbitrary and covered
2 640 km². The eight official EMS areas span a bounding box of
**(11.3101, 43.9978, 12.4836, 44.5956)**, 6 222 km², of which 3 232 km² are
actually mapped polygons — the box alone overstates the area by 92 %, so the
polygons are rasterised and used as a mask.

Results on the official area, grid 4052 × 5158 at 20 m (20.9 M pixels):

| | Radar only | Radar + optical |
|---|---|---|
| Flooded inside mapped areas | 67.4 km² | **77.6 km²** |
| Exposed value in footprint | 164 M USD | **1 238 M USD** |

Radar coverage 87.3 % of the box, of which 57.1 % assessable — better than the
41.8 % measured on the smaller, more urban test box.

**Official figures for comparison** (whole event, wider than the mapped areas):
total economic cost ~€9 bn, the costliest weather catastrophe on record in
Italy; **PERILS final insured loss €495 m**; agriculture ~€1.5 bn with 42 % of
cultivated land flooded; roughly 50 % of economic losses fall on public
infrastructure.

The comparable benchmark is **PERILS' €495 m**, not the €9 bn. LitPop produced
capital with a residential damage curve models private built assets; it covers
neither public infrastructure nor crops, which together account for most of the
€9 bn.

### Phase 1 final result

Chain complete: GFM extent → optical infill → despeckle → GHSL/LitPop exposure
→ JRC damage curve → CLIMADA → loss.

**Depth could not be measured.** FwDET was implemented and fails structurally
here: the footprint is 5 259 fragments with a median size of 800 m² (two
pixels), and the median distance from any flooded pixel to the footprint edge
is 45 m. FwDET infers water surface elevation from footprint boundaries, so it
needs coherent polygons with an interior; speckle has none. FABDEM's vertical
accuracy is also coarser than the depths being sought. Result: median depth
0.03 m, loss 100× too low.

Response: **publish a sensitivity range, not a false-precision figure.** This
is standard practice when a parameter is poorly constrained.

| Assumed depth | Damage ratio | Modelled loss | vs PERILS |
|---|---|---|---|
| 0.50 m | 25 % | 183 M € | 0.37× |
| 1.00 m | 40 % | 293 M € | 0.59× |
| 1.50 m | 50 % | 367 M € | 0.74× |
| 2.00 m | 60 % | 440 M € | 0.89× |

Right order of magnitude across the plausible range, and **systematically
conservative** — never above the actual 495 M €. Four identified reasons, all
pulling the same way: 58 % of the area blind to both sensors; EMS mapped areas
cover only part of the insured perimeter; LitPop in constant 2014 USD with no
inflation adjustment (~15 % to 2023); residential curve only, no commercial or
industrial.

**Despeckling matters more than it looks.** Dropping fragments below 5 pixels
costs 4 % of area but 36 % of exposed value (1 238 → 793 M USD): the speckle
sat in high-value areas, i.e. optical false positives in towns. Threshold of
5 pixels adopted as the conservative choice.

**Earth Engine synchronous downloads fail with "User memory limit exceeded"**
on wide areas combined with long image collections — not a file-size limit, a
compute-memory one. `_ee_to_grid` splits requests into tiles sized to stay
under it. A plain single-band image at 20 m over the full 6 222 km² succeeds
untiled; the Sentinel-2 composite over 22 scenes does not.

### EMSR926, Latvia — run 2026-08-28, and why it is not a tier 1 post

Activation *Flood in Latvia and Lithuania*, event 2026-08-21 21:00 UTC, four
mapped areas: Kuldiga, Liepaja, Dobele, Ruba, 3 544 km² of polygons inside a
box of (20.9958, 56.2378, 23.9888, 57.4097). Post-event imagery now exists;
the block recorded before was a timing issue, not a coverage one.

Chain result, 19 GFM scenes, 16 Sentinel-2 scenes, depth assumed 1.0 m:

| | Radar only | Radar + optical |
|---|---|---|
| Extent inside mapped areas | 2.6 km² | **23.8 km²** |
| Exposed value in footprint | 0.21 M USD | **32.3 M USD** |

Every threshold passed and the first run returned **tier 1 and a €12M loss**.
It should not have. Radar produced 13 % of the extent and 0.7 % of the exposed
value; the figure was a Sentinel-2 MNDWI product wearing a Copernicus Global
Flood Monitoring credit line. The contrast with EMSR664 is the whole point:
there, radar carried 74 % of the extent area and optical recovered value in
the blind spot, which is the documented design. Here the infill *is* the
measurement.

Nothing in `guards.py` looked at what the extent was made of, only at how big
it was and how much of the area was seen. `check_infill` was added for this,
and EMSR926 now returns tier 2: extent and exposed value, no currency figure.

Open question, not settled: whether GFM genuinely saw almost no water over an
activation serious enough for four mapped areas, or whether the maximum-over-
period rule across 16 optical scenes is accumulating false positives. The
answer changes which of the two numbers is wrong.

### Revisit: two different numbers, two different questions

"Revisit" is ambiguous and the ambiguity matters operationally. Measured on the
Latvia area (21.4, 56.6, 22.6, 57.3), 1 July to 25 August 2026, at ≥ 90 %
coverage:

| Question | Answer |
|---|---|
| When is the area imaged again, any geometry? | **~1 day** |
| When is it imaged again from the *same track*? | **~6 days** |
| Same track, single satellite | ~12 days |

Which one applies depends on the method:

* **GFM** produces an extent per acquisition and needs no same-track pair, so
  the number that governs it is **~1 day**. GFM is the primary source.
* **The hand-rolled threshold** (notebooks 02 and 03) compares before and
  after, which requires the same track: a different incidence angle changes
  backscatter and manufactures false positives. There, **6 days** is correct.
  This is the fallback method.

#### A third number, and it was wrong — found 2026-08-28

`pending_cases` took its area from `gdacs_aoi`, which returns the bounding box
of the GDACS affected-area polygon. For the Rasuwa flood that box is
(83.9194, 26.9191, 86.5726, 29.3207), about 260 km across, wider than the
250 km Sentinel-1 swath. No single pass can cover it, so asking for 90 %
coverage in one day measured how often the geometry happened to be favourable
rather than the revisit cycle: **3 qualifying days in 45, a cycle of 12 days,
and a next pass of 9 September**. Over the EMS activation box for the same
event, 96 by 66 km, the answer is 7 passes, a cycle of 4 days and a next pass
of 1 September.

The weekly digest would have published 9 September while the event note
published 1 September, from the same codebase on the same day. The pass date
is the one number in the digest nobody else publishes, so being eight days
wrong on it is the worst available failure.

No warning fired, because `best_coverage` reached 0.934 and the existing
warning only triggers when *no* day clears the threshold. `natcat.clip_aoi`
now shrinks the query box to 100 km around its centre before the revisit is
measured. The centre is where the event is; the edges are what the alert
threshold threw in.

### Earth Engine does carry S1C and S1D — hypothesis tested and rejected

A working hypothesis held that Earth Engine's Sentinel-1 archive lacked the
newer satellites, which would have made every revisit estimate pessimistic.
**It is wrong.** Measured on `platform_number` in `COPERNICUS/S1_GRD`:

| Sample period | Platforms present |
|---|---|
| 2021 | A |
| 2024 | A |
| 2025 | A |
| August 2026 | **C** |

The most recent image in the whole collection was 2026-08-28 08:37, platform
**D**, on the day of the check. Ingestion is current, and both new satellites
are present.

Consequence: revisit estimates from Earth Engine are sound, and
`next_satellite_pass` needs no correction. Its earlier failure was a calling
error on this side — a date passed to the `lookback_days` argument — not a bug
in the function.

### EMSR927, Nepal — verified against the upstream catalogue

GLOF-triggered flash flood, Rasuwa district, event 2026-08-25 22:00 UTC.
Cross-checked Earth Engine against the Copernicus Data Space catalogue, which
is upstream of every mirror: **no Sentinel-1 acquisition over the area since
the event**. Last pass 2026-08-24 00:19 (S1D, track 19), 46 hours *before* the
flood. The same query over the preceding window returns results, so the empty
answer is real and not a broken request.

Optical is no help either. Sentinel-2 did pass on 2026-08-27, two days after
the event: four scenes at 54 %, 78 %, 85 % and 86 % cloud, none below the 40 %
threshold. No Landsat 8 or 9 scenes at all. Monsoon.

Terrain measured on the same area: **59 % of the ground exceeds 20°**, against
5 % in Emilia-Romagna. This is what the terrain guard is calibrated against.

#### Chain result, run 2026-08-29

Copernicus GFM published its first scenes over the valley from the 2026-08-28
12:21 UTC acquisition, with a second pass on the 29th at 00:26. The event went
from "no product" to runnable in the course of one working session, which is
the whole reason the digest now separates "imaged" from "mapped".

| | |
|---|---|
| Extent | 0.87 km² |
| From radar | 0.0004 km², **0.05 %** |
| Coverage | 100 % |
| Assessable by radar | **5 %** |
| Exposed value | 14.1 M USD, constant 2014 |
| Affected population | 568 |
| Damage curve | `Flood Asia JRC Residential noPAA` |
| Terrain | 59 % above 20° |

**Tier 2, four blockers, all correct**: `INFILL` at 0 % radar, `ASSESSABLE` at
5 %, `TERRAIN` at 59 %, `MECHANISM` on a glacial lake outburst. The chain
computed 6.96 M USD of loss internally and the tier suppressed it, which is
the behaviour these guards exist for.

**Cross-check worth publishing**: 568 people inside the footprint against the
**900** the EMS activation reports. Same order of magnitude, two independent
methods, and the gap is in the direction the coarse exposure grid predicts.

The extent rests on **one Sentinel-2 scene at 78.5 % cloud**. Radar saw
nothing usable: shadow and layover in a valley where 59 % of the ground is
steep. Treat the figure as the weakest kind of observation, and prefer the
hand-drawn outline on the 0.5 m WorldView-3 ortho, which now has this to
compare against.

**Attribution error found in the draft and fixed.** The first draft opened
"from the Sentinel-1 pass of 2026-08-28 12:21 UTC" and credited
`L-SRC-GFM`, for an extent radar contributed 0.05 % of. The sentence and the
source credit now follow whichever sensor produced the footprint, decided by
the same 25 % threshold as `check_infill`, and `L-SRC-OPTICAL` was added for
the optical case. Latency is stated in days when the extent is optical,
because a Sentinel-2 acquisition date is known to the day and quoting hours
would be precision the source does not carry.

#### What the responders counted, read from the GeoPackages 2026-08-29

The grading packages for AOI01 Syapru Besi, AOI02 Timure and AOI03 Bidur,
read with `natcat.ems_vectors` and summarised with `natcat.ems_damage_summary`.

| | |
|---|---|
| Observed event, mapped by hand | **8.33 km²** in 4 polygons, all typed `6-Mass Movement / Landslide` |
| Area EMS was asked to map | 27.5 km² |
| Ground inside it that could not be read | 2.49 km² |
| Buildings graded | **3 207** |
| Destroyed | **2 521**, 79 % |
| Damaged | 285 |
| Possibly damaged | 401 |
| Roads mapped | 148.7 km |
| Roads destroyed | **47.4 km**, 32 % |
| Facilities destroyed | 14 of 16 graded |

An earlier version of this table said 21.3 km of roads with 15.7 km destroyed.
That was wrong, and the reason is worth keeping: the GeoPackage reader was
silently dropping the 613 road features of the Bidur package while reporting
the other two areas as if they were the whole. The published GeoJSON, which
`ems.vectors` now prefers, returns all 650. The building counts were identical
either way, which is exactly why the error survived a first look.

Named among the destroyed facilities: **Langtang Khola Hydroelectric Power
House 20MW**, the **Rasuwagadhi Hydropower Dam**, and **Trishuli Power House**,
plus further dams, an aqueduct and an industrial plant.

**This is the comparison that matters.** The chain detected **0.87 km²**
against the 8.33 km² EMS mapped: **10 %**. Every guard that fired was right,
and the size of the gap says why. A Sentinel-2 scene at 78.5 % cloud, over a
valley where radar could assess 5 % of the ground, finds a tenth of what an
operator finds in 50 cm imagery.

It also settles what the loss chain would have been modelling. A depth-damage
curve applied here would have been pricing standing water against a hydropower
corridor destroyed by debris and force, in which 74 % of the roads were carried
away. The `MECHANISM` guard refuses on principle; the vector data shows what
the principle was protecting against.

#### EMS tasked commercial imagery and delivered, checked 2026-08-28

The conclusion "nothing observed, tier 0 pending note" was right about
Sentinel-1 and Sentinel-2 and wrong about the event. Copernicus EMS Rapid
Mapping tasked very high resolution optical imagery and delivered graded
products on 27 August:

| Area | Sensor | Acquired | Status |
|---|---|---|---|
| AOI01 Syapru Besi | WorldView-3 | 2026-08-27 05:05 | delivered |
| AOI02 Timure | Legion | 2026-08-27 05:05 | delivered |
| AOI03 Bidur | BlackSky, Satellogic | 2026-08-27 | in production |
| AOI04 Bharatpur | Legion | 2026-08-29 04:01 | expected |

Open, no account needed, vectors as GeoJSON under the same S3 bucket as the
tiles. AOI01 alone carries 433 building points with a `damage_gra` grade;
activation totals are 864 identified buildings, 900 people, 11 ha built-up,
16 km of roads, 240 for `max_extent`.

Two consequences.

**The chain is blind to the source that covers its own blind spot.**
`compute()` asks GFM and nothing else. EMS tasks commercial VHR exactly when
Sentinel fails — steep terrain, cloud, flash floods — and delivers in about
48 hours. Every event where the pipeline reports "no imagery" is an event
where EMS is most likely to have some.

**EMS reaches the mechanism guard's conclusion from the imagery.** The
observed-event polygon at Syapru Besi is typed `6-Mass Movement`, described
`Landslide`, method `Photo-interpretation`. The refusal to run a depth-damage
curve here is not this project's opinion; it is what the official mapper
recorded after looking at 30 cm imagery.

### Val-de-Marne storm, 26 to 27 August 2026 — measured 2026-08-28

Nothing to draw from, and this is measured rather than assumed. Box
(2.32, 48.68, 2.62, 48.86), 22 by 20 km.

| Source | Finding |
|---|---|
| Sentinel-1 | Full coverage 20, 23, 24 and 26 August. Last acquisition 2026-08-26 17:39 UTC, S1D track 59 ascending. Nothing since. |
| Sentinel-2 | 25 August, 27 % cloud, before the event. 27 August, 72 % and 100 % cloud. |
| GSMaP hourly | About 15 mm over the department on 27 August, under 1 mm on 26 August. |

Fifteen millimetres in a day is an ordinary wet day. A short convective cell is
exactly what a 10 km hourly rainfall product smooths away, so this is a limit
of the instrument rather than a finding about the storm. Either way there is no
satellite evidence to draw an outline from today, and an outline drawn over
imagery that shows nothing would be an assertion in the shape of a
measurement. Method and the two honest alternatives:
`docs/MANUAL_DELINEATION.md`.
