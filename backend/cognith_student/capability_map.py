"""The capability map — Claude.md §21 Phase 4 and §9.

One renderer, used everywhere a profile is displayed. Before this existed the map was
drawn in two places (onboarding and the profile viewer) and the two were already
diverging; §9's distinction is too important to maintain twice.

THE DESIGN PROBLEM
------------------
§21 Phase 4 says to "clearly distinguish self-reported vs demonstrated". Two number
columns technically does that, and it is what Phases 2 and 3 shipped — but a reader has to
notice a dash in the second column to realise a number is unsubstantiated. That is present,
not unmissable.

So the bar is drawn in two materials on one axis:

    block   demonstrated          — evidence supports this
    shade   claimed, unverified   — the student's word alone
    dot     nothing

A profile fresh from onboarding renders almost entirely as shade. The reader sees that
their map is mostly unproven before reading a single number, which is precisely what §9
asks the UI to communicate.

This module renders. It decides nothing — no thresholds of its own, no selection policy.
"""

from __future__ import annotations

import textwrap

from cognith_capability.graph import CapabilityGraph

from .models import DEMONSTRATED_AT, MasteryStatus, StudentCapability
from .profile import CapabilityProfile

SOLID = "█"   # demonstrated
HOLLOW = "░"  # claimed but unverified
EMPTY = "·"   # no data

RULE = "─" * 78
BAR_WIDTH = 19

#: A claim this far from the evidence is worth naming in the label rather than leaving to
#: the reader. Presentation only — Phase 5 owns what counts as a gap worth acting on.
NOTABLE_GAP = 0.15


def pct(value: float | None) -> str:
    return "  —" if value is None else f"{round(value * 100):3d}%"


def bar(confidence: float | None, mastery: float | None, width: int = BAR_WIDTH) -> str:
    """Demonstrated mastery in solid, the unverified remainder of the claim in shade.

    When mastery exceeds confidence the solid simply runs past where the claim ended —
    the student undersold themselves, and there is no unverified remainder to draw.
    """
    solid = min(round((mastery or 0.0) * width), width)
    claim = min(round((confidence or 0.0) * width), width)
    hollow = max(0, claim - solid)
    return SOLID * solid + HOLLOW * hollow + EMPTY * (width - solid - hollow)


def label_for(row: StudentCapability) -> str:
    """A word for what this row actually is. Longer than the status enum on purpose.

    `MasteryStatus` is the data model's vocabulary; this is the reader's. "claimed" tells
    a reader more than "claimed" plus a dash they have to interpret.
    """
    if row.status is MasteryStatus.UNKNOWN:
        return "not rated"
    if row.mastery is None:
        return "claimed"
    gap = row.calibration_gap
    if gap is not None and gap >= NOTABLE_GAP:
        return "over-claimed"
    if gap is not None and gap <= -NOTABLE_GAP:
        return "under-claimed"
    return "verified" if row.is_demonstrated else "developing"


def render_legend() -> str:
    return (
        f"  {SOLID * 3} demonstrated — evidence supports it\n"
        f"  {HOLLOW * 3} claimed      — your word alone, not yet verified\n"
        f"  {EMPTY * 3} not rated    — nothing said and nothing shown"
    )


def render(
    profile: CapabilityProfile,
    *,
    focus: list[str] | None = None,
    title: str | None = None,
    show_legend: bool = True,
) -> str:
    """The full capability map, grouped by the §7 tree's areas."""
    graph: CapabilityGraph = profile.graph
    focus_set = set(focus or [])
    out: list[str] = []

    student = profile.student
    out.append(RULE)
    out.append(title or f"CAPABILITY MAP — {student.name}")
    if student.goal:
        out.append(f"Goal: {student.goal}")
    out.append(RULE)
    out.append("")

    for area_id, area_name in graph.areas.items():
        out.append(area_name)
        for cap in graph.by_area(area_id):
            row = profile.row_for(cap.id)
            star = "*" if cap.id in focus_set else " "
            out.append(
                f" {star} {cap.name:24} {bar(row.confidence, row.mastery)}  "
                f"{label_for(row):13} {pct(row.mastery)} /{pct(row.confidence)}"
            )
        out.append("")

    out.append(RULE)
    if show_legend:
        out.append(render_legend())
        out.append("")
    out.append(render_verified_share(profile))
    if focus_set:
        out.append(f"\n  '*' marks capabilities that matter for this goal.")
    return "\n".join(out)


def render_verified_share(profile: CapabilityProfile) -> str:
    """The headline §9 wants: how much of this map is actually substantiated.

    One number, because the whole point of the phase is that a reader should not have to
    tally 16 rows to learn that almost none of them have been checked.
    """
    rows = profile.all_rows()
    total = len(rows)
    verified = sum(1 for r in rows if r.is_demonstrated)
    assessed = sum(1 for r in rows if r.mastery is not None)
    claimed_only = sum(1 for r in rows if r.is_unverified)

    lines = [
        f"  {verified} of {total} capabilities verified"
        f"   ({assessed} assessed, {claimed_only} claimed but unchecked)"
    ]
    if claimed_only:
        share = claimed_only / total
        lines.append(
            f"  {share:.0%} of this map rests on what you told us, not on what you "
            f"have shown."
        )
    if assessed == 0:
        lines.append("")
        lines.append(textwrap.fill(
            "This is an initial estimate based on what you have told us. "
            "Nothing here has been verified yet — let's verify it.", 78,
            initial_indent="  ", subsequent_indent="  "))
    return "\n".join(lines)


def render_verification_queue(profile: CapabilityProfile, limit: int = 5) -> str:
    """§9's "let's verify it" — what is least substantiated, and why it stands out.

    This ORDERS SIGNALS. It does not select a diagnostic. Claude.md §10 is explicit that
    choosing what to test involves the student's goal, the capability relationships,
    uncertainty and prerequisites — that is Phase 5's job, and doing it here would bury
    the policy in a display module.
    """
    out: list[str] = [RULE, "WHAT TO VERIFY FIRST", RULE, ""]
    out.append(textwrap.fill(
        "Ordered by how much is being taken on trust. This is a signal, not a "
        "diagnostic: Phase 5 selects what to actually test, using the capability graph "
        "and prerequisites as well as these numbers.", 78, initial_indent="  ",
        subsequent_indent="  "))
    out.append("")

    over = profile.calibration_gaps(min_gap=NOTABLE_GAP)
    if over:
        out.append("  Claim sits above the evidence:")
        for row in over[:limit]:
            cap = profile.capability(row.capability_id)
            out.append(f"    {row.calibration_gap:+.2f}  {cap.name:24} "
                       f"claimed {pct(row.confidence)}, shown {pct(row.mastery)}")
        out.append("")

    unverified = profile.unverified()
    if unverified:
        out.append("  Claimed but never checked (boldest claim first):")
        for row in unverified[:limit]:
            cap = profile.capability(row.capability_id)
            blockers = profile.blocked().get(cap.id, [])
            note = ""
            if blockers:
                note = f"   — rests on {', '.join(b.name for b in blockers)}"
            out.append(f"    {pct(row.confidence)}  {cap.name:24} "
                       f"[{cap.level.value}]{note}")
        out.append("")

    if not over and not unverified:
        out.append("  Nothing outstanding — every rated capability has evidence behind it.")
        out.append("")

    out.append(f"  'rests on' marks a prerequisite not yet demonstrated at "
               f"{DEMONSTRATED_AT:.0%}.")
    return "\n".join(out)
