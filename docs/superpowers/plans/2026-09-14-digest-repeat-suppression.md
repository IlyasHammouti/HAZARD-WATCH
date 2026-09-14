# Digest repeat suppression + per-risk Green top-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the weekly digest from re-headlining the same continuing GDACS
event indefinitely, and give every peril type (earthquake, cyclone, volcano,
wildfire, flood, drought) a fresh weekly entry via that type's most severe
Green-level event when nothing of its own reached Orange/Red.

**Architecture:** A small git-ignored JSON history file records every
`event_id` ever shown by name (headline or Events bullet) in a published
digest. `weekly_digest()` filters headline/listing candidates against it
(Red always bypasses, per the existing "a Red alert is never hidden" rule),
and fills any peril type left with nothing eligible using a new
`natcat.top_green_per_type()` call ranked by GDACS's own `alertscore`
field. The figure and the "N more, already running" overflow accounting
are untouched — a suppressed event still counts, it just stops being named.

**Tech Stack:** Python 3, stdlib `json`/`pathlib` only. No new dependencies.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-09-14-digest-repeat-suppression-design.md`.
- Red is always eligible to be headlined/listed, regardless of history —
  never suppress a Red alert (editorial rules: "a Red alert is never
  hidden").
- Never invent a ranking: the only ordering signal for "most important
  Green event" is GDACS's own `alert_score` field.
- History file: `climada_flood/data/cache/digest_featured.json`, git-ignored
  (`climada_flood/data/cache/` is already in `.gitignore`).
- No template/formatting change beyond one new placeholder, `{{GREEN_NOTE}}`,
  added to `climada_flood/templates/01-weekly-digest.md` — everything else
  (`_digest_line`, `_digest_peril`, `_digest_fact`, etc.) already renders any
  alert level generically and needs no change.
- All new pure logic (suppression filter, headline priority, green-event
  ranking) must be unit-testable without a network call, matching the
  existing style in `climada_flood/test_digest.py`.
- Run tests with: `cd "C:/Dev/INO RE/climada_flood" && PYTHONPATH="C:/Dev/INO RE/climada_flood" conda run -n climada_env python test_digest.py`
  (PowerShell: no `&&` — use `;` — but the repo is being driven from Git
  Bash/Bash tool in this session, where `&&` works).

---

### Task 1: Suppression + headline-priority helpers (`report.py`)

**Files:**
- Modify: `climada_flood/report.py` (add near `_digest_selection`, around line 2440)
- Test: `climada_flood/test_digest.py` (add near the other `_digest_*` tests)

**Interfaces:**
- Consumes: nothing new — plain event dicts shaped like `_gdacs_event`'s
  output (`event_id`, `alert_level`, `event_type`, `is_new`, ...), same
  shape the `event()` test helper in `test_digest.py` already builds.
- Produces:
  - `_filter_unfeatured(events: list, history: dict) -> list` — used by
    Task 4.
  - `_pick_headline(new: list, continuing: list, green_topups: list, history: dict) -> dict | None`
    — used by Task 4.
  - Modified `_digest_selection` (existing, current line 2440): a Green
    top-up must always be listed as a bullet, even when it is not `is_new`
    (a continuing Green event promoted to represent its type still needs to
    say so explicitly, not just get folded into the figure).

- [ ] **Step 1: Write the failing tests**

Add to `climada_flood/test_digest.py`, near `test_text_lists_only_what_the_figure_cannot_carry`:

```python
def test_filter_unfeatured_drops_previously_shown_events():
    """A Red alert is never hidden, however long it has run or repeated."""
    history = {"3": {"first_shown": "2026-09-07", "name": "Flood in China"}}
    fresh = event(event_id=1)
    shown_before = event(event_id=3)
    red_shown_before = event(event_id=3, alert_level="Red")
    assert [e["event_id"] for e in
            report._filter_unfeatured([fresh, shown_before], history)] == [1]
    assert [e["event_id"] for e in
            report._filter_unfeatured([red_shown_before], history)] == [3]


def test_headline_prefers_new_then_red_then_green_topup_then_continuing():
    new_event = event(event_id=1, is_new=True)
    red = event(event_id=2, alert_level="Red")
    topup = {**event(event_id=3, event_type="EQ"), "green_topup": True}
    old = event(event_id=4)
    history = {}

    assert report._pick_headline([new_event], [red], [topup], history)["event_id"] == 1
    assert report._pick_headline([], [red, old], [topup], history)["event_id"] == 2
    assert report._pick_headline([], [old], [topup], history)["event_id"] == 3
    assert report._pick_headline([], [old], [], history)["event_id"] == 4
    assert report._pick_headline([], [], [], history) is None


def test_headline_skips_a_suppressed_continuing_event_when_nothing_else_exists():
    """The whole point: an old event shown once must not headline again,
    even with no fresh Green pick to replace it — unless it is the only
    event left in the world, the true last-resort safety net."""
    history = {"9": {"first_shown": "2026-09-07", "name": "Flood in China"}}
    suppressed = event(event_id=9)
    assert report._pick_headline([], [suppressed], [], history) is not None
    assert report._pick_headline([], [suppressed], [], history)["event_id"] == 9

    other = event(event_id=10)
    assert report._pick_headline(
        [], [suppressed, other], [], history)["event_id"] == 10


def test_digest_selection_always_lists_a_green_topup():
    """A Green top-up must appear as a bullet even when it is not `is_new` -
    otherwise it silently falls to the figure and the whole point (giving
    each risk type an explicit line) is lost."""
    continuing_topup = {**event(event_id=5, is_new=False, alert_level="Green"),
                        "green_topup": True}
    old = event(event_id=6)
    listed, dropped = report._digest_selection([continuing_topup, old], 8)
    assert [e["event_id"] for e in listed] == [5]
    assert [e["event_id"] for e in dropped] == [6]
```

Note the third assertion in `test_headline_skips_a_suppressed_continuing_event_when_nothing_else_exists`:
when a suppressed event is truly the *only* candidate anywhere, it still
returns rather than publishing an empty "Most recent:" line — that is the
documented last-resort safety net, not a suppression bug. The fourth
assertion is the actual fix: once a second, non-suppressed continuing event
exists, the suppressed one no longer wins.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "C:/Dev/INO RE/climada_flood" && PYTHONPATH="C:/Dev/INO RE/climada_flood" conda run -n climada_env python test_digest.py
```

Expected: `AttributeError: module 'report' has no attribute '_filter_unfeatured'`.

- [ ] **Step 3: Implement the two new functions, and extend `_digest_selection`**

First, widen `_digest_selection`'s predicate so a Green top-up is always
listed. Change (current lines 2450-2451):

```python
    listed = [e for e in ordered
              if e["is_new"] or e["alert_level"] == "Red"][:max_bullets]
```

to:

```python
    listed = [e for e in ordered
              if e["is_new"] or e["alert_level"] == "Red"
              or e.get("green_topup")][:max_bullets]
```

and update the function's docstring (current lines 2441-2449) to add, after
the existing "Everything else is a row in the figure's table" paragraph:

```
A Green top-up is always listed regardless of `is_new` - it was chosen
specifically to represent its risk type this week, and silently folding it
into the figure instead would defeat the reason it was picked.
```

Then add the two new functions directly above `_digest_selection` (currently line 2440):

```python
def _filter_unfeatured(events: list, history: dict) -> list:
    """Events still eligible to be headlined or listed by name this week.

    A Red alert is always eligible, however long it has run or however many
    times it has already been shown: rules section 5, a Red alert is never
    hidden. Anything else drops out once its `event_id` has appeared, by
    name, in a previously published digest.
    """
    return [e for e in events
            if e["alert_level"] == "Red" or str(e["event_id"]) not in history]


def _pick_headline(new: list, continuing: list, green_topups: list,
                    history: dict) -> dict | None:
    """The week's headline, in priority order: new, Red, this week's Green
    top-up, then whatever else is still running.

    `continuing` is the raw, unfiltered list. Without this function, the
    only thing keeping an old continuing event from resurfacing was chance
    of it also being the one with the most recent start date among a thin
    set - that is exactly how a month-old flood ended up "Most recent" two
    weeks running. Red and the Green top-ups are checked first, and a
    suppressed continuing event is skipped as long as anything else is
    available; it is used only as the very last resort, so a quiet week
    with nothing else in the world never publishes an empty headline line.
    """
    reds = [e for e in continuing if e["alert_level"] == "Red"]
    eligible_continuing = _filter_unfeatured(continuing, history)
    for group in (new, reds, green_topups, eligible_continuing, continuing):
        if group:
            return group[0]
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "C:/Dev/INO RE/climada_flood" && PYTHONPATH="C:/Dev/INO RE/climada_flood" conda run -n climada_env python test_digest.py
```

Expected: all checks print `ok`, including the four new ones.

- [ ] **Step 5: Commit**

```bash
git add climada_flood/report.py climada_flood/test_digest.py
git commit -m "$(cat <<'EOF'
Add suppression filter and headline-priority helpers to the digest

Pure, network-free building blocks for stopping a continuing GDACS
event from being re-headlined indefinitely: _filter_unfeatured
excludes anything already shown by name (Red alerts excepted),
_pick_headline picks new > Red > Green top-up > continuing, with a
last-resort fallback so a quiet week never publishes an empty
headline line. _digest_selection now also always lists a Green
top-up as a bullet, even when it is not `is_new`.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Per-type Green ranking (`natcat.py`)

**Files:**
- Modify: `climada_flood/natcat.py` (add after `gdacs_events`, around line 764)
- Test: `climada_flood/test_digest.py`

**Interfaces:**
- Consumes: `natcat.gdacs_events` (existing, unchanged), `natcat.GDACS_TYPES`
  (existing constant, tuple of the 6 peril codes).
- Produces:
  - `_pick_top_unexcluded(events: list, exclude_ids) -> dict | None` — the
    pure ranking step, `exclude_ids` any container supporting `in` with
    string ids.
  - `top_green_per_type(types: tuple, days: int = 7, end=None, exclude_ids=frozenset()) -> list`
    — used by Task 4. One network call per type in `types`, same pattern
    `gdacs_events` already uses per-type internally.

- [ ] **Step 1: Write the failing test**

Add to `climada_flood/test_digest.py`:

```python
def test_pick_top_unexcluded_ranks_by_alert_score_and_skips_excluded():
    import natcat

    low = {"event_id": 1, "alert_score": 1}
    high = {"event_id": 2, "alert_score": 5}
    mid = {"event_id": 3, "alert_score": 3}
    no_score = {"event_id": 4, "alert_score": None}

    assert natcat._pick_top_unexcluded([low, high, mid], frozenset())["event_id"] == 2
    # The highest-scoring one is excluded: falls through to the next.
    assert natcat._pick_top_unexcluded([low, high, mid], {"2"})["event_id"] == 3
    # Every candidate excluded: nothing to return, never a stretch pick.
    assert natcat._pick_top_unexcluded([low], {"1"}) is None
    assert natcat._pick_top_unexcluded([], frozenset()) is None
    # A missing/None alert_score ranks as 0, never crashes the comparison.
    assert natcat._pick_top_unexcluded([no_score, low], frozenset())["event_id"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "C:/Dev/INO RE/climada_flood" && PYTHONPATH="C:/Dev/INO RE/climada_flood" conda run -n climada_env python test_digest.py
```

Expected: `AttributeError: module 'natcat' has no attribute '_pick_top_unexcluded'`.

- [ ] **Step 3: Implement**

Add to `climada_flood/natcat.py`, directly after `gdacs_events` (after the
`return events` on the current line 764, before `_gdacs_event`):

```python
def _pick_top_unexcluded(events: list, exclude_ids) -> dict | None:
    """The event with the highest `alert_score`, skipping excluded ids.

    `alert_score` is a real field GDACS publishes on every event; nothing
    here invents a ranking. A missing score sorts as 0 rather than raising,
    since GDACS does not guarantee it is always present.
    """
    eligible = [e for e in events if str(e["event_id"]) not in exclude_ids]
    if not eligible:
        return None
    return max(eligible, key=lambda e: e.get("alert_score") or 0)


def top_green_per_type(types: tuple, days: int = 7, end: date | None = None,
                        exclude_ids=frozenset()) -> list:
    """The single most severe Green-level event for each peril type.

    One GDACS query per type in `types`, mirroring the per-type loop
    `gdacs_events` already runs. A type with no Green event at all, or
    whose every candidate is in `exclude_ids`, is simply absent from the
    result - never filled with a lesser stand-in, and never raises.

    Parameters
    ----------
    types : peril codes to fetch; typically whatever `weekly_digest` found
        no eligible Orange/Red event for this week.
    days, end : the same window `gdacs_events` takes.
    exclude_ids : event ids (as strings) that must not be picked however
        high their score - the digest's featured-event history.

    Returns
    -------
    List of event dictionaries, same shape `gdacs_events` returns, at most
    one per type in `types`, in the order `types` was given.
    """
    picks = []
    for peril in types:
        candidates = gdacs_events(days=days, types=(peril,), end=end,
                                   alert_levels=("Green",))
        pick = _pick_top_unexcluded(candidates, exclude_ids)
        if pick is not None:
            picks.append(pick)
    return picks
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "C:/Dev/INO RE/climada_flood" && PYTHONPATH="C:/Dev/INO RE/climada_flood" conda run -n climada_env python test_digest.py
```

Expected: all checks print `ok`.

- [ ] **Step 5: Commit**

```bash
git add climada_flood/natcat.py climada_flood/test_digest.py
git commit -m "$(cat <<'EOF'
Add natcat.top_green_per_type for the digest's per-risk fallback

Ranks each peril type's Green-level events by GDACS's own
alert_score and returns the highest-scoring one not already
excluded, so a risk type with nothing at Orange/Red this week can
still get a fresh, real entry instead of being skipped entirely.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Featured-history persistence (`report.py`)

**Files:**
- Modify: `climada_flood/report.py` (add near the top-level constants, after
  `TEMPLATES = ROOT / "templates"`, and near `_drop_empty_sections`)
- Test: `climada_flood/test_digest.py`

**Interfaces:**
- Consumes: `CACHE` (existing constant, `ROOT / "data" / "cache"`).
- Produces:
  - `FEATURED_HISTORY_PATH: Path` — `CACHE / "digest_featured.json"`.
  - `_load_featured_history(path: Path = FEATURED_HISTORY_PATH) -> dict`
  - `_save_featured_history(history: dict, path: Path = FEATURED_HISTORY_PATH) -> None`
  - Both used by Task 4. History keys are **strings** (JSON object keys are
    always strings, so every caller must `str(event_id)` before checking
    membership — `_filter_unfeatured` and `_pick_top_unexcluded` from Tasks
    1-2 already do this).

- [ ] **Step 1: Write the failing test**

Add to `climada_flood/test_digest.py`. Note `test_digest.py` runs its checks
as plain functions with no fixture framework (see `if __name__ ==
"__main__"` at the bottom, which calls every `test_*` global with no
arguments) — so this uses `tempfile` directly rather than a `tmp_path`
fixture:

```python
def test_featured_history_round_trips_through_json():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "digest_featured.json"
        assert report._load_featured_history(path) == {}

        history = {"1104081": {"first_shown": "2026-09-14", "name": "Flood in China"}}
        report._save_featured_history(history, path)
        assert report._load_featured_history(path) == history

        report._save_featured_history(
            {**history, "2": {"first_shown": "2026-09-14", "name": "x"}}, path)
        reloaded = report._load_featured_history(path)
        assert set(reloaded) == {"1104081", "2"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "C:/Dev/INO RE/climada_flood" && PYTHONPATH="C:/Dev/INO RE/climada_flood" conda run -n climada_env python test_digest.py
```

Expected: `AttributeError: module 'report' has no attribute '_load_featured_history'`.

- [ ] **Step 3: Implement**

Add near the top of `climada_flood/report.py`, directly after the existing
`TEMPLATES = ROOT / "templates"` line:

```python
FEATURED_HISTORY_PATH = CACHE / "digest_featured.json"
```

Add the two functions next to `_drop_empty_sections` (current line 2527):

```python
def _load_featured_history(path: Path = FEATURED_HISTORY_PATH) -> dict:
    """`event_id` (string) -> `{"first_shown": iso date, "name": ...}`.

    Empty when the file does not exist yet - the first run after this
    feature ships starts with nothing suppressed, which is why Task 4 seeds
    it once by hand for the events already published by name.
    """
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_featured_history(history: dict,
                           path: Path = FEATURED_HISTORY_PATH) -> None:
    """Persist the full history dict, creating the cache folder if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(history, indent=2, sort_keys=True),
                    encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "C:/Dev/INO RE/climada_flood" && PYTHONPATH="C:/Dev/INO RE/climada_flood" conda run -n climada_env python test_digest.py
```

Expected: all checks print `ok`.

- [ ] **Step 5: Commit**

```bash
git add climada_flood/report.py climada_flood/test_digest.py
git commit -m "$(cat <<'EOF'
Add featured-event history persistence for the weekly digest

Thin JSON read/write for the cache file that will record every
event shown by name in a published digest, so a future run can
tell _filter_unfeatured what to exclude. No caller yet - wired up
in the next task.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Wire it into `weekly_digest()`, seed history, regenerate this week's post

**Files:**
- Modify: `climada_flood/report.py:2536-2656` (`weekly_digest`)
- Modify: `climada_flood/templates/01-weekly-digest.md:37-39`
- Create (generated, not hand-written): `climada_flood/data/cache/digest_featured.json` (seed)
- Regenerate (local output only, git-ignored, not committed):
  `climada_flood/output/digests/2026-09-14-digest.txt`, `.md`, `.png`

**Interfaces:**
- Consumes: everything from Tasks 1-3 (`_filter_unfeatured`,
  `_pick_headline`, `natcat.top_green_per_type`, `_load_featured_history`,
  `_save_featured_history`, `natcat.GDACS_TYPES`).
- Produces: the updated `weekly_digest()` behavior — no new public
  interface, this is the integration point.

- [ ] **Step 1: Add the `{{GREEN_NOTE}}` placeholder to the template**

In `climada_flood/templates/01-weekly-digest.md`, change line 39 from:

```
The natural catastrophes you may have missed last week, from the GDACS alert
feed. {{NEW_COUNT}} entered the list at {{ALERT_FILTER}} level and
{{CONTINUING_COUNT}} already running. {{RED_STATEMENT}}
```

to:

```
The natural catastrophes you may have missed last week, from the GDACS alert
feed. {{NEW_COUNT}} entered the list at {{ALERT_FILTER}} level and
{{CONTINUING_COUNT}} already running. {{RED_STATEMENT}}{{GREEN_NOTE}}
```

Also update the comment block above it (lines 17-35) to document the new
field, adding after the existing "RED_STATEMENT is not decoration" paragraph:

```
GREEN_NOTE names a peril type only when this week substituted its most
severe Green-level event for a missing Orange/Red one. Empty most weeks,
same as PENDING_LINES - nothing is said about a mechanism that was not
used.
```

- [ ] **Step 2: Rewrite the event-selection section of `weekly_digest()`**

In `climada_flood/report.py`, replace this block (currently lines 2554-2569):

```python
    events = natcat.gdacs_events(days=7, alert_levels=alert_levels, end=week_end)
    cases = natcat.pending_cases(events, end=week_end)

    new = [e for e in events if e["is_new"]]
    continuing = [e for e in events if not e["is_new"]]

    # New events first, then the continuing ones, each already sorted by alert
    # level and date by `gdacs_events`.
    ordered = new + continuing

    listed, dropped = _digest_selection(ordered, max_bullets)

    headline = (new or events or [None])[0]
    locked = locked_phrases()

    overflow = _digest_remainder(dropped)
```

with:

```python
    events = natcat.gdacs_events(days=7, alert_levels=alert_levels, end=week_end)
    cases = natcat.pending_cases(events, end=week_end)

    new = [e for e in events if e["is_new"]]
    continuing = [e for e in events if not e["is_new"]]

    # A risk type gets a Green top-up only when nothing of its own is
    # eligible at Orange/Red this week - "eligible" excludes whatever has
    # already been shown by name in a previous digest, Red alerts excepted.
    history = _load_featured_history()
    covered_types = {e["event_type"]
                     for e in _filter_unfeatured(events, history)}
    missing_types = [t for t in natcat.GDACS_TYPES if t not in covered_types]

    green_topups = []
    if missing_types:
        picks = natcat.top_green_per_type(missing_types, days=7, end=week_end,
                                          exclude_ids=set(history))
        green_topups = [{**e, "green_topup": True} for e in picks]
        # Most severe first, so a headline that falls through to the Green
        # top-ups (nothing new, nothing Red) picks the single most
        # significant one across every filled-in type, not just whichever
        # peril happens to sort first.
        green_topups.sort(key=lambda e: e.get("alert_score") or 0, reverse=True)

    # New events first, then the continuing ones (both raw - the figure and
    # the overflow sentence account for every event regardless of whether it
    # is eligible to be named), then this week's Green top-ups.
    ordered = new + continuing + green_topups

    listed, dropped = _digest_selection(ordered, max_bullets)

    headline = _pick_headline(new, continuing, green_topups, history)
    locked = locked_phrases()

    overflow = _digest_remainder(dropped)
```

- [ ] **Step 3: Add `GREEN_NOTE` to the template values and save history after writing**

In the `values = {` dict (currently lines 2595-2620), add a new entry right
after `"RED_STATEMENT": _red_statement(reds),`:

```python
        "GREEN_NOTE": (
            f" The list also carries the most significant Green-level event "
            f"for {len(green_topups)} risk type"
            f"{'s' if len(green_topups) != 1 else ''} with nothing more "
            f"severe this week."
        ) if green_topups else "",
```

Then, in the `if write:` block that currently writes `draft_path` and
`plain_path` (currently lines 2626-2632), add the history save right after
the two `write_text` calls, still inside `if write:`:

```python
        shown = listed + ([headline] if headline else [])
        newly_featured = {
            str(e["event_id"]): {"first_shown": str(monday), "name": e["name"]}
            for e in shown
        }
        if newly_featured:
            _save_featured_history({**history, **newly_featured})
```

- [ ] **Step 4: Run the full test suite**

```bash
cd "C:/Dev/INO RE/climada_flood" && PYTHONPATH="C:/Dev/INO RE/climada_flood" conda run -n climada_env python test_digest.py
```

Expected: every check prints `ok`, nothing broken by the template or
`weekly_digest` changes (the template test,
`test_every_locked_string_a_template_asks_for_exists`, only checks
`{{LOCKED:...}}` ids, so the new `{{GREEN_NOTE}}` placeholder does not
affect it).

- [ ] **Step 5: Seed the history file with what has already been published by name**

This is the one manual, one-time step (per the spec's "Out of scope"
section) - without it, the first run after this change would have empty
history and would headline China again, since nothing has told the new
code it was already shown.

`climada_flood/data/cache/` is git-ignored (confirmed: `git check-ignore -v
climada_flood/data/cache/digest_featured.json` matches
`climada_flood/.gitignore:3:data/`), same as every other pipeline cache -
this file is local machine state, not a versioned artifact, and Step 7 does
not commit it.

Write `climada_flood/data/cache/digest_featured.json`:

```json
{
  "1104081": {"first_shown": "2026-09-14", "name": "Flood in China"},
  "1104124": {"first_shown": "2026-09-07", "name": "Flood in Nepal"}
}
```

(`1104081` is China's GDACS `event_id`, headlined in the 2026-09-14 draft
this feature exists to fix; `1104124` is Nepal's, Red, headlined the week
before - confirmed against the live GDACS feed while investigating this
issue. Nepal's flood already closed on the GDACS feed on 2026-09-01 and
will not reappear on its own, but seeding it costs nothing and keeps the
history accurate.)

- [ ] **Step 6: Regenerate this week's digest and inspect it**

```bash
cd "C:/Dev/INO RE/climada_flood" && PYTHONPATH="C:/Dev/INO RE/climada_flood" conda run -n climada_env python -c "import report; d=report.weekly_digest(monday='2026-09-14'); print(d['words']); print(); print(d['plain'])"
```

Confirm by reading the printed plain text:
- The headline is no longer "Flood in China" (China's `event_id` 1104081 is
  now in history, and the flood type had no other eligible Orange/Red
  event, so `FL` lands in `missing_types` and gets a Green top-up instead -
  or, if GDACS's Green flood data that week has nothing usable either, some
  other type's Red/Green candidate wins per `_pick_headline`'s priority
  order).
- `GREEN_NOTE` appears in the opening paragraph, naming how many risk types
  were filled by a Green top-up, whenever `missing_types` was non-empty.
- The `## Events` section (previously absent - nothing was new or Red that
  week) now lists each Green top-up as a bullet, in the same
  `Peril, Country, Alert Level. Fact.` format every other line uses.
- `climada_flood/data/cache/digest_featured.json` gained one entry per
  newly headlined/listed event_id from this run (inspect the file after).

If the headline or the Events section still look wrong, do not move on -
that means a step above was mis-transcribed; re-check Steps 2-3 against the
exact line numbers before continuing.

- [ ] **Step 7: Commit**

`climada_flood/output/` is git-ignored (`climada_flood/.gitignore` /
root `.gitignore:43`); confirm with `git status --porcelain --ignored
climada_flood/output/digests/` before adding anything from that folder -
regenerated digest files are local output, not committed, regardless of
whether an older digest under that path happens to already be tracked from
before the ignore rule existed.

```bash
git add climada_flood/report.py climada_flood/templates/01-weekly-digest.md
git commit -m "$(cat <<'EOF'
Wire repeat suppression and Green top-ups into weekly_digest()

China's flood (event_id 1104081) had been headlined two weeks
running - once in overflow, once as "Most recent" - purely because
it had the latest start date among a thin, stale Orange/Red set.
weekly_digest() now filters headline/listing candidates through the
featured-event history (Red alerts excepted) and fills any peril
type left with nothing eligible using that type's top Green-level
event, so every week surfaces something real per risk category
instead of repeating whatever happened to be "most recent" among
old continuing events. History seeded once with China's and Nepal's
already-published event ids; self-maintaining from here.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Post-plan verification

- [ ] Re-read the regenerated `climada_flood/output/digests/2026-09-14-digest.txt`
  end to end against `docs/HANDOVER.md`'s publication workflow and the
  editorial rules (`docs/EDITORIAL_RULES.md` sections 5, 7, 9) before it is
  pasted anywhere - this plan produces the draft, it does not sign off on
  publishing it (rule 11, human plausibility check, same as every other
  post type).
