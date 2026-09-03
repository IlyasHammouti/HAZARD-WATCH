# Handover — state of the project, and what to do next

Version 2, written 2026-08-29. Read this first, then `DECISIONS.md`.

The owner does not write Python. Explain what each step does and why, do not
hand over finished files without walking through them.

---

## What this project is

A pipeline that takes a real natural catastrophe and produces a quantified
damage estimate, following the structure of a catastrophe model:

```
Hazard × Exposure × Vulnerability = Loss
```

It exists to demonstrate, to a reinsurance recruiter, an understanding of that
chain and the ability to produce defensible figures. Target: an internship at
Swiss Re, Zurich, February 2027.

**V2 changed what the product is.** V1 treated flood detection as the
deliverable and everything downstream as plumbing. Then EMSR927 measured it:
the detector found 10 % of what Copernicus EMS mapped by hand, and EMS
delivered a building-by-building product 35 hours before this pipeline had an
extent at all.

So the product is the **loss chain applied to the best available footprint**,
whoever drew it, with an honest account of which source that was. Detection is
a fallback for events nobody else maps, and a demonstration of method.

---

## The shape of V2

Five modules feed one assembly point.

| Module | Answers |
|---|---|
| `natcat.py` | GDACS events, GFM extent, exposure, damage curve, loss |
| `ems.py` | Which activations exist, when, what was tasked, what was counted |
| `plan.py` | When the ground is next planned to be imaged, from ESA's own plan |
| `catalog.py` | What has actually been imaged, across every open catalogue |
| `manual.py` | Imagery prepared for hand delineation, and the provenance gate |
| `guards.py` | What the evidence supports, split from what may be reported |
| `report.py` | The chain, the maps, the drafts, the weekly digest |
| `carto.py` | The visual identity |
| `check_sources.py` | Whether anything this documentation claims is still true |

### Two vulnerability routes, and the better one wins

`report._loss` picks between them:

* **Graded.** Where Copernicus EMS has looked at every building in 50 cm
  imagery and recorded whether it is standing, the loss is priced from the
  observed grade. No assumed depth, no borrowed curve, and no mechanism to
  worry about. `natcat.graded_loss`.
* **Depth-damage.** Everywhere else. An assumed uniform depth through a JRC
  curve on a 100 m grid, which is V1's route and still the only one available
  when nobody has graded anything.

The graded route removes the two largest error sources in the project at once,
which is why `MECHANISM` and `TERRAIN` do not block on it: both are questions
about a depth-damage curve, and no curve is used.

**EMS publishes no monetary value, ever.** `cd_value` reads `Not Applicable`
on all 7 855 objects across four activations. They publish what was damaged;
this project publishes what it cost. That is the whole differentiator, and it
holds even on an event as thoroughly covered as Rasuwa.

### Whether to run our own detection: `FloodEvent.detect`

Decided per event, from what EMS delivered.

| EMS delivered | Run the detector? |
|---|---|
| Grading products | **No.** They mapped the same ground by hand at 50 cm |
| Delineation only | Yes. We are the only source beyond the outline |
| Nothing | Yes, or draw by hand |

### The extent source ladder

`report.compute` takes the footprint from the first source that has one:

1. **Copernicus EMS**, where operators mapped the event by hand from 30 to
   50 cm imagery. Better than anything this chain detects.
2. **A hand-drawn outline**, where `footprint_path` is set.
3. **GFM radar plus Sentinel-2 infill**, the V1 path.
4. Nothing, which is a pending note and not a failure.

Where the detector is run, the ratio between what it found and what the
official map holds is published as a finding. That ratio is the honest thing
this project can say about its own detector, and on EMSR927 it is 10 %.

### The tier no longer gates the post

A verdict carries `tier`, which limits what this pipeline may compute, and
`reported`, which holds figures a named source published. The tier does not
touch the second. This is the change everything else in V2 hangs from: V1
published no figure at all for Rasuwa while Copernicus EMS had counted 2 521
destroyed buildings in the same valley.

Hard fails H15 and H16 in `EDITORIAL_RULES.md` make the separation binding.

### The publication calendar

Six post types keyed to the event clock, in section 3.2 of the editorial
rules. Types 7 and 8 are new: the activation note at T+12 h, and the official
figures at T+45 h. Type 8 carries content that is open and absent from the
platforms this project posts to, which is the clearest value it has.

---

## What works today

| Component | File | State |
|---|---|---|
| Loss from observed damage grades | `natcat.graded_loss` | Working, EMSR927 at tier 1 |
| Activation watch and drafting | `watch.py` | Working, never publishes |
| GDACS watch and weekly digest | `natcat.py`, `report.py` | Working, published format |
| EMS activation discovery, timings, damage vectors | `ems.py` | Working |
| ESA acquisition plans | `plan.py` | Working, plans to 2026-09-14 |
| STAC scene search, three sensors, two catalogues | `catalog.py` | Working |
| Imagery preparation for hand delineation | `manual.py` | Working |
| GFM extent, optical infill, exposure, loss | `natcat.py` | Working |
| Guards, tiers, reported facts | `guards.py` | Working |
| Maps, digest figure | `carto.py`, `report.py` | Working |
| Source verification | `check_sources.py` | Working, 10 checks |

Reference case EMSR664, Emilia-Romagna: modelled loss €293M against PERILS'
€495M, a range of 0.37 to 0.89× over plausible depths, always below.

---

## What is solid, and what is not

| Element | Confidence | Basis |
|---|---|---|
| EMS mapped extent | **High** | Photo-interpretation of 30 to 50 cm imagery |
| Flood extent, GFM | High | Official product, three-algorithm consensus |
| Own detection | **Low on hard ground** | 10 % of the official map on EMSR927 |
| Exposed value | Moderate | Published JRC and World Bank data |
| Damage curve | Moderate | Published, peer-reviewed, per continent |
| Damage from EMS grades | **High** | Observed per building, not inferred |
| **Water depth** | **Low** | Assumed, not measured. Dominates the depth route |
| Value per building | Moderate | National aggregate, not a local valuation |
| Exposure resolution | Moderate | 100 m, not per building |

**Depth is still the weak link, on the route that still needs it.** FwDET
fails structurally on fragmented footprints, so the depth route publishes a
sensitivity range and never a single figure. The graded route does not use
depth at all, and its own range is far tighter: 7 % of the upper bound on
EMSR927, against a factor of 2.4 for depth on EMSR664.

**The detector is weak where the ground is hard.** Steep terrain, debris
mechanisms, small footprints, cloud. Named and measured rather than hidden.

---

## What to do next, in order

### 1. Publish the weekly digest, Monday morning

```bash
conda run -n climada_env python -c "import report; d=report.weekly_digest(monday='2026-08-31'); print(d['words'], d['plain_path'], d['figure_path'])"
```

Writes the draft, the plain text that gets pasted, and the figure carrying the
title, the dates and every event of the week.

### 2. Publish EMSR927, Nepal — ready

Everything is written and every slot is filled. The chain runs on the
Copernicus EMS footprint, prices the observed damage grades, and returns
**tier 1**.

```bash
conda run -n climada_env python -c "import ee; ee.Initialize(project='zeta-bonfire-478712-n9'); import report, events; o = report.make_post(events.EMSR927); print(o['verdict'].report())"
```

| Output | Path |
|---|---|
| Post, plain text ready to paste | `output/EMSR927/EMSR927_post.txt` |
| Draft with the check log | `output/EMSR927/EMSR927_draft.md` |
| Carousel, in reading order | `EMSR927_00_sites.png`, then `_01_bidur`, `_02_syapru-besi`, `_03_timure` |

652 words, no unresolved placeholder, nothing left `[TO WRITE]`, both
anti-slop passes clean, longest prose sentence 35 words.

**What is still missing is Bharatpur.** It is the fourth area of the
activation, still `status=W` at the last check, expected 2026-08-29 17:01 UTC.
The other three all arrived late against their estimate, Timure by 22 hours.
The post says plainly that Bharatpur is not counted. Rerun the command above
once it lands and a fourth sheet appears with the figures updated; the text
regenerates from the same data and needs no editing.

**Before publishing**: rule 11, the human plausibility sign-off. Nothing in
this repository can do it.

### 3. Wire the calendar to the clock

`watch.py` finds new activations, places them on the calendar and drafts what
is due. It never publishes. What is not automated is the trigger: it has to be
run, by hand or by a scheduler.

### 4. Val-de-Marne

Nothing to draw from on 28 August. The next full Sentinel-1 look over the
department was planned for **2026-08-30 05:51 UTC**, from the ESA plan. Rerun
`manual.prepare_imagery` after it and see whether anything is readable.

### 5. Deferred, ready when wanted

Wildfire and earthquake, both researched, neither started. See `DECISIONS.md`.
Wildfire is the cheaper: CLIMADA ingests FIRMS directly and FIRMS is daily.

---

## Environment

Windows. Miniforge at `C:\Users\hammo\miniforge3`, environment `climada_env`.
Run through `conda run -n climada_env python ...`; calling `python.exe`
directly fails on a GDAL DLL path. Set `PYTHONPATH` to the repository when
running a script from outside it.

PowerShell here is 5.1: `&&` is a syntax error. Chain with `;`.

Earth Engine project id `zeta-bonfire-478712-n9`. Authenticate with
`ee.Authenticate(auth_mode="localhost")`.

Added in V2: `pystac-client`, for Earth Search and the Planetary Computer.
Neither needs an account.

Cached intermediate results live in `data/cache/`, which is git-ignored.
Rebuilding one event from scratch takes several minutes. Downloaded EMS
vectors live in `data/ems/`, acquisition plans in `data/cache/plans/`.

**Before trusting anything in the documentation about what a service holds,
run `check_sources.py`.** It exists because this file used to contain claims
that had quietly stopped being true.
