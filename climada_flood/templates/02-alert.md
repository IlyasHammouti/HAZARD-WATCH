<!--
Template: post type 2, alert.
Read docs/EDITORIAL_RULES.md before generating. Sections 5, 7 and 9 apply in
full. Length: 120 to 220 words.

Hard constraint: no loss figure, no exposed value, no damage estimate, no
range, no order of magnitude (H1). The absence of a figure is the point of
this format. L-NO-FIGURE is mandatory and verbatim.

The satellite pass estimate is the differentiating content. It goes high in
the post, not in a footnote.

Graphics: world locator map, figures block, critical facilities, event
timeline, method and disclaimer strip.

Two rules bite hardest here: no value is invented to fill a slot (H11), and
the draft is converted to plain text before publishing (section 3.1).
-->

# {{PERIL}} in {{COUNTRY}}, {{EVENT_DATE}}

<!--
Opening. First 140 characters. State the event, the alert level, and that the
extent is not available yet. No dramatic register (A21).
-->

{{PERIL}} in {{REGION}}, {{COUNTRY}}, {{EVENT_TIME}}. GDACS alert level
{{ALERT_LEVEL}}. No observed extent exists yet.

## What is known

<!--
Facts from the feed and from named sources only. Each line carries its source
and its timestamp. Casualty and displacement figures are quoted, never
modelled (H5). Maximum 5 lines.
-->

- {{FACT}} ({{SOURCE}}, {{TIMESTAMP}})
- {{FACT}} ({{SOURCE}}, {{TIMESTAMP}})

## What is not known

<!--
Use the phrasings in section 7 of the rules. This block is longer than the
previous one in most alerts, and that is correct.
-->

No post-event imagery covers the area yet. {{ADDITIONAL_UNKNOWNS}}

## When the extent is expected

{{LOCKED:L-PASS}}

<!--
Optional single sentence on what the pass will and will not resolve. Example:
a descending pass covers the eastern half of the area only.
-->

{{PASS_CAVEAT}}

## No figure

{{LOCKED:L-NO-FIGURE}}

## Method

{{LOCKED:L-METHOD}}

## Sources

{{LOCKED:L-SRC-GDACS}}
{{LOCKED:L-SRC-SENTINEL}}

---

{{LOCKED:L-DISC-SHORT}}

{{LOCKED:L-LICENCE}}

{{HASHTAGS}}
