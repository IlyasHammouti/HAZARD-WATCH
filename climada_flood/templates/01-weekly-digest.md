<!--
Template: post type 1, weekly digest.
Read docs/EDITORIAL_RULES.md before generating. Sections 5, 7 and 9 apply in
full. Length: 180 to 320 words.

Carries no loss figure, ever. This type exists to guarantee a weekly
publication with no exposure to being wrong about money.

Graphics: world locator map, figures block, method and disclaimer strip.

Two rules bite hardest here: no value is invented to fill a slot (H11), and
the draft is converted to plain text before publishing (section 3.1).
-->

# {{DIGEST_TITLE}}

<!--
The title names the format and the week, because "Natural catastrophes" alone
says neither. It stays in the published text and it also prints on the figure.

Opening. One framing sentence, then the counts, then the most recent event.

Two counts, not one. The GDACS window filters on overlap, so a drought that
began last November is returned in this week's list. "N events this week" over
a list where most of them started months ago is a false statement, and it is
the first thing this template got wrong.

RED_STATEMENT is not decoration. A week with no Red alert is a fact about the
week, and printing it is what stops a reader assuming the filter was set to
hide something.

GREEN_NOTE names a peril type only when this week substituted its most
severe Green-level event for a missing Orange/Red one. Empty most weeks,
same as PENDING_LINES - nothing is said about a mechanism that was not
used.

No superlative anywhere. GDACS alert level is a classification, not a ranking
of size (rules section 4), and "the largest" would be a superlative claim with
no source making it (H9).
-->

The natural catastrophes you may have missed last week, from the GDACS alert
feed. {{NEW_COUNT}} entered the list at {{ALERT_FILTER}} level and
{{CONTINUING_COUNT}} already running. {{RED_STATEMENT}}{{GREEN_NOTE}}

Most recent: {{HEADLINE_LINE}}

## Events

<!--
Only the events the figure cannot speak for: what entered the week, and
whatever reached Red however long it has been running. Maximum 8, ordered by
alert level then by date, new events before continuing ones.

The figure carries every event of the week as a table. Listing all of them
here as well made half the post a caption for the image beside it, so the
text keeps what changed and the table keeps the record.

Format is fixed: peril, country, dates, alert level, one factual clause from
the source feed. The peril carries the name GDACS gives the event, which is
how a volcano stops being "Volcano, Indonesia" and becomes a place a reader
can look up. No adjectives. No ranking language beyond the alert level.
Casualty counts only if quoted from a named source with a timestamp (H5).
EVENT_OVERFLOW accounts for everything left to the figure, counted by peril
and dated to the oldest, so the shorter list never silently shrinks the week.
-->

{{EVENT_LINES}}

{{EVENT_OVERFLOW}}

## Pending

<!--
Events under watch where no extent exists yet. This block is the reason the
digest is worth reading: the estimated next satellite pass is published
nowhere else. Use L-PASS verbatim for each entry, or once with a list if the
revisit cycle is identical.
Omit the whole block if nothing is pending. Do not write "nothing pending".
-->

{{PENDING_LINES}}

## Not known yet

<!--
Block 6. Two sentences at most. What the feed does not tell us, what the
imagery does not cover yet. Use the phrasings in section 7 of the rules.
-->

{{UNKNOWNS}}

## Method

<!--
Fixed. The digest reports the feed and the satellite schedule, nothing more.
No loss figure appears in this type, so no tier statement is needed unless the
post carries exposure numbers, in which case use L-TIER-2 or L-TIER-3.
-->

Events are taken from the GDACS feed and filtered by alert level.
{{PASS_METHOD}}

{{LOCKED:L-METHOD}}

## Sources

<!--
One credit per line, and a blank line between them: the plain-text conversion
unwraps consecutive lines into a paragraph, which would run the two
attributions into one sentence.

HASHTAGS closes the post with two, the maximum section 3 allows. They are
fixed rather than generated from the week: they name the format and the
discipline, and a tag that moved every Monday would index nothing.

The Sentinel credit is filled only in a week that carries a pending case, the
one place this format touches satellite data. Rules section 8 allows a source
credit only for a source actually used, and a week with nothing pending uses
GDACS alone.
-->

{{LOCKED:L-SRC-GDACS}}

{{SENTINEL_CREDIT}}

---

{{LOCKED:L-DISC-FEED}}

{{LOCKED:L-LICENCE}}

{{HASHTAGS}}
