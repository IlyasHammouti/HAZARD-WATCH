# Project phases

Read `docs/DECISIONS.md` first — it carries every verified technical fact and
settled decision, so they do not have to be re-derived.

Ordering principle: one excellent published case is worth more than five
correct invisible ones. Publication is front-loaded, starting with the format
that carries the least risk.

## Pipeline shape

Seven steps. Only two of them vary by peril, which is what makes adding a
peril cheap.

| # | Step | Varies by peril |
|---|---|---|
| 1 | Watch — which events deserve treatment | No |
| 2 | **Extent** — where the event struck | **Yes** |
| 3 | Exposure — what is there and its value | No |
| 4 | **Vulnerability** — damage rate | **Yes** |
| 5 | Impact — loss in currency | No |
| 6 | Context — population, facilities, defences | No |
| 7 | Output — map, figures, text | No |

Per peril:

| Peril | Extent | Vulnerability | Tier reached |
|---|---|---|---|
| Flood | GFM Copernicus, 20 m | JRC | Loss |
| Wildfire | FIRMS, daily | CLIMADA wildfire | Loss |
| Earthquake | USGS ShakeMap grid | To transcribe from literature | Loss |
| Tropical cyclone | IBTrACS tracks | CLIMADA tropical cyclone | Loss |
| Landslide, lava flow | Dedicated detection | Total destruction step function | Loss |
| Others | Varies | None | Exposed value + population |

## Repository layout

```
climada_flood/
├── natcat.py           shared functions, single file
├── docs/               DECISIONS, POST_TYPES, PROJECT_PHASES
├── notebooks/
│   ├── 00..04_*.ipynb  early work, kept as history
│   ├── watch.ipynb     runs regularly: what happened
│   └── events/         one notebook per event covered
└── output/             exported maps and figures
```

No database, no web API, no container, no scheduler, no configuration system,
no classes. Each added component is one more thing to understand and maintain.
Automation comes when it is needed, not in anticipation.

## Phases

### Phase 1 — Shared core, on the Italian case

**Status: in progress.**

GFM extent, GHSL exposure, FABDEM-derived depth, population, OSM context,
LitPop as cross-check. Produces a reference result and a measured comparison
against the naive first-pass figure of 18.9 M USD.

Writes five of the seven shared steps. Everything downstream depends on it.

### Phase 2 — Graphics engine

The industrial mould: palette, typography, grid, fixed blocks, LinkedIn
formats, one accent colour per peril. Designed once, against real Phase 1
output. This is where the visual identity becomes code and stops being a
manual task.

### Phase 3 — Watch and weekly digest

GDACS watch plus post type 1. No loss figure, therefore no risk. First
publication and the start of the cadence, at the lowest possible cost.

### Phase 4 — Editorial rules and text generation

Rules file, templates per post type, anti-slop check. Then the flagship
publication: the method article built on the Italian case.

### Phase 5 — Wildfire

Only steps 2 and 4 change. If it is quick, the architecture is proven.
Favourable season, and the highest event volume in the feed.

### Phase 6 — Earthquake

The substantive work on the vulnerability function, transcribed from published
curves.

### Phase 7 — Guards and interface

Plausibility bounds, refusal on incomplete input, then the event selection
table. This is where the daily workflow becomes real: morning recap, pick an
event, generate, review, publish manually.

### Phase 8 — Latvia

EMSR926 catch-up with the completed chain.

## What can run in parallel

Phases 3, 4 and part of 6 touch nothing that Phase 1 produces. They can be run
in separate sessions at the same time.

| Phase | Depends on Phase 1 | Can start now |
|---|:--:|:--:|
| 2 — Graphics engine | Partly | Style system yes, map rendering no |
| 3 — Watch and digest | No | **Yes** |
| 4 — Editorial rules | No | **Yes** |
| 5 — Wildfire | Yes | No |
| 6 — Earthquake curve research | No | **Yes** |
| 7 — Guards and interface | Yes | No |
| 8 — Latvia | Yes | No |

### Prompts for parallel sessions

Each prompt is written to load context from the repository rather than restate
it, to keep token use low.

**Phase 3 — watch and weekly digest**

> Read `docs/DECISIONS.md`, `docs/POST_TYPES.md` and `docs/PROJECT_PHASES.md`
> in this repository, then implement Phase 3. Write the GDACS watch functions
> in a **new file `watch.py`** — do **not** edit `natcat.py`, another session
> is working in it and we would collide; the two files will be merged later.
> Add a `notebooks/watch.ipynb` that lists significant events over a chosen
> window plus pending cases with their estimated satellite pass dates. Respect
> the 100-result cap documented in DECISIONS: filter by `eventlist=<type>` and
> `alertlevel=`. Do not touch the exposure, vulnerability or impact steps.
> Explain each function as you go; I do not code.

**Phase 4 — editorial rules**

> Read `docs/POST_TYPES.md` and `docs/DECISIONS.md` in this repository, then
> implement Phase 4. Write `docs/EDITORIAL_RULES.md` — required and forbidden
> vocabulary, fixed structure per post type, mandatory phrasings for
> uncertainty, locked wording for the disclaimer and source attribution — and
> one Markdown template per post type under `templates/`. English only. No
> Python in this session. Prioritise anti-slop rules; the text will be
> generated.

**Phase 6 — earthquake vulnerability research**

> Read `docs/DECISIONS.md` in this repository. Research published earthquake
> damage functions (HAZUS, Global Earthquake Model) and produce
> `docs/EARTHQUAKE_VULNERABILITY.md`: which curves exist, what intensity
> measure they take as input, whether they are compatible with USGS ShakeMap
> output, and which building classes they cover. Cite sources. Do not write
> code and do not touch `natcat.py` — this is a research deliverable only.

Running Phases 3 and 4 in parallel with Phase 1 is the most useful
combination: they are independent, and together they deliver the first
publication.
