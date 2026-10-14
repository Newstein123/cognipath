#!/usr/bin/env python3
"""Phase 1 — inspect the capability graph. No LLM, no network.

  python capabilities.py                    the §7 tree
  python capabilities.py --edges            every relationship, grouped by type
  python capabilities.py --show scalability one capability and everything touching it
  python capabilities.py --validate         check data/capabilities.yaml only
  python capabilities.py --coverage         which capabilities the corpus can teach
  python capabilities.py --records          the §19 Firestore collection shape
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  — must precede project imports

import argparse
import json
import sys
import textwrap

from cognith_capability.graph import CapabilityGraph
from cognith_capability.models import (
    RELATION_SEMANTICS,
    GraphValidationError,
    RelationType,
)

RULE = "─" * 78


def show_tree(g: CapabilityGraph) -> None:
    print(f"\n{RULE}\n{g.domain}  —  {len(g)} capabilities, {len(g.edges)} relationships\n{RULE}")
    areas = list(g.areas.items())
    for i, (area_id, area_name) in enumerate(areas):
        last_area = i == len(areas) - 1
        print(f"\n{'└──' if last_area else '├──'} {area_name}")
        caps = g.by_area(area_id)
        for j, cap in enumerate(caps):
            stem = "    " if last_area else "│   "
            branch = "└──" if j == len(caps) - 1 else "├──"
            print(f"{stem}{branch} {cap.name:24} [{cap.level.value}]")
            wrap = textwrap.fill(
                cap.statement,
                74,
                initial_indent=f"{stem}{'    ' if j == len(caps) - 1 else '│   '}",
                subsequent_indent=f"{stem}{'    ' if j == len(caps) - 1 else '│   '}",
            )
            print(wrap)
    print()


def show_edges(g: CapabilityGraph) -> None:
    print(f"\n{RULE}\nRELATIONSHIPS  ({len(g.edges)} total)\n{RULE}")
    for relation in RelationType:
        group = [e for e in g.edges if e.relation is relation]
        if not group:
            continue
        doc = RELATION_SEMANTICS[relation]
        print(f"\n{relation.value}  ({len(group)})")
        print(textwrap.fill(doc, 74, initial_indent="   ", subsequent_indent="   "))
        print()
        for e in sorted(group, key=lambda x: (x.source_id, x.target_id)):
            mark = "§7" if e.origin == "claude-md-7" else "  "
            print(f"   {mark} {g.get(e.source_id).name:24} -> {g.get(e.target_id).name}")
    print(f"\n{RULE}")
    print("§7 marks the six relationships given verbatim in Claude.md §7; the rest were")
    print("authored for Phase 1.")
    isolated = g.isolated()
    if isolated:
        print(f"\nNo relationships yet: {', '.join(c.name for c in isolated)}")
    print()


def show_one(g: CapabilityGraph, capability_id: str) -> int:
    try:
        cap = g.get(capability_id)
    except KeyError as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"\n{RULE}\n{cap.name}   [{cap.id}]\n{RULE}")
    print(f"\n{textwrap.fill(cap.statement, 74)}\n")
    if cap.description:
        print(textwrap.fill(cap.description, 74, initial_indent="   ", subsequent_indent="   "))
    print(f"\n   domain {cap.domain}   area {g.areas[cap.area]}   level {cap.level.value}")

    def block(title: str, caps, empty: str) -> None:
        print(f"\n{title}")
        if not caps:
            print(f"   {empty}")
            return
        for c in caps:
            print(f"   • {c.name:24} [{c.level.value}]")

    block("Direct prerequisites — must come first:", g.prerequisites_of(cap.id), "none")
    closure = g.prerequisite_closure(cap.id)
    if len(closure) > len(g.prerequisites_of(cap.id)):
        print("\n   full prerequisite chain, furthest upstream first:")
        print("   " + " -> ".join(c.name for c in closure) + f" -> {cap.name}")
    block("Composed of / exercised through:", g.contributors_to(cap.id), "none")
    block("This is a prerequisite for:", g.unlocked_by(cap.id), "nothing")

    print("\nKnowledge documents (Phase 7 joins on these):")
    print(f"   {', '.join(cap.knowledge_docs) if cap.knowledge_docs else 'NONE — the corpus cannot teach this yet'}")
    print()
    return 0


def show_coverage(g: CapabilityGraph) -> None:
    """Which capabilities the existing corpus can actually support.

    Also validates every knowledge_docs reference against the real corpus. This is the
    dangling-reference class of bug that decisions.md Q3 found in the corpus's own
    `prerequisites` field; the capability graph should not repeat it.

    Reuses cognith_rag's frontmatter parser rather than reimplementing it. The import
    lives here, in the harness — cognith_capability itself imports nothing from the
    RAG package, so the two layers stay independent (Claude.md §25).
    """
    from cognith_rag.chunker import parse_frontmatter
    from cognith_rag.config import knowledge_dir

    corpus: dict[str, str] = {}          # doc id -> filename
    for path in sorted(knowledge_dir().glob("*.md")):
        meta, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        doc_id = meta.get("id")
        if doc_id:
            corpus[doc_id] = path.name

    print(f"\n{RULE}\nKNOWLEDGE COVERAGE\n{RULE}\n")
    print(f"{'capability':26} {'level':13} knowledge documents")
    print(f"{'-' * 26} {'-' * 13} {'-' * 34}")

    covered = 0
    dangling: list[str] = []
    for area_id in g.areas:
        for cap in g.by_area(area_id):
            known = [d for d in cap.knowledge_docs if d in corpus]
            missing = [d for d in cap.knowledge_docs if d not in corpus]
            dangling.extend(f"{cap.id} -> {d}" for d in missing)
            if known:
                covered += 1
                label = ", ".join(corpus[d] for d in known)
            else:
                label = "— none"
            print(f"{cap.name:26} {cap.level.value:13} {label}")
            if missing:
                print(f"{'':41} DANGLING: {', '.join(missing)}")

    print(f"\n{RULE}")
    print(f"{covered}/{len(g)} capabilities have knowledge behind them.")

    if dangling:
        print(f"\n!! {len(dangling)} knowledge_docs reference(s) point at no document:")
        for d in dangling:
            print(f"   - {d}")

    gaps = g.without_knowledge()
    if gaps:
        print(f"\nNo corpus material ({len(gaps)}): {', '.join(c.name for c in gaps)}")
        print(textwrap.fill(
            "This is a gap in the CORPUS, not in the graph. Phase 7 connects capability "
            "gaps to retrieval, and it can only retrieve what has been written. Listed "
            "here so the work is visible before that phase depends on it.", 78))

    unused = sorted(set(corpus) - {d for c in g.capabilities.values() for d in c.knowledge_docs})
    if unused:
        print(f"\nDocuments mapped to no capability: {', '.join(corpus[d] for d in unused)}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Inspect the Cognith capability graph.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--edges", action="store_true", help="list every relationship")
    ap.add_argument("--show", metavar="ID", help="detail for one capability")
    ap.add_argument("--validate", action="store_true", help="validate the data file only")
    ap.add_argument("--coverage", action="store_true",
                    help="cross-check against knowledge/*.md")
    ap.add_argument("--records", action="store_true",
                    help="print the §19 Firestore collection shape as JSON")
    args = ap.parse_args()

    try:
        g = CapabilityGraph.load()
    except GraphValidationError as exc:
        print(f"\ndata/capabilities.yaml is invalid.\n\n{exc}\n", file=sys.stderr)
        return 1

    if args.validate:
        print(f"\ndata/capabilities.yaml is valid — {len(g)} capabilities, "
              f"{len(g.edges)} relationships, no dangling ids, no prerequisite cycles.\n")
        return 0
    if args.records:
        print(json.dumps(g.to_records(), indent=2))
        return 0
    if args.show:
        return show_one(g, args.show)
    if args.coverage:
        show_coverage(g)
        return 0
    if args.edges:
        show_edges(g)
        return 0
    show_tree(g)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
