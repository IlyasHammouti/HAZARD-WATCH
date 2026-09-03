# Rapid natural catastrophe loss estimation from satellite imagery

An open pipeline that starts from a real natural catastrophe, detects its
footprint from satellite imagery, and produces a quantified damage estimate —
following the logic of a catastrophe model:

```
Hazard  ×  Exposure  ×  Vulnerability  =  Loss
```

Public services generally stop at the physical footprint. Financial estimates
are produced by private providers behind closed methods. This project occupies
the space in between: a quantified estimate where every assumption is explicit
and reproducible.

## Disclaimer

**All figures produced here are modelled estimates. They are not loss
adjustments, official assessments, or professional insurance advice.**

They rest on the simplifying assumptions documented below, on aggregated
exposure data, and on vulnerability functions calibrated at regional rather
than event level. Differences from actual observed losses may be substantial.

This work is carried out for learning and methodological demonstration.

## Current state

| Notebook | Purpose | State |
|---|---|---|
| `00_test_installation` | Installation check, tropical cyclone demo data | Working |
| `01_gee_setup_test` | Google Earth Engine connection | Working |
| `02_flood_detection_latvia` | EMSR926, Latvia, August 2026 | Awaiting satellite pass |
| `03_flood_detection_italy` | EMSR664, Emilia-Romagna, May 2023: detection | Working |
| `04_impact_italy` | EMSR664: footprint to estimated loss | Working |

The Latvian case illustrates a real constraint of this kind of chain: at the
time of analysis no post-event imagery existed, because the satellite had not
yet passed over. The pipeline detects this, estimates the next pass from the
observed revisit cycle, and stops cleanly instead of failing.

## Method

**Hazard.** Flood footprint from before-and-after comparison of Sentinel-1
radar imagery. Radar rather than optical, because it penetrates the cloud
cover that is always present during a flood event. Open water reflects little
signal back to the sensor, so a sharp drop in backscatter indicates
inundation.

**Exposure.** Produced capital from LitPop (CLIMADA), which distributes a
national macroeconomic value across a grid using night-time lights and
population density.

**Vulnerability.** Depth-damage functions published by the Joint Research
Centre of the European Commission (Huizinga et al., 2017), calibrated for
Europe and the residential sector.

**Loss.** The three components combined through the CLIMADA engine.

## Known limitations

These are real and they affect the order of magnitude of the results.

- **Uniform assumed water depth.** The radar mask shows where water is, not
  how deep. A constant depth is applied across the whole footprint, while the
  damage functions are highly sensitive to it.
- **Exposure resolution.** The LitPop grid used is roughly 4.6 km across, far
  wider than the inundated strips along watercourses. Part of the detected
  footprint is therefore not correctly matched to exposed value.
- **Empirical detection threshold.** The backscatter drop used as the
  inundation criterion is set by hand, without a permanent water mask or
  exclusion mask.
- **Generic vulnerability function.** The residential sector is applied to all
  built-up area, without distinguishing use.
- **Currency and base year.** LitPop values are in constant 2014 US dollars.
  No inflation adjustment or conversion is applied.

## Planned improvements

- Footprint from the official **Global Flood Monitoring** product (Copernicus,
  20 m, three-algorithm consensus, permanent water mask) instead of a
  hand-tuned threshold.
- **GHSL** exposure at 100 m replacing LitPop, with LitPop retained as a
  cross-check.
- Water depth derived from footprint and a bare-earth terrain model (FABDEM)
  following the FwDET approach, replacing the uniform assumption.
- Affected population and critical facilities (health, education, transport)
  reported systematically, including for perils that have no vulnerability
  function.
- Extension to wildfire, earthquake and tropical cyclone.

See `docs/PROJECT_PHASES.md` for the full plan and `docs/DECISIONS.md` for
verified technical findings.

## Installation

Installation goes through conda-forge. Installing with `pip` fails because of
the GDAL dependency, which requires system libraries.

```
mamba create -n climada_env -c conda-forge climada jupyter
```

The flood module lives in the companion package `climada_petals`, whose
dependency resolution can stall on Windows. Installing from source is more
reliable:

```
git clone https://github.com/CLIMADA-project/climada_petals.git
mamba env update -n climada_env -f climada_petals/requirements/env_climada.yml
python -m pip install -e climada_petals/
```

A Google Earth Engine account is required for the detection notebooks.

## Data

The `data/` directory is not versioned. Datasets are downloaded by the
notebooks or retrievable from the sources listed in `LICENSE-CONTENT.md`.

## Licensing

Code under **AGPL-3.0** (`LICENSE`). Editorial content, maps and figures under
**CC BY-SA 4.0**. Source data conditions in `LICENSE-CONTENT.md`.

## References

- CLIMADA, ETH Zurich — <https://github.com/CLIMADA-project/climada_python>
- Huizinga, J., De Moel, H., Szewczyk, W. (2017). *Global flood depth-damage
  functions*. JRC105688, Publications Office of the European Union.
- Copernicus Emergency Management Service —
  <https://mapping.emergency.copernicus.eu/>
- UN-SPIDER, *Recommended Practice: Flood Mapping and Damage Assessment Using
  Sentinel-1 SAR Data in Google Earth Engine*
