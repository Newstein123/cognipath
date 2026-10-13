#!/usr/bin/env python3
"""Stage 2 — grounded answer with sources, or an abstention."""

from __future__ import annotations

import argparse
import textwrap

from cognith_rag.config import MIN_SCORE, TOP_K
from cognith_rag.embeddings import embed_query
from cognith_rag.generate import answer
from cognith_rag.store import Store

RULE = "─" * 78


def main() -> int:
    ap = argparse.ArgumentParser(description="Ask a grounded question.")
    ap.add_argument("question")
    ap.add_argument("-k", type=int, default=TOP_K)
    ap.add_argument("--min-score", type=float, default=MIN_SCORE)
    ap.add_argument("--show-prompt", action="store_true",
                    help="dump the exact payload sent to Gemini")
    args = ap.parse_args()

    store = Store.load()
    hits = store.search(embed_query(args.question), k=args.k)
    result = answer(args.question, hits, min_score=args.min_score)

    print(f"\n{RULE}\nQ: {args.question}\n{RULE}")

    if args.show_prompt:
        if result.prompt:
            print("\n### EXACT PROMPT SENT TO GEMINI ###\n")
            print(result.prompt)
            print(f"\n### END PROMPT ###\n{RULE}")
        else:
            print("\n(no prompt sent — refused at the similarity floor)\n" + RULE)

    status = "ANSWERED" if result.answered else "ABSTAINED"
    print(f"\n[{status}]  gate={result.gate}\n")
    print(textwrap.fill(result.answer, 78))

    if result.answered:
        print(f"\n{RULE}\nSources ({len(result.cited_hits)} cited):")
        for hit in result.cited_hits:
            src = hit.chunk.metadata.get("source")
            print(f"  • {hit.chunk.citation}   (score {hit.score:.3f})")
            print(f"    {src}")
    else:
        print(f"\n{RULE}\nWhy: {result.reasoning}")
        if result.gate == "api_error" and result.hits:
            print("\nMost relevant excerpts (retrieval-only fallback):")
            for hit in result.hits[:3]:
                print(f"  • {hit.chunk.citation}   (score {hit.score:.3f})")

    print(f"\n{RULE}\nRetrieved (top {args.k}):")
    for rank, hit in enumerate(result.hits, 1):
        mark = "*" if hit.chunk.id in result.citations else " "
        print(f" {mark}{rank}. {hit.score:.3f}  {hit.chunk.citation}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
