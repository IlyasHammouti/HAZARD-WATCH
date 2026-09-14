# Weekly digest: repeat suppression + per-risk Green top-up

Status: approved. Written 2026-09-14.

## Problem

`report.weekly_digest()` selects only GDACS Orange/Red events for the week
(`natcat.gdacs_events(alert_levels=("Orange", "Red"))`). On a week where no
new Orange/Red event enters and nothing reaches Red, the headline
("Most recent") falls back to whichever continuing event happens to have the
latest `from_date` among an often-old set. On the week of 7-13 September
2026 this produced a flood in China (running since 31 July) as the headline
two weeks running, with nothing else to say — GDACS's Orange/Red feed for
that window held only four events, all continuing, all a month or more old.

Two problems, one fix each:

1. **The same event gets re-headlined/re-listed indefinitely** as long as it
   stays the "most recent" of a thin set. There is currently no memory of
   what has already been shown by name.
2. **Some peril types (earthquake, cyclone, volcano, wildfire) never appear**
   in a week where nothing of theirs reached Orange/Red, even though GDACS
   recorded dozens of Green-level events for several of them that week (92
   earthquakes, 6 cyclones, 100+ wildfires, capped).

## Design

### 1. Featured-event history (stops the repeat)

A persistent record of every `event_id` that has ever been shown **by name**
— as the digest headline or as a line in the Events list (not merely counted
in "N more, already running", which stays honest and unaffected).

- File: `climada_flood/data/cache/digest_featured.json` (git-ignored, same
  folder as every other pipeline cache per `HANDOVER.md`).
- Shape: `{"<event_id>": {"first_shown": "YYYY-MM-DD", "name": "..."}}`.
- Load at the start of `weekly_digest()`, filter these `event_id`s out of
  headline/Events-list eligibility (they still count toward the continuing
  total and the figure's overflow table — that bookkeeping is already
  correct and unaffected).
- After the week's selection is finalised, append the `event_id`s that ended
  up headlined/listed this run, and write the file back. Only on
  `write=True` runs, to keep a dry-run (`write=False`, used by tests) free
  of side effects.
- Once written, an event never re-enters eligibility, even if it is still
  the most severe of its type in a later week ("exclu définitivement",
  confirmed with the user over a repeat suppression that only blocked the
  headline slot but still allowed re-listing).

### 2. Per-risk Green top-up (fills the gap left by suppression or by a
quiet Orange/Red week)

For every peril type with **no eligible Orange/Red event this week**
(eligible = present in this week's Orange/Red pull and not in the history
file), fetch that type's Green-level events for the same window and take the
one with the highest GDACS `alertscore` (a real published field — nothing
invented, keeps rule H9 clean). If the top-scoring one is itself already in
the history file, fall through to the next-highest-scoring one of that type,
so a type is not silently dropped just because its single loudest event was
shown weeks ago.

- Red and Orange always take priority; a Green top-up never displaces or
  suppresses a Red/Orange event of the same type. Red is always reported
  regardless of history — a week must never look like it hid a Red alert.
- At most one Green top-up per peril type, so at most 6 extra entries
  (EQ, TC, VO, WF, FL, DR), well inside the existing 8-line digest cap.
- These entries merge into the same `ordered` list `_digest_selection`
  already consumes — no template or line-formatting change needed, since
  `_digest_line` prints whatever `alert_level` an event carries (`Alert
  Green.` renders exactly like `Alert Orange.` does today).

### Where it lives

- `natcat.py`: new `top_green_per_type(missing_types, days=7, end=...,
  exclude_ids=())` — one query per type still missing after Orange/Red,
  mirroring the existing per-type loop already used inside `gdacs_events`.
  Returns at most one event per type, or none for a type with no eligible
  Green event at all (not an error — a quiet type is a fact, not a gap to
  fill with a stretch pick).
- `report.py`:
  - New pure helper `_load_featured_history()` /
    `_save_featured_history(ids)` — thin JSON read/write, easy to unit test
    by pointing at a temp path.
  - New pure helper `_filter_unfeatured(events, history)` — the eligibility
    filter, testable without network.
  - `weekly_digest()`: after building `events` from Orange/Red, filter by
    history; compute the missing peril types; call
    `natcat.top_green_per_type` for those; merge the result into `ordered`
    before `_digest_selection`; after building `listed`, save the union of
    `listed` event_ids (+ any headline id) into history.
  - Intro sentence (`values["ALERT_FILTER"]` / opening paragraph) updated so
    the method statement stays accurate: it currently reads "entered the
    list at Orange or Red level"; it needs to also say, in one added clause,
    that a Green-level event fills in for a risk type with nothing more
    severe this week. No invented framing — this describes the actual
    query, same standard the rest of the template already holds to.

### Testing

Following the existing style in `test_digest.py` (pure functions, no network
mock — `gdacs_events` itself is exercised against the live feed per the
project's own workflow, not unit-tested):

- `_filter_unfeatured`: an event whose id is in history is dropped; one that
  isn't stays; order is preserved.
- The "highest score, fall through on exclusion" selection logic (the ranking
  half of `top_green_per_type`, factored so it can be tested on a plain list
  of dicts without a real query): given events of one type with descending
  `alert_score` and one exclusion, the next-highest not excluded is chosen;
  if all are excluded, nothing is returned for that type (no stretch pick).
- History round-trip: write then load returns the same ids.

### Out of scope

- No change to the Orange/Red selection logic, the 8-line cap, the figure,
  or the overflow sentence — those already behave correctly.
- No change to how droughts/other long-running continuing events are
  counted — this only affects what gets shown *by name*.
- No retroactive suppression of anything not already published: history
  starts seeded with only what has actually appeared by name in a published
  digest so far — concretely, the China flood (`event_id` from this week's
  already-generated `2026-09-14-digest.txt`) and the Nepal flood headlined
  the week before. Seeding is a one-time manual step run once, alongside
  this change, not an ongoing mechanism. From then on the history file is
  self-maintaining: every future `weekly_digest(write=True)` run appends
  what it showed, with no further manual seeding needed.
