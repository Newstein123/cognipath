#!/usr/bin/env python3
"""Phase 7 — connect capability gaps to the knowledge layer. Claude.md §5, §21 Phase 7.

    Capability Gap -> Relevant Knowledge -> RAG Retrieval -> Gemini -> Learning Experience

  python learn.py                       the student's demonstrated gaps
  python learn.py --coverage            which gaps the corpus can teach (offline)
  python learn.py --gap scalability --retrieve-only    retrieval, no generation
  python learn.py --gap scalability     retrieve and explain (network)
  python learn.py --next                take the weakest gap and teach it (network)

--retrieve-only and --coverage make no generation call.
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  — must precede project imports

import argparse
import sys
import textwrap

from cognith_capability.graph import CapabilityGraph
from cognith_learning.experience import ExperienceLibrary, ExperienceType
from cognith_learning.knowledge import GapResolver, KnowledgeForGap
from cognith_student.capability_map import pct
from cognith_student.models import DEMONSTRATED_AT
from cognith_student.profile import CapabilityProfile

RULE = "─" * 78


def show_gaps(resolver: GapResolver, graph: CapabilityGraph, include_unverified: bool) -> None:
    gaps = resolver.gaps(include_unverified=include_unverified)
    print(f"\n{RULE}\nCAPABILITY GAPS — {resolver.profile.student.name}\n{RULE}\n")
    if not gaps:
        print("  No demonstrated gaps. Either nothing has been assessed yet, or every\n"
              "  assessed capability is at or above the bar.\n")
        print("  Run `python diagnose.py` to produce evidence first.\n")
        return

    print(textwrap.fill(
        "A gap is a capability the student has DEMONSTRATED they cannot yet do. A merely "
        "claimed capability is not a gap — it is an unknown, and the honest response to "
        "an unknown is a diagnostic, not a lesson.", 78))
    print()
    for g in gaps:
        cap = graph.get(g.capability_id)
        docs = [f"{d}.md" for d in cap.knowledge_docs]
        print(f"  {cap.name}   [{cap.level.value}]")
        print(f"      {g.reason}")
        for u in g.unmet:
            print(textwrap.fill(u, 70, initial_indent="      · ", subsequent_indent="        "))
        print(f"      corpus: {', '.join(docs) if docs else 'NONE — nothing to teach from'}")
        print()


def show_coverage(resolver: GapResolver, graph: CapabilityGraph) -> None:
    coverage = resolver.coverage()
    gaps = {g.capability_id for g in resolver.gaps()}
    print(f"\n{RULE}\nCAN THE CORPUS TEACH THIS?\n{RULE}\n")
    teachable = untouchable = 0
    for area_id, area_name in graph.areas.items():
        print(area_name)
        for cap in graph.by_area(area_id):
            docs = coverage[cap.id]
            mark = "GAP" if cap.id in gaps else "   "
            if docs:
                teachable += 1
                print(f"  {mark} {cap.name:24} {', '.join(docs)}")
            else:
                untouchable += 1
                print(f"  {mark} {cap.name:24} — no material")
        print()
    print(RULE)
    print(f"  {teachable} of {teachable + untouchable} capabilities have corpus material.")
    print("  'GAP' marks a capability this student has demonstrated they cannot yet do.")
    print(textwrap.fill(
        "A gap with no material is not a crash. Retrieval runs, the grounding contract "
        "refuses, and the tutor says it has nothing to teach from — which is the RAG "
        "system's abstention behaviour doing exactly the job it was built for.", 78,
        initial_indent="\n  ", subsequent_indent="  "))
    print()


def show_knowledge(k: KnowledgeForGap, graph: CapabilityGraph) -> None:
    cap = k.capability
    print(f"\n{RULE}\nLEARNING — {cap.name}\n{RULE}\n")
    print(textwrap.fill(cap.statement, 78))
    print(f"\n  gap: {k.gap.reason}")

    if k.prerequisites_first:
        names = ", ".join(c.name for c in k.prerequisites_first)
        print(f"\n  NOTE — prerequisites not yet demonstrated: {names}")
        print(textwrap.fill(
            "The capability graph says these come first. Working on this capability "
            "before them is likely to be the wrong use of the student's time.", 78,
            initial_indent="  ", subsequent_indent="  "))

    print(f"\n{RULE}\nRETRIEVAL\n{RULE}\n")
    print(textwrap.fill(f"embedded: {k.query}", 78, subsequent_indent="            "))
    print(textwrap.fill(f"asked:    {k.question}", 78, subsequent_indent="            "))
    print(f"\n  restricted to: {', '.join(k.docs) if k.docs else 'NOTHING — no corpus for this capability'}")

    if not k.has_corpus:
        print()
        print(textwrap.fill(
            "There is no material in the corpus for this capability, so nothing was "
            "retrieved and no explanation was generated. This is a content gap, and the "
            "honest thing to report. Writing a document for it is the fix.", 78,
            initial_indent="  ", subsequent_indent="  "))
        print()
        return

    print()
    for rank, hit in enumerate(k.hits, 1):
        mark = "*" if k.result and hit.chunk.id in k.result.citations else " "
        print(f" {mark}{rank}. {hit.score:.3f}  {hit.chunk.citation}")
    if k.result:
        print(f"\n  '*' marks excerpts the explanation actually cited.")

    if k.result is None:
        print(f"\n{RULE}\n  Retrieval only — no explanation generated.")
    else:
        print(f"\n{RULE}\nEXPLANATION\n{RULE}\n")
        _show_explanation(k)

    _show_practice(k, graph)


def _show_explanation(k: KnowledgeForGap) -> None:
    if k.answered:
        print(textwrap.fill(k.result.answer, 78, initial_indent="  ", subsequent_indent="  "))
        print(f"\n  Sources:")
        for hit in k.result.cited_hits:
            src = hit.chunk.metadata.get("source")
            print(f"    • {hit.chunk.citation}")
            print(f"      {src}")
    else:
        print(f"  [ABSTAINED]  gate={k.result.gate}\n")
        print(textwrap.fill(k.result.answer, 78, initial_indent="  ", subsequent_indent="  "))
        print(f"\n  Why: {k.result.reasoning}")
        print(textwrap.fill(
            "The knowledge layer refused rather than improvising. That is the behaviour "
            "the RAG spike was built to guarantee — a tutor that answers from "
            "pretraining is indistinguishable from a chatbot.", 78,
            initial_indent="\n  ", subsequent_indent="  "))

def _show_practice(k: KnowledgeForGap, graph: CapabilityGraph) -> None:
    cap = k.capability
    # Phase 8: offer real, assessable experiences rather than raw corpus chunks. The
    # library is asked for practice that evidences THIS capability, which is a stronger
    # match than "an exercise chunk that happened to retrieve well".
    try:
        library = ExperienceLibrary.load(graph)
        practice = library.practice_for(cap.id)
    except Exception:  # noqa: BLE001 — practice is a bonus, never a reason to fail
        practice = []

    if practice:
        print(f"\n{RULE}\nPRACTICE — do one of these to produce evidence\n{RULE}\n")
        for e in practice[:3]:
            weight = sum(c.weight for c in e.rubric if c.capability_id == cap.id)
            total = sum(c.weight for c in e.rubric)
            print(f"  {e.title}   ({e.level.value}, {e.minutes} min)")
            print(f"      {weight:.1f} of {total:.1f} rubric weight evidences {cap.name}")
            print(f"      python practice.py --show '{e.id}'")
            print()
        print(textwrap.fill(
            "Reading an explanation produces no evidence — §6.5 wants observable proof, "
            "and there is nothing to observe in having read something. Answering one of "
            "these does.", 78, initial_indent="  ", subsequent_indent="  "))
    elif k.exercises:
        print(f"\n{RULE}\nRELATED EXERCISES IN THE CORPUS\n{RULE}\n")
        for hit in k.exercises:
            print(f"  • {hit.chunk.citation}   ({hit.score:.3f})")
        print("\n  No rubric authored for these yet, so they cannot be assessed.")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Connect a student's capability gaps to the knowledge layer.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--student", default="student-001")
    ap.add_argument("--gap", metavar="ID", help="teach one capability")
    ap.add_argument("--next", action="store_true", help="teach the weakest gap")
    ap.add_argument("--retrieve-only", action="store_true", help="no generation call")
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--include-unverified", action="store_true",
                    help="also list capabilities that were claimed but never checked")
    ap.add_argument("-k", type=int, default=5)
    args = ap.parse_args()

    graph = CapabilityGraph.load()
    try:
        profile = CapabilityProfile.load(args.student, graph)
    except FileNotFoundError as exc:
        print(f"{exc}\nRun `python onboard.py --save --student-id {args.student}` first.",
              file=sys.stderr)
        return 1
    resolver = GapResolver(graph, profile)

    if args.coverage:
        show_coverage(resolver, graph)
        return 0

    target = args.gap
    if args.next:
        gaps = resolver.gaps()
        if not gaps:
            print("\nNo demonstrated gaps. Run `python diagnose.py` to produce evidence.\n")
            return 0
        target = gaps[0].capability_id

    if not target:
        show_gaps(resolver, graph, args.include_unverified)
        return 0

    try:
        graph.get(target)
    except KeyError as exc:
        print(exc, file=sys.stderr)
        return 1

    gap = next((g for g in resolver.gaps(include_unverified=True)
                if g.capability_id == target), None)
    if gap is None:
        row = profile.row_for(target)
        from cognith_learning.knowledge import Gap
        gap = Gap(capability_id=target, mastery=row.mastery, confidence=row.confidence,
                  reason=f"not currently a gap (mastery {pct(row.mastery)}, "
                         f"bar {DEMONSTRATED_AT:.0%}) — shown on request")

    try:
        knowledge = resolver.knowledge_for(gap, k=args.k, explain=not args.retrieve_only)
    except Exception as exc:  # noqa: BLE001
        print(f"\nRetrieval failed: {type(exc).__name__}: {exc}\n", file=sys.stderr)
        return 1

    show_knowledge(knowledge, graph)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
