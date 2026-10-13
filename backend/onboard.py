#!/usr/bin/env python3
"""Phase 3 — student onboarding. Claude.md §8's intake -> §9's initial capability map.

No LLM, no network. Every estimate can be explained back to the answer that produced it.

  python onboard.py                       run §8's example intake
  python onboard.py --explain databases   full provenance for one capability
  python onboard.py --verify              check the output against §9's example map
  python onboard.py --interactive          answer the five questions yourself
  python onboard.py --vocabulary          what technologies and phrases are recognised
  python onboard.py --save                 write the profile to data/students/
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  — must precede project imports

import argparse
import sys
import textwrap

from cognith_capability.graph import CapabilityGraph
from cognith_student import capability_map as cmap
from cognith_student.capability_map import pct
from cognith_student.onboarding import (
    OnboardingAnswers,
    OnboardingEngine,
    OnboardingError,
    OnboardingResult,
)

RULE = "─" * 78

#: Claude.md §8's worked example, verbatim.
EXAMPLE = OnboardingAnswers(
    student_name="Demo Student",
    goal="backend-engineer",
    technologies=("PHP", "Laravel", "MySQL", "Redis", "Docker"),
    knows="I know backend web development.",
    built="I have built APIs and booking systems.",
    self_rated_level="intermediate",
)

#: Claude.md §9's example capability map — the spec's own acceptance criteria.
SECTION_9_MAP = {
    "api-design": 0.75,
    "databases": 0.80,
    "authentication": 0.70,
    "debugging": 0.65,
    "system-design": 0.50,
    "scalability": 0.35,
    "trade-off-analysis": 0.40,
}

TOLERANCE = 0.05


def show_answers(a: OnboardingAnswers, engine: OnboardingEngine) -> None:
    print(f"\n{RULE}\nINTAKE  (Claude.md §8)\n{RULE}\n")
    print(f"  What are you working toward?   {engine.goals[a.goal]['name']}")
    print(f"  What do you already know?      {a.knows or '—'}")
    print(f"  What technologies?             {', '.join(a.technologies) or '—'}")
    print(f"  What have you built?           {a.built or '—'}")
    print(f"  How confident are you?         "
          f"{engine.levels[a.self_rated_level]['label']} "
          f"(caps estimates at {engine.levels[a.self_rated_level]['ceiling']:.0%})")


def show_map(profile, result: OnboardingResult, engine: OnboardingEngine) -> None:
    """Render through Phase 4's canonical map so onboarding and the profile viewer
    cannot drift apart. §9's framing lives in the renderer, not here."""
    print()
    print(cmap.render(
        profile,
        focus=engine.focus_for(result.answers.goal),
        title="INITIAL CAPABILITY MAP  (Claude.md §9)",
    ))
    if result.matched_phrases:
        print(f"\n  Phrases recognised in your answers: "
              f"{', '.join(sorted(set(result.matched_phrases)))}")
    if result.unrecognised_technologies:
        print(f"  Not recognised (no signal contributed): "
              f"{', '.join(result.unrecognised_technologies)}")
    print()


def explain(result: OnboardingResult, graph: CapabilityGraph, capability_id: str) -> int:
    try:
        cap = graph.get(capability_id)
    except KeyError as exc:
        print(exc, file=sys.stderr)
        return 1
    est = result.by_id().get(capability_id)

    print(f"\n{RULE}\n{cap.name}   [{cap.id}]\n{RULE}\n")
    print(textwrap.fill(cap.statement, 78))
    if est is None:
        print("\nNot rated — nothing in your answers produced a signal for this "
              "capability.\nThat is an honest absence, not a score of zero.\n")
        return 0

    print(f"\nSelf-reported confidence: {pct(est.confidence)}")
    if est.ceiling_applied:
        print(f"  strongest signal was {est.ceiling_applied:.0%}, capped by your "
              f"self-rated level")
    print(f"\nChosen reason (the strongest single signal):")
    print(f"  {est.chosen}")
    print(f"\nEverything considered ({len(est.considered)} signal(s)):")
    for s in est.considered:
        mark = "->" if s is est.chosen else "  "
        print(f"  {mark} {s}")
    print(textwrap.fill(
        "Signals combine by MAX, not by sum. Adding three weak signals into one strong "
        "one would manufacture confidence you never expressed, and max keeps exactly one "
        "nameable reason behind every number.", 78, initial_indent="\n", subsequent_indent=""))
    print()
    return 0


def verify(result: OnboardingResult) -> int:
    """Check §8's example input against §9's example output."""
    by_id = result.by_id()
    print(f"\n{RULE}\nSPEC CONFORMANCE — §8 example input vs §9 example map\n{RULE}\n")
    print(f"{'capability':22} {'§9':>6} {'ours':>6} {'delta':>7}   reason")
    print(f"{'-' * 22} {'-' * 6} {'-' * 6} {'-' * 7}   {'-' * 34}")
    worst = 0.0
    failures = 0
    for cid, want in SECTION_9_MAP.items():
        est = by_id.get(cid)
        if est is None:
            print(f"{cid:22} {want:6.2f} {'—':>6} {'MISSING':>7}")
            failures += 1
            continue
        delta = est.confidence - want
        worst = max(worst, abs(delta))
        flag = "" if abs(delta) <= TOLERANCE else "  OUT OF TOLERANCE"
        if abs(delta) > TOLERANCE:
            failures += 1
        print(f"{cid:22} {want:6.2f} {est.confidence:6.2f} {delta:+7.2f}   "
              f"{est.chosen.kind}: {est.chosen.source[:34]}{flag}")
    print(f"\n{RULE}")
    print(f"  max deviation {worst:.3f}, tolerance {TOLERANCE:.2f}  ->  "
          f"{'PASS' if failures == 0 else f'FAIL ({failures})'}")
    print(textwrap.fill(
        "Two of these come from the capability graph rather than the technology table: "
        "Scalability via Caching --supports--> Scalability, and Trade-off Analysis via "
        "applies_to backward. That is Phase 1's graph doing work Phase 3 would otherwise "
        "have to hard-code.", 78, initial_indent="\n  ", subsequent_indent="  "))
    print()
    return 0 if failures == 0 else 1


def show_vocabulary(engine: OnboardingEngine) -> None:
    print(f"\n{RULE}\nRECOGNISED VOCABULARY  (data/onboarding.yaml)\n{RULE}\n")
    print(f"Goals ({len(engine.goals)}):")
    for key, g in engine.goals.items():
        print(f"  {key:22} {g['name']}")
    print(f"\nSelf-rated levels ({len(engine.levels)}):")
    for key, l in engine.levels.items():
        print(f"  {key:22} caps estimates at {l['ceiling']:.0%}")
    print(f"\nTechnologies ({len(engine.technologies)}):")
    for key, t in engine.technologies.items():
        sig = ", ".join(f"{c} {v:.2f}" for c, v in t["signals"].items())
        print(f"  {t['name']:16} {sig}")
    print(f"\nFree-text phrases ({len(engine.concepts)}), discounted by "
          f"{engine.rules['free_text_discount']:.2f}:")
    for key, c in engine.concepts.items():
        print(f"  {key:16} {', '.join(c['aliases'])}")
    print()


def ask_interactive(engine: OnboardingEngine) -> OnboardingAnswers:
    print(f"\n{RULE}\nONBOARDING  (Claude.md §8)\n{RULE}")
    name = input("\nYour name: ").strip() or "Student"
    print("\nWhat are you currently working toward?")
    keys = list(engine.goals)
    for i, k in enumerate(keys, 1):
        print(f"  {i}. {engine.goals[k]['name']}")
    raw = input(f"Choose 1-{len(keys)} [1]: ").strip() or "1"
    goal = keys[int(raw) - 1] if raw.isdigit() and 1 <= int(raw) <= len(keys) else keys[0]

    knows = input("\nWhat do you already know? ").strip()
    techs = input("What technologies have you used? (comma separated) ").strip()
    built = input("What have you built? ").strip()

    print("\nHow confident are you overall?")
    lvls = list(engine.levels)
    for i, k in enumerate(lvls, 1):
        print(f"  {i}. {engine.levels[k]['label']}")
    raw = input(f"Choose 1-{len(lvls)} [3]: ").strip() or "3"
    level = lvls[int(raw) - 1] if raw.isdigit() and 1 <= int(raw) <= len(lvls) else "intermediate"

    return OnboardingAnswers(
        student_name=name,
        goal=goal,
        technologies=tuple(t.strip() for t in techs.split(",") if t.strip()),
        knows=knows,
        built=built,
        self_rated_level=level,
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run student onboarding and produce an initial capability map.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--interactive", action="store_true", help="answer the questions yourself")
    ap.add_argument("--explain", metavar="ID", help="provenance for one capability")
    ap.add_argument("--verify", action="store_true", help="check against §9's example map")
    ap.add_argument("--vocabulary", action="store_true", help="what is recognised")
    ap.add_argument("--save", action="store_true", help="write the profile to data/students/")
    ap.add_argument("--student-id", default="student-001")
    args = ap.parse_args()

    graph = CapabilityGraph.load()
    try:
        engine = OnboardingEngine.load(graph)
    except OnboardingError as exc:
        print(exc, file=sys.stderr)
        return 1

    if args.vocabulary:
        show_vocabulary(engine)
        return 0

    answers = ask_interactive(engine) if args.interactive else EXAMPLE
    try:
        profile, result = engine.build_profile(answers, student_id=args.student_id)
    except OnboardingError as exc:
        print(exc, file=sys.stderr)
        return 1

    if args.verify:
        if args.interactive:
            print("--verify compares against §8's example; it needs the example intake.",
                  file=sys.stderr)
            return 1
        return verify(result)
    if args.explain:
        return explain(result, graph, args.explain)
    if args.save:
        profile.save()
        rows = profile.to_records()["student_capabilities"]
        print(f"\nsaved {profile.student.id} — {len(rows)} rows, all self-reported, "
              f"0 demonstrated\n")
        return 0

    show_answers(answers, engine)
    show_map(profile, result, engine)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
