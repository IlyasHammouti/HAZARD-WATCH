# Post types

Six formats. The skeleton is identical across all of them; only the filling
changes. This is what makes the output recognisable and the production
industrialisable.

All posts are written in English.

## Overview

| Type | Trigger | Target frequency | Loss figure |
|---|---|---|---|
| 1 — Weekly digest | Calendar | Weekly | No |
| 2 — Alert | Major event unfolding | Occasional | No, explicitly |
| 3 — Observed extent | Extent available | Per event | Optional |
| 4 — Loss estimate | Full chain completed | Per major event | **Yes** |
| 5 — Revision | Official figures published | Retrospective | Comparison |
| 6 — Retrospective | Seasonal | Annual | Depends |

## Type 1 — Weekly digest

The backbone. Guarantees a publication every week even when nothing major
happens, carries no loss figure and therefore no risk of being wrong, and is
almost fully automatable.

Contents: seven events that started in the week, Orange and Red first and
Green filling the rest. Peril, country, alert level, dates. A Red alert is
kept whatever its age. Pending cases with their expected satellite pass dates.

Nothing that began before the week is listed. A drought open since last
November was most of the list, and it was not what happened last week.

### The video

The same week, as a video of about a minute (`video.py`). It opens on the
world with every event marked, flies to each in turn, and closes on the
world again with the droughts filled in.

Each hazard's badge is the logo's own corner-bracket "viseur" (viewfinder)
closing on the event, built and animated from artwork at
`brand/hazard-icons/viseur-v2/` rather than drawn in code.

| Peril | On screen |
|---|---|
| Tropical cyclone | Its track through the week draws itself, dated each midnight UTC, with category and wind from IBTrACS as it goes |
| Earthquake | A seismograph badge that jolts at each shock, with wavefronts sized by magnitude; magnitude and depth written beside it |
| Volcano | A cone with a drifting ash plume and sparks; its name written beside it |
| Wildfire | A flickering flame at the GDACS point; the fire area written beside it |
| Flood | Running water in a badge at the GDACS point, with ripples. Never an area: no extent exists on a Monday |
| Drought | No scene. Its countries fill in on the closing world view, with the start date |

Any figure written on the map carries its source on the same label (H15).
The paper bands at the top and bottom never move, card or no card, and the
owner's mark sits at the bottom right of the map.

Sound: a whoosh under every flight between scenes, and an ambient bed under
every scene matched to its hazard (wind, rumble, crackle, water, an eruption
burst), from royalty-free, no-attribution clips (`docs/decisions.md` has the
licence and the mix). Most LinkedIn video plays muted, so this is heard by
whoever unmutes, not something the post depends on.

The choice of events is made by hand from a suggested list, to spread the
video across the world and across the week. A clip may follow any scene, with
its source printed on it; the pipeline never fetches footage itself. Every
figure on screen names its source on the same line (H15), and the closing card
carries `L-SRC-GDACS` and `L-DISC-FEED`.

Length follows the events, not a target: roughly a minute for six scenes.
LinkedIn's own guidance for B2B video is to stay under three minutes, and
Socialinsider's engagement benchmarks show no penalty below that.

## Type 2 — Alert

For a significant event still unfolding, before any extent is observable.

States clearly what is known, what is not, and **when the extent is expected**.
The satellite revisit date is the differentiating element here — no one else
publishes it.

Must never carry a loss figure. The absence of a figure is the point.

## Type 3 — Observed extent

Extent is available. Map with affected population and critical facilities.
Exposed value may be given; loss is optional at this stage.

## Type 4 — Loss estimate

The flagship. Full chain: extent, exposure, vulnerability, loss, context.
Carries the currency figure with all its caveats.

Mandatory sections: the figure, what it covers, what it excludes, the
assumptions behind it, and the method link.

## Type 5 — Revision

Published when official or industry figures become available. Compares the
earlier estimate against them and explains the gap.

Rare in this field and worth doing deliberately. Publicly checking your own
estimate against reality is a credibility signal no commercial provider can
afford to send. Plan for it from the start rather than treating it as
optional.

## Type 6 — Retrospective

Seasonal or annual analysis. Drought summers compared across years is the
first candidate: drought is frequent in the feed but unsuited to event-based
coverage, and the volume of data works in favour of a comparative format.

## Graphic elements by type

| Element | T1 | T2 | T3 | T4 | T5 |
|---|:--:|:--:|:--:|:--:|:--:|
| World locator map | ● | ● | ● | ● | ● |
| Main map: extent and context | | | ● | ● | ● |
| Figures block | ● | ● | ● | ● | ● |
| Critical facilities affected | | ● | ● | ● | |
| Loss distribution | | | | ● | |
| Event timeline | | ● | | | ● |
| Estimate versus official | | | | | ● |
| Method and disclaimer strip | ● | ● | ● | ● | ● |

## Format constraints

LinkedIn favours square and 4:5 images. Output sizes: 1080 × 1080 and
1080 × 1350.

The main map must stay legible as a thumbnail: few elements, strong contrast,
generous type. A layout designed for A3 print is unreadable in a feed.

## Visual identity

One accent colour per peril, constant across every post. After a few weeks a
reader identifies the event type before reading the title. Costs nothing,
returns a great deal in recognisability.

Fixed blocks on every graphic: title, legend, scale, north arrow, sources,
disclaimer strip, signature.

## Editorial rules

Three levels, all enforced:

**A rules file in the repository** — required and forbidden vocabulary, fixed
structure, length, tone, mandatory phrasings for uncertainty. Versioned, and
used as input to generation.

**Locked phrasings for anything that commits.** The disclaimer, the source
attribution, the wording of "modelled estimate" — never paraphrased. A
variation in the phrasing of a methodological caveat is a variation in
meaning.

**An anti-slop pass on output.** Generated text carries recognisable
markers — hollow symbolism, promotional register, systematic triads, excess
em dashes, vague attribution. These are more conspicuous in English than in
French, so the check is mandatory, not optional.

## Automation boundary

Automated: figures, dates, coordinates, sources, method box, disclaimer,
comparison against references, all graphics.

Human: choosing the event, drawing the area of interest, choosing the
vulnerability sector, **checking that the figure is plausible**, choosing the
angle, approving before publication.

At high cadence the plausibility gate matters more, not less. An absurd figure
published because the chain ran unattended is the primary risk of this setup.
Automatic guards are required: plausibility bounds, refusal to generate when
inputs are incomplete, alert when loss exceeds an improbable share of exposed
value.
