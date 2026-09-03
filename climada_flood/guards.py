"""Refuse to publish a figure the chain has no right to produce.

At one event a week a wrong number is embarrassing. At one a day, unattended,
it is the main risk this project carries: the chain will happily apply a
floodplain damage curve to a Himalayan torrent and return a confident figure in
euros, because nothing in the arithmetic knows the difference.

These checks encode what the measurements are actually allowed to support. A
blocking finding does not stop the post: it lowers the **tier**, so an event
that cannot carry a currency figure still gets an extent and a population.

Tiers, as set out in docs/DECISIONS.md:

1. modelled loss in currency
2. exposed value and affected population
3. observed extent only

**The tier governs modelled figures and nothing else.** This is the change
that defines V2. In V1 the tier gated the whole post, so EMSR927 published no
number at all while Copernicus EMS had already counted 2 521 destroyed
buildings in the same valley. That is a category error: the editorial rules
already separate *Modelled*, which this pipeline computed, from *Reported*,
which is quoted from a named source with a date. A weak measurement of ours
says nothing about someone else's count.

So a verdict now carries two things: the tier, which limits what we may
compute, and the reported facts, which are published with their source
whatever the tier says.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Thresholds. Each one has a measured or documented reason, not a round number
# picked because it looked reasonable.
# ---------------------------------------------------------------------------

# Below this share of the observed area, radar saw so little that a loss figure
# would describe a minority of the exposure. Measured on EMSR664: 57 %
# assessable already meant 43 % of exposed value unaccounted for.
MIN_ASSESSABLE = 0.35

# Below this share of the area actually observed at all, the footprint is a
# sample rather than a map.
MIN_COVERAGE = 0.60

# JRC depth-damage curves are calibrated on floodplains. Beyond this share of
# steep ground the flow is a torrent, not standing water, and radar suffers
# shadow and layover in the valleys where the water is. Measured: 5 % steep in
# Emilia-Romagna against 59 % in Rasuwa.
MAX_STEEP_SHARE = 0.25

# A footprint this small at 20 m is a few hundred pixels: within the noise the
# despeckling step is there to remove.
MIN_EXTENT_KM2 = 0.5

# Optical infill recovers the pixels radar cannot judge, so it is a minority
# correction by construction and the extent stays a radar product. Measured on
# EMSR664, radar carried 74 % of the extent area. On EMSR926 it carried 11 %,
# and 99.3 % of the exposed value behind the loss figure came from the optical
# layer alone, over ground where docs/DECISIONS.md records MNDWI producing
# false positives precisely because value and buildings sit together there.
# Below this share the post would credit Copernicus Global Flood Monitoring for
# an extent Sentinel-2 produced.
MIN_RADAR_SHARE = 0.25

# Damage ratio outside this band means the curve is being read far from where
# it was calibrated, or the depth assumption is wrong.
DAMAGE_RATIO_BAND = (0.02, 0.85)

# A single event destroying more than this share of a region's entire built
# capital is not impossible, but it is never something to publish unreviewed.
MAX_LOSS_VS_REGION = 0.15

# Flood mechanisms the JRC depth-damage curves were built for. Anything else
# damages by force, debris or burial rather than by standing water depth.
DEPTH_DAMAGE_MECHANISMS = {"riverine", "coastal", "pluvial"}


@dataclass
class Finding:
    """One check, its verdict, and why."""

    code: str
    level: str  # "ok", "warn" or "block"
    message: str
    value: object = None

    def __str__(self) -> str:
        mark = {"ok": "ok  ", "warn": "WARN", "block": "STOP"}[self.level]
        return f"[{mark}] {self.code}: {self.message}"


@dataclass
class Verdict:
    """What the evidence supports, and everything that was checked.

    `tier` limits the figures this pipeline computes. `reported` holds facts
    published by a named source, which the tier does not touch and which the
    post carries with its attribution.
    """

    tier: int
    findings: list = field(default_factory=list)
    reported: dict = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return any(f.level == "block" for f in self.findings)

    @property
    def warnings(self) -> list:
        return [f for f in self.findings if f.level == "warn"]

    @property
    def blockers(self) -> list:
        return [f for f in self.findings if f.level == "block"]

    def report(self) -> str:
        lines = [f"Tier {self.tier} of 3"]
        lines += [str(f) for f in self.findings]
        return "\n".join(lines)


def check_imagery(scenes: int, next_pass=None) -> Finding:
    """Is there anything observed after the event at all?"""
    if scenes > 0:
        return Finding("IMAGERY", "ok", f"{scenes} post-event scenes", scenes)
    when = f" Next pass estimated {next_pass}." if next_pass else ""
    return Finding(
        "IMAGERY", "block",
        f"No post-event imagery yet.{when} Publish the pending-case note "
        f"instead of an extent.", 0,
    )


def check_coverage(coverage: float) -> Finding:
    if coverage >= MIN_COVERAGE:
        return Finding("COVERAGE", "ok",
                       f"{coverage:.0%} of the area observed", coverage)
    return Finding(
        "COVERAGE", "warn",
        f"Only {coverage:.0%} of the area was observed, below the "
        f"{MIN_COVERAGE:.0%} the footprint needs to be read as a map.",
        coverage,
    )


# Who is doing the assessing, so the finding never credits radar for an
# outline that came from an operator reading 50 cm optical.
ASSESSOR = {
    "gfm": "Radar",
    "ems": "The Copernicus EMS operators",
    "manual": "The operator",
    "none": "The imagery",
}


def check_assessable(assessable: float, source: str = "gfm") -> Finding:
    who = ASSESSOR.get(source, "The imagery")
    if assessable >= MIN_ASSESSABLE:
        return Finding("ASSESSABLE", "ok",
                       f"{who} could assess {assessable:.0%} of the area",
                       assessable)
    return Finding(
        "ASSESSABLE", "block",
        f"{who} could assess only {assessable:.0%} of the area, below "
        f"{MIN_ASSESSABLE:.0%}. A loss figure would describe a minority of the "
        f"exposure and read as if it described all of it.",
        assessable,
    )


def check_terrain(steep_share: float | None) -> Finding:
    """Is this the kind of ground the damage curves were built for?"""
    if steep_share is None:
        return Finding("TERRAIN", "warn", "Terrain steepness not measured", None)
    if steep_share <= MAX_STEEP_SHARE:
        return Finding("TERRAIN", "ok",
                       f"{steep_share:.0%} of the ground is steep", steep_share)
    return Finding(
        "TERRAIN", "block",
        f"{steep_share:.0%} of the ground exceeds 20 degrees, against "
        f"{MAX_STEEP_SHARE:.0%} allowed. Depth-damage curves assume standing "
        f"water on a floodplain; on this terrain the flow is a torrent and "
        f"radar is blinded by shadow in the valleys.",
        steep_share,
    )


def check_mechanism(mechanism: str) -> Finding:
    """Does the peril damage things the way the curve assumes?"""
    if mechanism in DEPTH_DAMAGE_MECHANISMS:
        return Finding("MECHANISM", "ok",
                       f"{mechanism} flooding suits a depth-damage curve",
                       mechanism)
    return Finding(
        "MECHANISM", "block",
        f"A {mechanism} damages by force, debris or burial, not by standing "
        f"water depth. The JRC curve would return a number, and the number "
        f"would mean nothing.",
        mechanism,
    )


def check_extent(extent_km2: float) -> Finding:
    if extent_km2 >= MIN_EXTENT_KM2:
        return Finding("EXTENT", "ok", f"{extent_km2:.1f} km² detected",
                       extent_km2)
    return Finding(
        "EXTENT", "block",
        f"Detected extent of {extent_km2:.2f} km² is within the noise the "
        f"despeckling step removes. Nothing reliable was seen.",
        extent_km2,
    )


def check_infill(radar_km2: float, extent_km2: float) -> Finding:
    """Is this still a radar extent, or has the infill become the product?

    Every other check reads the extent as a whole. This one reads what it is
    made of, which is the thing that went wrong on EMSR926: not one threshold
    was breached, and the currency figure still rested almost entirely on an
    optical layer designed to be a correction.
    """
    if not extent_km2:
        return Finding("INFILL", "warn", "No extent to decompose", None)
    share = radar_km2 / extent_km2
    if share >= MIN_RADAR_SHARE:
        return Finding("INFILL", "ok",
                       f"{share:.0%} of the extent came from radar", share)
    return Finding(
        "INFILL", "block",
        f"Radar produced only {share:.0%} of the extent, below "
        f"{MIN_RADAR_SHARE:.0%}. The remainder is Sentinel-2 infill, which "
        f"exists to correct the radar blind spot rather than to replace the "
        f"measurement, and which over-detects on built-up land. Report the "
        f"extent and the exposed value; do not attach a currency figure to it.",
        share,
    )


def check_exposure(exposed: float) -> Finding:
    if exposed > 0:
        return Finding("EXPOSURE", "ok", f"{exposed:,.0f} exposed", exposed)
    return Finding("EXPOSURE", "block",
                   "No exposed value inside the footprint.", exposed)


def check_damage_ratio(ratio: float) -> Finding:
    low, high = DAMAGE_RATIO_BAND
    if low <= ratio <= high:
        return Finding("DAMAGE_RATIO", "ok", f"{ratio:.0%} damage ratio", ratio)
    return Finding(
        "DAMAGE_RATIO", "warn",
        f"Damage ratio of {ratio:.0%} falls outside {low:.0%} to {high:.0%}. "
        f"Check the depth assumption and the sector before publishing.",
        ratio,
    )


def check_provenance(source: str, provenance: dict | None) -> Finding:
    """Can a reader tell where this outline came from?

    Every other check here tests a measurement against something. A hand-drawn
    outline has nothing to be tested against: the operator is the instrument.
    So this one does not judge the outline, it makes sure the post says the
    outline was drawn, which is what H13 requires.
    """
    if source == "ems":
        return Finding("PROVENANCE", "ok",
                       "Extent mapped by Copernicus EMS operators from very "
                       "high resolution imagery", source)
    if source != "manual":
        return Finding("PROVENANCE", "ok", "Extent from an automated product",
                       source)
    scenes = "; ".join(f"{s['sensor']} {s['acquired'][:10]}"
                       for s in (provenance or {}).get("imagery", []))
    return Finding(
        "PROVENANCE", "warn",
        f"Extent drawn by hand by {(provenance or {}).get('operator', 'unknown')} "
        f"from {scenes or 'unrecorded imagery'}. L-SRC-MANUAL and L-DRAWN are "
        f"mandatory in the post (H13).",
        provenance,
    )


# Below this share of graded buildings actually landing on the exposure grid,
# the figure prices a minority of what was observed.
MIN_PLACED = 0.80


def check_graded(result: dict) -> Finding:
    """Is the observed-damage route on solid ground?

    It replaces two assumptions with an observation, so the checks change with
    it. What matters now is whether the graded buildings could be given a
    value at all, and how much of the loss sits on the one grade that needs no
    assumption. `Destroyed` costs its replacement by definition; the lower
    grades are the only place a judgement is being made.
    """
    graded = result.get("graded_buildings") or 0
    if not graded:
        return Finding("GRADED", "warn", "No graded buildings placed on the "
                                         "exposure grid", 0)

    grades = result.get("grades") or {}
    destroyed = grades.get("Destroyed", 0)
    share = destroyed / graded

    low = result.get("loss_low_usd")
    high = result.get("loss_high_usd")
    spread = ((high - low) / high) if (high and low is not None) else None
    spread_text = (f" The assumed range spans {spread:.0%} of the upper bound."
                   if spread else "")

    return Finding(
        "GRADED", "ok",
        f"{graded} buildings priced from their observed grade, "
        f"{share:.0%} of them destroyed and costed at full replacement, which "
        f"is definitional rather than assumed.{spread_text}",
        share,
    )


def check_against_official(detected_km2: float, ems: dict | None) -> Finding:
    """How much of the mapped event our own detection actually found.

    Not a threshold, a measurement. Where Copernicus EMS has mapped the event
    by hand there is a ground truth to check against, and the ratio is the most
    honest thing this project can put next to its own extent. On EMSR927 it was
    10 %, which is what says the detector is the wrong tool in a Himalayan
    valley rather than a tool that needs tuning.
    """
    if not ems or not ems.get("observed_km2"):
        return Finding("VERSUS_EMS", "ok", "No official mapped extent to "
                                           "compare against", None)
    share = detected_km2 / ems["observed_km2"]
    message = (f"Own detection covers {share:.0%} of the {ems['observed_km2']:.1f} "
               f"km2 Copernicus EMS mapped by hand")
    level = "ok" if share >= 0.5 else "warn"
    return Finding("VERSUS_EMS", level, message, share)


def reported_facts(ems: dict | None, timings: dict | None = None) -> dict:
    """Figures published by a named source, which the tier does not gate.

    Everything here is somebody else's measurement, quoted. It is kept apart
    from the modelled result on purpose: the post says who counted what, and a
    weak measurement of ours never suppresses a strong one of theirs.
    """
    facts = {}
    if ems:
        grades = ems.get("building_grades") or {}
        if ems.get("buildings"):
            facts["buildings_mapped"] = ems["buildings"]
            facts["buildings_destroyed"] = grades.get("Destroyed", 0)
            facts["buildings_damaged"] = (grades.get("Damaged", 0)
                                          + grades.get("Possibly damaged", 0))
        if ems.get("observed_km2"):
            facts["observed_km2"] = ems["observed_km2"]
            facts["mechanisms"] = ems.get("mechanisms") or []
        if ems.get("roads_km"):
            facts["roads_km"] = ems["roads_km"]
            facts["roads_destroyed_km"] = ems.get("roads_destroyed_km", 0.0)
        if ems.get("named_destroyed"):
            facts["named_destroyed"] = ems["named_destroyed"]
        facts["source"] = "Copernicus EMS Rapid Mapping"

    if timings:
        for key in ("activation_hours", "first_product_hours"):
            if timings.get(key) is not None:
                facts[key] = timings[key]
    return facts


def check_loss_scale(loss: float, region_total: float) -> Finding:
    """Is the loss credible against everything the region owns?"""
    if not region_total:
        return Finding("LOSS_SCALE", "warn", "No regional total to compare against")
    share = loss / region_total
    if share <= MAX_LOSS_VS_REGION:
        return Finding("LOSS_SCALE", "ok",
                       f"{share:.1%} of the region's built capital", share)
    return Finding(
        "LOSS_SCALE", "warn",
        f"Modelled loss is {share:.0%} of the region's entire built capital. "
        f"Possible, but never publish this unreviewed.",
        share,
    )


def assess(result: dict, mechanism: str = "riverine",
           steep_share: float | None = None,
           region_total: float | None = None,
           next_pass=None, ems: dict | None = None,
           timings: dict | None = None) -> Verdict:
    """Run every check and decide which tier the evidence supports.

    Order matters only for readability; the tier is decided from the set. A
    blocking finding on imagery or extent leaves nothing to publish at all,
    while a block on terrain, mechanism or radar coverage still allows the
    exposed value and the affected population to be reported.
    """
    scenes = len(result.get("timeline", []) or [])
    source = result.get("source", "gfm")
    findings = [check_imagery(scenes, next_pass)]

    if scenes:
        findings += [
            check_provenance(source, result.get("provenance")),
            check_extent(result.get("extent_km2", 0.0)),
        ]
        # A drawn outline and an EMS footprint have no radar layer to
        # decompose, and the disclosure they need instead is PROVENANCE.
        if source not in ("manual", "ems"):
            findings.append(check_infill(result.get("radar_km2", 0.0),
                                         result.get("extent_km2", 0.0)))
        findings.append(check_against_official(
            result.get("detected_km2", result.get("extent_km2", 0.0)), ems))
        findings += [
            check_coverage(result.get("coverage", 0.0)),
            check_assessable(result.get("assessable", 0.0), source),
        ]

        # Terrain and mechanism are questions about a depth-damage curve:
        # whether the ground is a floodplain, and whether the water damages by
        # standing on things. Neither applies when the damage was observed
        # building by building. Refusing a graded figure because a curve we did
        # not use would have been misapplied is refusing the wrong thing.
        if result.get("method") == "graded":
            findings.append(check_graded(result))
        else:
            findings += [check_terrain(steep_share), check_mechanism(mechanism)]

        findings += [
            check_exposure(result.get("exposed_usd", 0.0)),
            check_damage_ratio(result.get("damage_ratio", 0.0)),
        ]
        if region_total:
            findings.append(check_loss_scale(result.get("loss_usd", 0.0),
                                             region_total))

    blocking = {f.code for f in findings if f.level == "block"}

    if blocking & {"IMAGERY", "EXTENT"}:
        tier = 0                      # nothing observed; publish a pending note
    elif blocking & {"EXPOSURE"}:
        tier = 3                      # extent only
    elif blocking:
        tier = 2                      # exposed value and population, no loss
    else:
        tier = 1

    return Verdict(tier=tier, findings=findings,
                   reported=reported_facts(ems, timings))


TIER_TEMPLATES = {
    1: "04-loss-estimate.md",
    2: "03-observed-extent.md",
    3: "03-observed-extent.md",
    0: "02-alert.md",
}


def choose_template(verdict: Verdict, result: dict) -> str:
    """Which post the event is at, on the publication calendar.

    The calendar in the editorial rules is keyed to the event clock, but the
    clock is only a guide: what decides the format is what actually exists.
    Order matters, and it runs from the strongest available content down.
    """
    reported = verdict.reported or {}

    # Somebody has counted the damage. That post exists whatever our tier is,
    # and it is the one with content nobody else is putting in front of a
    # general audience.
    if reported.get("buildings_mapped"):
        return "08-official-figures.md"

    # An activation is open and nothing has been measured yet by anyone.
    if verdict.tier == 0 and reported.get("activation_hours") is not None:
        return "07-activation.md"

    return TIER_TEMPLATES[verdict.tier]


def tier_statement(verdict: Verdict) -> str:
    """One sentence saying what this pipeline does and does not claim.

    Written into the draft so the limitation travels with the figures instead
    of living in a log nobody reads. It is explicit that the tier applies to
    modelled figures, because a post carrying both kinds must not let a reader
    think a reported count was withheld.
    """
    scope = ("This applies to figures this pipeline computed. Figures "
             "attributed to another source are reported as published.")

    if verdict.tier == 1:
        head = "Output tier 1 of 3: modelled loss in currency."
    elif verdict.tier == 2:
        reasons = "; ".join(f.message for f in verdict.blockers)
        head = (f"Output tier 2 of 3: exposed value and affected population, "
                f"no modelled loss figure. {reasons}")
    elif verdict.tier == 3:
        head = "Output tier 3 of 3: observed extent only."
    else:
        head = ("This pipeline has no observation of its own yet, so it "
                "models nothing for this event.")

    return f"{head} {scope}" if verdict.reported else head
