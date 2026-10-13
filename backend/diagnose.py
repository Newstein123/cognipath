#!/usr/bin/env python3
"""Phase 5 — build a targeted diagnostic. Claude.md §10.

No LLM, no network. Selection is deterministic and every choice shows its reasoning.

  python diagnose.py                      build a diagnostic for the saved profile
  python diagnose.py --explain            why each capability was chosen
  python diagnose.py --ranking            the full scored ranking
  python diagnose.py --coverage           which capabilities have scenarios authored
  python diagnose.py --save               persist the session as pending
  python diagnose.py --student student-002
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  — must precede project imports

import argparse
import sys
import textwrap

from cognith_capability.graph import CapabilityGraph
from cognith_student.capability_map import pct
from cognith_student.diagnostic import Diagnostic, DiagnosticEngine, DiagnosticError
from cognith_capability.milestone import MilestoneMap
from cognith_student.onboarding import OnboardingEngine
from cognith_student.profile import CapabilityProfile
from cognith_student.progress import active, path_for

RULE = "─" * 78


def show_diagnostic(d: Diagnostic, graph: CapabilityGraph, profile: CapabilityProfile) -> None:
    print(f"\n{RULE}\nDIAGNOSTIC — {profile.student.name}\n{RULE}\n")
    print(textwrap.fill(
        "You are not being given a general exam. These questions were chosen because "
        "they are the parts of your profile we are taking most on trust — and because "
        "answering them tells us the most about everything else.", 78))
    print(f"\n  {len(d.items)} scenarios, about {d.minutes} minutes.")
    print("  Answers are not scored yet — Phase 6 does that.\n")

    print(f"{RULE}\nWHY THESE\n{RULE}\n")
    for cand in d.selected:
        cap = graph.get(cand.capability_id)
        print(f"  {cap.name}   [{cap.level.value}]  score {cand.score:.2f}")
        for note in cand.notes:
            print(f"      · {note}")
        top = ", ".join(f"{k} {v:.2f}" for k, v in cand.top_factors(3))
        print(f"      strongest factors: {top}")
    if d.secondary_coverage:
        names = ", ".join(graph.get(c).name for c in d.secondary_coverage)
        print(f"\n  Also exercised by these scenarios: {names}")
    if d.skipped_no_scenario:
        names = ", ".join(graph.get(c.capability_id).name for c in d.skipped_no_scenario)
        print(f"\n  Ranked high but no scenario authored yet: {names}")
        print("  (a content gap, not a scoring decision — see --coverage)")

    for n, item in enumerate(d.items, 1):
        cap = graph.get(item.capability_id)
        others = ", ".join(graph.get(c).name for c in item.also_exercises)
        print(f"\n{RULE}")
        print(f"SCENARIO {n} of {len(d.items)}   —   {cap.name}   ({item.minutes} min)")
        print(f"{RULE}")
        print(f"\n  probes: {', '.join(item.probes)}")
        if others:
            print(f"  also exercises: {others}")
        print()
        print(textwrap.indent(item.prompt, "  "))
    print(f"\n{RULE}\n")


def show_ranking(d: Diagnostic, graph: CapabilityGraph, profile: CapabilityProfile) -> None:
    chosen = {c.capability_id for c in d.selected}
    print(f"\n{RULE}\nSELECTION RANKING — every capability scored\n{RULE}\n")
    print(f"{'':3}{'capability':24} {'score':>6}  {'unc':>5} {'stake':>5} {'goal':>5} "
          f"{'lev':>5} {'cal':>5} {'supp':>5}   state")
    print(f"{'':3}{'-' * 24} {'-' * 6}  {'-' * 5} {'-' * 5} {'-' * 5} {'-' * 5} "
          f"{'-' * 5} {'-' * 5}   {'-' * 12}")
    for c in d.considered:
        cap = graph.get(c.capability_id)
        row = profile.row_for(c.capability_id)
        f = c.factors
        mark = "->" if c.capability_id in chosen else ("· " if not c.ready else "  ")
        state = row.status.value
        print(f" {mark}{cap.name:24} {c.score:6.3f}  "
              f"{f['uncertainty']:5.2f} {f['stake']:5.2f} {f['goal_relevance']:5.2f} "
              f"{f['leverage']:5.2f} {f['calibration']:5.2f} {f['claim_support']:5.2f}"
              f"   {state}")
    print(f"\n  '->' selected   '·' prerequisites unproven, score reduced")
    print("  unc=uncertainty  lev=leverage  cal=calibration  supp=claim_support")
    print(textwrap.fill(
        "claim_support is §10's rule: a bold unverified claim makes the capabilities it "
        "RESTS ON worth testing, rather than the claim itself.", 78,
        initial_indent="\n  ", subsequent_indent="  "))
    print()


def show_explain(d: Diagnostic, graph: CapabilityGraph, profile: CapabilityProfile) -> None:
    print(f"\n{RULE}\nWHY EACH CAPABILITY WAS SELECTED\n{RULE}")
    for cand in d.selected:
        cap = graph.get(cand.capability_id)
        row = profile.row_for(cap.id)
        print(f"\n{cap.name}   [{cap.id}]   score {cand.score:.3f}")
        print(f"  {cap.statement}")
        print(f"\n  current state: {row.status.value}, "
              f"claimed {pct(row.confidence)}, shown {pct(row.mastery)}")
        print("\n  score breakdown:")
        for k, v in sorted(cand.factors.items(), key=lambda kv: -kv[1]):
            if v <= 0:
                continue
            print(f"    {k:16} {v:.3f}")
        dependents = graph.unlocked_by(cap.id)
        if dependents:
            print(f"\n  verifying this also informs: "
                  f"{', '.join(c.name for c in dependents)}")
        for note in cand.notes:
            print(f"  · {note}")
    print()


def show_coverage(engine: DiagnosticEngine, graph: CapabilityGraph) -> None:
    print(f"\n{RULE}\nSCENARIO COVERAGE\n{RULE}\n")
    for area_id, area_name in graph.areas.items():
        print(area_name)
        for cap in graph.by_area(area_id):
            items = engine.items_for(cap.id)
            also = [i for i in engine.items if cap.id in i.also_exercises]
            if items:
                label = ", ".join(i.id for i in items)
            elif also:
                label = f"— secondary only, in {', '.join(i.id for i in also)}"
            else:
                label = "— none"
            print(f"  {cap.name:24} {label}")
        print()
    missing = engine.uncovered()
    print(RULE)
    print(f"  {len(graph) - len(missing)} of {len(graph)} capabilities have a scenario "
          f"targeting them.")
    if missing:
        print(f"\n  No scenario authored: {', '.join(c.name for c in missing)}")
        print(textwrap.fill(
            "A content gap, not an engine gap. A capability with no scenario is reported "
            "when it ranks highly rather than being silently dropped.", 78,
            initial_indent="  ", subsequent_indent="  "))
    print()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build a targeted diagnostic from a student's capability profile.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--student", default="student-001", help="saved profile id")
    ap.add_argument("--explain", action="store_true")
    ap.add_argument("--ranking", action="store_true")
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("-n", type=int, help="how many capabilities to verify")
    args = ap.parse_args()

    graph = CapabilityGraph.load()
    try:
        engine = DiagnosticEngine.load(graph)
    except DiagnosticError as exc:
        print(exc, file=sys.stderr)
        return 1

    if args.coverage:
        show_coverage(engine, graph)
        return 0

    try:
        profile = CapabilityProfile.load(args.student, graph)
    except FileNotFoundError as exc:
        print(f"{exc}\nRun `python onboard.py --save --student-id {args.student}` first.",
              file=sys.stderr)
        return 1

    # Relevance comes from the learner's ACTIVE milestone — the first one they have not
    # completed. That is what makes a question worth asking: it targets the requirements
    # their progress estimate depends on and cannot yet justify.
    relevance = None
    milestone = None
    if profile.student.goal:
        onboarding = OnboardingEngine.load(graph)
        goal_key = next((k for k, spec in onboarding.goals.items()
                         if spec["name"] == profile.student.goal), None)
        if goal_key:
            try:
                path = path_for(profile, MilestoneMap.load(graph), goal_key)
                current = active(path)
                if current:
                    milestone, relevance = current, current.relevance()
            except (FileNotFoundError, KeyError):
                relevance = None

    diagnostic = engine.build(profile, relevance=relevance, limit=args.n)
    if milestone is not None and not (args.ranking or args.explain):
        print(f"\n  Aiming at: {milestone.summary()}")
    if not diagnostic.items:
        print("\nNothing worth verifying — every capability is either demonstrated or "
              "has no scenario authored.\n")
        return 0

    if args.ranking:
        show_ranking(diagnostic, graph, profile)
        return 0
    if args.explain:
        show_explain(diagnostic, graph, profile)
        return 0
    if args.save:
        path = diagnostic.save()
        print(f"\nwrote {path.name} — {len(diagnostic.items)} scenarios, status pending, "
              f"no responses (Phase 6 collects those)\n")
        return 0

    show_diagnostic(diagnostic, graph, profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
