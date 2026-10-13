#!/usr/bin/env python3
"""Stage 1 — inspect retrieval. No LLM involved."""

from __future__ import annotations

import argparse
import textwrap

from cognith_rag.config import MIN_SCORE, TOP_K
from cognith_rag.embeddings import embed_query
from cognith_rag.store import Store


def main() -> int:
    ap = argparse.ArgumentParser(description="Show the chunks retrieved for a question.")
    ap.add_argument("question")
    ap.add_argument("-k", type=int, default=TOP_K)
    ap.add_argument("--capability", help="filter: e.g. database-reasoning")
    ap.add_argument("--difficulty", help="filter: beginner|intermediate|advanced")
    ap.add_argument("--kind", help="filter: explanation|exercise|reference")
    ap.add_argument("--full", action="store_true", help="print full chunk text")
    args = ap.parse_args()

    store = Store.load()
    hits = store.search(
        embed_query(args.question),
        k=args.k,
        capability=args.capability,
        difficulty=args.difficulty,
        kind=args.kind,
    )

    print(f"\nQ: {args.question}")
    filters = {k: v for k, v in vars(args).items()
               if k in ("capability", "difficulty", "kind") and v}
    if filters:
        print(f"   filters: {filters}")
    print(f"   {len(store.chunks)} chunks in index, showing top {args.k}\n")

    if not hits:
        print("   no hits")
        return 0

    for rank, hit in enumerate(hits, 1):
        m = hit.chunk.metadata
        flag = " " if hit.score >= MIN_SCORE else "↓"  # below the abstain floor
        print(f"{flag}{rank}. {hit.score:.3f}  {hit.chunk.citation}")
        print(f"      id={hit.chunk.id}")
        print(f"      capability={m.get('capability')}  difficulty={m.get('difficulty')}"
              f"  kind={m.get('kind')}")
        body = hit.chunk.text if args.full else hit.chunk.text[:220].replace("\n", " ") + "..."
        print(textwrap.indent(textwrap.fill(body, 88) if not args.full else body, "      "))
        print()

    print(f"   (floor = {MIN_SCORE:.2f}; ↓ marks chunks below it)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
