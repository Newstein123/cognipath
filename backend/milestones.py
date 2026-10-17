#!/usr/bin/env python3
"""Phase 11 — where you want to reach, and how far you have come.

Offline. No LLM, no network.

  python milestones.py                     your path, milestone by milestone
  python milestones.py --student me
  python milestones.py --all               every goal's path (the curriculum)
  python milestones.py --verify            what to check next, and why it matters most
  python milestones.py --coverage          which requirements the system can actually test
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  — must precede project imports

import argparse
import sys
import textwrap

from cognith_capability.graph import CapabilityGraph
from cognith_capability.milestone import MilestoneError, MilestoneMap
from cognith_learning.experience import ExperienceLibrary, ExperienceType
from cognith_student.capability_map import pct
from cognith_student.onboarding import OnboardingEngine
from cognith_student.profile import CapabilityProfile
from cognith_student.progress import (
    MilestoneProgress,
    RequirementState,
    active,
    path_for,
)

RULE = "═" * 78
THIN = "─" * 78

MARK = {
    RequirementState.DEMONSTRATED: "[x]",
    RequirementState.SHORT: "[~]",
    RequirementState.CLAIMED: "[?]",
    RequirementState.UNKNOWN: "[ ]",
}


def bar(progress: MilestoneProgress, width: int = 22) -> str:
    """Demonstrated in solid, claimed in shade — the same encoding as the capability map.

    A claim must never be drawn as progress. §6.2's whole point is that what you say and
    what you have shown are different kinds of thing, and a milestone bar that adds them
    together would undo Phase 4's work.
    """
    solid = round(progress.demonstrated_fraction * width)
    hollow = round(progress.claimed_fraction * width)
    hollow = min(hollow, width - solid)
    return "█" * solid + "░" * hollow + "·" * (width - solid - hollow)


def goal_key(profile: CapabilityProfile, graph: CapabilityGraph) -> str | None:
    if not profile.student.goal:
        return None
    goals = OnboardingEngine.load(graph).goals
    return next((k for k, spec in goals.items()
                 if spec["name"] == profile.student.goal), None)


def show_path(path: list[MilestoneProgress], graph: CapabilityGraph,
              profile: CapabilityProfile) -> None:
    print(f"\n{RULE}")
    print(f"  {profile.student.name}  —  {profile.student.goal}")
    print(RULE)
    print(textwrap.fill(
        "Solid is demonstrated. Shade is claimed but unverified — it is shown beside the "
        "progress, never added to it. A milestone is reached on evidence, not on "
        "self-report.", 76, initial_indent="\n  ", subsequent_indent="  "))

    current = active(path)
    for mp in path:
        m = mp.milestone
        state = ("COMPLETE" if mp.complete
                 else f"LOCKED — finish {mp.locked_by} first" if not mp.unlocked
                 else "IN PROGRESS" if mp is current else "")
        print(f"\n{THIN}")
        print(f"  Level {m.level} — {m.name}   {state}")
        print(f"  {bar(mp)}  {mp.demonstrated} of {mp.total} demonstrated"
              + (f", {mp.claimed} on trust" if mp.claimed else ""))
        print(f"{THIN}\n")
        print(textwrap.fill(m.summary, 74, initial_indent="  ", subsequent_indent="  "))
        print()
        for r in mp.requirements:
            cap = graph.get(r.capability_id)
            shown = pct(r.row.mastery)
            claim = pct(r.row.confidence)
            note = {
                RequirementState.DEMONSTRATED: "",
                RequirementState.SHORT: f"short by {r.shortfall:.0%}",
                RequirementState.CLAIMED: "never checked",
                RequirementState.UNKNOWN: "nothing known",
            }[r.state]
            print(f"  {MARK[r.state]} {cap.name:24} shown {shown}  "
                  f"claimed {claim}  target {r.requirement.target:.0%}   {note}")

    print(f"\n{THIN}")
    if current is None:
        print("  Every milestone complete. This goal is reached.\n")
    else:
        print(f"  You are on Level {current.milestone.level} — {current.milestone.name}.")
        print(f"  `python milestones.py --verify` for what to check next.\n")


def show_verify(path: list[MilestoneProgress], graph: CapabilityGraph,
                library: ExperienceLibrary, student: str) -> None:
    current = active(path)
    print(f"\n{RULE}\n  WHAT TO CHECK NEXT\n{RULE}\n")
    if current is None:
        print("  Nothing — every milestone is complete.\n")
        return
    print(textwrap.fill(
        f"Your progress on {current.milestone.name} rests on these. The ones you have "
        "claimed but never had checked come first: that is where the estimate above is "
        "most likely to be wrong, so testing them tells us more than anything else would.",
        76, initial_indent="  ", subsequent_indent="  "))
    print()
    todo = current.next_to_verify()
    if not todo:
        print("  Every requirement has evidence behind it. What remains is work, not "
              "uncertainty.\n")
        return
    for r in todo:
        cap = graph.get(r.capability_id)
        testable = [e for e in library.for_capability(cap.id)
                    if e.type is ExperienceType.DIAGNOSTIC]
        reason = ("your starting estimate is " + pct(r.row.confidence) + " and nothing checked it"
                  if r.state is RequirementState.CLAIMED
                  else "nothing is known about it at all")
        print(f"  {cap.name}   — {reason}")
        if testable:
            print(f"      testable now — about {testable[0].minutes} min")
            print(f"      $ python diagnose.py --student {student}")
        else:
            print(f"      NOT TESTABLE — no diagnostic scenario written for it, so this "
                  f"milestone\n      cannot be completed until one is")
        print()


def show_coverage(mm: MilestoneMap, graph: CapabilityGraph,
                  library: ExperienceLibrary) -> None:
    print(f"\n{RULE}\n  CAN EACH REQUIREMENT BE TESTED?\n{RULE}\n")
    print(textwrap.fill(
        "A milestone requirement with no diagnostic can never be demonstrated, so the "
        "milestone can never complete. That is a content gap that blocks a learner "
        "permanently, which makes it more serious than an ordinary one.", 76,
        initial_indent="  ", subsequent_indent="  "))
    blocked: list[tuple[str, str]] = []
    for m in sorted(mm.milestones.values(), key=lambda x: (x.goal, x.level)):
        print(f"\n  {m.goal} / Level {m.level} — {m.name}")
        for r in m.requires:
            cap = graph.get(r.capability_id)
            found = library.for_capability(cap.id)
            dg = [e for e in found if e.type is ExperienceType.DIAGNOSTIC]
            ex = [e for e in found if e.type is ExperienceType.EXERCISE]
            if dg or ex:
                print(f"      {cap.name:24} {len(dg)} diagnostic, {len(ex)} exercise")
            else:
                print(f"      {cap.name:24} NOTHING — this milestone cannot be completed")
                blocked.append((m.name, cap.name))
    print(f"\n{THIN}")
    if blocked:
        print(f"  {len(blocked)} requirement(s) block a milestone permanently:\n")
        for milestone, cap in blocked:
            print(f"      {milestone:28} needs {cap}")
        print(textwrap.fill(
            "Writing a scenario in data/diagnostics.yaml, or an exercise rubric in "
            "data/exercises.yaml, is what unblocks these.", 76,
            initial_indent="\n  ", subsequent_indent="  "))
    else:
        print("  Every requirement of every milestone can be tested.")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Milestones — where you want to reach, and how far you have come.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--student", default="student-001")
    ap.add_argument("--all", action="store_true", help="every goal's path")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--coverage", action="store_true")
    args = ap.parse_args()

    graph = CapabilityGraph.load()
    try:
        mm = MilestoneMap.load(graph)
    except (MilestoneError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1
    library = ExperienceLibrary.load(graph)

    if args.coverage:
        show_coverage(mm, graph, library)
        return 0

    if args.all:
        print(f"\n{RULE}\n  THE CURRICULUM  ({len(mm)} milestones)\n{RULE}")
        for goal in mm.goals():
            print(f"\n  {goal}")
            for m in mm.for_goal(goal):
                after = f"  (after {m.after})" if m.after else ""
                print(f"    Level {m.level}  {m.name:28} "
                      f"{len(m.requires)} requirements{after}")
                for r in m.requires:
                    print(f"        {graph.get(r.capability_id).name:24} "
                          f"target {r.target:.0%}")
        print()
        return 0

    try:
        profile = CapabilityProfile.load(args.student, graph)
    except FileNotFoundError as exc:
        print(f"{exc}\nRun `python onboard.py --save --student-id {args.student}` first.",
              file=sys.stderr)
        return 1

    key = goal_key(profile, graph)
    if key is None:
        print(f"\n  {profile.student.name} has no goal recorded, so there is no "
              f"milestone to measure against.\n", file=sys.stderr)
        return 1
    path = path_for(profile, mm, key)
    if not path:
        print(f"\n  No milestones defined for {profile.student.goal!r}.\n", file=sys.stderr)
        return 1

    if args.verify:
        show_verify(path, graph, library, args.student)
        return 0
    show_path(path, graph, profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
