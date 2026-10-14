#!/usr/bin/env python3
"""Test suite and threshold calibration.

  python eval.py --calibrate   score distribution -> pick MIN_SCORE from data
  python eval.py               full pass/fail report
"""

from __future__ import annotations

import argparse
import textwrap

import numpy as np
import yaml

from cognith_rag.config import MIN_SCORE, TOP_K, tests_path
from cognith_rag.embeddings import embed_query
from cognith_rag.generate import answer
from cognith_rag.store import Store

RULE = "─" * 78


def load_cases() -> list[dict]:
    return yaml.safe_load(tests_path().read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Calibration
# --------------------------------------------------------------------------
def calibrate(store: Store, cases: list[dict]) -> int:
    """Print top-1 scores split by in-corpus vs out-of-corpus, and the best split."""
    rows = []
    for case in cases:
        hits = store.search(embed_query(case["q"]), k=1)
        rows.append((case["expect"], hits[0].score if hits else 0.0, case["q"],
                     hits[0].chunk.citation if hits else "-"))

    in_scores = sorted(s for e, s, _, _ in rows if e == "answer")
    out_scores = sorted((s for e, s, _, _ in rows if e == "abstain"), reverse=True)

    print(f"\n{RULE}\nTOP-1 SCORE DISTRIBUTION\n{RULE}\n")
    for label, want in (("IN-CORPUS (should answer)", "answer"),
                        ("OUT-OF-CORPUS (should abstain)", "abstain")):
        print(f"{label}")
        for expect, score, q, cite in sorted(
            [r for r in rows if r[0] == want], key=lambda r: -r[1]
        ):
            print(f"  {score:.3f}  {q[:52]:54} -> {cite}")
        print()

    lo_in = min(in_scores) if in_scores else 0.0
    hi_out = max(out_scores) if out_scores else 0.0
    print(RULE)
    print(f"lowest in-corpus      {lo_in:.3f}")
    print(f"highest out-of-corpus {hi_out:.3f}")
    margin = lo_in - hi_out
    print(f"margin                {margin:+.3f}")
    print(RULE)

    if margin > 0:
        suggested = hi_out + margin / 2
        print(f"\nSeparable. Suggested MIN_SCORE = {suggested:.3f} (midpoint).")
        print("The similarity floor alone can separate these questions.")
    else:
        # Best achievable threshold when the classes overlap.
        candidates = sorted({round(s, 3) for _, s, _, _ in rows})
        best_t, best_err = None, len(rows) + 1
        for t in candidates:
            err = sum(1 for e, s, _, _ in rows
                      if (e == "answer" and s < t) or (e == "abstain" and s >= t))
            if err < best_err:
                best_t, best_err = t, err
        print(f"\nNOT separable — the classes overlap by {-margin:.3f}.")
        print(f"Best single threshold is {best_t:.3f}, still misclassifying "
              f"{best_err}/{len(rows)}.")
        print(textwrap.fill(
            "This is the expected outcome, and it is why Layer 2 exists. Set MIN_SCORE "
            "below the lowest in-corpus score so the floor only catches questions that "
            "are clearly unrelated, and let the grounding contract reject the "
            "plausible-but-uncovered ones. Tightening the floor to force separation "
            "here would start refusing legitimate questions.", 78))
        print(f"\nSuggested MIN_SCORE = {max(0.0, lo_in - 0.03):.3f} "
              f"(just under the lowest in-corpus score).")
    return 0


# --------------------------------------------------------------------------
# Full evaluation
# --------------------------------------------------------------------------
def evaluate(store: Store, cases: list[dict], k: int, min_score: float) -> int:
    results = []
    print(f"\n{RULE}\nEVALUATION  (k={k}, min_score={min_score:.2f})\n{RULE}\n")

    for case in cases:
        q, expect = case["q"], case["expect"]
        hits = store.search(embed_query(q), k=k)
        res = answer(q, hits, min_score=min_score)

        behaviour_ok = res.answered == (expect == "answer")

        # Recall@k: did the expected document appear in the retrieved chunks?
        recall_ok = None
        expect_docs = case.get("expect_docs")
        if expect_docs:
            retrieved = {h.chunk.doc for h in hits}
            recall_ok = (
                bool(retrieved & set(expect_docs))
                if case.get("match") == "any"
                else set(expect_docs) <= retrieved
            )

        # Citation validity: every cited id was genuinely in the sent context.
        sent = {h.chunk.id for h in hits}
        cite_ok = all(c in sent for c in res.citations) if res.answered else True

        ok = behaviour_ok and (recall_ok is not False) and cite_ok
        results.append((ok, behaviour_ok, recall_ok, cite_ok, case, res))

        mark = "PASS" if ok else "FAIL"
        got = "answered" if res.answered else "abstained"
        print(f"[{mark}] {q}")
        print(f"       expected {expect:8} got {got:9} gate={res.gate}")
        if expect_docs:
            print(f"       recall@{k}: {'hit' if recall_ok else 'MISS'} "
                  f"(wanted {'any of ' if case.get('match')=='any' else ''}"
                  f"{expect_docs})")
        if res.answered:
            print(f"       cited: {res.citations}")
        else:
            print(f"       why: {res.reasoning[:150]}")
        if not ok:
            top = ", ".join(f"{h.chunk.doc}:{h.score:.2f}" for h in hits[:3])
            print(f"       top hits: {top}")
        print()

    # --- summary ----------------------------------------------------------
    total = len(results)
    passed = sum(1 for r in results if r[0])
    behaviour = sum(1 for r in results if r[1])
    recall_cases = [r for r in results if r[2] is not None]
    recall_hits = sum(1 for r in recall_cases if r[2])
    cite_ok = sum(1 for r in results if r[3])

    abstain_cases = [r for r in results if r[4]["expect"] == "abstain"]
    abstain_ok = sum(1 for r in abstain_cases if not r[5].answered)
    false_answers = [r for r in abstain_cases if r[5].answered]

    print(RULE)
    print(f"Overall            {passed}/{total}")
    print(f"Behaviour          {behaviour}/{total}   (answered vs abstained as expected)")
    print(f"Recall@{k}           {recall_hits}/{len(recall_cases)}   "
          f"(expected document retrieved)")
    print(f"Citation validity  {cite_ok}/{total}   (no fabricated excerpt ids)")
    print(f"Abstention         {abstain_ok}/{len(abstain_cases)}  "
          f"(refused when the corpus lacked the answer)")

    gates: dict[str, int] = {}
    for r in results:
        if not r[5].answered:
            gates[r[5].gate] = gates.get(r[5].gate, 0) + 1
    if gates:
        print(f"\nAbstentions by layer: {gates}")
        print("  score_floor    = Layer 1, refused before calling Gemini")
        print("  model          = Layer 2, grounding contract refused")
        print("  citation_check = post-check caught a fabricated citation")

    if false_answers:
        print(f"\n!! {len(false_answers)} ANSWER(S) FROM OUTSIDE THE CORPUS "
              f"— the failure that matters most:")
        for r in false_answers:
            print(f"   - {r[4]['q']}")
    print(RULE + "\n")
    return 0 if passed == total else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--calibrate", action="store_true",
                    help="print the score distribution instead of running the suite")
    ap.add_argument("-k", type=int, default=TOP_K)
    ap.add_argument("--min-score", type=float, default=MIN_SCORE)
    args = ap.parse_args()

    store = Store.load()
    cases = load_cases()
    if args.calibrate:
        return calibrate(store, cases)
    return evaluate(store, cases, args.k, args.min_score)


if __name__ == "__main__":
    raise SystemExit(main())
