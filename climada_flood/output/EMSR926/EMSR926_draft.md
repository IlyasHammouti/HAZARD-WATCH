# Flood extent, Kurzeme and Zemgale, Latvia, 2026-08-21

The observed extent covers 24 km2 in Kurzeme and Zemgale, measured from
Sentinel-2, [TO WRITE]. About 800 people live inside it.

## What happened

[TO WRITE] [TO WRITE]

## Figures

- Extent: 24 km2, 20 m resolution
- Affected population: 800
- Exposed value: €30M

Figures are in EUR, base year 2014, converted at 2023 rates. No inflation adjustment or conversion is applied unless the rate and its year are stated alongside.

## What this covers and excludes

The extent is the water surface at the moment of the satellite pass, not the
peak of the event. Permanent water is removed using the reference water mask.
Public infrastructure, agriculture and vehicles are outside the model. Only private built assets are counted.

## What is not known yet

[TO WRITE]

## Method

Output tier 2 of 3: exposed value and affected population, no loss figure. Radar produced only 13% of the extent, below 25%. The remainder is Sentinel-2 infill, which exists to correct the radar blind spot rather than to replace the measurement, and which over-detects on built-up land. Report the extent and the exposed value; do not attach a currency figure to it.

Extent observed 88 hours after the event, from Copernicus Global Flood Monitoring at 20 m, merged with Sentinel-2 where radar is blind. Exposure from GHSL and LitPop.

Method, code and assumptions: https://github.com/ihammouti/hazard-watch

## Sources

Flood extent: derived from Sentinel-2 by this project, using the MNDWI index, over ground Copernicus Global Flood Monitoring could not assess.
Contains modified Copernicus Sentinel data 2026.
Exposure: GHSL built-up surface and population (European Commission, Joint Research Centre).

---

All figures here are modelled estimates. They are not loss adjustments, official assessments, or professional insurance advice. They rest on documented simplifying assumptions, on aggregated exposure data, and on vulnerability functions calibrated at regional rather than event level. Differences from actual observed losses may be substantial.

Text and figures CC BY-SA 4.0. Code AGPL-3.0.

[TO WRITE]


---

## Automatic checks

```
Tier 2 of 3
[ok  ] IMAGERY: 19 post-event scenes
[ok  ] PROVENANCE: Extent from an automated product
[ok  ] EXTENT: 23.8 km² detected
[STOP] INFILL: Radar produced only 13% of the extent, below 25%. The remainder is Sentinel-2 infill, which exists to correct the radar blind spot rather than to replace the measurement, and which over-detects on built-up land. Report the extent and the exposed value; do not attach a currency figure to it.
[ok  ] COVERAGE: 83% of the area observed
[ok  ] ASSESSABLE: 65% of the area radar could judge
[ok  ] TERRAIN: 0% of the ground is steep
[ok  ] MECHANISM: riverine flooding suits a depth-damage curve
[ok  ] EXPOSURE: 32,345,212 exposed
[ok  ] DAMAGE_RATIO: 40% damage ratio
```
