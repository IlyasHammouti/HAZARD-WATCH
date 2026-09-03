"""Event definitions, so a published figure can be reproduced from the repo.

Until now every run was an ad-hoc call and only the cached result survived,
which means the numbers in `docs/DECISIONS.md` could be read but not rebuilt.
One dictionary per event fixes that: the windows, the depth assumption and the
sector are all part of the result, and a figure whose inputs are not recorded
is not a reproducible figure.

    from report import make_post
    from events import EMSR926
    make_post(EMSR926)

EMSR664 (Emilia-Romagna, May 2023) is deliberately absent. Its cached result
predates this file and the exact windows used for it were not written down;
adding a definition that produced *nearly* the published numbers would be
worse than admitting the gap. Rebuild it from scratch when there is a reason
to, and add it here at that point.
"""

from report import FloodEvent

# Flood in Latvia and Lithuania, Copernicus EMS activation of 21 August 2026.
# Four mapped areas: Kuldiga, Liepaja (Kurzeme), Dobele, Ruba (Zemgale).
#
# The activation covers two countries and the exposure step anchors to one
# national total. Latvia holds all four mapped areas and the great majority of
# the boxed surface, so Latvia is the anchor; the southern edge of the box
# reaches into Lithuania and that strip is anchored to the wrong national
# total. The mapped-area mask keeps the effect small, and it is stated rather
# than hidden.
EMSR926 = FloodEvent(
    ems_code="EMSR926",
    country="Latvia",
    region="Kurzeme and Zemgale",
    event_date="2026-08-21",
    # The event began at 21:00 UTC on the 21st, so the hazard window opens on
    # the same day and runs to the present: the maximum extent over the period
    # is what a damage estimate needs, not the situation on any one day.
    hazard_start="2026-08-21",
    hazard_end="2026-08-29",
    optical_start="2026-08-22",
    optical_end="2026-08-29",
    seas={"Baltic Sea": (21.1, 56.5)},
    depth_m=1.0,
    sector="residential",
    mechanism="riverine",
)

# GLOF-triggered flash flood, Rasuwa district, 25 August 2026 22:00 UTC.
#
# Two independent guards refuse a currency figure here and both are right:
# 59 % of the ground exceeds 20 degrees, and a glacial lake outburst damages
# by force and debris rather than by standing water depth. The mechanism is
# named `glof` precisely so the guard fires instead of a JRC floodplain curve
# returning a confident number that would mean nothing.
EMSR927 = FloodEvent(
    ems_code="EMSR927",
    country="Nepal",
    region="Rasuwa",
    event_date="2026-08-25",
    # Copernicus Global Flood Monitoring published its first scenes over the
    # valley on 2026-08-28 12:21 UTC, from the first Sentinel-1 acquisition
    # after the event, with a second pass on the 29th. The window runs past
    # both: the maximum extent over the period is what a damage estimate
    # needs, not the situation on one day.
    hazard_start="2026-08-25",
    hazard_end="2026-08-31",
    optical_start="2026-08-26",
    optical_end="2026-08-31",
    seas={},
    depth_m=1.0,
    sector="residential",
    # The JRC curves are calibrated per continent and the default is Europe.
    # They are not used on this event — the damage was graded building by
    # building, so the loss is priced from what was observed rather than from
    # an assumed depth — but a wrong continent left in place is a number
    # waiting to be published by accident.
    curve_region="Asia",
    mechanism="glof",
    # Our own detection is off. Copernicus EMS graded all three delivered
    # areas by hand from 30 to 50 cm imagery; running the radar and optical
    # chain would spend twenty-five minutes to produce a worse outline of the
    # same ground. The comparison was measured once, on 2026-08-29: 0.87 km2
    # against the 8.33 km2 EMS mapped, and zero in both gorge sections. That
    # is a finding, and findings do not need recomputing.
    detect=False,
)
