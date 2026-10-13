#!/usr/bin/env python3
"""Cognith — the front door. Claude.md §15, §21 Phase 10, §27.

One command that answers "where am I, and what should I do next?"

  python cognith.py                      where you are and what to do next
  python cognith.py --student me
  python cognith.py --map                the capability map
  python cognith.py --loop               the whole loop, and which parts you have done
  python cognith.py --backlog            what the system cannot yet teach anyone

Offline. Every recommendation is a command you can run.
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  — must precede project imports

import argparse
import sys
import textwrap

from cognith_capability.graph import CapabilityGraph
from cognith_learning.experience import ExperienceError, ExperienceType
from cognith_learning.loop import AdaptiveLoop, LoopState, StepKind
from cognith_student import capability_map as cmap
from cognith_student.profile import CapabilityProfile

RULE = "═" * 78
THIN = "─" * 78

#: §27's definition of done, as a checklist the learner can see themselves against.
LOOP_STAGES = [
    ("Goal", "a goal was recorded at onboarding"),
    ("Initial capability map", "self-reported estimates exist"),
    ("Diagnostic", "at least one capability has been tested"),
    ("Evidence", "at least one response has been judged against a rubric"),
    ("Capability profile", "mastery has been computed from evidence"),
    ("Gap detection", "a demonstrated gap has been identified"),
    ("Knowledge", "the corpus can teach at least one of those gaps"),
    ("Practice", "an exercise has been completed"),
    ("Apply", "several capabilities have been integrated without scaffolding"),
    ("Mission", "the flagship mission has been attempted"),
    ("Updated capability", "a capability changed because of evidence"),
    ("Next experience", "the system recommends what to do next"),
]

ICON = {
    StepKind.ONBOARD: "start",
    StepKind.DIAGNOSE: "test",
    StepKind.LEARN: "read",
    StepKind.PRACTISE: "do",
    StepKind.APPLY: "apply",
    StepKind.MISSION: "mission",
    StepKind.NOTHING: "—",
}


def show_next(state: LoopState, loop: AdaptiveLoop) -> None:
    student = loop.profile.student
    print(f"\n{RULE}")
    print(f"  {student.name}" + (f"  —  {student.goal}" if student.goal else ""))
    print(RULE)
    print(f"\n  {loop.position()}")

    s = state.summary
    print(f"\n  demonstrated {s['demonstrated']:>2}   "
          f"assessed {s['assessed']:>2}   "
          f"claimed only {s['claimed_unverified']:>2}   "
          f"open gaps {s['gaps']:>2}")

    print(f"\n{THIN}\n  WHAT TO DO NEXT\n{THIN}")
    for n, step in enumerate(state.steps, 1):
        mins = f"  ~{step.minutes} min" if step.minutes else ""
        print(f"\n  {n}. [{ICON[step.kind]}] {step.title}{mins}")
        print(textwrap.fill(step.why, 72, initial_indent="        ",
                            subsequent_indent="        "))
        print(f"\n        $ {step.command}")

    if state.backlog:
        print(f"\n{THIN}")
        print(f"  {len(state.backlog)} thing(s) held back — `--backlog` for why.")
    print()


def show_backlog(state: LoopState) -> None:
    print(f"\n{RULE}\n  CONTENT BACKLOG\n{RULE}\n")
    print(textwrap.fill(
        "These would be worth working on and the system cannot deliver them. That is a "
        "fact about the product, not about the learner — so it is reported here rather "
        "than recommended and then found empty.", 76, initial_indent="  ",
        subsequent_indent="  "))
    print()
    if not state.backlog:
        print("  Nothing held back.\n")
        return
    for cap, reason in state.backlog:
        print(f"  {cap.name:26} {reason}")
    print(f"\n  Writing a document in knowledge/ or a scenario in data/diagnostics.yaml")
    print(f"  is what clears these.\n")


def show_loop(loop: AdaptiveLoop, state: LoopState) -> None:
    """§27's loop, with what this learner has actually done."""
    p = loop.profile
    rows = p.all_rows()
    library = loop.library

    from cognith_student.storage import get_storage
    entries = get_storage().load_evidence(p.student.id)
    done_ids = {e["evidence"]["experienceId"] for e in entries}

    def did(t: ExperienceType) -> bool:
        return any(e.id in done_ids for e in library.of_type(t))

    checks = [
        bool(p.student.goal),
        any(r.confidence is not None for r in rows),
        did(ExperienceType.DIAGNOSTIC),
        bool(entries),
        any(r.mastery is not None for r in rows),
        bool(loop.resolver.gaps()),
        any(loop.graph.get(g.capability_id).knowledge_docs for g in loop.resolver.gaps()),
        did(ExperienceType.EXERCISE),
        did(ExperienceType.APPLY),
        did(ExperienceType.MISSION),
        any(r.evidence_count > 0 for r in rows),
        bool(state.steps),
    ]

    print(f"\n{RULE}\n  THE LEARNING LOOP  (Claude.md §27)\n{RULE}\n")
    for (name, meaning), ok in zip(LOOP_STAGES, checks):
        print(f"  {'[x]' if ok else '[ ]'} {name:24} {meaning}")
    reached = sum(checks)
    print(f"\n{THIN}")
    print(f"  {reached} of {len(checks)} stages reached.")
    if reached == len(checks):
        print(textwrap.fill(
            "The complete loop, for one learner. §27: \"That complete loop is more "
            "important than the number of features.\"", 76,
            initial_indent="\n  ", subsequent_indent="  "))
    print()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Where you are, and what to do next.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--student", default="student-001")
    ap.add_argument("--map", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--backlog", action="store_true")
    ap.add_argument("-n", type=int, default=3, help="how many next steps")
    args = ap.parse_args()

    graph = CapabilityGraph.load()
    try:
        profile = CapabilityProfile.load(args.student, graph)
    except FileNotFoundError:
        print(f"\n{RULE}\n  Cognith\n{RULE}\n")
        print(f"  No profile for {args.student!r} yet.\n")
        print(f"  $ python onboard.py --interactive --save --student-id {args.student}\n")
        print("  That records what you are working toward and produces an initial")
        print("  capability estimate — a starting point to verify, not an assessment.\n")
        return 0

    try:
        loop = AdaptiveLoop(graph, profile)
    except ExperienceError as exc:
        print(exc, file=sys.stderr)
        return 1
    state = loop.recommend(limit=args.n)

    if args.map:
        print()
        print(cmap.render(profile))
        print()
        return 0
    if args.backlog:
        show_backlog(state)
        return 0
    if args.loop:
        show_loop(loop, state)
        return 0

    show_next(state, loop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
