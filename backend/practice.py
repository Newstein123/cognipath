#!/usr/bin/env python3
"""Phase 8 — the learning experience library. Claude.md §6.3, §21 Phase 8.

No LLM, no network. Assessing a response is `assess.py`; this is discovery.

  python practice.py                       everything the system can offer
  python practice.py --for scalability     what would produce evidence for one capability
  python practice.py --show ID             the full prompt and rubric
  python practice.py --coverage            which capabilities have no experience
  python practice.py --next --student ID   practice for this student's weakest gap
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  — must precede project imports

import argparse
import sys
import textwrap

from cognith_capability.graph import CapabilityGraph
from cognith_learning.experience import (
    ExperienceError,
    ExperienceLibrary,
    ExperienceType,
    LearningExperience,
)
from cognith_learning.knowledge import GapResolver
from cognith_student.profile import CapabilityProfile

RULE = "─" * 78


def line(e: LearningExperience, graph: CapabilityGraph, highlight: str | None = None) -> str:
    caps = ", ".join(graph.get(c).name for c in e.capability_ids)
    if highlight and highlight in e.capability_ids:
        caps = caps.replace(graph.get(highlight).name, f"*{graph.get(highlight).name}*")
    return (f"  {e.title:30} {e.type.value:11} {e.level.value:12} "
            f"{e.minutes:2}m\n      {caps}")


def show_all(lib: ExperienceLibrary, graph: CapabilityGraph) -> None:
    print(f"\n{RULE}\nLEARNING EXPERIENCES  ({len(lib)})\n{RULE}\n")
    print(textwrap.fill(
        "An experience is something the student does (§6.3). Every one connects to one or "
        "more capabilities through its rubric, so completing it produces evidence for all "
        "of them.", 78))
    for t in ExperienceType:
        items = lib.of_type(t)
        print(f"\n{t.value.upper()}  ({len(items)})")
        if not items:
            note = {
                ExperienceType.EXPLANATION: "produced on demand by `learn.py` against a "
                                            "gap; not a stored artefact, and produces no "
                                            "evidence — reading is not doing",
                ExperienceType.MISSION: "Phase 9",
            }.get(t, "none")
            print(f"      — {note}")
            continue
        for e in sorted(items, key=lambda x: (x.level.value, x.title)):
            print(line(e, graph))
    print(f"\n{RULE}")
    print("  exercise   authored in knowledge/*.md, rubric in data/exercises.yaml")
    print("  diagnostic authored in data/diagnostics.yaml")
    print("  Both are assessed by the same code — see `python assess.py --rubric ID`.\n")


def show_for(lib: ExperienceLibrary, graph: CapabilityGraph, capability_id: str) -> int:
    try:
        cap = graph.get(capability_id)
    except KeyError as exc:
        print(exc, file=sys.stderr)
        return 1
    found = lib.for_capability(capability_id)
    print(f"\n{RULE}\nEXPERIENCES FOR — {cap.name}\n{RULE}\n")
    print(textwrap.fill(cap.statement, 78))
    print()
    if not found:
        print("  Nothing yet. No experience has a rubric criterion for this capability,")
        print("  so nothing the system can offer would produce evidence for it.\n")
        return 0
    for e in found:
        weight = sum(c.weight for c in e.rubric if c.capability_id == capability_id)
        total = sum(c.weight for c in e.rubric)
        primary = " (primary)" if e.capability_id == capability_id else ""
        print(f"  {e.title}{primary}")
        print(f"      {e.type.value}, {e.level.value}, {e.minutes} min   "
              f"— {weight:.1f} of {total:.1f} rubric weight evidences this capability")
        print(f"      {e.id}")
        print()
    print(textwrap.fill(
        "Ordered by how much of each rubric actually evidences this capability. An "
        "experience whose primary target is something else still counts — that is the "
        "same criterion-level tagging that lets one answer move several capabilities.",
        78, initial_indent="  ", subsequent_indent="  "))
    print()
    return 0


def show_one(lib: ExperienceLibrary, graph: CapabilityGraph, experience_id: str) -> int:
    try:
        e = lib.get(experience_id)
    except KeyError as exc:
        print(f"{exc}. Run `python practice.py` to list them.", file=sys.stderr)
        return 1
    print(f"\n{RULE}\n{e.title}   [{e.type.value}]\n{RULE}\n")
    print(f"  {e.level.value}, about {e.minutes} minutes")
    print(f"  evidences: {', '.join(graph.get(c).name for c in e.capability_ids)}")
    if e.source:
        print(f"  source: {e.source}")
    print(f"\n{RULE}\n")
    print(textwrap.indent(e.prompt, "  "))
    print(f"\n{RULE}\nJudged on {len(e.rubric)} criteria\n{RULE}\n")
    for c in e.rubric:
        print(f"  [{graph.get(c.capability_id).name:22}] weight {c.weight}")
        print(textwrap.fill(c.criterion, 74, initial_indent="      ",
                            subsequent_indent="      "))
        print()
    print(f"  To answer it:")
    print(f"    python assess.py --item '{e.id}' --response-file answer.txt --gemini --save\n")
    return 0


def show_coverage(lib: ExperienceLibrary, graph: CapabilityGraph) -> None:
    print(f"\n{RULE}\nEXPERIENCE COVERAGE\n{RULE}\n")
    for area_id, area_name in graph.areas.items():
        print(area_name)
        for cap in graph.by_area(area_id):
            found = lib.for_capability(cap.id)
            ex = sum(1 for e in found if e.type is ExperienceType.EXERCISE)
            dg = sum(1 for e in found if e.type is ExperienceType.DIAGNOSTIC)
            label = f"{dg} diagnostic, {ex} exercise" if found else "— nothing"
            print(f"  {cap.name:24} {label}")
        print()
    missing = lib.uncovered()
    print(RULE)
    print(f"  {len(graph) - len(missing)} of {len(graph)} capabilities can produce evidence.")
    if missing:
        print(f"\n  No experience at all: {', '.join(graph.get(c).name for c in missing)}")
        print(textwrap.fill(
            "The same five that have no corpus material. A capability with no experience "
            "cannot be assessed and cannot be taught, so it cannot enter the loop — worth "
            "knowing before Phase 10 assumes every capability is reachable.", 78,
            initial_indent="  ", subsequent_indent="  "))
    print()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Browse the learning experiences the system can offer.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--for", dest="capability", metavar="ID")
    ap.add_argument("--show", metavar="ID")
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--next", action="store_true", help="practice for the weakest gap")
    ap.add_argument("--student", default="student-001")
    args = ap.parse_args()

    graph = CapabilityGraph.load()
    try:
        lib = ExperienceLibrary.load(graph)
    except ExperienceError as exc:
        print(exc, file=sys.stderr)
        return 1

    if args.show:
        return show_one(lib, graph, args.show)
    if args.capability:
        return show_for(lib, graph, args.capability)
    if args.coverage:
        show_coverage(lib, graph)
        return 0
    if args.next:
        try:
            profile = CapabilityProfile.load(args.student, graph)
        except FileNotFoundError as exc:
            print(exc, file=sys.stderr)
            return 1
        gaps = GapResolver(graph, profile).gaps()
        if not gaps:
            print("\nNo demonstrated gaps. Run `python diagnose.py` to produce evidence.\n")
            return 0
        gap = gaps[0]
        print(f"\n  Weakest demonstrated gap: {graph.get(gap.capability_id).name} "
              f"({gap.reason})")
        return show_for(lib, graph, gap.capability_id)

    show_all(lib, graph)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
