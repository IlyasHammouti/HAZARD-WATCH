# Flood loss estimate, Emilia-Romagna, Italy, 2023-05-16

Modelled loss for the 2023-05-16 Flood in Emilia-Romagna:
€293M, EUR base year 2014, converted at 2023 rates. Computed from the
observed extent.

## What happened

[TO WRITE]

## Figures

- Extent: 75 km2, 20 m resolution
- Affected population: [TO WRITE]
- Exposed value inside the extent: €733M
- Modelled loss: €293M
- Loss as a share of exposed value: 40.0%
- Cross-check with PERILS final insured loss estimate: EUR 495M

Figures are in EUR, base year 2014, converted at 2023 rates. No inflation adjustment or conversion is applied unless the rate and its year are stated alongside.

## What the figure covers

The estimate covers 57% of the exposed value. The remaining 43% falls in areas radar could not assess, chiefly built-up land.

## What the figure excludes

Public infrastructure, agriculture and vehicles are outside the model. Only private built assets are counted.

## Assumptions behind it

- Water depth is assumed uniform at 1.0 m. It was not measured: the footprint is too fragmented for depth to be derived from terrain.
- Damage curve: Flood Europe JRC Residential noPAA (JRC, Huizinga et al., 2017).
- Exposure is GHSL built-up surface at 100 m, anchored to the LitPop national total for produced capital.
- Extent merges Copernicus GFM radar with Sentinel-2 optical infill over the radar blind spot; fragments below 5 pixels are discarded as speckle.

Assumed water depth dominates the result. At 0.5 m the loss would be roughly 40% lower, at 2 m roughly 50% higher.

## What is not known yet

[TO WRITE]

## Method

Output tier 1 of 3: modelled loss in currency, from a published damage curve.

Extent observed 65 hours after the event, from Copernicus Global Flood Monitoring at 20 m, merged with Sentinel-2 where radar is blind. Exposure from GHSL and LitPop. Loss computed with CLIMADA.

When official or industry figures are published for this event, this estimate will be compared against them here, in whichever direction the gap goes.

Method, code and assumptions: https://github.com/ihammouti/hazard-watch

## Sources

Flood extent: Copernicus Global Flood Monitoring (Copernicus EMS, EODC), derived from Sentinel-1.
Contains modified Copernicus Sentinel data 2023.
Exposure: GHSL built-up surface and population (European Commission, Joint Research Centre).
Terrain: FABDEM, the Forest And Buildings removed Copernicus DEM.
Damage functions: Huizinga, J., De Moel, H., Szewczyk, W. (2017), Global flood depth-damage functions, JRC105688, Publications Office of the European Union.
Loss computed with CLIMADA (ETH Zurich).
Critical facilities: OpenStreetMap contributors, ODbL.

---

All figures here are modelled estimates. They are not loss adjustments, official assessments, or professional insurance advice. They rest on documented simplifying assumptions, on aggregated exposure data, and on vulnerability functions calibrated at regional rather than event level. Differences from actual observed losses may be substantial.

Text and figures CC BY-SA 4.0. Code AGPL-3.0.

[TO WRITE]
