# Hazard Watch

Rapid loss estimates for natural catastrophes, from open satellite data to a
figure in currency, with every assumption written down.

```
Hazard × Exposure × Vulnerability = Loss
```

A catastrophe model rests on that one identity. Public services such as
Copernicus EMS stop at the physical damage: what flooded, which buildings
fell. Commercial providers put a price on it behind closed methods. Hazard
Watch sits in between: it takes the best footprint available for a real
event, prices it, and publishes the figure together with the method that
produced it, then revises it in public as better data arrives.

The output is published on LinkedIn under the name Hazard Watch. This
repository is the method behind those posts.
https://www.linkedin.com/company/hazard-watch/

> **All figures produced here are modelled estimates. They are not loss
> adjustments, official assessments, or professional insurance advice.**

## How it works

### The four terms

| Term | Where it comes from |
|---|---|
| **Hazard** | A satellite footprint: Copernicus EMS mapping where it exists, otherwise Sentinel-1 radar (Copernicus Global Flood Monitoring) with Sentinel-2 optical infill, or an outline drawn by hand |
| **Exposure** | National asset value mapped to a grid: GHSL built-up surface at 100 m, LitPop (CLIMADA) as a cross-check |
| **Vulnerability** | A depth-damage curve (JRC, Huizinga et al. 2017), or the damage grades Copernicus EMS operators recorded building by building |
| **Loss** | One currency figure, or a range when the inputs call for one, published and revised |

### Two routes to a loss, and the better one wins

* **Graded.** Where Copernicus EMS has graded every building from 30 to 50 cm
  imagery, the loss is priced from the observed grade. No assumed water
  depth, no borrowed curve. This is how the Rasuwa flood (Nepal, EMSR927)
  was estimated.
* **Depth-damage.** Everywhere else: a footprint, an assumed or derived water
  depth, and a JRC damage curve, combined through the
  [CLIMADA](https://github.com/CLIMADA-project/climada_python) engine
  (ETH Zurich).

Copernicus EMS never publishes a monetary value. It records what was
damaged; this project estimates what that damage cost.

### From alert to loss

| Step | Delay after the event | What happens | Source |
|---|---|---|---|
| Alert | T+3 h | Feed only, no figure | GDACS |
| Activation | T+12 h | Mapping begins | Copernicus EMS |
| Extent | T+30 to 45 h | First satellite read | Copernicus EMS |
| Figures | T+45 h | Damage counted on the ground | Copernicus EMS |
| Loss | Days later | Priced into currency | CLIMADA or graded route |
| Update | Ongoing | Revised in public | Hazard Watch |

Each step has its own post type, so nothing is published before the data
behind it exists. An alert never carries a loss figure.

### What gets published

* **Weekly digest.** Every Monday, the events that started in the past week
  according to GDACS, grouped by peril. Alert levels as published, no loss
  figure. Published as a short map video that flies from one event to the
  next (cyclone tracks drawn from IBTrACS, droughts on a closing world view),
  with the same week as a single figure alongside.
* **Event posts.** One event followed through the chain: activation, official
  counts, then a modelled loss, updated as new damage grades are delivered.

Post formats are described in [docs/post-types.md](docs/post-types.md). The
wording rules every post must pass, including the locked disclaimers, are in
[docs/editorial-rules.md](docs/editorial-rules.md); the code reads them from
that file, so a post and the rules cannot drift apart.

## Repository layout

```
hazard_watch/          the pipeline
  natcat.py            GDACS events, flood extent, exposure, damage curves, loss
  ems.py               Copernicus EMS activations: what was tasked, what was counted
  plan.py              when the ground is next due to be imaged (ESA acquisition plans)
  catalog.py           what has actually been imaged, across the open catalogues
  manual.py            imagery prepared for hand delineation, and its provenance check
  guards.py            what the evidence supports, kept apart from what may be reported
  report.py            the chain, maps, post drafts and the weekly digest
  video.py             the weekly digest as a video: picks file, maps, flights, MP4
  carto.py             the visual identity shared by every graphic
  watch.py             finds new activations and drafts what is due; never publishes
  events.py            event definitions used for published cases
  check_sources.py     checks that what the docs claim about each data source is still true
  test_digest.py       self-checks for the weekly digest
  test_video.py        self-checks for the video digest
  templates/           one text template per post type
docs/
  decisions.md         settled technical decisions and measured facts
  editorial-rules.md   vocabulary, structure, locked phrasings, hard fails
  post-types.md        the post formats and when each is used
  roadmap.md           phases and perils, done and planned
  manual-delineation.md        drawing an extent by hand when no product exists
  earthquake-vulnerability.md  research note for the earthquake peril
notebooks/
  watch.ipynb          interactive view of the week's events
  exploration/         first version (2023 Emilia-Romagna and 2026 Latvia floods),
                       kept as history; superseded by the pipeline
brand/                 logo and banner assets, and the script that renders them
  hazard-icons/viseur-v2/      one SVG per hazard badge, plus rasterised layers/ for video.py
```

Generated data and outputs (`hazard_watch/data/`, `hazard_watch/output/`) are
not versioned. The pipeline rebuilds them.

## Running it

Install through conda-forge. `pip` alone fails on the GDAL dependency.

```bash
mamba create -n climada_env -c conda-forge climada jupyter pystac-client
```

The flood damage curves live in the companion package `climada_petals`,
which installs more reliably from source:

```bash
git clone https://github.com/CLIMADA-project/climada_petals.git
mamba env update -n climada_env -f climada_petals/requirements/env_climada.yml
python -m pip install -e climada_petals/
```

A Google Earth Engine account is needed for anything that reads imagery.
Point the pipeline at your own project with the `EE_PROJECT` environment
variable, then authenticate once with `ee.Authenticate()`.

Commands are run from `hazard_watch/`:

```bash
conda run -n climada_env python -c "import report; d = report.weekly_digest(monday='2026-09-21'); print(d['plain_path'], d['figure_path'])"
```

The video digest is two commands with an edit between them. The first lists
the week's events and writes `output/digests/video/<monday>-picks.txt`, with a
suggestion already in it; delete, reorder or add lines, attach a clip with its
source if there is one, then render:

```bash
conda run -n climada_env python video.py candidates 2026-09-28
conda run -n climada_env python video.py render 2026-09-28
```

```bash
conda run -n climada_env python -c "import ee, natcat; ee.Initialize(project=natcat.EE_PROJECT); import report, events; o = report.make_post(events.EMSR927); print(o['verdict'].report())"
```

```bash
conda run -n climada_env python test_digest.py
conda run -n climada_env python test_video.py
```

```bash
conda run -n climada_env python check_sources.py
```

`check_sources.py` exists because documentation about external services goes
stale quietly. Run it before trusting a statement in `docs/` about what a
service holds.

## Known limitations

These are real and they move the results.

* **Water depth.** A radar footprint shows where water is, not how deep. On
  the depth-damage route, depth is assumed or derived from terrain, and the
  loss is published as a sensitivity range rather than a single figure.
* **Exposure.** Asset values come from aggregated national datasets, not local
  valuations. They cover more than buildings alone, so a graded loss is more
  likely high than low.
* **Detection.** The pipeline's own flood detector is weak on steep ground,
  small footprints, debris flows and under cloud. On EMSR927 it found about
  10 % of what Copernicus EMS mapped by hand, which is why an official
  footprint always takes precedence.
* **Currency.** Values are in EUR at a stated base year and conversion rate,
  given with every figure.

## Built with Claude Code

I am a geographer, not a software developer. This pipeline was written with
[Claude Code](https://claude.com/claude-code), Anthropic's coding agent: I
set the method, the sources, the editorial rules and the checks, and made
every call on what gets published; Claude Code wrote and tested the Python.
The commit history is the record of that work.

## Licence

Code under **AGPL-3.0** ([LICENSE](LICENSE)). Text, maps and figures under
**CC BY-SA 4.0**. Conditions for each source dataset are in
[LICENSE-CONTENT.md](LICENSE-CONTENT.md).

## References

* CLIMADA, ETH Zurich: <https://github.com/CLIMADA-project/climada_python>
* Copernicus Emergency Management Service, Rapid Mapping:
  <https://mapping.emergency.copernicus.eu/>
* GDACS, Global Disaster Alert and Coordination System (European Commission,
  United Nations): <https://www.gdacs.org/>
* Huizinga, J., De Moel, H., Szewczyk, W. (2017). *Global flood depth-damage
  functions*. JRC105688, Publications Office of the European Union.
* Copernicus Global Flood Monitoring: <https://global-flood.emergency.copernicus.eu/>

Ilyas Hammouti
