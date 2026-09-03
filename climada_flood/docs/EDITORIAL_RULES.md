# Editorial rules

Version 2.0. Last updated 2026-08-29.

Changes in 2.0, the version that follows the pipeline into V2:

**A tier limits what this pipeline may compute. It never limits what a named
source has already published.** V1 conflated the two and produced a post about
Rasuwa carrying no figure at all while Copernicus EMS had counted 2 521
destroyed buildings in the same valley. H15 makes the separation a hard fail,
`L-SRC-EMS-GRADING` and `L-REPORTED` carry it, and every template gains a
reported block that the tier does not touch.

Publication is now keyed to the event clock rather than to whatever is ready:
section 3.2 sets out the six posts and the hour each is defensible at.

Changes in 1.2, all from the first real generation run: `L-SRC-MANUAL` and
`L-DRAWN` added for extents drawn by hand (H13); H14 added, because the first
draft printed an event as ended on the day its feed record was last updated.

Changes in 1.1: fabricated placeholder values added as a hard fail (H11);
plain-text publishing format specified (section 3.1); hook cut to 140
characters and hashtags to two; anti-slop rules A26 to A36 added from the
sources listed in section 12.

These rules govern every public text produced by this project: LinkedIn posts,
figure captions, disclaimer strips, and the method article. They exist because
the text is generated, and generated text fails in predictable ways.

Two uses:

1. **Input to generation.** This file is loaded together with the template for
   the post type being written.
2. **Gate before publication.** Nothing is published until it passes section 9
   and a human has signed off on plausibility.

Related: `docs/POST_TYPES.md` (what each type is for), `docs/DECISIONS.md`
(verified facts, output tiers, currency policy), `templates/` (one skeleton per
type).

All public output is in English. British spelling is the repository default;
one post is internally consistent either way.

## 1. Hard fails

A draft that breaks any of these is not edited, it is regenerated.

| # | Rule |
|---|---|
| H1 | A loss figure in a post type that forbids one (type 2), or in any post where the chain did not complete. |
| H2 | A locked string paraphrased, reordered, shortened, or "improved". Section 8 is verbatim or nothing. |
| H3 | A number without a unit, a source, and a date. |
| H4 | A currency figure without its base year. |
| H5 | A casualty or missing-persons figure that is not quoted from a named official source with a timestamp. Casualties are never modelled here. |
| H6 | Attribution of the event to climate change without a cited attribution study for that event. |
| H7 | Our own output described as confirmed, official, verified, or actual. |
| H8 | Any `{{` placeholder left unresolved in the published text. |
| H9 | A superlative claim ("worst in N years", "largest ever") without a cited source making exactly that claim. |
| H10 | Missing method link, missing disclaimer, or missing source list. |
| H11 | A value invented to fill a placeholder. Every `{{FIELD}}` is filled from pipeline output or from a named source. A slot with no value stops the post, it is never estimated, interpolated, rounded from memory, or made plausible. |
| H12 | An engagement-bait close: "Agree?", "Thoughts?", "What do you think?", "Comment below", "Like for part 2". |
| H13 | An extent drawn by hand, published without `L-SRC-MANUAL` and `L-DRAWN`. A reader cannot tell a drawn outline from a detected one, so the post has to. |
| H14 | An event described as ended when its source still lists it as running. A feed's last-update timestamp is not an end date. |
| H15 | A figure from a named source presented without that source on the same line, or a modelled figure presented without saying this pipeline computed it. A post carrying both kinds must let a reader tell them apart at a glance. |
| H16 | A reported figure suppressed because our own tier is low. The tier governs what we compute and nothing else. |

H11 is the failure this setup is most exposed to, because generation fills
slots and a plausible number is indistinguishable from a computed one once
published. When a value is missing, use `L-INCOMPLETE` or drop to a lower
tier.

## 2. Fixed skeleton

Every type uses the same nine blocks in the same order. Types differ only in
which blocks carry content and how much.

| Block | Content | T1 | T2 | T3 | T4 | T5 | T6 |
|---|---|:--:|:--:|:--:|:--:|:--:|:--:|
| 1 | Title | ● | ● | ● | ● | ● | ● |
| 2 | Opening, first 140 characters | ● | ● | ● | ● | ● | ● |
| 3 | What happened, factual | ● | ● | ● | ● | ● | ● |
| 4 | Figures block | ● | ● | ● | ● | ● | ● |
| 5 | What the figure covers and excludes | | | ● | ● | ● | ● |
| 6 | What is not known yet | ● | ● | ● | ● | | ● |
| 7 | Method, tier statement, method link | ● | ● | ● | ● | ● | ● |
| 8 | Sources | ● | ● | ● | ● | ● | ● |
| 9 | Disclaimer and licence | ● | ● | ● | ● | ● | ● |

Blocks are never reordered. A block with nothing to say is omitted entirely,
not filled with a sentence saying it is empty.

Block 1 is the title, and it does not go in the published text. LinkedIn has
no title field, so a title placed there spends the 140-character preview on a
label instead of on an event. The title belongs on the figure. Block 2 is
therefore the first thing a reader sees, and it opens with the event.

The figures in this file are orders of magnitude rather than limits. A post
that needs 340 words is published at 340 words; a post padded to 200 because
the table says 180 is worse than a short one.

## 3. Length and structure

| Type | Words | Paragraphs | Bullets per list |
|---|---|---|---|
| 1 Weekly digest | 180 to 320 | 4 to 7 | 8 |
| 2 Alert | 120 to 220 | 3 to 5 | 5 |
| 3 Observed extent | 200 to 350 | 4 to 7 | 6 |
| 4 Loss estimate | 300 to 500 | 6 to 10 | 6 |
| 5 Revision | 250 to 400 | 5 to 8 | 6 |
| 6 Retrospective | 400 to 700 | 8 to 14 | 6 |
| 7 Activation | 120 to 220 | 3 to 5 | 5 |
| 8 Official figures | 450 to 700 | 8 to 14 | 8 |

Type 8 was drafted at 250 to 450 before one had been written, and the first
real one came out at 660. The floor is not padding: the locked strings this
type must carry — the reported-figures disclosure, the currency statement,
the graded disclaimer, the revision promise and four source credits — come to
about 270 words before a single sentence of our own. Setting a band the format
cannot meet only teaches the writer to ignore the table.

- Sentences: 30 words maximum. At least one sentence per post under 10 words.
- Paragraphs: 3 sentences maximum, because LinkedIn shows about three lines
  before truncating.
- The first 140 characters carry the event, the place and the headline number.
  Mobile truncates at about 140 characters and desktop at about 210, so the
  post is written for the shorter one. No throat-clearing, no "this week we
  look at".
- Headings inside a post: sentence case, never title case.
- No emoji anywhere, including the figures block and the graphics.
- Hashtags: zero to two, at the very end, lowercase, specific to the peril or
  the region. Zero is an acceptable and common choice. Never `#innovation`,
  `#ai`, `#datascience`.
- Closing: the disclaimer block, or one specific technical question naming the
  subject. Never a generic prompt for engagement (H12).

## 3.2 The publication calendar

A post is defensible at the hour it is published, not whenever the chain
happens to finish. The clock starts at the event, and the hours below are
measured, not assumed: they come from EMSR927, Rasuwa, 25 August 2026.

| Hour | Type | What it carries | Why it is worth reading |
|---|---|---|---|
| T+3 h | 2 Alert | GDACS facts, no figure | The date of the first planned look, read from the ESA acquisition plan |
| T+12 h | 7 Activation | EMS opened, areas, sensors tasked, delivery expected | That the activation exists at all, and when its product lands |
| T+30 to 45 h | 3 Observed extent | The first readable scene, with its limits | Speed, and an honest account of what could not be seen |
| T+45 h | 8 Official figures | EMS counts, quoted, plus our exposure layer on their footprint | These counts are not published on the platforms this project posts to |
| T+3 to 7 d | 4 Loss estimate | Our modelled loss, where the guards allow it, against the EMS count | The only currency figure in the sequence |
| Weeks | 5 Revision | Against PERILS or an official total | The comparison in whichever direction it goes |

Two rules govern the sequence. A later post never silently replaces an earlier
one: it says what changed and why. And a post is not held back because a
better one is coming, because being late with a correct figure is the failure
this calendar exists to prevent.

## 3.1 Publishing format

Templates are Markdown because the repository is Markdown. LinkedIn renders
none of it. Asterisks, hashes and backticks appear literally in the feed and
are an immediate marker of pasted generated text.

Before publication the draft is converted to plain text:

| In the template | In the published post |
|---|---|
| `## Heading` | Plain line, sentence case, blank line after. Drop the heading entirely when the section is two sentences. |
| `**bold**` | Nothing. Emphasis comes from position, not markup. The figure goes in the first line instead. |
| `- item` | `- item`, kept as a typed character. |
| Backticks, tables, footnotes | Removed and rewritten as sentences or lines. |
| `[text](url)` | The bare URL. |

One blank line between ideas, not between every sentence. Stacked
single-line paragraphs are their own tell (A29).

The method link stays in the post body even though an external link in the
body costs reach. Reproducibility is the point of the project, and a link
hidden in the comments is a link the reader has to trust exists. Repeating it
in the first comment is fine.

## 4. Required vocabulary

These terms are precise and are used exactly as defined. Substituting a
synonym changes the claim.

| Term | Means | Not the same as |
|---|---|---|
| Modelled estimate | A figure this pipeline computed | Assessment, valuation, adjustment |
| Flood extent | The mapped area under water | Flood map, flood zone, flood risk |
| Footprint | The area the hazard covered | Impact area |
| Exposed value | Value of assets inside the footprint | Loss, damage, insured loss |
| Loss | Modelled monetary damage from applying a damage curve | Exposed value, insured loss, damages |
| Affected population | People living inside the footprint | Victims, casualties, displaced |
| Damage curve | Function mapping hazard intensity to damage rate | Model, algorithm |
| Alert level | GDACS classification, written Green, Orange or Red | Severity, warning |
| Revisit | Interval between satellite passes over the same area | Update, refresh |
| Observed | Measured from imagery | Estimated, modelled |
| Reported | Quoted from a named source | Confirmed |

Attribution of work matters. If the extent comes from Copernicus Global Flood
Monitoring, the post says so. It does not say "we detected".

## 5. Forbidden vocabulary

### 5.1 Register and accuracy, domain specific

Never used: devastating, catastrophic (except in the technical phrase
"catastrophe model"), apocalyptic, biblical, ravaged, wreaked havoc, hit hard,
tragedy, horror, victims, damages (as a money noun, it is a legal term),
real-time, AI-powered, powered by AI, our AI, our algorithm predicted,
forecast (this pipeline analyses events that have already happened), proves,
demonstrates, accurate to, guaranteed, insured loss (unless quoting an
insurance body), impacted as a verb (use affected), in excess of (use more
than), officials confirmed (unless the official and the statement are named).

### 5.2 Generated-text markers

Never used: delve, tapestry, testament, underscore, showcase, pivotal,
crucial, vital, key as an adjective, landscape (figurative), interplay,
intricate, robust (figurative), leverage as a verb, harness as a verb, foster,
unlock, navigate (figurative), realm, myriad, plethora, seamless, holistic,
cutting-edge, game-changer, groundbreaking, revolutionary, transformative,
unprecedented, stands as, serves as, marks a turning point, represents a
shift, in the heart of, nestled, boasts, vibrant, rich (figurative), profound,
resonates, deeply rooted, evolving, ensuring that, it is important to note, it
is worth noting, in today's world, in an era of, as we move forward, the
future looks, exciting, journey, empower, dive in, let us explore, at its
core, the real question is, here is what you need to know.

Also never used: meticulous, bolster, garner, multifaceted, paramount,
encompass, utilise, facilitate, commence, aforementioned, spearhead, synergy,
pain points, thought leadership, ecosystem (outside its ecological sense),
paradigm, beacon, embark, ever-evolving, remarkable, stunning, epic.

### 5.3 Banned openers and connectives

No post, paragraph or bullet opens with: Certainly, Absolutely, Sure, Indeed,
Moreover, Furthermore, Additionally, Interestingly, Notably, Importantly,
Overall, In conclusion, Firstly (or Secondly, Thirdly), In today's, When it
comes to, In the realm of, Whether you are.

No sentence contains: at the end of the day, the bottom line is, in a
nutshell, this is where X comes in, take it to the next level, move the
needle, bridge the gap.

The opening word of a post is the event, the place, the product or the number.
Not a connective, not a frame, not a question.

### 5.4 Hedging and filler

Never used: arguably, potentially possibly, somewhat, quite, very, rather,
in order to (use to), due to the fact that (use because), at this point in
time (use now), has the ability to (use can), a number of (give the number).

One hedge per sentence is the maximum. Uncertainty is expressed with the
phrasings in section 7, not by stacking qualifiers.

## 6. Numbers, dates, units, currency

- **Significant figures.** Loss and exposed value: two significant figures,
  never more. `18.9 M USD` is acceptable, `18,943,271 USD` is not, because the
  method does not support that precision. Areas: two significant figures.
  Population: rounded to the nearest thousand above 10,000.
- **Units.** Always written: `km2`, `m`, `h`, `M USD`, `bn USD`. Money carries
  the ISO code after the number, never a bare symbol.
- **Currency.** Source currency and base year, always. Conversions are shown
  with the rate and the rate year alongside. Silent conversion is a hard fail.
- **Dates in prose:** `16 May 2023`.
- **Two clocks, and never a third.** They answer different questions and both
  are always labelled.

  | What | Format |
  |---|---|
  | Satellite acquisition, product delivery, orbit | **UTC only.** `2026-08-28 12:21 UTC` |
  | The event itself | **Local time where it happened, UTC alongside.** `26 August 2026 at 03:45 local time (2026-08-25 22:00 UTC)` |
  | Elapsed time | Hours since the event, computed in UTC. `45 hours after the event` |

  Never the author's time zone, and never the reader's. Zurich would be wrong
  for a Nepali reader and wrong for the satellite. A reader wants to know the
  water came in the middle of the night; the data wants a timestamp that does
  not move; neither wants where the post was written.

  **Check the basis before computing an elapsed time.** Copernicus EMS
  timestamps were confirmed as UTC by checking a sun-synchronous acquisition
  against local solar time: the WorldView-3 scene over Rasuwa is stamped
  05:05, which is 10:50 in Kathmandu, exactly where such a satellite crosses.
  Had the field been local, every latency in this project would have been out
  by 5 hours 45.
- **Ranges** are written `12 to 18 M USD`, not `12-18M`.
- **Percentages** state their base: `14% of the built-up area inside the
  footprint`, not `14% affected`.
- **Latency** is stated as measured hours from event to product, not as
  "fast", "rapid" or "near real-time".
- A figure taken from a source carries that source on the same line or the
  line below. A figure this pipeline produced carries the tier statement from
  section 8.

## 7. Mandatory phrasings for uncertainty

Uncertainty is stated in plain declarative sentences. Pick the case that
applies and use the phrasing as written. Wording may be fitted to the sentence
around it, but the commitment it makes may not be weakened.

| Case | Phrasing |
|---|---|
| Extent not yet available | "No post-event imagery covers the area yet." |
| Product exists but is partial | "The extent covers {{SHARE}} of the affected area. The remainder was not usable." |
| Cloud, exclusion or unreliable pixels | "{{SHARE}} of the area falls inside the product exclusion mask and is not counted." |
| Damage curve borrowed from another region or sector | "The damage curve is calibrated for {{CALIBRATION}} and is applied here to {{APPLIED}}. This is the largest single source of error in the figure." |
| Exposure resolution coarser than the footprint | "The exposure grid is {{RESOLUTION}}, wider than the inundated strips, so part of the footprint is not matched to exposed value." |
| Depth assumption | "Water depth is derived from the extent and a bare-earth terrain model, not measured." |
| No damage curve available | "No published damage curve exists for this peril, so no loss figure is given." |
| Order of magnitude only | "This figure is an order of magnitude, not a valuation." |
| Disagreement with another published figure | "This differs from {{OTHER_SOURCE}}, which reports {{OTHER_FIGURE}}. The likely reason is {{REASON}}." |

Never write "may vary", "results could differ", or "please note that estimates
are approximate". They say nothing and they read as generated.

## 8. Locked strings

Verbatim, always. Referenced from templates as `{{LOCKED:ID}}`. Editing one of
these strings is a change to this file with a version bump, not an edit to a
post. Placeholders inside a locked string are filled; the surrounding words
are not touched.

### Disclaimers

`L-DISC-SHORT`, for the graphics strip and captions:

> Modelled estimate. Not a loss adjustment, official assessment, or insurance advice.

`L-DISC-GRADED`, for a loss priced from observed damage grades:

> All figures here are modelled estimates. They are not loss adjustments, official assessments, or professional insurance advice. The damage itself was observed and graded by Copernicus EMS operators. What this pipeline adds is a value for each graded building, from an aggregated national dataset rather than any local valuation. That value, and the share of it lost at each grade, are where the uncertainty sits.

`L-DISC-FEED`, for type 1, which reports a feed and models nothing:

> Alert levels and event descriptions are GDACS classifications, reproduced as published. No loss figures are given in this format.

`L-DISC-FULL`, for the post body, types 3 to 6:

> All figures here are modelled estimates. They are not loss adjustments, official assessments, or professional insurance advice. They rest on documented simplifying assumptions, on aggregated exposure data, and on vulnerability functions calibrated at regional rather than event level. Differences from actual observed losses may be substantial.

`L-NO-FIGURE`, mandatory in type 2:

> No loss figure is given for this event. The observed extent is not available yet, and any figure published at this stage would be a guess rather than an estimate.

`L-INCOMPLETE`, any type, when the chain stopped:

> The chain did not complete for this event, so no figure is published.

`L-REPORTED`, mandatory above any block of figures this pipeline did not compute:

> The figures below were published by {{REPORTED_SOURCE}} and are reproduced here with that attribution. They are counts made by its operators, not outputs of this pipeline, and the output tier above does not apply to them.

`L-DRAWN`, mandatory in the body of any post whose extent was drawn by hand:

> This outline was drawn by hand, by reading the imagery listed in the sources, because the automated flood products produced nothing usable over this area. The operator worked from a partial view, and its limits were these. {{DRAWN_LIMITATIONS}}

### Output tiers

One of these three appears in every post carrying numbers.

`L-TIER-1`:

> Output tier 1 of 3: modelled loss in currency, from a published damage curve.

`L-TIER-2`:

> Output tier 2 of 3: exposed value and affected population. No damage curve is applied.

`L-TIER-3`:

> Output tier 3 of 3: physical extent only. No exposure or loss is reported.

### Currency

`L-CURRENCY`:

> Figures are in {{CURRENCY}}, base year {{BASE_YEAR}}. No inflation adjustment or conversion is applied unless the rate and its year are stated alongside.

### Satellite timing

`L-PASS`:

> The next Sentinel-1 pass over the area is estimated for {{PASS_DATE}}, from an observed revisit cycle of {{REVISIT_DAYS}} days. This is an estimate of the pass, not a published acquisition schedule.

`L-AWAITING-PRODUCT`, when the area has been imaged but no flood extent exists:

> Sentinel-1 imaged the area on {{LAST_PASS}}. No flood extent product has been published from that acquisition yet, so the footprint cannot be measured.

### Revision

`L-REVISION-PROMISE`, mandatory in type 4:

> When official or industry figures are published for this event, this estimate will be compared against them here, in whichever direction the gap goes.

`L-REVISION-COMPARE`, mandatory in type 5:

> Earlier estimate: {{EARLIER}}. Reference figure: {{OFFICIAL}}, {{OFFICIAL_SOURCE}}, {{OFFICIAL_DATE}}. Difference: {{DIFF}}.

`L-COMPARABILITY`, types 5 and 6:

> Years and events are compared on the same method and the same exposure data. Where that is not the case it is stated explicitly.

### Method and licence

`L-METHOD`:

> Method, code and assumptions: {{REPO_URL}}

`L-LICENCE`:

> Text and figures CC BY-SA 4.0. Code AGPL-3.0.

### Source attributions

Used as written, and only for sources actually used in that post.

| ID | String |
|---|---|
| `L-SRC-SENTINEL` | Contains modified Copernicus Sentinel data {{YEAR}}. |
| `L-SRC-GFM` | Flood extent: Copernicus Global Flood Monitoring (Copernicus EMS, EODC), derived from Sentinel-1. |
| `L-SRC-OPTICAL` | Flood extent: derived from Sentinel-2 by this project, using the MNDWI index, over ground Copernicus Global Flood Monitoring could not assess. |
| `L-SRC-EMS` | Reference extent: Copernicus Emergency Management Service, Rapid Mapping, activation {{EMSR_CODE}}. |
| `L-SRC-MANUAL` | Extent drawn by hand by {{OPERATOR}} on {{DRAWN_ON}}, by {{METHOD}}, from {{IMAGERY}}. This outline is not a Copernicus product and carries no official status. |
| `L-SRC-EMS-GRADING` | Damage counts and mapped extent: Copernicus Emergency Management Service, Rapid Mapping, grading products for activation {{EMSR_CODE}}, mapped by photo-interpretation of very high resolution imagery. |
| `L-SRC-PLAN` | Planned acquisitions: Copernicus Sentinel mission acquisition plans, published by ESA. |
| `L-SRC-GDACS` | Event alerts: GDACS (European Commission, United Nations). |
| `L-SRC-GHSL` | Exposure: GHSL built-up surface and population (European Commission, Joint Research Centre). |
| `L-SRC-LITPOP` | Exposure value: LitPop, a dataset published by ETH Zurich through the CLIMADA package, constant 2014 USD. The loss above is computed by this pipeline, not by CLIMADA's own engine. |
| `L-SRC-CURVES` | Damage functions: Huizinga, J., De Moel, H., Szewczyk, W. (2017), Global flood depth-damage functions, JRC105688, Publications Office of the European Union. |
| `L-SRC-FABDEM` | Terrain: FABDEM, the Forest And Buildings removed Copernicus DEM. |
| `L-SRC-USGS` | Ground shaking: USGS ShakeMap. |
| `L-SRC-FIRMS` | Active fire and burned area: NASA FIRMS. |
| `L-SRC-OSM` | Critical facilities: OpenStreetMap contributors, ODbL. |
| `L-SRC-CLIMADA` | Loss computed with CLIMADA (ETH Zurich). |

Open item: FABDEM redistribution terms are not recorded in
`LICENSE-CONTENT.md` yet. Until they are, FABDEM is credited but no
FABDEM-derived raster is redistributed.

## 9. Anti-slop pass

Mandatory on every draft, before the plausibility check and before any graphic
is finalised. Generated English carries markers a native reader spots
immediately, and they destroy the credibility the rest of the method is built
on. This section is the priority of this file.

### 9.1 Structural markers

**A1. No inflated significance.** The event is described, not framed as
meaningful. Cut any sentence whose only job is to tell the reader why the
sentence before it mattered.

- No: "The May 2023 Emilia-Romagna flood marked a turning point for European
  flood response, highlighting the growing importance of rapid satellite
  mapping."
- Yes: "The first usable Sentinel-1 pass came 19 hours after the event. The
  Copernicus Rapid Mapping activation followed about 7 hours later."

**A2. No participle tails.** A sentence does not end with a comma and an
`-ing` clause that restates it: highlighting, underscoring, reflecting,
demonstrating, ensuring, showcasing, contributing to.

- No: "The extent covers 640 km2, affecting thousands of residents and
  underscoring the scale of the event."
- Yes: "The extent covers 640 km2. About 47,000 people live inside it."

**A3. Break the rule of three.** Generated text groups everything in threes.
Vary deliberately: two items, or four, or five. A list that genuinely has
three members keeps them, but not three lists of three in one post.

**A4. No triadic adjectives.** One adjective per noun, or none.

**A5. No bolded inline list headers.** Lists are `- item text`, not
`- **Item:** text`. The only exception is the figures block, where the label
is data rather than emphasis.

**A6. No emphasis markup in the published post.** LinkedIn does not render it
and the asterisks show (section 3.1). A figure is emphasised by standing in
the first line of the post or on its own line in the figures block. Bold and
italics exist in the repository draft only, and at most twice there.

**A7. No "challenges and future prospects" ending.** Posts end on the last
concrete fact or on the disclaimer. No send-off, no outlook paragraph, no "as
this method matures".

**A8. No signposting.** No "let us look at", "here is what the data shows",
"first, some context". Say the thing.

**A9. No restating the heading.** A heading is followed by content, not by a
one-line paraphrase of itself.

**A10. Vary sentence length.** Generated text sits at an even 18 to 22 words.
Mix a 6-word sentence with a 28-word one. Read the draft aloud, and if the
rhythm is flat, rewrite two sentences.

**A11. No manufactured punchlines.** A run of short declarative fragments
engineered for drama is as recognisable as the padding it replaced. One short
sentence for emphasis is fine, three in a row is a tell.

**A12. No aphorisms.** No "X is the Y of Z", no "the language of risk", no
"the currency of trust". State the claim.

**A13. No false ranges.** "From detection to decision" and "from pixels to
policy" are banned. The two ends are not on a scale.

**A14. No synonym cycling.** The flood extent is called the flood extent every
time, not "the inundation footprint", then "the water mask", then "the
affected zone". Repetition is correct in a technical text. Variation reads as
generated and introduces ambiguity.

**A15. No vague attribution.** No "experts say", "observers note", "industry
reports suggest", "it is believed". Name the source or cut the claim.

### 9.2 Punctuation and typography

**A16. Em dash budget: one per post, and never two in a paragraph.** Replace
with a full stop, a comma, a colon, or parentheses. Clusters of em dashes are
the single most recognisable marker in English.

**A17. Straight quotes only.** No curly quotes.

**A18. No emoji, no decorative arrows, no unicode bullets inside sentences.**

**A19. Sentence case in every heading.**

**A20. No exclamation marks.**

### 9.3 Domain slop

**A21. No disaster register.** The post reports what a sensor measured. Human
consequences are given in counted terms with a named source, or not at all.

**A22. No method triumphalism.** The pipeline is not described as innovative,
novel, or the first of its kind. Its limitations appear in the same post as
its results.

**A23. No commercial register.** No "unlock insight", "actionable", "deliver
value", "at scale", "end-to-end solution". This project sells nothing.

**A24. No borrowed authority.** Copernicus, ESA, JRC and NASA are cited as
data sources and nothing more. Never phrased so a reader could take the
estimate as endorsed by them.

**A25. Attribution of computation.** Say who produced each artefact. The
extent is Copernicus GFM's. The damage curve is the JRC's. The loss figure is
this project's, and the wording makes that unambiguous.

### 9.4 Shape, setups and reveals

**A26. The portability test.** If a sentence could be moved unchanged into a
post about a different event, a different country or a different peril, it is
filler. Cut it, or replace it with a fact, a number or a mechanism specific to
this event. Applied honestly this removes more generated text than any word
list, and it is the fastest check in this section.

- No: "Rapid mapping products have become an important input for emergency
  response across Europe."
- Yes: "The Copernicus activation for this event produced its first delineation
  map 26 hours after the peak."

**A27. No three consecutive sentences of similar length.** The most measurable
signal there is. Mix a 6-word sentence with a 28-word one inside the same
paragraph.

**A28. No parataxis.** Three or more short declaratives in a row read as
generated even when every word is correct. Connect them with a subordinate
clause, a conjunction, a semicolon or a colon, so the sentence shows how the
facts relate.

- No: "The extent was published. The exposure was matched. The loss was
  computed."
- Yes: "Once the extent was published, matching it against the exposure grid
  gave the loss figure."

**A29. Vary paragraph shape.** Not every paragraph is topic sentence, then
explanation, then example, then transition. Some are one sentence. Some end
without a transition, which is allowed and often better.

**A30. No colon reveals.** A noun phrase, a colon, then a small dramatic
payoff. "The detail that makes it work: the exclusion mask." Write it as a
sentence. Colons are for lists, labels and quotes.

**A31. No faux-insight setups.** "What nobody tells you", "the part everyone
misses", "most people get this wrong". Make the claim without the frame that
casts the author as the only person who noticed.

**A32. No rhetorical setups.** "What if I told you", "think about it", a
question asked and immediately answered by the writer. State the finding.

**A33. No binary contrasts or negative listing.** "This is not a forecast, it
is an estimate" and "not a map, not a model, a measurement" are the same tell
in two costumes. Say what the thing is. The one exception is `L-NO-FIGURE`,
where the negation is the content and the wording is locked.

**A34. No interpretive metadiscourse.** Do not tell the reader how to weigh
what they just read: "this matters more than it sounds", "the key point here",
"as you can see", "in other words". Either the facts carry it or they do not.

**A35. Prefer is and has.** "The extent is 640 km2" beats "the extent
represents a total of 640 km2". Weak verb phrases become direct verbs: "made a
decision" becomes "decided", "has the ability to" becomes "can".

**A36. Punctuation budgets beyond the em dash.** Ellipses: one per post, only
for a genuine trailing off, never as a transition. Exclamation marks: none
(A20). Semicolons: allowed and encouraged, since generated text underuses them
and they are the natural fix for A28.

### 9.5 Check before publication

Run the pattern check, then read the draft once against A1 to A36. Anything
found is fixed before the plausibility gate, not after.

```bash
grep -nEi "delve|tapestry|testament|underscor|showcas|pivotal|crucial|vital|landscape|interplay|intricate|seamless|holistic|cutting-edge|groundbreaking|revolutionary|transformative|unprecedented|stands as|serves as|nestled|boasts|vibrant|profound|resonat|devastating|catastrophic|apocalyptic|ravaged|wreaked|victims|real-time|AI-powered|impacted|in excess of|it is (important|worth) (to note|noting)|—|–|\{\{" draft.md
```

A second pass for the phrase-level patterns added in 1.1:

```bash
grep -nEi "here's the (thing|deal)|what if I told you|think about it|nobody tells you|everyone misses|most people get|not just .* but|it's not .*, it's|at the end of the day|the bottom line|in a nutshell|as you can see|in other words|the key point|what do you think|thoughts\?|agree\?|comment below|\*\*|^#|in today's" draft.md
```

The two commands catch em dashes, en dashes, unresolved placeholders,
engagement bait and leftover Markdown. A clean run is not a pass on its own:
A1, A3, A10, A14, A26 and A27 need a human read.

## 10. Placeholders

Two forms only.

- `{{FIELD_NAME}}` for a value the pipeline computes or a human supplies.
- `{{LOCKED:ID}}` for a string from section 8, inserted verbatim.

HTML comments in templates are instructions to the generator and never appear
in output. No `{{` survives into a published post (H8).

## 11. Refusal conditions

The text is not generated at all when any of these holds. This is Phase 7
territory, and the thresholds below are provisional until that phase confirms
them.

| Condition | Action |
|---|---|
| Extent missing, more than half unusable, or predating the event | No figure. Type 2 only. |
| Exposure or damage curve missing | Drop to tier 2 or 3, keep the post. |
| Modelled loss above 10% of exposed value inside the footprint | Flag for human review before generation. |
| Modelled loss above 25% of exposed value | Refuse. Publish only with a written justification inside the post. |
| Modelled loss above the reported national annual disaster loss | Refuse. |
| Any input dated after the post date | Refuse. |
| No human plausibility sign-off | Refuse to publish, whatever the figures look like. |

## 12. Sources of these rules, and what was left out

Sections 5 and 9 draw on the Wikipedia page *Signs of AI writing* (WikiProject
AI Cleanup), the `humanizer` skill built on it, and three public anti-slop rule
sets: `petergyang/no-ai-slop`, `jalaalrd/anti-ai-slop-writing`, and the voice
and algorithm notes in `sergebulaev/linkedin-skills`. Rules A26 to A36, H11,
H12 and section 3.1 come from those.

Three things in those sources are deliberately not adopted, because they fit a
personal brand voice and not a technical bulletin. A future session that loads
a generic anti-slop skill will be told to do all three, and should not.

- **Contractions, slang, profanity, deliberately ugly sentences.** Neutral and
  plain is the correct human register for a measurement bulletin. The
  `humanizer` skill says the same: for technical and reference text, injecting
  personality is the error, not the fix.
- **First-person anecdote, friction, vulnerability, "one moment of real
  stakes".** This project publishes what a sensor measured and what a model
  computed. The author appears only in the method, and never in a sentence
  about people who were flooded.
- **Engagement mechanics.** Comment seeding, posting windows, save bait,
  reply-within-90-minutes, hook formulas built to maximise the "see more"
  click. Cadence and formats are already settled in `docs/POST_TYPES.md`. The
  one heuristic taken from that material is the 140-character mobile cutoff,
  which is a fact about rendering rather than a growth tactic.

The reach cost of these choices is accepted and not revisited post by post.

## 13. Versioning

The version at the top of this file is recorded by the generation run that
used it. Changing a locked string, a threshold, or a hard fail is a minor
version bump. Changing the skeleton is a major bump. Published posts are not
retrofitted: a superseded phrasing stays as it was, and the reason for the
change is stated in the first post that uses the new one.
