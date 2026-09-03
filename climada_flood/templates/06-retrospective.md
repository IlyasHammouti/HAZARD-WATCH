<!--
Template: post type 6, retrospective.
Read docs/EDITORIAL_RULES.md before generating. All sections apply.
Length: 400 to 700 words, the longest format.

Seasonal or annual comparison across years or events. The first candidate is
drought summers compared across years, since drought is frequent in the feed
and unsuited to event-based coverage.

The risk specific to this format is narrative slop: a comparison across years
invites trend language, climate attribution, and a closing paragraph about
what it all means. H6 forbids attribution without a cited study for the events
in question, A1 forbids the significance framing, and A7 forbids the closing
paragraph.

Comparability is the technical trap. If the exposure layer, the extent
product, or the damage curve changed between the years compared, the
difference between years is partly the pipeline and not the hazard. Say so
(L-COMPARABILITY), or do not publish the comparison.

Graphics: world locator map, main map, figures block, method and disclaimer
strip. A time series replaces the loss distribution.

Two rules bite hardest here: no value is invented to fill a slot (H11), and
the draft is converted to plain text before publishing (section 3.1).
-->

# {{PERIL}} in {{REGION}}, {{PERIOD_LABEL}}

<!--
Opening. First 140 characters. The comparison and its single clearest number.
No "as the season draws to a close".
-->

{{PERIL}} across {{REGION}}, {{YEARS_COMPARED}}. {{HEADLINE_COMPARISON}}

## What is compared

<!--
The unit of comparison, the period boundaries, the geography, and the metric.
Stated before any number, because a reader cannot check a comparison whose
terms are implicit.
-->

{{COMPARISON_DEFINITION}}

{{LOCKED:L-COMPARABILITY}}

## Figures

<!--
One line per year or per event. Same metric, same units, same order every
time. Two significant figures. A table is acceptable here and nowhere else in
the post types, because a series of years is tabular data.
-->

| {{PERIOD_COLUMN}} | {{METRIC_1}} | {{METRIC_2}} | {{METRIC_3}} |
|---|---|---|---|
| {{PERIOD_VALUE}} | {{V1}} | {{V2}} | {{V3}} |
| {{PERIOD_VALUE}} | {{V1}} | {{V2}} | {{V3}} |

{{LOCKED:L-CURRENCY}}

## What the comparison covers and excludes

<!--
Block 5. Which events entered the series and which were dropped, and why.
Selection is the largest source of error in a retrospective, so the selection
rule is stated explicitly rather than described as "the significant events".
-->

{{SELECTION_RULE}}

{{EXCLUSION_STATEMENT}}

## What the series shows

<!--
Description of the measured differences, in the terms of the metric. No trend
claim unless the series is long enough to support one, and no cause unless a
cited source establishes it (H6, A15). "Higher than" is a measurement.
"Increasing" is a claim about a process.
-->

{{OBSERVED_DIFFERENCES}}

## What it does not show

<!--
Mandatory in this format. Confounders: exposure growth, changes in the
detection product, changes in reporting, population change, and the fact that
a comparison of measured extents is not a comparison of severity as
experienced.
-->

{{CONFOUNDERS}}

## What is not known yet

{{UNKNOWNS}}

## Method

{{TIER_STATEMENT}}

<!--
L-TIER-1, L-TIER-2 or L-TIER-3 as applicable. A retrospective often mixes
tiers across years; when it does, the tier is stated per year in the figures
table and this line states the lowest tier present.
-->

{{METHOD_SUMMARY}}

{{LOCKED:L-METHOD}}

## Sources

{{SOURCE_LIST}}

<!--
Locked source strings for every product used across the whole series, not only
the most recent year.
-->

---

{{LOCKED:L-DISC-FULL}}

{{LOCKED:L-LICENCE}}

{{HASHTAGS}}
