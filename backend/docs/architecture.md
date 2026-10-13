# Architecture

**Status:** Phase 0 complete — the existing RAG system, documented as-is.
**Last updated:** 2026-09-23 (Phase 14 — see §13 RAG, §14 loop)

This is the `Claude.md` §21 Phase 0 deliverable: inspect and document the existing Python
RAG system without modifying it. Everything below describes code that exists and runs
today. Anything not yet built is confined to [Where this is going](#where-this-is-going)
and explicitly marked as such.

`Claude.md` is the plan. This file records what was actually built.

---

## 1. What the system is

A **grounded question-answering pipeline** over a small curated corpus of software
engineering notes. It retrieves relevant passages and asks Gemini to answer *only* from
them.

Its defining behaviour is not answering — it is **refusing**. When the corpus does not
cover a question, the system declines rather than answering from Gemini's pretraining.
That is the property that makes it a knowledge layer for a learning product instead of a
chatbot: a student cannot tell the difference between a sourced answer and a confident
invention, so the system must never produce the latter.

Scale today: **7 documents → 42 chunks**, 768-dimension embeddings, a single JSON index
file. Small on purpose — every stage is inspectable by hand.

---

## 2. Layout

```
knowledge/*.md            7 curated documents with YAML frontmatter
cognith_rag/           the portable core — intended to move into Cloud Run
├── config.py             models, TOP_K, MIN_SCORE, paths
├── chunker.py            heading-aware chunking + metadata inheritance
├── embeddings.py         Gemini embeddings, asymmetric document/query task types
├── store.py              index.json persistence, cosine search, metadata filters
├── prompts.py            the grounding contract (system instruction)
└── generate.py           abstention layers + grounded answer generation
ingest.py                 entry point: build the index
retrieve.py               entry point: inspect retrieval, no LLM
ask.py                    entry point: full grounded answer
eval.py                   entry point: test suite + threshold calibration
tests.yaml                15 cases — 9 must answer, 6 must abstain
index.json                generated artifact (gitignored)
```

The split is deliberate and is stated in `cognith_rag/__init__.py`: the **four root
scripts are a throwaway test harness**; `cognith_rag/` is the part meant to survive
into the backend (`Claude.md` §18 — Cloud Run).

---

## 3. Entry points

There is no long-running process. Four command-line scripts, each exposing one stage so
the pipeline can be inspected at any depth:

| Entry point | Purpose | Calls Gemini? |
|---|---|---|
| [`ingest.py`](../ingest.py) | Chunk `knowledge/*.md`, embed, write `index.json` | yes — embeddings |
| [`retrieve.py`](../retrieve.py) | Show which chunks a question retrieves, and their scores | yes — one query embedding |
| [`ask.py`](../ask.py) | Full pipeline: retrieve → ground → answer or abstain | yes — embedding + generation |
| [`eval.py`](../eval.py) | Run `tests.yaml`; or `--calibrate` to print the score distribution | yes — per case |

```bash
source .venv/bin/activate
python ingest.py                                          # required first: index.json is gitignored
python retrieve.py "why did my query get slow?"           # retrieval only
python ask.py "What is the CAP theorem?"                  # must abstain
python ask.py "Why does an index help?" --show-prompt     # proves only chunks are sent
python eval.py                                            # 15/15
python eval.py --calibrate                                # score distribution
```

`retrieve.py` existing separately from `ask.py` matters: it is how you tell a *retrieval*
failure from a *grounding* failure. If a question is answered badly, `retrieve.py` shows
whether the right chunks were even found.

### API endpoints

**There are none.** No HTTP layer, no web framework, no server — the dependency list is
`google-genai`, `numpy`, `python-dotenv`, `pyyaml`, `pydantic`, and nothing else.

This is a real gap, not an oversight to gloss over. `Claude.md` §18 specifies a Cloud Run
backend, and §21 Phase 7 connects RAG to capability gaps. Something has to expose
`cognith_rag` over HTTP before either can happen. Recorded here so the gap is visible
rather than discovered later.

---

## 4. Data model

One dataclass carries everything. From [`chunker.py`](../cognith_rag/chunker.py):

```python
@dataclass
class Chunk:
    id: str                      # "database-indexing.md#why-queries-get-slow-without-an-index"
    doc: str                     # "database-indexing.md"
    section: str                 # "Why queries get slow without an index"
    text: str                    # the embedded text (see note below)
    metadata: dict[str, Any]     # concept, capability, difficulty, prerequisites, source, kind
    embedding: list[float] | None # 768 floats, L2-normalized
```

`Chunk.citation` renders as `database-indexing.md § Why queries get slow without an index`
— exact provenance, always available for display to a student.

Two smaller types complete the model:
- `Hit` ([`store.py`](../cognith_rag/store.py)) — a `Chunk` plus its similarity `score`.
- `Result` ([`generate.py`](../cognith_rag/generate.py)) — the pipeline outcome:
  `answered`, `answer`, `hits`, `citations`, `reasoning`, `gate`, and optionally the exact
  `prompt` sent.

### How chunks are cut

One chunk per `##` heading. Not fixed-size windows, for two reasons:

1. **Provenance stays exact.** A chunk *is* a named section, so citations are meaningful.
2. **Boundaries land on concept boundaries** — which is what the capability layer will key
   off later.

The `# Title` preamble before the first `##` is dropped; the frontmatter already captures
it. Sections longer than `MAX_CHUNK_CHARS` (1200) are split on blank lines, packing whole
paragraphs, so a split never lands mid-sentence.

### Metadata inheritance

Each document's YAML frontmatter is inherited by every chunk in it:

```yaml
---
id: database-indexing
concept: Database Indexing
capability: database-reasoning
difficulty: beginner
prerequisites: [how-databases-store-data]
source: "Markus Winand, Use The Index, Luke — Ch. 1"
---
```

An individual section can override fields with an HTML comment on its first line:

```markdown
## Exercise: Spot the missing index
<!-- meta: kind=exercise, difficulty=intermediate -->
```

`kind` defaults to `explanation`. Current distribution across the 42 chunks:

| Field | Values present today |
|---|---|
| `kind` | `explanation` 31, `exercise` 7, `reference` 4 |
| `difficulty` | `intermediate` 21, `beginner` 18, `advanced` 3 |
| `capability` | `system-design` 13, `database-reasoning` 13, `trade-off-analysis` 6, `http-fundamentals` 5, `api-design` 5 |

`prerequisites` is authored but **not yet used by any code** — nothing reads it. It is
forward-looking metadata for the capability layer, which is why one reference is currently
dangling: `database-indexing.md` declares `prerequisites: [how-databases-store-data]`, and
no such document exists. All seven other references resolve:

```
caching              -> http                    OK
database-indexing    -> how-databases-store-data DANGLING
database-replication -> database-indexing       OK
load-balancing       -> http                    OK
rest-api             -> http                    OK
system-design        -> caching, load-balancing, database-replication   OK
```

Harmless today. It matters at Phase 1, because these prerequisite edges are the closest
thing the corpus already has to §7's capability relationships — so whichever phase starts
reading them needs to decide whether a dangling target is an error or a placeholder for
a document not yet written.

### One detail worth knowing

The text that gets embedded is **not** the raw section body. From `chunker.py`:

```python
embed_text = f"{metadata['concept']} — {heading}\n\n{piece}"
```

Each chunk carries its own concept and heading into its embedding, so an isolated chunk
still states what it is about. A paragraph reading "this doubles read throughput" is
ambiguous alone; prefixed with `Database Replication — Read replicas: when to use
one` it is not. This is noted in the source as measurably improving retrieval.

---

## 5. Embeddings

[`embeddings.py`](../cognith_rag/embeddings.py) — `gemini-embedding-001` at 768
dimensions.

The important property is **asymmetry**. Documents and queries are embedded with
different task types:

```python
embed_documents(texts)  ->  task_type="RETRIEVAL_DOCUMENT"
embed_query(text)       ->  task_type="RETRIEVAL_QUERY"
```

A question and the passage answering it are different kinds of text — the question does
not resemble the answer. Telling the model which role it is embedding lets it place them
in compatible regions of the space. `config.py` records this as the reason
`gemini-embedding-001` was chosen over `gemini-embedding-2`: the newer model does not
support `task_type`.

Two mechanical details:

- **Manual L2 normalization is required.** `gemini-embedding-001` only returns unit-length
  vectors at its full 3072 dimensions. At a truncated `output_dimensionality=768` they come
  back un-normalized, so `normalize()` does it. This is what makes cosine similarity a
  plain dot product downstream.
- Requests batch at 32 texts to stay inside request limits.

The client is lazily constructed and reads `GEMINI_API_KEY` from `.env` via
`python-dotenv`, with an error message pointing at the key page if it is missing.

---

## 6. Vector storage and retrieval

[`store.py`](../cognith_rag/store.py) — an in-memory numpy matrix persisted to
`index.json`.

No vector database. At 42 chunks a brute-force dot product over a 42×768 matrix is
instant, and the entire index is a readable JSON file you can open and inspect. The
docstring names the upgrade path (Vertex Vector Search) for when the corpus outgrows this.

`index.json` structure:

```json
{
  "manifest": {
    "embed_model": "gemini-embedding-001",
    "dim": 768,
    "chunk_count": 42,
    "files": { "caching.md": "<sha256[:16]>", ... }
  },
  "chunks": [ { "id": ..., "embedding": [768 floats], ... } ]
}
```

The manifest earns its place. `Store.load()` **refuses to load** an index whose
`embed_model` or `dim` disagrees with `config.py`:

```
Index was built with gemini-embedding-001/768d but config wants .../1536d.
Re-run `python ingest.py`.
```

Without that check, changing the embedding model would silently compare vectors from two
different spaces — producing plausible-looking but meaningless scores. Per-file SHA256
hashes are also stored, so it is possible to tell which source documents an index was
built from.

### Search

```python
Store.search(query_vector, k=5, capability=None, difficulty=None, kind=None) -> list[Hit]
```

Cosine similarity via `self._matrix @ query_vector` (valid as a plain dot product because
all vectors are normalized), then optional metadata filters, then top-k.

Filters are applied by masking scores to `-inf` rather than by rebuilding the matrix, and
non-finite scores are dropped from the result — so an over-narrow filter returns fewer
hits or none, never padding.

```bash
python retrieve.py "indexing" --capability database-reasoning --kind exercise
```

The filters are wiring, proving authored metadata reaches retrieval. The capability-gap
query API on top of them is deliberately **not** built (see
[Where this is going](#where-this-is-going)).

---

## 7. Generation and the abstention pipeline

This is the part to understand before changing anything.

[`generate.py`](../cognith_rag/generate.py) does not simply ask Gemini a question. It
runs **three independent gates**, and `Result.gate` records which one decided the outcome.

```
                        hits from Store.search()
                                  │
              ┌───────────────────▼───────────────────┐
              │  GATE 1 — similarity floor            │   deterministic, pre-LLM
              │  hits[0].score < MIN_SCORE (0.55)?    │   costs no API call
              └───────────────────┬───────────────────┘
                     refuse ◄─────┤ gate="score_floor"
                                  │ pass
              ┌───────────────────▼───────────────────┐
              │  GATE 2 — grounding contract          │   inside the model
              │  build_prompt() + SYSTEM_INSTRUCTION  │   structured JSON out
              │  answerable == false?                 │
              └───────────────────┬───────────────────┘
                     refuse ◄─────┤ gate="model"
                                  │ answerable
              ┌───────────────────▼───────────────────┐
              │  GATE 3 — citation check              │   post-LLM, deterministic
              │  every cited id was actually sent?    │
              │  at least one citation present?       │
              └───────────────────┬───────────────────┘
                     refuse ◄─────┤ gate="citation_check"
                                  │ valid
                                  ▼
                         grounded answer + sources
```

**Gate 1 — similarity floor.** If the best chunk scores below `MIN_SCORE`, refuse without
calling Gemini. Deterministic and free. It catches questions clearly unrelated to the
corpus.

**Gate 2 — the grounding contract.** [`prompts.py`](../cognith_rag/prompts.py) holds a
system instruction whose rules are ordered by priority, and whose first rule is that
knowing the answer is not permission to give it. Its rule 3 is the load-bearing one:

> Partial overlap is not coverage. If the excerpts mention a topic in passing, or cover
> something adjacent to the question but not the question itself, that is NOT enough.

The response comes back as a structured `GroundedAnswer` (a pydantic schema enforced via
`response_format`) at `temperature=0.0`:

```python
class GroundedAnswer(BaseModel):
    answerable: bool
    answer: str
    citations: list[str]   # ids of exactly the excerpts used
    reasoning: str         # why it could or could not answer — read by eval.py
```

Refusing is framed to the model as a correct outcome, not a failure. `reasoning` is always
populated, which is what makes an abstention debuggable instead of opaque.

**Gate 3 — citation check.** Every id in `citations` must be one that was actually sent.
A cited id that was never supplied means the model drifted off-corpus — and no similarity
threshold can detect that, only comparing the ids can. Claiming `answerable` while citing
nothing is also rejected.

### Why two abstention layers instead of one

Because calibration proved one is not enough. `python eval.py --calibrate` compares
top-1 scores for questions that should be answered against questions that should be
refused, and the two classes **overlap**:

```
lowest in-corpus       0.616   "a user updated their profile but the change disappeared"
highest out-of-corpus  0.662   "what is the CAP theorem?"
margin                -0.046
```

"What is the CAP theorem?" scores **higher** than a legitimate in-corpus question. The
corpus discusses consistency/availability trade-offs, so retrieval surfaces genuinely
plausible chunks — but discussing trade-offs is not covering a specific named theorem.

So no threshold separates these classes. Raising the floor to 0.66 to catch CAP theorem
would start refusing real questions. `MIN_SCORE = 0.55` is therefore set *conservatively
and from data*: its job is cheap rejection of the obviously unrelated (weather 0.489,
"write me a linked list" 0.531), and Gate 2 handles the plausible-but-uncovered.

**A similarity floor alone is not a grounding strategy.** That is the spike's main finding
and the reason the architecture looks like this.

### Failure handling

Any exception from the Gemini call is caught and degrades to **retrieval-only** with
`gate="api_error"` — the student still gets the most relevant excerpts and an honest note
that the AI service is unavailable. A failed AI call never breaks the learning experience
and never crashes the caller.

---

## 8. Configuration

All of it in [`config.py`](../cognith_rag/config.py), no scattered constants:

| Setting | Value | Note |
|---|---|---|
| `EMBED_MODEL` | `gemini-embedding-001` | chosen for `task_type` support |
| `EMBED_DIM` | `768` | supported 128–3072; 768/1536/3072 recommended |
| `GENERATION_MODEL` | `gemini-3.8-flash` | override: `COGNITH_MODEL=... python eval.py` |
| `TOP_K` | `5` | chunks retrieved per question |
| `MIN_SCORE` | `0.55` | Gate 1 floor — calibrated, see above |
| `MAX_CHUNK_CHARS` | `1200` | split threshold |
| `ABSTAIN_MESSAGE` | fixed string | what a student sees on refusal |
| paths | `KNOWLEDGE_DIR`, `INDEX_PATH`, `TESTS_PATH` | resolved from the package location |

Secrets are separate: `GEMINI_API_KEY` lives in `.env` (gitignored, with `.env.example`
committed). `GENERATION_MODEL` being env-overridable exists so models can be A/B tested
without editing code.

The comments in `config.py` explaining `MIN_SCORE` and the model choice are load-bearing
documentation — they record the calibration run that produced the number. Worth preserving.

---

## 9. Data flow

### Ingest — `python ingest.py`

```
knowledge/*.md  (7 files, YAML frontmatter)
      │
      ▼
chunk_corpus()                    split on `##`, inherit frontmatter,
  chunker.py                      apply <!-- meta: --> overrides,
      │                           split >1200 chars on paragraphs
      ▼
  42 Chunk objects                text = "{concept} — {heading}\n\n{body}"
      │
      ▼
embed_documents()                 Gemini, task=RETRIEVAL_DOCUMENT,
  embeddings.py                   batches of 32, then L2 normalize
      │
      ▼
Store(chunks, manifest).save()    + embed_model, dim, chunk_count,
  store.py                        per-file SHA256
      │
      ▼
index.json                        ~1 MB, gitignored
```

### Query — `python ask.py "..."`

```
question
      │
      ▼
embed_query()                     Gemini, task=RETRIEVAL_QUERY
  embeddings.py                   → one normalized 768-d vector
      │
      ▼
Store.load()                      manifest guard: model/dim must match config
Store.search(vec, k=5)            matrix @ vector → optional filters → top-k
  store.py                        → list[Hit]
      │
      ▼
answer(question, hits)            GATE 1  similarity floor      → score_floor
  generate.py                     GATE 2  grounding contract     → model
                                  GATE 3  citation check         → citation_check
                                  (exception → api_error, retrieval-only)
      │
      ▼
Result                            answered, answer, citations,
                                  reasoning, gate, hits, prompt
      │
      ▼
ask.py renders                    answer + cited sources with scores,
                                  or the abstention and why
```

Note that **Gemini appears twice** in the query path, for two unrelated jobs: embedding
the question, and generating the grounded answer. Gate 1 sits between them, which is what
lets a refusal cost only the (cheap) embedding call.

---

## 10. Testing

[`tests.yaml`](../tests.yaml) holds **15 cases: 9 must answer, 6 must abstain.** Each case
is a question, an `expect` of `answer` or `abstain`, optional `expect_docs`, an optional
`match: any`, and an optional `note`.

`eval.py` asserts three things per case, not one:

| Check | Question it answers |
|---|---|
| Behaviour | did it answer vs abstain as required? |
| Recall@k | did the expected document appear among the retrieved chunks? |
| Citation validity | was every cited id genuinely sent? |

Separating these localizes failures. An abstention caused by bad retrieval is a different
bug from an abstention caused by an over-strict grounding contract, and only recall@k
tells them apart.

The summary also prints **abstentions broken down by gate**, which is how you verify both
layers are actually load-bearing rather than one doing all the work. And a false answer —
answering a question that should have been refused — is reported separately and loudly as
"the failure that matters most".

Last recorded run: **15/15**, recall@5 9/9, citation validity 15/15, abstention 6/6, with
4 abstentions from Gate 2 and 2 from Gate 1. Both layers carry weight.

```bash
python eval.py             # exit 0 only if every case passes
python eval.py --calibrate # score distribution + threshold analysis
```

`--calibrate` is worth a note: it does not just print scores, it detects whether the
classes are separable and says so. On overlap it reports the best achievable single
threshold and how many cases it still misclassifies. It is the tool that produced the
finding in §7.

---

## 11. Where this is going

> RAG's position in the product was settled in Phase 7 — see §13. What remains open:

- §19's data model lists a `knowledge_chunks/` collection, so `index.json` is expected to
  become Firestore-backed eventually.
- There is still **no HTTP layer** (§3). §18 specifies a Cloud Run backend, and
  `cognith_rag/__init__.py` states this package is the part meant to move into it.
  Nothing has needed it yet because every layer runs in-process.

### Resolved: capability naming

Phase 1 recorded an open question about the corpus's `capability:` frontmatter values
(`http-fundamentals`, `api-design`, `database-reasoning`, …) not matching §6.1's "can do"
framing or §7's tree. Resolved in Phase 1 ([decisions.md](decisions.md) D9): they remain
**knowledge tags**, a separate vocabulary, and capabilities carry `knowledge_docs` mapping
to documents instead.

Phase 7 then proved why that was right — see §13.

---

## 12. Phase log

| Phase | Scope | Status | Doc |
|---|---|---|---|
| 0 | Existing RAG — inspect and document | **done** 2026-09-22 | this file |
| 1 | Capability model + relationships | **done** 2026-09-22 | [capability-model.md](capability-model.md) |
| 2 | Student capability | **done** 2026-09-22 | [capability-model.md](capability-model.md) §§11–17 |
| 3 | Student onboarding | **done** 2026-09-22 | [onboarding.md](onboarding.md) |
| 4 | Capability map | **done** 2026-09-22 | [onboarding.md](onboarding.md) §§10–16 |
| 5 | Diagnostic | **done** 2026-09-22 | [assessment.md](assessment.md) |
| 6 | Evidence + assessment | **done** 2026-09-22 | [assessment.md](assessment.md) §§12–21 |
| 7 | RAG integration | **done** 2026-09-22 | this file §13 |
| 8 | Learning experience | **done** 2026-09-22 | [learning-experiences.md](learning-experiences.md) |
| 9 | Flagship mission | **done** 2026-09-22 | [missions.md](missions.md) |
| 10 | Complete adaptive loop | **done** 2026-09-22 | this file §14 |
| 11 | Milestones and progress | **done** 2026-09-23 | [milestones-and-progress.md](milestones-and-progress.md) |
| 12 | APPLY — the integration rung | **done** 2026-09-23 | [learning-experiences.md](learning-experiences.md) §§11–16 |
| 13 | Retry tracking and learner signals | **done** 2026-09-23 | [learner-history.md](learner-history.md) |
| 14 | Interactive session | **done** 2026-09-23 | [the-app.md](the-app.md) |
| 15 | HTTP API + storage seam (Cognith rename) | **done** 2026-10-14 | [api.md](api.md) |

Phase 0 modified no code. Phases 1–6 added the capability and student layers alongside
it and modified no file described in this document. Phase 6 is the first to call Gemini,
reusing this system's client and generation model but none of its retrieval. The project now has three
independent packages, with imports pointing one way only —
`cognith_student → cognith_capability → ∅`, and `cognith_rag → ∅`
(see [decisions.md](decisions.md) D14). See [decisions.md](decisions.md) for the reasoning
behind the choices described above.

**Open questions from §11, as of Phase 1:**

- Q1 (capability ids vs knowledge tags) — **resolved.** Two vocabularies, joined by
  `knowledge_docs` on each capability. See [decisions.md](decisions.md) D9, which also
  records why the corpus's `capability:` tags turned out to be too coarse to join on.
- Q3 (`prerequisites` frontmatter) — **still open.** Phase 1 reads it not at all and left
  the dangling reference in place, deliberately.

---

## 13. Phase 7 — the capability layer connected

Claude.md §5 places this system **beneath** the capability layer:

```
Capability Gap -> Relevant Knowledge -> RAG Retrieval -> Gemini -> Learning Experience
```

That is now built. `cognith_learning/` is the join, and it is the only package that
imports all three others:

```
cognith_learning  ->  cognith_student, cognith_capability, cognith_rag
cognith_student   ->  cognith_capability, cognith_rag
cognith_capability->  (nothing)
cognith_rag       ->  (nothing)
```

Verified by AST, not by grep: nothing imports the learning layer, and **this system remains
unaware that a capability layer exists.**

### The only change to the RAG system

One parameter on `Store.search`:

```python
if docs is not None:
    wanted_docs = set(docs)
    keep &= np.array([c.doc in wanted_docs for c in self.chunks])
```

Three lines, following the masking pattern already there. Nothing else in
`cognith_rag/` was touched — not the chunker, the embeddings, the prompts, or the
abstention gates. §21 Phase 7 says "Do not redesign the RAG unnecessarily"; adding a filter
parameter is not a redesign.

**Why a document filter rather than the existing `capability` filter.** The corpus's
`capability:` tags are too coarse to join on — one `system-design` tag covers `caching.md`,
`load-balancing.md` and `system-design.md`, so filtering by it cannot distinguish the
Caching capability from Load Balancing ([decisions.md](decisions.md) D9). Capabilities map
to documents, which are 1:1.

And **filtering at search time, not after.** Post-filtering a global top-k would drop the
chunks a capability needs whenever something louder outranks them.

### What drives the query

Phase 6 produces something far better than a capability name: the specific rubric criteria
a student failed. So a gap carries them, and they steer retrieval:

```
embedded: Can diagnose why a query or database is slow and choose a change that fixes it.
          Identifies the database as a likely constraint and gives a reason
          (connections, CPU, contention)

restricted to: database-indexing.md, database-replication.md

  1. 0.698  database-indexing.md § Exercise: Diagnose the slow query
 *2. 0.659  database-indexing.md § Reading a query plan
 *3. 0.651  database-indexing.md § Why queries get slow without an index
 *4. 0.648  database-replication.md § Read replicas: when to use one
```

### The mistake this phase made, and what it taught

The first version used **one string** for both retrieval and the question put to the
generator. Retrieval was excellent — the chunks above are exactly right. The generator then
**abstained**:

```
[ABSTAINED]  gate=model
Why: The excerpts do not contain information regarding database constraints related to
     connections, CPU, or contention.
```

The grounding contract was correct. The corpus never discusses connections or contention,
and rule 3 says adjacent coverage is not coverage. But the *question* was wrong: a rubric
criterion is **assessment language** — it describes what a good answer does. A learner needs
a **question**.

Split into two strings ([decisions.md](decisions.md) D27):

```
embedded: <capability statement> + <unmet criteria>     -> steers retrieval
asked:    How do I diagnose why a query or database is slow...?  -> put to the generator
```

Same retrieval, and now a grounded explanation citing four of the five excerpts. The
criteria were good at finding material and bad at being a question, and conflating the two
made the knowledge layer refuse to teach material it had.

### Abstention is the coverage mechanism

Seven of seventeen capabilities have no corpus material. That needed no special handling:

- **No documents mapped** — retrieval is skipped entirely, no embedding call is spent, and
  the tutor reports a content gap.
- **Documents mapped but not actually covering it** — the three gates fire exactly as
  designed, and the tutor says so rather than improvising.

The spike's central finding (§7 above) turns out to be precisely the mechanism the
capability layer needed. A tutor that fills a gap from pretraining is the failure this
system was built to prevent, and a capability gap is the case where the temptation is
strongest.

### Practice is reachable

`kind: exercise` chunks are retrieved alongside the explanation using the same document
filter, so the corpus's seven authored exercises surface against a real gap. Phase 8 turns
them into learning experiences; Phase 7 only shows they are reachable.

```
PRACTICE AVAILABLE
  • database-indexing.md § Exercise: Diagnose the slow query   (0.698)
  • database-replication.md § Exercise: Route the reads   (0.634)
```

---

## 14. Phase 10 — the adaptive loop

```
cognith_learning/loop.py     NextStep, LoopState, AdaptiveLoop
cognith.py                   the front door
```

§15's loop ended with "Select Next Experience", and that selector did not exist. Every
other arrow had been built by Phase 9; a person still had to choose which command to run.

**Phase 10 added no new machinery.** It is a policy over signals each earlier phase
surfaced and deliberately refused to act on:

| Signal | Built in |
|---|---|
| `profile.unverified()`, `calibration_gaps()`, `blocked()` | Phase 2 |
| `graph.prerequisites_of()`, `prerequisite_closure()` | Phase 1 |
| `GapResolver.gaps()` with unmet criteria | Phase 7 |
| `ExperienceLibrary.for_capability()` | Phase 8 |
| corpus coverage per capability | Phase 7 |

That each phase stopped at the signal is what made this one small.

### Two rules

**Never recommend what cannot be delivered.** Five capabilities have no corpus material
*and* no experience. Recommending one is a dead end that makes the system look broken, so
every step is filtered to something that exists, and the rest is reported as a **content
backlog** — a fact about the product, not about the learner.

**Every step is actionable now.** A plan is a short ordered list the learner can start
immediately, each with the exact command.

### The policy

| State | Recommendation |
|---|---|
| no profile | onboard |
| claims but nothing verified | diagnose, boldest claim first |
| demonstrated gap with corpus | **learn**, then **practise** it |
| foundations demonstrated | the flagship mission |
| claims still outstanding | diagnose those |
| nothing left | say so, and point at the backlog |

The mission's prerequisites are **derived from the capability graph**, not listed —
`prerequisites_of` over the mission's capabilities yields Databases and HTTP. Hardcoding
them would have given the same answer today and drifted the moment an edge changed.

### Two defects found by running it

*A ready learner never saw the mission.* Gaps filled every slot and the mission sat at
position 8 of a 3-item plan. It is the flagship (§12) and the spine of the demo (§23), so
when earned it now takes the last slot — the plan reads "close a gap or two, then apply it
under real constraints", which is §16's progression.

*The held-back explanation vanished when the plan was full.* A mission absent with no
reason is indistinguishable from one that does not exist. The backlog entry is now recorded
regardless of remaining slots, because it explains an absence rather than competing for a
place.

### §27's definition of done

`python cognith.py --loop` checks the learner against §27's eleven stages:

```
[x] Goal                     [x] Gap detection
[x] Initial capability map   [x] Knowledge
[x] Diagnostic               [x] Practice
[x] Evidence                 [x] Mission
[x] Capability profile       [x] Updated capability
                             [x] Next experience

11 of 11 stages reached.
```

One learner, one complete loop. §27: *"That complete loop is more important than the number
of features."*
