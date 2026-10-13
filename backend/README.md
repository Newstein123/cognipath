# Cognith — RAG Spike

Proves the knowledge layer described in spec §9: retrieval from a small curated corpus,
answers grounded **only** in retrieved chunks, and — the part that matters — **abstention**
when the corpus doesn't cover the question.

> A tutor that silently answers "What is the CAP theorem?" from Gemini's pretraining is
> indistinguishable from a generic chatbot, which spec §19 rules out.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# add your key from https://aistudio.google.com/apikey
echo "GEMINI_API_KEY=your-key-here" > .env
```

## Run

```bash
python ingest.py                 # 7 docs -> 42 chunks -> index.json
python eval.py --calibrate       # score distribution; pick MIN_SCORE from data
python eval.py                   # full pass/fail report

python retrieve.py "why did my query get slow?"          # Stage 1: retrieval only
python ask.py "What is the CAP theorem?"                 # must abstain
python ask.py "Why does an index help?" --show-prompt    # proves only chunks are sent
```

## How abstention works

Two **independent** layers, plus a post-check. Either layer alone is unreliable.

| Layer | Where | Catches |
|---|---|---|
| **1. Similarity floor** | before Gemini is called | questions unrelated to the corpus — deterministic, costs no API call |
| **2. Grounding contract** | inside the model | questions that *retrieve* plausible chunks but aren't actually covered |
| **3. Citation check** | after the model | fabricated excerpt ids — the model drifting off-corpus |

`Result.gate` records which one fired, and `eval.py` reports the breakdown.

The hard case is **CAP theorem**: `system-design.md` discusses consistency/availability
trade-offs, so retrieval surfaces plausible-looking chunks and the similarity floor won't
save you. Layer 2 has to recognise that adjacent coverage isn't coverage.

## Measured results

`eval.py` — **15/15**, recall@5 9/9, citation validity 15/15, abstention 6/6.
Both layers are load-bearing: 4 abstentions came from the grounding contract, 2 from the floor.

`eval.py --calibrate` settled the threshold question empirically, and the answer was the
interesting one — **the classes overlap**:

```
lowest in-corpus      0.616   "a user updated their profile but the change disappeared"
highest out-of-corpus 0.662   "what is the CAP theorem?"
margin                -0.046
```

CAP theorem scores *higher* than a legitimate question, so **no similarity threshold can
separate them**. Raising the floor to catch CAP would refuse real questions. `MIN_SCORE` is
therefore set conservatively (0.55) to do cheap rejection of the obviously-unrelated —
weather 0.489, "write me a linked list" 0.531 — and Layer 2 handles the rest.

This is the spike's main finding: a similarity floor alone is not a grounding strategy.

## Layout

```
knowledge/*.md        7 curated docs, YAML frontmatter (Stage 3 metadata)
cognith_rag/       portable core — this is what moves to Cloud Run
  config.py           models, top_k, MIN_SCORE
  chunker.py          heading-aware chunking + metadata inheritance
  embeddings.py       asymmetric RETRIEVAL_DOCUMENT / RETRIEVAL_QUERY
  store.py            index.json, cosine search, metadata filters
  prompts.py          the grounding contract
  generate.py         the three layers above
ingest.py retrieve.py ask.py eval.py    test harness (throwaway)
tests.yaml            15 cases: 9 must answer, 6 must abstain
```

## Stage 3 metadata

Authored into every doc now; the capability-gap query API is deliberately **not** built yet.

```yaml
---
id: database-indexing
concept: Database Indexing
capability: database-reasoning     # maps to spec §7
difficulty: beginner
prerequisites: [how-databases-store-data]
source: "Use The Index, Luke — Ch. 1"
---
```

Sections override with `<!-- meta: kind=exercise, difficulty=intermediate -->`.
`kind` ∈ `explanation | exercise | reference` — 7 exercises exist already, which is what
"retrieve a beginner explanation + prerequisites + a practice exercise" will need.

Filters are wired through retrieval today:

```bash
python retrieve.py "indexing" --capability database-reasoning --kind exercise
```

## Notes on the Gemini API

Verified against the live SDK (`google-genai 2.24.0`), which has moved on from older tutorials:

- Generation is `client.interactions.create(...)` → `interaction.output_text`.
- `gemini-embedding-001` is used over `gemini-embedding-2` because it supports `task_type`,
  enabling asymmetric query/document embedding.
- Vectors at `output_dimensionality=768` are **not** unit-length; `embeddings.normalize()`
  fixes that so cosine similarity is a plain dot product.
- On any API failure `ask.py` degrades to retrieval-only rather than crashing (spec Appendix A).
