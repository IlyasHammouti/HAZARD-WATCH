# Flood in Rasuwa, Nepal: what the responders counted

Copernicus EMS operators graded 3 207 buildings in Rasuwa, Nepal, and recorded 2 521 of them destroyed, from imagery read 45 hours after the event.

## What happened

The event was 26 August 2026 at 03:45 local time (2026-08-25 22:00 UTC). Copernicus recorded the reason for the
activation as follows.

"On the 26 August 2026, a flash flood reportedly triggered by a Glacial Lake Outburst Flood (GLOF) in Nepal has caused significant damage in Rasuwa District. There is a 7 m-deep water level recorded by monitoring stations. Copernicus EMS Rapid Mapping is requested to provide flood extent and damage assessment emergency mapping."

## What was mapped

The figures below were published by Copernicus EMS Rapid Mapping and are reproduced here with that attribution. They are counts made by its operators, not outputs of this pipeline, and the output tier above does not apply to them.

- Buildings graded: 3 207, of which 2 521 destroyed and 686 damaged
- Area mapped as affected: 8.3 km2, typed Landslide
- Roads: 47.4 km destroyed of 148.7 km graded
- Destroyed and named in the product: Langtang Khola Hydroelectric Power House 20MW
- Destroyed and named in the product: Rasuwagadhi Hydropower Dam
- Destroyed and named in the product: Trishuli Power House

The activation opened 12 hours after the event and the first graded product was delivered 45 hours after it.

## What this project adds

- Modelled loss: €36M to €39M
- Exposed value of the graded buildings: €45M
- Population inside the mapped area: 5 600
- Our own detection found: 0.9 km2, 10% of what Copernicus mapped

Figures are in EUR, base year 2014, converted at 2023 rates. No inflation adjustment or conversion is applied unless the rate and its year are stated alongside.

Those figures are this project's, computed on the footprint Copernicus mapped rather than on one of our own. An independent footprint count (Google Open Buildings) finds 3 254 structures inside the same polygons, of which Copernicus graded 99%. The destroyed share above is read against nearly the full count, not a sample of it.

## What the counts do not cover

The mapped areas were readable over 92% of their surface. Copernicus EMS marks the remaining 8% as not analysed, and nothing inside it is counted, by them or here.

Public infrastructure, agriculture and vehicles are outside the model. Only private built assets are counted.

## What is not known yet

Bharatpur is inside the activation and has not been graded yet, so nothing here counts it. What each building is worth comes from an aggregated national exposure dataset rather than from any local valuation. At the two lower damage grades, the share of that value lost is assumed. No official or industry cost figure has been published for this event.

## Method

Output tier 1 of 3: modelled loss in currency. This applies to figures this pipeline computed. Figures attributed to another source are reported as published.

Extent mapped by Copernicus EMS operators from very high resolution imagery, by photo-interpretation. Exposure from GHSL and LitPop. Loss is the replacement share of each building's recorded damage grade, summed. No water depth is assumed and no depth-damage curve is used.

When official or industry figures are published for this event, this estimate will be compared against them here, in whichever direction the gap goes.

Method, code and assumptions: https://github.com/ihammouti/hazard-watch

## Sources

Damage counts and mapped extent: Copernicus Emergency Management Service, Rapid Mapping, grading products for activation EMSR927, mapped by photo-interpretation of very high resolution imagery.

Exposure: GHSL built-up surface and population (European Commission, Joint Research Centre).

Exposure value: LitPop, a dataset published by ETH Zurich through the CLIMADA package, constant 2014 USD. The loss above is computed by this pipeline, not by CLIMADA's own engine.

Contains modified Copernicus Sentinel data 2026.

---

All figures here are modelled estimates. They are not loss adjustments, official assessments, or professional insurance advice. The damage itself was observed and graded by Copernicus EMS operators. What this pipeline adds is a value for each graded building, from an aggregated national dataset rather than any local valuation. That value, and the share of it lost at each grade, are where the uncertainty sits.

Text and figures CC BY-SA 4.0. Code AGPL-3.0.


---

## Automatic checks

```
Tier 1 of 3
[ok  ] IMAGERY: 2 post-event scenes
[ok  ] PROVENANCE: Extent mapped by Copernicus EMS operators from very high resolution imagery
[ok  ] EXTENT: 8.5 km² detected
[WARN] VERSUS_EMS: Own detection covers 10% of the 8.3 km2 Copernicus EMS mapped by hand
[ok  ] COVERAGE: 100% of the area observed
[ok  ] ASSESSABLE: The Copernicus EMS operators could assess 92% of the area
[ok  ] GRADED: 3207 buildings priced from their observed grade, 79% of them destroyed and costed at full replacement, which is definitional rather than assumed. The assumed range spans 7% of the upper bound.
[ok  ] EXPOSURE: 49,020,508 exposed
[ok  ] DAMAGE_RATIO: 83% damage ratio
```
