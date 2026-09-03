<!--
Template: post type 3, observed extent.
Read docs/EDITORIAL_RULES.md before generating. Sections 5, 6, 7 and 9 apply
in full. Length: 200 to 350 words.

Tier 2 by default: extent, affected population, exposed value. A loss figure
is optional at this stage and, when absent, no apology is written for its
absence. If a loss figure is included, use template 04 instead.

Attribution matters here (A25): the extent is the Copernicus GFM product, not
our detection, unless the fallback threshold method was used, in which case
say so plainly.

Graphics: world locator map, main map with extent and context, figures block,
critical facilities, method and disclaimer strip.

Two rules bite hardest here: no value is invented to fill a slot (H11), and
the draft is converted to plain text before publishing (section 3.1).
-->

# {{PERIL}} extent, {{REGION}}, {{COUNTRY}}, {{EVENT_DATE}}

<!--
Opening. First 140 characters. Lead with the measured extent and the date of
the imagery, not with the event narrative.
-->

The observed extent covers {{EXTENT_AREA}} km2 in {{REGION}}, measured from
{{SENSOR}}, {{PASS_TIMESTAMP}}. About {{POPULATION}} people live inside it.

## What happened

<!--
Three sentences at most. Event, dates, alert level, and the latency between
the event and the first usable image, stated in hours (section 6).
-->

{{EVENT_SUMMARY}} The event was {{EVENT_TIME}}. {{LATENCY_STATEMENT}}

## Figures

<!--
Block 4. Label and value, one per line. Units always. Two significant figures.
Every figure carries its source or is covered by the tier statement below.
No emoji, no bold beyond the two-span budget (A6).
-->

- Extent: {{EXTENT_AREA}} km2, {{PRODUCT_RESOLUTION}} resolution
- Affected population: {{POPULATION}}
- Exposed value: {{EXPOSED_VALUE}}

<!--
Two lines were removed here on 2026-08-28: built-up area inside the extent,
and critical facilities. The chain computes neither. Built-up area is measured
over the whole area of interest rather than inside the footprint, and nothing
in the pipeline reads OpenStreetMap at all, so both slots could only have been
filled by hand or by a plausible guess (H11). Put them back when the numbers
exist.
-->

{{LOCKED:L-CURRENCY}}

## What this covers and excludes

<!--
Block 5. Mandatory from type 3 onward. Say what the extent is a measurement
of and what it is not. Permanent water is excluded. Exclusion mask pixels are
not counted. Water present at the moment of the pass only, not peak extent.
-->

The extent is the water surface at the moment of the satellite pass, not the
peak of the event. Permanent water is removed using the reference water mask.
{{EXCLUSION_STATEMENT}}

## Reported by others

<!--
Figures somebody else measured. The output tier above governs what this
pipeline computes and has no bearing on these (H16), and every line carries
its source (H15). Omitted entirely when there is nothing to report; never
filled with a sentence saying the block is empty.
-->

{{REPORTED_BODY}}

## What is not known yet

{{UNKNOWNS}}

## Method

{{TIER_STATEMENT}}

<!--
Use L-TIER-2 when exposed value and population are reported, L-TIER-3 when
only the extent is. Do not invent a fourth tier.
-->

{{METHOD_SUMMARY}}

{{LOCKED:L-METHOD}}

## Sources

<!--
The extent credit follows whichever sensor actually produced the footprint,
on the same threshold the INFILL guard uses. Crediting Copernicus Global Flood
Monitoring for an extent Sentinel-2 produced is a false attribution (A25) and
a source credit for a source that did not supply it (section 8).
-->

{{EXTENT_CREDIT}}
{{LOCKED:L-SRC-SENTINEL}}
{{LOCKED:L-SRC-GHSL}}

<!--
L-SRC-OSM removed 2026-08-28. Nothing in the pipeline reads OpenStreetMap, and
rules section 8 allows a source credit only for a source actually used. Put it
back with the critical-facilities line.
-->

---

{{LOCKED:L-DISC-FULL}}

{{LOCKED:L-LICENCE}}

{{HASHTAGS}}
