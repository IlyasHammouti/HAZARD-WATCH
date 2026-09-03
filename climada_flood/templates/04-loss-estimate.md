<!--
Template: post type 4, loss estimate.
Read docs/EDITORIAL_RULES.md before generating. All sections apply, and
section 11 gates generation: this template is not filled at all if the chain
did not complete or if a refusal condition is met.

Length: 300 to 500 words. This is the only type that carries a currency
figure, and it carries it with every caveat attached.

Mandatory sections, from docs/POST_TYPES.md: the figure, what it covers, what
it excludes, the assumptions behind it, the method link. L-REVISION-PROMISE is
mandatory.

Graphics: world locator map, main map with extent and context, figures block,
critical facilities, loss distribution, method and disclaimer strip.

Two rules bite hardest here: no value is invented to fill a slot (H11), and
the draft is converted to plain text before publishing (section 3.1).
-->

# {{PERIL}} loss estimate, {{REGION}}, {{COUNTRY}}, {{EVENT_DATE}}

<!--
Opening. First 140 characters. The figure, its currency, its base year, and
the word "modelled". Never lead with the method or with the event narrative.
No emphasis markup: the figure carries itself by standing first (A6).
-->

Modelled loss for the {{EVENT_DATE}} {{PERIL}} in {{REGION}}:
{{LOSS_FIGURE}}, {{CURRENCY}} base year {{BASE_YEAR}}. Computed from the
observed extent.

## What happened

<!--
Three sentences at most. Event, dates, extent, latency in hours.
-->

{{EVENT_SUMMARY}}

## Figures

<!--
Block 4. Two significant figures throughout. No bold anywhere (A6). Every
line is filled from pipeline output; a slot with no value stops the post
rather than being estimated (H11).
-->

- Extent: {{EXTENT_AREA}} km2, {{PRODUCT_RESOLUTION}} resolution
- Affected population: {{POPULATION}}
- Exposed value inside the extent: {{EXPOSED_VALUE}}
- Modelled loss: {{LOSS_FIGURE}}
- Loss as a share of exposed value: {{LOSS_SHARE}}
- Cross-check with {{CROSSCHECK_SOURCE}}: {{CROSSCHECK_FIGURE}}

{{LOCKED:L-CURRENCY}}

## What the figure covers

<!--
Positive scope. Which sector, which asset class, which geography, which
moment. Sentences, not a list, so it cannot be read as a specification.
-->

{{COVERAGE_STATEMENT}}

## What the figure excludes

<!--
Explicit exclusions. Business interruption, contents, infrastructure outside
the exposure layer, agriculture, vehicles, clean-up, indirect losses,
casualties. Anything not modelled is named here rather than left implied.
-->

{{EXCLUSION_STATEMENT}}

## Assumptions behind it

<!--
The honest part of the post, and the part a reader remembers. Use the
phrasings from section 7 of the rules for depth, curve transfer, and exposure
resolution. State the assumption that most affects the result first, and say
that it does.
-->

- {{ASSUMPTION_DEPTH}}
- {{ASSUMPTION_CURVE}}
- {{ASSUMPTION_EXPOSURE}}
- {{ASSUMPTION_OTHER}}

{{DOMINANT_ASSUMPTION_STATEMENT}}

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

{{LOCKED:L-TIER-1}}

<!--
Two sentences on the chain: extent source, exposure layer, depth derivation,
damage curve, engine. Attribution of each artefact to its producer (A25). No
claim of novelty (A22).
-->

{{METHOD_SUMMARY}}

{{LOCKED:L-REVISION-PROMISE}}

{{LOCKED:L-METHOD}}

## Sources

{{LOCKED:L-SRC-GFM}}
{{LOCKED:L-SRC-SENTINEL}}
{{LOCKED:L-SRC-GHSL}}
{{LOCKED:L-SRC-FABDEM}}
{{LOCKED:L-SRC-CURVES}}
{{LOCKED:L-SRC-CLIMADA}}

---

{{LOCKED:L-DISC-FULL}}

{{LOCKED:L-LICENCE}}

{{HASHTAGS}}
