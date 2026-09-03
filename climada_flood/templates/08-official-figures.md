<!--
Template: post type 8, official figures. Published around T+45 h.
Read docs/EDITORIAL_RULES.md before generating. Length: 250 to 450 words.

The post V1 could not produce. Copernicus EMS has counted the damage building
by building, from imagery this project does not have, and those counts are
open. They are also absent from the platforms this project publishes on.

Two rules govern this type and they pull in opposite directions on purpose.
Every EMS figure carries its source on the same line (H15), because the reader
must never take somebody else's count for ours. And our own layer is added on
top rather than omitted, because republishing a bulletin is not analysis: what
this project adds is the exposure behind the count and an honest statement of
what the count leaves out.

The output tier does not gate anything in this post except our own modelled
figures (H16).

Graphics: one map per mapped area, EMS observed event outline over the terrain,
damage counts in the bubbles with the source named on the bubble.
-->

# {{PERIL}} in {{REGION}}, {{COUNTRY}}: what the responders counted

<!--
Opening. First 140 characters. Lead with the strongest counted fact and its
source, not with the activation code.
-->

{{HEADLINE_COUNT}}

<!--
UPDATE_NOTE is empty on a first post for an event and stays empty. It is set
only when this run genuinely supersedes a post that already went out, and it
says what changed and why (section 3.2's rule against a silent replacement),
in the caller's own words rather than generated here.
-->

{{UPDATE_NOTE}}

## What happened

<!--
Block 3. Quoted from the activation request rather than written here: it is
the requester's own account, it names the mechanism, and it sometimes carries
a ground measurement nothing else in the chain has.
-->

The event was {{EVENT_TIME}}. Copernicus recorded the reason for the
activation as follows.

"{{EVENT_CAUSE}}"

## What was mapped

<!--
Block 4. The mapped area, the method, and the hour. The method matters: these
are people reading very high resolution imagery, not an automatic detector,
and that is why the counts exist at all where radar produced nothing.
-->

{{REPORTED_BODY}}

## What this project adds

<!--
Our layer, on their footprint. This is the section that makes the post
analysis rather than a relay. Exposure and population are ours and are
labelled as ours; the extent underneath them is theirs and is labelled as
theirs.
-->

- Modelled loss: {{LOSS_RANGE}}
- Exposed value of the graded buildings: {{EXPOSED_VALUE}}
- Population inside the mapped area: {{POPULATION}}
{{DETECTION_LINE}}

{{LOCKED:L-CURRENCY}}

{{OWN_LAYER_CAVEAT}}

## What the counts do not cover

<!--
Block 5. What an EMS grading product is not. It grades what the imagery shows
in the areas that were requested, which is neither the whole event nor a
financial assessment.
-->

{{COVERAGE_STATEMENT}}

{{EXCLUSION_STATEMENT}}

## What is not known yet

{{UNKNOWNS}}

## Method

{{TIER_STATEMENT}}

{{METHOD_SUMMARY}}

{{LOCKED:L-REVISION-PROMISE}}

{{LOCKED:L-METHOD}}

## Sources

<!--
Only what was used. This post's extent and damage counts come from Copernicus
EMS; the Sentinel credit belongs here only when a Sentinel scene actually
entered the figures, which is not the case when the detector was not run.
-->

{{LOCKED:L-SRC-EMS-GRADING}}

{{LOCKED:L-SRC-GHSL}}

{{LOCKED:L-SRC-LITPOP}}

{{SENTINEL_CREDIT}}

---

{{DISCLAIMER}}

{{LOCKED:L-LICENCE}}

{{HASHTAGS}}
