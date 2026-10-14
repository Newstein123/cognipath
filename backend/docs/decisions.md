# Decision record

Append-only. Each entry records a decision that is **not obvious from reading the code**,
so the reasoning survives the person who made it.

Format: decision → why → where it lives → what would make us revisit it.

Entries 1–8 were made during the RAG spike and are backfilled here from code comments and
`README.md` as part of Phase 0. Later phases append; nothing is edited in place.

---

## D1 — `gemini-embedding-001` over `gemini-embedding-2`

**Decision:** use the older embedding model.

**Why:** `gemini-embedding-001` supports the `task_type` parameter; the newer model does
not. That parameter lets documents and queries be embedded asymmetrically
(`RETRIEVAL_DOCUMENT` vs `RETRIEVAL_QUERY`). A question does not resemble the passage that
answers it, so telling the model which role it is embedding places the two in compatible
regions of the space. `config.py` calls this "the highest-leverage knob in retrieval
quality" — worth more here than a newer model without it.

**Where:** `cognith_rag/config.py` (`EMBED_MODEL`), `cognith_rag/embeddings.py`
(`embed_documents` / `embed_query`).

**Revisit when:** a newer Gemini embedding model supports `task_type`, or measured recall
with a symmetric newer model beats the current asymmetric setup on `eval.py`.

---

## D2 — 768 dimensions, with manual L2 normalization

**Decision:** truncate embeddings to 768 dimensions and normalize them ourselves.

**Why:** 768 keeps `index.json` around 1 MB and the search matrix trivially small, at no
measured cost to retrieval on this corpus. The normalization is not optional:
`gemini-embedding-001` only returns unit-length vectors at its **full 3072 dimensions**.
At a truncated `output_dimensionality` they come back un-normalized. Skipping
`normalize()` would make the dot product in `Store.search()` silently not a cosine
similarity — scores would still look plausible while ranking wrongly.

**Where:** `cognith_rag/config.py` (`EMBED_DIM`), `cognith_rag/embeddings.py`
(`normalize`).

**Revisit when:** the corpus grows enough that retrieval quality becomes the bottleneck;
1536 or 3072 are the documented next steps. Changing this **requires a re-ingest** — the
manifest guard (D4) will refuse the stale index.

---

## D3 — Heading-aware chunking, not fixed-size windows

**Decision:** one chunk per `##` section, with document frontmatter inherited and
overridable per section.

**Why:** two reasons, both about what the chunk is *for*.

1. **Provenance stays exact.** A chunk is a named section, so a citation reads
   `caching.md § Invalidation and eviction` and can be shown to a student as a real source.
   Fixed windows produce citations like "chunk 17", which are useless in a learning product.
2. **Boundaries land on concept boundaries.** A section is one idea. That is what the
   capability layer will key off later — a chunk that straddles two concepts cannot be
   cleanly tagged with one capability.

Sections over 1200 characters are split on blank lines, packing whole paragraphs, so a
split never lands mid-sentence.

**Where:** `cognith_rag/chunker.py`.

**Revisit when:** source documents stop being well-structured markdown. The approach
depends on authors writing meaningful `##` headings; it degrades on scraped or
machine-generated text.

---

## D4 — `index.json` flat file, not a vector database

**Decision:** an in-memory numpy matrix persisted to a single JSON file, with brute-force
search.

**Why:** at 42 chunks a 42×768 dot product is instant, and the entire index is a readable
file you can open and inspect. Every stage of the pipeline stays debuggable by hand. A
vector DB at this scale would add infrastructure, a deployment dependency, and opacity in
exchange for performance that is not needed — which `Claude.md` §26.9 and §26.8 rule out.

The **manifest is the load-bearing part** of this decision. `Store.load()` refuses to load
an index whose `embed_model` or `dim` disagrees with `config.py`. Without that check,
changing the embedding model would silently compare vectors from two different spaces and
produce meaningless scores that still *look* like valid similarities. Per-file SHA256
hashes are also stored, so an index can be traced to the documents it was built from.

**Where:** `cognith_rag/store.py` (`Store.save` / `Store.load` / `Store.search`).

**Revisit when:** the corpus reaches a few thousand chunks, or the index needs to be shared
across processes. The docstring names Vertex Vector Search as the upgrade path, and
`Claude.md` §19 anticipates a `knowledge_chunks/` Firestore collection.

---

## D5 — `MIN_SCORE = 0.55`, calibrated from data, not guessed

**Decision:** set the Gate 1 similarity floor deliberately **low**, and accept that it
cannot separate covered from uncovered questions.

**Why:** this is the most important entry here, because the obvious approach does not work
and the evidence says so.

`python eval.py --calibrate` compares top-1 similarity scores for questions that must be
answered against questions that must be refused. The two classes **overlap**:

```
lowest in-corpus       0.616   "a user updated their profile but the change disappeared"
highest out-of-corpus  0.662   "what is the CAP theorem?"
margin                -0.046
```

"What is the CAP theorem?" scores **higher** than a legitimate in-corpus question.
`system-design.md` genuinely discusses consistency/availability trade-offs, so retrieval
surfaces genuinely relevant chunks — but discussing trade-offs is not covering a specific
named theorem.

The consequence: **no single threshold separates these classes.** Raising the floor to
0.66 to catch CAP theorem would begin refusing real questions. So the floor is set at 0.55,
just under the lowest in-corpus score, and its job is narrowed to cheap deterministic
rejection of the obviously unrelated — weather scores 0.489, "write me a linked list"
0.531.

**A similarity floor alone is not a grounding strategy.** That is the spike's finding, and
it is the direct reason D6 exists.

**Where:** `cognith_rag/config.py` (`MIN_SCORE`, with the calibration run recorded in
the comment), `eval.py` (`calibrate`).

**Revisit when:** the corpus changes materially. Re-run `python eval.py --calibrate` — the
distribution is corpus-dependent, so the number is only valid for the corpus it was
measured on. Do not adjust it by intuition; the whole point of the entry is that intuition
gets this wrong.

---

## D6 — Two *independent* abstention layers, plus a citation check

**Decision:** three gates, each able to refuse on its own, recorded in `Result.gate`.

**Why:** follows directly from D5. If the similarity floor cannot catch
plausible-but-uncovered questions, something else must, and it has to work on a different
signal.

| Gate | Where | Catches | `gate` value |
|---|---|---|---|
| 1. Similarity floor | before Gemini is called | clearly unrelated questions — deterministic, free | `score_floor` |
| 2. Grounding contract | inside the model | questions that retrieve plausible chunks but are not actually covered | `model` |
| 3. Citation check | after the model | fabricated excerpt ids — the model drifting off-corpus | `citation_check` |

The layers are independent by design: Gate 1 is a number, Gate 2 is a judgment, Gate 3 is
a set membership test. A failure mode that defeats one does not defeat the others. Gate 3
in particular catches something neither of the others can see — a cited id that was never
sent means the answer came from outside the supplied context, and only comparing ids
reveals it.

Gate 2's rule 3 in `prompts.py` is the load-bearing sentence: *"Partial overlap is not
coverage."* Gate 2 also returns `reasoning` on every outcome, which is what makes an
abstention debuggable rather than opaque.

`eval.py` reports abstentions broken down by gate specifically so it stays visible that
both layers carry weight. Last run: 4 abstentions from Gate 2, 2 from Gate 1 — neither is
decoration.

**Where:** `cognith_rag/generate.py` (`answer`), `cognith_rag/prompts.py`
(`SYSTEM_INSTRUCTION`).

**Revisit when:** `eval.py` shows one layer never firing across a representative question
set. Until then, removing either is a regression, not a simplification.

---

## D7 — API failure degrades to retrieval-only, never crashes

**Decision:** catch every exception from the generation call and return a `Result` with
`gate="api_error"`, carrying the retrieved excerpts and an honest note that the AI service
is unavailable.

**Why:** a failed AI call should not break the learning experience. The retrieved chunks
are still genuinely useful to a student on their own — the system falls back to being a
search tool rather than to being broken. It is a deliberate catch-all (`except Exception`,
with the lint suppression annotated), because the goal is that *no* generation failure
reaches the caller as a crash.

**Where:** `cognith_rag/generate.py` (`answer`), surfaced by `ask.py`.

**Revisit when:** distinguishing failure types becomes useful — a rate limit deserves a
retry, a malformed-response error does not. Today they are treated identically.

---

## D8 — Root scripts are a throwaway harness; `cognith_rag/` is the portable core

**Decision:** keep a hard line between the four CLI scripts at the repo root and the
`cognith_rag/` package.

**Why:** the package is the part intended to move into the Cloud Run backend
(`Claude.md` §18) — it has no CLI concerns, no printing, no argument parsing. The root
scripts exist to make each pipeline stage inspectable during development and are expected
to be discarded.

This is why `retrieve.py` exists separately from `ask.py`: it is how you tell a
*retrieval* failure from a *grounding* failure. If an answer is bad, `retrieve.py` shows
whether the right chunks were even found.

**Where:** stated in `cognith_rag/__init__.py`; enforced by the package importing
nothing from the root scripts.

**Revisit when:** never, ideally. When the HTTP layer arrives it should import
`cognith_rag` and leave the scripts alone. If backend code starts reaching into
`ask.py` or `eval.py`, the line has been crossed.

---

## Open questions

Not decisions yet — recorded so they get decided deliberately rather than by accident.

### Q1 — Capability ids vs knowledge tags (owner: Phase 1)

The `capability:` values in the knowledge frontmatter (`http-fundamentals`, `api-design`,
`database-reasoning`, `system-design`, `trade-off-analysis`) are **topics**. `Claude.md`
§6.1 says capabilities must be things a learner *can do*, and names bare topics as the
wrong model. They also do not match §7's capability tree.

They are reasonable *knowledge tags* — they just are not capabilities. Phase 1 chooses:

1. Rename the frontmatter to real capability ids — simpler, but collapses two vocabularies
   into one and requires a re-ingest.
2. Keep knowledge tags as their own vocabulary with an explicit
   `capability → knowledge tag` mapping — preserves the knowledge/capability separation
   §5 insists on, and touches no existing files.

See `architecture.md` §11.

### Q2 — No HTTP layer (owner: Phase 7, possibly earlier)

There is no API surface of any kind today. `Claude.md` §18 specifies a Cloud Run backend
and §21 Phase 7 connects RAG to capability gaps; both need `cognith_rag` exposed over
HTTP first. Deciding *when* this lands — and whether the capability layer is built against
a local import or an HTTP client — affects Phases 1–6.

### Q3 — Dangling prerequisite, and what `prerequisites` is for (owner: Phase 1)

`prerequisites` is authored into every knowledge document but **read by no code** — it
appears exactly once in the codebase, being copied into `Chunk.metadata`
(`chunker.py:112`). Nothing consumes it.

Because nothing validates it, one reference is dangling: `database-indexing.md` declares
`prerequisites: [how-databases-store-data]` and no such document exists. The other seven
references all resolve.

This matters at Phase 1 because these prerequisite edges are the closest thing the corpus
already has to §7's capability relationships (`HTTP → prerequisite_for → API Design`).
Whoever starts reading them must decide:

* Is a dangling target an error to fix, or a placeholder for an unwritten document?
* Are document prerequisites the same thing as capability prerequisites, or a separate
  knowledge-level graph that happens to look similar?

Related to Q1 — both are about whether the knowledge corpus and the capability graph share
one vocabulary or two. See `architecture.md` §4.

---

## D9 — The knowledge join is on document ids, not the corpus's `capability:` tags

**Phase 1.** Resolves Q1.

**Decision:** each `Capability` carries `knowledge_docs` — a list of `id:` values from
`knowledge/*.md` frontmatter. The corpus keeps its `capability:` tags as its own
vocabulary; the capability graph does not reuse them.

**Why:** two reasons, and the second only emerged from testing.

First, Claude.md §5 keeps knowledge and capability as separate concepts, and §6.1 requires
capabilities to be "can do" statements. The corpus tags (`http-fundamentals`, `api-design`,
`database-reasoning`, `system-design`, `trade-off-analysis`) are topics. Reusing them as
capability ids would collapse two vocabularies into one and require re-ingesting the corpus.

Second — and this is what settled it — **the tags are too coarse to join on.** The first
implementation did map capabilities to tags, and the coverage report immediately showed the
Caching capability resolving to `load-balancing.md`, because one `system-design` tag is
shared by `caching.md`, `load-balancing.md` and `system-design.md`. No tag-level mapping
can distinguish Caching from Load Balancing. Document ids are 1:1 with files and precise.

**Consequence for Phase 7:** the existing `Store.search(capability=...)` filter is **not**
the join. It filters on the coarse tags. Phase 7 needs document-level filtering, which
`store.py` does not currently expose.

**Where:** `data/capabilities.yaml` (`knowledge_docs` per capability),
`cognith_capability/models.py` (`Capability.knowledge_docs`),
`capabilities.py --coverage` (validates every reference against the real corpus).

**Revisit when:** the corpus grows enough that per-document mapping becomes tedious to
maintain. The alternative is a finer tag vocabulary — but that means re-tagging
`knowledge/*.md`, which Phase 1 deliberately did not touch.

---

## D10 — Hierarchy is a field; only semantic relationships are edges

**Phase 1.**

**Decision:** `Capability.area` stores the §7 tree position as a string. Parent/child is
not represented as `CapabilityEdge` rows. Areas themselves get no capability row.

**Why:** §6.1 — "Backend" is not something a learner can do, so it should not be a
capability. And §7 says the hierarchy "alone is not the main point"; the semantic
relationships are. Storing hierarchy both as a field and as edges would let the two drift
apart, with no obvious winner when they disagree.

The cost is that System Design has to exist as both an area and a capability, because §7's
own edge examples and §9's capability map both treat it as assessable. That is a wrinkle in
the source material, not in this model.

**Where:** `data/capabilities.yaml` (`areas:` map plus `area:` per capability),
`cognith_capability/graph.py` (`tree()`, `by_area()`).

**Revisit when:** the tree needs more than two levels, or a capability needs to belong to
more than one area.

---

## D11 — Relation semantics in code, relation instances in data

**Phase 1.**

**Decision:** `RelationType` is a closed four-member enum with its meanings in
`RELATION_SEMANTICS`. The edges themselves live entirely in YAML. Propagation weights are
**not** defined.

**Why:** §7 requires relationships as data, but an engine still has to know that a missing
prerequisite blocks assessment while a missing contributor does not — that is logic. The
line drawn here: *which* capabilities relate is data; *what a relation means* is code.

Propagation weight (how much evidence for Caching should raise the Scalability estimate) is
excluded on purpose. It is an assessment policy, and §26.3 says keep AI and engine
responsibilities explicit. Phase 6 owns it. Putting a number in Phase 1 would bury
assessment logic in the capability layer.

Only `prerequisite_for` is required to be acyclic; it is the only type implying an order.
`applies_to` cycles are legal and the validator permits them.

**Where:** `cognith_capability/models.py` (`RelationType`, `RELATION_SEMANTICS`,
`ACYCLIC_RELATIONS`).

**Revisit when:** a phase needs a fifth relation type. Adding one means defining its
semantics and deciding whether it must stay acyclic.

---

## D12 — `mastery` is nullable; `None` means never demonstrated, not zero

**Phase 2.** The most important decision in the phase.

**Decision:** `StudentCapability.mastery` is `float | None`, defaulting to `None`. It is
`None` for every capability until evidence exists, and it is paired with the invariant
`mastery is not None` ⟺ `evidence_count > 0`.

**Why:** Claude.md §6.2's example JSON shows `"mastery": 0.35`, which invites a `0.0`
default. That would make two opposite states identical:

```
mastery = 0.0     "we have no evidence about this"
mastery = 0.0     "we have evidence, and they cannot do it"
```

The first is ignorance, the second is a finding. §6.2's whole point is "do not treat
self-reported confidence as proof of mastery" — and a `0.0` default breaks that from the
other direction: it lets an unverified capability be read as a *measured* zero. A student
who rated themselves 0.8 would then appear to have been checked and found wanting, when in
fact nothing was ever checked.

The nullability is what makes §9's framing implementable: an onboarding profile has every
`confidence` set and every `mastery` `None`, which is literally "this is an initial
estimate. Let's verify it."

**Where:** `cognith_student/models.py` (`StudentCapability`, the two biconditional
invariants in `__post_init__`, `MasteryStatus.CLAIMED` vs `DEVELOPING`).

**Revisit when:** never, ideally. If a later phase wants a prior or a default estimate, it
belongs in a separate field (`prior_mastery`) so that "what we assumed" stays
distinguishable from "what we showed".

---

## D13 — `status` is derived, not stored

**Phase 2.**

**Decision:** `StudentCapability.status` is a computed property over `mastery`,
`confidence` and `DEMONSTRATED_AT`. It is written into the §19 record shape but recomputed
on every read and never trusted from storage.

**Why:** §6.2 lists `status` as a field, but a stored status can contradict the numbers
next to it — `status: "demonstrated"` beside `evidenceCount: 0` — and there is then no
principled answer to which one is correct. Deriving it means the inconsistency cannot be
represented at all.

It is still serialized because a Firestore query cannot call a Python property, and Phase 4
will want to filter by status without loading every row. That is denormalization for
queryability, with the source of truth unambiguous.

`DEMONSTRATED_AT = 0.70` is a **presentation threshold, not an assessment policy**, kept as
a single named constant. Phase 6 owns the real policy and may want a per-capability bar.

**Where:** `cognith_student/models.py` (`MasteryStatus`, `StudentCapability.status`,
`DEMONSTRATED_AT`).

**Revisit when:** Phase 6 defines per-capability thresholds. At that point `status` should
take the graph into account, which means moving it to the profile or passing a threshold in.

---

## D14 — `cognith_student` is a separate package with a one-way dependency

**Phase 2.**

**Decision:** three packages, and the import arrows only ever point one way:

```
cognith_student  ->  cognith_capability  ->  (nothing)
cognith_rag      ->  (nothing)
```

`cognith_student` imports the graph because it needs it — to reject rows for
capabilities that do not exist, and to answer `blocked()`. Neither of the other two
packages imports it.

**Why:** §25 requires the layers to stay separate, and an import graph is the only
enforcement that cannot rot. The alternative — putting `StudentCapability` inside
`cognith_capability` — would have been fewer files, but Phase 3 adds substantial Student
material (goal, technologies, experience, background per §8) that has nothing to do with
the capability graph, and it would then need extracting under pressure.

The one cross-layer import to `cognith_rag` in the whole project is in
`capabilities.py --coverage`, deliberately placed in the **harness** rather than in a
package, reusing `parse_frontmatter` instead of duplicating it.

**Where:** package layout; verified by grepping for cross-imports.

**Revisit when:** a fourth layer needs the student state. The arrow direction is the part
to preserve — capability and knowledge must never import student state.

---

## D15 — Onboarding is fully deterministic; no Gemini call

**Phase 3.**

**Decision:** §8's intake is turned into §9's capability map by a data-driven table plus
one-hop propagation over the Phase 1 graph. No LLM is involved. The free-text answers are
used via deterministic phrase matching, not inference.

**Why:** four reasons, in order of weight.

1. **§26.4 — do not hide important logic inside prompts.** "Laravel implies API Design at
   0.75" is domain knowledge, exactly like a capability edge. It belongs in
   `data/onboarding.yaml` where it can be reviewed and disagreed with, not inside a prompt
   string where it is invisible.
2. **§26.7 — preserve provenance.** This number is shown to the student and they are asked
   to confirm it. "Databases 80% because you listed MySQL" is defensible; "Gemini thought
   so" is not. The engine records every signal it considered, not just the winner.
3. **The output is a claim, not a finding.** §9 frames the map as "an initial estimate
   based on what you've told us", and Phase 5 exists to test it. Inferring past what the
   student actually said makes it less clear what they said — which defeats the purpose of
   asking.
4. **Free to test.** No key, no quota, no network, and `--verify` can run in CI.

This is a change from the plan stated at the end of Phase 2, which proposed using Gemini
for the free-text fields. Designing it made the case against clear: phrase matching against
the same vocabulary covers the realistic inputs and stays auditable.

**Where:** `data/onboarding.yaml`, `cognith_student/onboarding.py`.

**Revisit when:** real intake answers contain material the phrase table demonstrably
misses. The extension point is deliberate — `Signal.kind` already distinguishes
`technology` / `phrase` / `derived`, so an LLM extraction layer can emit `kind="inferred"`
and remain separately attributable, auditable and switchable. It must not replace the
deterministic layer, only add to it.

---

## D16 — Signals combine by `max`, and derived signals never chain

**Phase 3.** Two rules, one purpose: not manufacturing confidence.

**Decision:** where several signals point at one capability, take the **maximum**, not the
sum or a weighted blend. And **derived signals propagate only from direct signals**, never
from other derived signals.

**Why:**

*Max over sum.* §8's example produces four signals for System Design (0.52, 0.50, 0.47,
0.24). Summing gives 1.73, clipped to 1.0 — "you are certainly an expert" out of three weak
hints. Max also keeps exactly one **nameable** reason behind every number, which is what
makes `--explain` possible. A blended score has no explanation, only a formula.

*No chaining.* Without this rule, `Docker → system-design → reliability → testing` would
produce a testing estimate from a student who never mentioned testing. Each hop is a
weakening inference; composing them multiplies the error while the number stays
superficially plausible.

Verified: `trade-off-analysis` = 0.40, derived from System Design's **direct** 0.50 × 0.80,
not from its **derived** 0.525 which would have given 0.42.

**Where:** `cognith_student/onboarding.py` (`estimate`, `_derived_signals`).

**Revisit when:** a noisy-or combination (`1 - Π(1 - sᵢ)`) becomes worth the loss of
explainability. It would give principled diminishing returns, but no single signal could
then be named as the reason.

---

## D17 — Propagation discounts are asymmetric by direction

**Phase 3.**

**Decision:** each relation type has separate forward and backward discounts, and
`prerequisite_for` has **no forward discount at all**.

| Relation | forward | backward |
|---|---|---|
| `prerequisite_for` | — | 0.90 |
| `contributes_to` | 0.70 | 0.60 |
| `supports` | 0.50 | 0.55 |
| `applies_to` | 0.50 | 0.80 |

**Why:** the asymmetry is real, not a tuning artefact. If a student can design APIs, they
necessarily know HTTP — that inference is strong. The reverse is worthless: knowing HTTP
says nothing about whether someone can design an API, which is the entire reason HTTP is a
*prerequisite* rather than a component. Giving it a small forward value would still let a
long prerequisite chain accumulate unearned confidence, so it is **omitted** rather than
set near zero.

`applies_to` is the mirror case: a cross-cutting capability like Trade-off Analysis is
exercised *inside* other capabilities, so evidence about the container says a lot about the
cross-cutting skill (0.80 backward) and less the other way (0.50).

This is where Phase 1's decision to keep relation *semantics* in code (D11) pays off — the
discounts are only meaningful because each relation type has a defined direction and
meaning.

**Where:** `data/onboarding.yaml` (`rules.propagation`), consumed by
`OnboardingEngine._derived_signals`.

**Revisit when:** real diagnostic results (Phase 5) show a systematic bias — e.g. derived
estimates consistently overshooting measured mastery for one relation type. At that point
these numbers become empirically checkable rather than authored, which is the right way to
settle them.

---

## D18 — The capability map distinguishes claim from evidence structurally, not columnar

**Phase 4.**

**Decision:** one bar per capability, drawn in two materials on a single axis — solid for
demonstrated mastery, shade for the unverified remainder of the claim, dots for nothing.

**Why:** §21 Phase 4 says to "clearly distinguish self-reported vs demonstrated", and two
number columns satisfies that literally. It is not enough. A reader has to notice a dash in
the second column and infer what it means; the distinction is legible rather than obvious,
and this is the single most important idea in the product.

Drawn as two materials, a profile straight out of onboarding contains **no solid blocks at
all**. The reader learns their map is unproven before reading a number, which is exactly
what §9 asks the UI to communicate.

The encoding also handles the awkward cases without special-casing: an over-claim is a wide
band of shade rather than a subtraction the reader performs, and a student who *undersold*
themselves gets solid running past where the shade would have ended, which reads correctly
as a good outcome.

**Where:** `cognith_student/capability_map.py` (`bar`, `label_for`,
`render_verified_share`).

**Revisit when:** a real UI replaces the terminal. The renderer returns strings but the
encoding is the part worth keeping — solid/shade translates directly to a stacked bar in
any frontend.

---

## D19 — One renderer, and display code may be consolidated into the phase that owns display

**Phase 4.**

**Decision:** `capability_map.py` is the only place a profile is drawn. `students.py` and
`onboard.py` were edited to call it; `onboard.py`'s own `bar()` was deleted and its `pct()`
now imports from the renderer.

**Why:** Phases 2 and 3 each shipped a renderer, and the two were already diverging while
both encoded §9's distinction. Two implementations of the most important idea in the
product is a defect, not a duplication nit.

This is the first phase to edit files from earlier phases. That is deliberate and bounded:
**display is precisely what Phase 4 owns**, so consolidating display is in scope rather
than the unrelated refactoring §26.10 forbids. No data-layer file was touched, and
`onboard.py --verify` still passes §9 conformance at an unchanged 0.025 deviation — which
is the evidence that the change was presentational.

The numeric table survives as `students.py --table`; it carries evidence counts the bar
does not, so it is a different view rather than a superseded one.

**Where:** `cognith_student/capability_map.py`, called from `students.py` and
`onboard.py`.

**Revisit when:** a second output format is needed (HTML, JSON for a frontend). The
functions return strings today; that is the seam to change, not the callers.

---

## D20 — `database-performance` is its own capability

**Phase 5.** Resolves the open question Phase 1 recorded (see `capability-model.md` §8).

**Decision:** add `database-performance` as a seventeenth capability rather than treating
it as a facet of `databases`.

**Why:** §10's diagnostic example names it as a target and §7's tree does not contain it,
so a decision was unavoidable. The two are separately assessable: `databases` is modelling
and querying — "can you design a schema and write correct queries" — while
`database-performance` is behaviour under load: indexes, execution plans, read/write split,
and knowing which of those the evidence actually points at. A student can be solid at the
first and helpless at the second, which is precisely the case §12's flagship mission is
built around.

It also gives `database-indexing.md` a capability to attach to; previously the corpus's
strongest document mapped only to the broad `databases`.

Adding it disturbed nothing: `capabilities.py --validate` passes at 17/25, and
`onboard.py --verify` still matches §9 at the same 0.025 deviation.

**Where:** `data/capabilities.yaml` (capability + 4 edges), `data/onboarding.yaml`
(signals from MySQL/Postgres and the `indexing` phrase).

**Revisit when:** the same argument recurs for another pair. The test applied here — *can
a student plausibly be strong at one and weak at the other?* — is the one to reuse.

---

## D21 — Selection scores are transparent and prerequisite-gated

**Phase 5.**

**Decision:** six named factors with weights in data, every contribution recorded on the
`Candidate` and persisted with the session. Capabilities whose own prerequisites are
unproven are **scaled by 0.55**, not excluded.

**Why:** §10 asks the diagnostic to identify "important or uncertain" capabilities, which
is a judgement with several inputs. Collapsing it into one opaque number would repeat the
mistake §11 forbids for assessment — a score with no explanation. A student asking "why am
I being asked this?" deserves an answer, and so does whoever tunes the weights later.

Scaling rather than excluding matters for the common case: a freshly onboarded student has
**nothing** proven, so every capability has unproven prerequisites. Excluding them would
produce an empty diagnostic for exactly the student who most needs one. Scaling instead
lets foundations rise naturally to the top, which produces the right pedagogical order
without a special rule:

```
round 1 (nothing proven)   ->  HTTP, Databases, Trade-off Analysis
round 2 (HTTP + DB proven) ->  Authentication, Caching, Database Performance
round 3 (backend proven)   ->  Caching, Database Performance, Scalability
```

**Where:** `cognith_student/diagnostic.py` (`score`, `Candidate.factors`),
`data/diagnostics.yaml` (`selection.weights`, `unready_penalty`).

**Revisit when:** real diagnostic outcomes exist. These weights are authored judgement; once
Phase 6 produces measured mastery, they become empirically checkable — does a
high-`uncertainty` pick actually change the profile more than a low one?

**Not done deliberately:** the weights were **not** tuned to reproduce §10's example list
exactly. Under §10's premise the engine picks Caching, Database Performance and Scalability
where §10 lists Scalability, Trade-off Analysis and Database Performance; Trade-off
Analysis ranks fourth and is exercised as a secondary capability, so all three are covered.
Fitting six weights to one worked example would look principled and be arbitrary.

---

## D22 — Diagnostic scenarios are authored, not model-generated

**Phase 5.**

**Decision:** the 12 scenarios live in `data/diagnostics.yaml`. Gemini is not called.

**Why:** this was the first genuine opening for a model — §10's diagnostic is prose, and
generating scenarios is the obvious use. It was declined for one specific, non-ideological
reason: **§11 requires structured rubrics, Phase 6 authors them, and a scenario generated
independently of its rubric cannot be scored against one.** A generated question is
unscoreable, and an unscoreable question produces no evidence, which is the entire point of
the diagnostic.

`probes` is the bridge that makes the authored bank work: each scenario names the reasoning
dimensions it is meant to expose (§10's decomposition / reasoning / decision / trade-offs /
application), and Phase 6's rubric criteria will be written against those same dimensions.

Secondary reasons: scenario quality is the product's content, and a hackathon demo needs it
to be reliable rather than freshly sampled.

**Where:** `data/diagnostics.yaml`, `cognith_student/diagnostic.py` (`DiagnosticItem`).

**Revisit when:** rubric and scenario can be generated **together** as one artefact and
reviewed before use. Generating a scenario alone is the thing to avoid; generating a
scenario plus its criteria, then having a human accept it into the bank, is a reasonable
authoring tool. That is a content pipeline, not a runtime behaviour.

---

## D23 — Gemini judges criteria; it never produces a score

**Phase 6.** The decision §11 exists to force.

**Decision:** the model is given the scenario, the response, and the rubric criteria, and
returns one verdict per criterion (`met` / `partial` / `unmet`) with a justification. It is
NOT given the student's profile, their claimed confidence, their mastery, or any other
criterion's outcome. Capability scores, the mastery update and the explanation are all
computed by us.

**Why:** §11 says "Do NOT simply ask Gemini: 'How good is this student?'" and "Do not create
a single opaque AI score as the student's identity." Prompt discipline alone would not
achieve that — a model given a profile and a response will anchor on the profile. So the
constraint is structural: there is nothing in the model's context to anchor on, and no
field in the response schema that could carry an overall verdict.

**The test applied:** `ManualEvaluator` takes human judgements and produces identical
downstream structures. If the model were removed the system still works; it just needs a
person to judge criteria. An AI doing a bounded job can be swapped for a human doing the
same bounded job — an AI holding the system up cannot. That swap-test is the check to
re-apply whenever a later phase wants to add a model call.

**Verified live.** On a deliberately weak response, Gemini's six judgements matched six
hand-written `ManualEvaluator` judgements exactly, and every justification quoted the
response. On a strong response it scored all six `met`, with quotes. The rubric
discriminates and the justifications are checkable.

**Where:** `cognith_student/evidence.py` (`GeminiEvaluator`, `SYSTEM_INSTRUCTION`,
`ManualEvaluator`, `score_criteria`, `next_mastery`, `explain`).

**Revisit when:** never for the boundary. The prompt and the schema will change; what must
not change is that the model's output is a judgement per criterion and the arithmetic is
ours.

---

## D24 — Mastery is capped by how much evidence supports it

**Phase 6.** Found by testing, not designed.

**Decision:** `mastery_new = min(blended, 0.55 + 0.15 × n)`, where `n` is the evidence
count including the new observation.

**Why:** the first live Gemini run on a strong response scored all six criteria `met`, and
mastery came out at **100%** — because with no prior evidence the single observation stood
alone. One scenario cannot establish mastery of a capability, and §6.2 says so directly:
"Do NOT treat mastery as an absolute truth."

The chosen constants give a property worth having: **one piece of evidence tops out at
0.70, which is exactly `DEMONSTRATED_AT`.** A flawless first answer earns "demonstrated"
and nothing beyond it. Two reach 0.85; three remove the cap.

It only ever caps. A weak answer scoring 0.12 stays at 0.12 no matter how often repeated —
the ceiling cannot lift anyone, only stop thin evidence claiming more than it supports.

Paired with `EVIDENCE_WEIGHT_FLOOR = 0.35`, which keeps a new observation carrying at least
35% of the update however much history exists. A plain running mean would let old evidence
outvote what a student just demonstrated, which is wrong for a platform whose entire
premise is that people improve.

**Where:** `cognith_student/evidence.py` (`mastery_ceiling`, `next_mastery`,
`EVIDENCE_CEILING_BASE`, `EVIDENCE_CEILING_STEP`, `EVIDENCE_WEIGHT_FLOOR`).

**Revisit when:** there is real data on how many diagnostics it takes before a mastery
estimate stops moving. These constants are authored judgement standing in for a
measurement that does not exist yet; the evidence log makes that measurement possible later.

---

## D25 — Rubrics are authored inside their scenario, and each criterion names a capability

**Phase 6.**

**Decision:** the 62 criteria live in `data/diagnostics.yaml` under their `items:` entry,
not in a separate rubric file. Each criterion carries a `capability` and a `weight`.

**Why:** two things.

*Not a separate file.* A criterion like "identifies the database as a likely constraint" is
meaningless apart from the scenario that sets up the constraint. Splitting them invites the
exact drift D22 was written to prevent — a question and its rubric are one artefact.
Validation now refuses a scenario with no rubric: an unscoreable question produces no
evidence, which defeats the diagnostic.

*Criterion-level capability tags.* §11's rubric example is keyed by capability. Tagging each
criterion instead reaches the same place from the other direction and does more: one
10-minute answer produces evidence for three capabilities at once, which is what
`also_exercises` promised in Phase 5 and never cashed in. Across the bank Trade-off Analysis
picks up 12 criteria spread over 8 scenarios — what a genuinely cross-cutting capability
should look like.

**Where:** `data/diagnostics.yaml`, `cognith_student/diagnostic.py` (`RubricCriterion`,
`DiagnosticEngine._validate`), `cognith_student/evidence.py` (`score_criteria`).

**Revisit when:** the same criterion is wanted across many scenarios. A shared criterion
library referenced by id would help then; it is not worth the indirection for 62.

---

## D26 — The capability graph is the only prerequisite graph. Resolves Q3.

**Phase 7.**

**Decision:** the corpus's `prerequisites:` frontmatter stays **inert**. Capability
prerequisites in `data/capabilities.yaml` are the single source of truth, and Phase 7 uses
those to warn when a student is being taught something whose foundations they cannot
demonstrate.

**Why:** Q3 recorded that `prerequisites` is authored in every knowledge document, read by
no code, and contains one dangling reference (`how-databases-store-data`, which does not
exist). Phase 7 was the phase that would either use it or leave it permanently ornamental.

Using it would mean maintaining **two prerequisite graphs** — one over documents, one over
capabilities — with no rule for what happens when they disagree. That is exactly the drift
D10 avoided by refusing to store the capability hierarchy both as a field and as edges. And
the capability graph is the better of the two: it is validated, acyclic, and expresses
what actually matters pedagogically. "Databases comes before Database Performance" is a
statement about capability, not about which markdown file to read first.

So `GapResolver.knowledge_for` calls `graph.prerequisites_of()` and reports unproven ones:

```
NOTE — prerequisites not yet demonstrated: Databases
The capability graph says these come first. Working on this capability before them is
likely to be the wrong use of the student's time.
```

**Not done:** the frontmatter field is not removed. `knowledge/*.md` has not been edited in
any phase, and deleting authored metadata to tidy up is not worth breaking that. The
dangling reference is harmless precisely because nothing reads it — which is the point.

**Where:** `cognith_learning/knowledge.py` (`knowledge_for`), `data/capabilities.yaml`.

**Revisit when:** someone proposes reading document prerequisites. The question to ask is
what happens when the two graphs disagree; if there is no good answer, there should not be
two graphs.

---

## D27 — The retrieval query and the learner's question are different strings

**Phase 7.** Found by testing.

**Decision:** a gap produces two strings.

```
build_query(gap)     capability statement + unmet rubric criteria   -> embedded, steers retrieval
build_question(gap)  "How do I <capability statement>?"             -> put to the generator
```

**Why:** the first implementation used one string for both, and it failed in an instructive
way. Retrieval was excellent — for a Database Performance gap it surfaced the query-plan
section, the missing-index section and a diagnosis exercise. Then the generator abstained:

```
[ABSTAINED]  gate=model
Why: The excerpts do not contain information regarding database constraints related to
     connections, CPU, or contention.
```

The grounding contract was **right**. The criterion said "identifies the database as a
likely constraint and gives a reason (connections, CPU, contention)", the corpus never
discusses connections or contention, and rule 3 of the contract says adjacent coverage is
not coverage.

The error was mine: **a rubric criterion is assessment language.** It describes what a good
*answer* does — it is written to be judged against, not to be answered. A learner needs a
question. Conflating the two made the knowledge layer refuse to teach material it was
holding.

Split, the same retrieval now produces a grounded explanation citing four of five excerpts.
The criteria were good at finding material and bad at being a question; they now only do
the first.

**Where:** `cognith_learning/knowledge.py` (`build_query`, `build_question`).

**Revisit when:** the question should carry focus. It is tempting to append "in particular,
focus on X" from the unmet criteria — that reintroduces the exact failure above, because
the grounding contract will hold the explanation to X. If focus is wanted, it belongs in
how the explanation is *presented*, not in what the generator is asked to cover.

---

## D28 — RAG gained one search filter and nothing else

**Phase 7.**

**Decision:** `Store.search` takes `docs: list[str] | None`, filtering on `Chunk.doc`. No
other file in `cognith_rag/` was modified.

**Why:** §21 Phase 7 says "Do not redesign the RAG unnecessarily", and the join needed
document-level filtering that did not exist — the `capability` filter joins on the corpus's
coarse tags, which D9 established cannot distinguish Caching from Load Balancing.

Two alternatives were rejected:

*Post-filter a global top-k.* Simpler, and wrong: the chunks a capability needs are dropped
whenever something louder outranks them corpus-wide. Filtering must happen before the
top-k, which means inside `search`.

*Re-tag the corpus to finer `capability:` values.* That means editing `knowledge/*.md` and
re-running ingestion, to reach a place document ids already occupy.

The change is three lines following the masking pattern already present, plus a docstring.
The chunker, embeddings, prompts and all three abstention gates are untouched, and
`retrieve.py` with its existing filters still behaves identically.

**Where:** `cognith_rag/store.py`.

**Revisit when:** the corpus outgrows a linear scan. The filter is `O(n)` over chunks like
every other; at 42 chunks that is free, and the docstring in `store.py` already names
Vertex Vector Search as the upgrade path.

---

## D29 — Three experience types, and explanation produces no evidence

**Phase 8.**

**Decision:** `explanation`, `exercise`, `diagnostic`, plus `mission` declared for Phase 9.
Not the nine types §6.3 lists. And an explanation carries no rubric, so it produces no
evidence.

**Why the three:** §21 Phase 8 asks for "the minimum experience types required for the MVP"
and §22 lists "Full LMS" as a non-goal. §16's progression — explain, example, small
practice, guided challenge, independent challenge, realistic mission — is covered by these.
The other six names (quiz, coding challenge, case study, project, reflection, interactive
example) would each be an experience with a prompt and a rubric, which is what `exercise`
already is. Adding them would add vocabulary, not behaviour.

**Why explanation produces nothing:** §6.5 defines evidence as observable proof, and there
is nothing to observe in having read something. This is §4's distinction between Cognith
and a content platform: content completion is not capability. The UI says so rather than
leaving it implied — "Reading an explanation produces no evidence. Answering one of these
does."

`exercise` and `diagnostic` are identical in form and differ in **intent**: a diagnostic is
chosen to resolve uncertainty, an exercise to close a known gap. Same assessment code.

**Where:** `cognith_learning/experience.py` (`ExperienceType`, `LearningExperience`).

**Revisit when:** a type needs behaviour the others do not have. A coding challenge that
runs tests would qualify — that is a different evaluator, not a different label.

---

## D30 — `Assessable` is a Protocol, so exercises became assessable without touching assessment

**Phase 8.**

**Decision:** `LearningExperience` carries `id`, `capability_id`, `prompt`, `rubric` — the
same shape as `DiagnosticItem` — and `cognith_student/evidence.py` types `assess()`
against a `Protocol` rather than a concrete class.

**Why:** the seven corpus exercises had been visible since Phase 7 and impossible to do.
Making them assessable could have meant a parallel exercise-assessment path, a base class
both inherit, or an adapter. All three would have put knowledge of exercises inside
`cognith_student`, which has no business knowing the corpus has exercises in it.

A Protocol costs nothing and keeps the arrow straight: `cognith_learning` knows about
assessment, `cognith_student` does not know about experiences. Phase 9's mission will
satisfy the same Protocol and require no further change.

The measure of whether this was the right shape: **making seven exercises assessable
changed one type hint.**

**Where:** `cognith_student/evidence.py` (`Assessable`),
`cognith_learning/experience.py` (`LearningExperience`).

**Revisit when:** an experience needs assessing by something other than a rubric — a coding
challenge scored by running tests. That is a second `Evaluator`, which the Protocol already
allows, not a change to this one.

---

## D31 — Exercise prose stays in the corpus; the rubric file references it by chunk id

**Phase 8.**

**Decision:** `data/exercises.yaml` holds rubrics keyed by chunk id. The prompt is read
from the index at load time, never copied.

**Why:** the exercises are already written, in `knowledge/*.md`, tagged `kind: exercise`,
and they are good. Copying the prose into the rubric file would create two versions, and an
edit to the markdown would silently stop matching its rubric — the drift D25 avoided by
keeping diagnostic rubrics inside their scenario. Here the two must live apart, because
`knowledge/*.md` has not been edited in any phase and should not start now. So the chunk id
is the join, and the loader **verifies it resolves**, refusing to construct otherwise.

The entry also restates `capabilities` explicitly, because the corpus's `capability:`
frontmatter is too coarse to reuse (D9) — the caching exercise is tagged `system-design`,
which spans three documents.

**Where:** `data/exercises.yaml`, `cognith_learning/experience.py`
(`ExperienceLibrary._exercises`).

**Revisit when:** exercises stop being corpus sections. If they get authored directly as
experiences, the indirection is pure cost.

---

## D32 — The mission simulation is arithmetic; the model never touches it

**Phase 9.** §13's requirement, made structural.

**Decision:** `MissionEngine.evaluate()` computes every consequence from parameters in
`data/missions.yaml`. Each action declares its own effects and its own **authored**
consequence text. No model call exists anywhere in `cognith_learning/mission.py`.

**Why:** §13 says not to let Gemini decide consequences. The reasons are practical, not
ideological.

*Consistency.* Two learners making the same decision must see the same result, or the
mission is not a system to reason about — it is a story being improvised around them.

*Explainability.* `--explain` prints the arithmetic: `latency = 40ms + 115ms / (1 − 0.24)`.
A learner who is told their latency is 190ms and cannot see why has learned nothing
transferable. A simulation whose consequences cannot be explained teaches the wrong lesson.

*Calibration.* Because it is deterministic, `--calibrate` can assert that §12's starting
state comes out exactly and that every single-lever strategy fails. That check would be
meaningless against a generative model.

`evaluate()` is one function rather than six helpers, deliberately. §13 asks for mechanics
*controlled* by application logic, and logic assembled from six places is merely located,
not controlled.

**Where:** `cognith_learning/mission.py`, `data/missions.yaml`.

**Revisit when:** a mission needs a consequence that genuinely cannot be tabulated. Even
then the model should produce *prose describing* a state the rules computed, never the
state itself.

---

## D33 — A mission is one experience assessed over its transcript

**Phase 9.**

**Decision:** a mission is a single `LearningExperience(type=MISSION)` whose prompt is the
brief and whose response is the whole session transcript — every investigation, every
decision, the reasoning given, and the consequence that followed. One rubric, one
assessment, at the end.

**Why:** §6.5's evidence example shows a single decision with its reasoning, which suggests
one evidence record per decision. Rejected for three reasons.

*The capability under test is the shape of the plan.* §12 asks whether a learner can design
a system meeting stated constraints. No individual step demonstrates that; the sequence
does. Scoring "added a cache" in isolation cannot distinguish a considered decision from a
lucky one.

*Cost.* A rubric and a model call per decision, for a worse signal.

*The transcript already preserves what §6.5 wants.* Decision and reasoning are recorded
verbatim per step. Nothing is lost by assessing them together.

Because `LearningExperience` satisfies the `Assessable` protocol (D30), **Phase 9 required
no change to the assessment layer at all.** That is the second time that Protocol has paid
for itself.

**Verified:** on a session that met all three requirements, the assessment still marked
three criteria short — including reading the *order* of decisions ("still prioritized
scaling the application tier before addressing the database"), which only the transcript
reveals and a final-state check would have missed.

**Where:** `cognith_learning/mission.py` (`build_transcript_text` in `mission.py`),
`cognith_learning/experience.py` (`_missions`).

**Revisit when:** a mission gets long enough that one rubric cannot cover it. The split
should then be by phase of the mission, not by individual decision.

---

## D34 — Investigation is free, and recorded

**Phase 9.**

**Decision:** the four investigations cost nothing, change no state, and are written into
the transcript. The first rubric criterion asks whether the learner investigated before
changing anything.

**Why:** §23 describes the demo as the student *investigating* and then deciding, and §10
wants diagnostics that test reasoning rather than recall. Whether someone looked before
acting is one of the clearest available signals of that, and it is invisible in the final
architecture — two learners can arrive at the identical system, one by diagnosis and one by
applying every lever until it worked.

Charging for investigation would be the obvious "realistic" touch and would teach the wrong
habit: guessing is already cheaper than measuring in most engineering cultures, and this
mission should not reinforce that.

**Verified:** the assessment credited a learner specifically for having "ran two explicit
investigations into request profiles and database latency before making any architectural
decisions", and separately noticed that a cache-invalidation concern "only appeared in the
system-generated result text" rather than in the learner's own reasoning — refusing to
credit the student for something the simulation said. The transcript's separation of
`REASONING:` from `RESULT:` is what makes that distinction possible.

**Where:** `data/missions.yaml` (`investigations`), `mission.py` (`--investigate`,
`build_transcript_text`).

**Revisit when:** investigation becomes a way to stall. A time budget would be the lever,
not a cost.

---

## D35 — The loop never recommends what cannot be delivered

**Phase 10.**

**Decision:** every recommendation is filtered to something that exists — an authored
experience, or corpus material. Capabilities that would be worth working on but have
neither are reported in a separate **content backlog**.

**Why:** the same five capabilities — Programming Fundamentals, Data Structures,
Algorithms, Testing, Git — have appeared in three independent coverage reports across
Phases 5, 7 and 8. A loop that ranked purely on learner need would put them near the top
for a beginner and then have nothing to offer.

The alternative of silently skipping them is worse than either recommending or reporting:
a capability that never appears, with no explanation, looks like a scoring bug. Naming it
as a **content** problem is accurate — the learner is not at fault and neither is the
engine, someone simply has not written the material.

This mirrors the same instinct as the RAG layer's abstention (architecture.md §7): when the
system cannot help, it says so rather than producing something hollow.

**Where:** `cognith_learning/loop.py` (`_can_teach`, `_can_practise`, `_can_diagnose`,
`LoopState.backlog`), `cognith.py --backlog`.

**Revisit when:** the backlog is empty. Until then it doubles as the content team's queue.

---

## D36 — The flagship mission is gated by graph-derived prerequisites, and holds a reserved slot

**Phase 10.** Both halves were found by running the loop, not by designing it.

**Decision:** a mission is offered only when the prerequisites of its capabilities are
**demonstrated**, and those prerequisites are computed from the capability graph rather
than listed. When it is earned it takes the final slot of the plan.

**Why gated:** §16 — an advanced learner starts later in the progression, a beginner
earlier, same engine. Putting someone into a mission whose foundations are claimed rather
than shown tests the foundations by accident and teaches nothing about the mission.

**Why derived:** `prerequisites_of` over the mission's six capabilities yields Databases
and HTTP. The first implementation hardcoded exactly that tuple, which was correct on the
day and would have drifted silently the moment an edge changed. Phase 1 already stores this
relationship; restating it in Python is a second source of truth (D10's objection).

**Why a reserved slot:** with gaps ranked first, the mission sat at **position 8 of a
3-item plan** — a learner who had earned it would never be told it existed. It is the
flagship (§12) and the spine of the demo (§23). Reserving the last slot makes the plan read
"close a gap or two, then apply it under real constraints", which is §16's progression
rather than an unbounded queue of gaps.

A related fix: the "held back because X is not demonstrated" note was only recorded when
the plan had room. A mission that is absent with no explanation is indistinguishable from
one that does not exist, so the note is now recorded regardless — it explains an absence
rather than competing for a place.

**Where:** `cognith_learning/loop.py` (`mission_prerequisites`, `recommend`).

**Revisit when:** there is more than one mission. The reserved slot should then hold the
most appropriate mission, not the first.

---

## D37 — A milestone sets a target mastery per capability, not membership

**Phase 11.**

**Decision:** a milestone lists capabilities each with a `target` mastery, and `after`
chains one milestone to the next. No separate "level" concept.

**Why:** a goal previously produced a flat focus list — membership, binary, worth 0.15 in
diagnostic scoring. Membership cannot answer "how far along am I", because it has no notion
of how much of a capability the goal needs.

A target gives a **distance**. Distance makes progress computable, and computable progress
is what makes a question worth asking: the most informative thing to test is a requirement
the learner claims and nothing has checked, because that is where the estimate is most
likely wrong. That was the stated purpose — know the learner and how far they have reached
*before* asking questions — and membership could not deliver it.

Targets are deliberately not uniform. `DEMONSTRATED_AT` (0.70) is the bar for calling
something demonstrated at all; a milestone may want 0.70 of a central capability and 0.60
of a supporting one.

"Level" needs no type: a level is a milestone whose predecessor is complete, which `after`
already expresses. Validation rejects a chain loop, which would make "next level"
non-terminating.

**Where:** `cognith_capability/milestone.py`, `data/milestones.yaml`.

**Revisit when:** a milestone needs alternatives ("any three of these five"). The current
model requires all of them.

---

## D38 — Progress is two numbers, and a claim is never counted as progress

**Phase 11.**

**Decision:** `MilestoneProgress` reports `demonstrated_fraction` and `claimed_fraction`
separately. They are displayed side by side and never summed. The milestone bar reuses
Phase 4's solid/shade encoding.

**Why:** a single percentage would average demonstrated capability together with
self-report — the exact conflation §6.2 forbids and D18's two-material bar was built to
prevent. **A learner who claims everything and has shown nothing is not 80% of the way to a
milestone; they are 0% of the way with an 80% guess attached.**

It paid off on the first run. A profile showed *three of seven Level 2 capabilities
demonstrated and zero of six Level 1* — the learner had been proving advanced capabilities
on entirely unverified foundations. A blended percentage would have shown healthy progress
and hidden it.

The four `RequirementState` values are ordered by diagnostic value rather than by
attainment, and `claimed` (1.0) deliberately outranks `unknown` (0.6): the learner is
*counting on* a claimed capability, so the estimate depends on it, while an unknown one is
merely absent.

**Where:** `cognith_student/progress.py` (`MilestoneProgress`, `DIAGNOSTIC_VALUE`),
`milestones.py` (`bar`).

**Revisit when:** weighting requirements by importance is wanted. Today every requirement
counts equally toward the fraction.

---

## D39 — Milestones made an old content gap into a blocker, so the content was written

**Phase 11.**

**Decision:** five diagnostic scenarios were authored — `prog-fundamentals-001`,
`data-structures-001`, `algorithms-001`, `testing-001`, `git-001` — taking the bank from 12
to 17 scenarios and 62 to 82 criteria.

**Why:** `milestones.py --coverage` asked a question nothing had asked before — can each
requirement actually be tested? — and the answer was that **every milestone in the system
was impossible to complete.** All five. Programming Fundamentals, Data Structures,
Algorithms, Testing and Git had no scenario and no exercise, and each milestone required at
least one of them.

Those five capabilities had been reported as a content gap by three separate coverage
reports since Phase 5, and left alone each time as "a content problem, not an engine
problem" (D35). That framing was right until milestones existed. A gap that means "we
cannot help with this topic" is a backlog item; a gap that means "no learner can ever
complete any milestone" is a broken feature.

So the content was written as part of the phase. Shipping a milestone system in which no
milestone can complete would have been delivering the report of a defect instead of the
feature.

**Where:** `data/diagnostics.yaml`.

**Revisit when:** never for these five. The general lesson is the one to keep: a coverage
report is a backlog item until something depends on it, and then it is a defect.

---

## D40 — APPLY is a fourth type, because it carries behaviour the others do not

**Phase 12.** Partly reverses D29.

**Decision:** `ExperienceType.APPLY` — several capabilities combined, with nothing in the
prompt naming which one is relevant, and a readiness gate.

**Why D29 was wrong about this one:** it collapsed §16's middle stages on the grounds that
they would each be "an experience with a prompt and a rubric, which is what `exercise`
already is". True of quiz, case study and project. Not true here, and the difference is not
size.

An exercise names the lever: *"Explain why the existing index does not help."* An apply
scenario does not: *"Checkout got slow. Here is what you know."* — and in the authored
scenario, **indexing is the wrong answer.** Deciding which lever applies is a capability
practice structurally cannot test, because practice puts the lever in the question. That is
behaviour, not vocabulary.

It also carries `requires`, which no other type has — the readiness gate below.

**Where:** `cognith_learning/experience.py` (`ExperienceType.APPLY`,
`_applications`), `data/applications.yaml`.

**Revisit when:** a fifth type is proposed. The test D40 establishes: does it test something
the existing types structurally cannot, or is it the same shape with a different name?

---

## D41 — An apply scenario unlocks on evidence, not on mastery

**Phase 12.**

**Decision:** `requires` lists the capabilities an apply scenario integrates, and it
unlocks when each has `evidence_count > 0`. Not when each is demonstrated.

**Why a gate at all:** it is what makes the four stages a ladder rather than a menu. You
cannot integrate what you have not practised, and a learner sent to an integration scenario
cold will fail it for reasons that teach them nothing.

**Why evidence rather than mastery:** requiring demonstrated mastery would make apply
unreachable for exactly the learners it helps most. Someone who practised a capability and
did badly still benefits from seeing it in combination — that is often what reveals *why*
they did badly. Mastery-gating would turn a teaching rung into a reward.

Locked scenarios are reported with what would unlock them, following D35: an absent option
with no explanation looks like a bug.

The loop reserves one slot for the highest **earned** rung, and APPLY takes precedence over
MISSION — a learner who has not integrated capabilities without scaffolding is not ready
for one that also carries state and a budget. Completed rungs are read from the evidence
log so the ladder advances rather than loops.

**Where:** `cognith_learning/experience.py` (`ready_to_apply`, `apply_blocked_by`),
`cognith_learning/loop.py`.

**Revisit when:** a scenario wants partial readiness ("any two of these three"). Today all
components must have evidence.

---

## D42 — Attempt history is derived from the evidence log, never stored separately

**Phase 13.**

**Decision:** `Evidence.attempt` is assigned by counting the log, and every retry signal —
trajectories, blind spots, improvement, responsiveness to feedback — is computed from the
log on read. No attempt counter lives on the profile.

**Why:** the evidence log is already the record of what happened (§11: "preserve the
underlying evidence"). A counter stored beside it is a second source of truth that can
drift, which is the same objection D13 raised against storing `status` and D10 raised
against storing the hierarchy twice.

It also means the signals are **retroactive**: the five retry metrics were computed over
evidence collected in earlier phases with no change to that data.

**Where:** `cognith_student/history.py`, `cognith_student/evidence.py`
(`attempt_number`).

**Revisit when:** the log grows enough that recomputing is slow. A cache would then be
right — but a cache, not a second source of truth.

---

## D43 — A criterion missed twice is a blind spot; missed once is a slip

**Phase 13.**

**Decision:** `PERSISTENT_AFTER = 2`. A criterion missed on two or more attempts, and not
met on the latest, is a **blind spot**. Blind spots lead the gap query, are named in the
loop's reasoning, and are reported separately from ordinary unmet criteria.

**Why:** the second attempt is the one where the learner had **already been told exactly
what was wrong**. Missing it again is not noise — it is something they cannot yet
self-correct, which is precisely what a lesson should target. A first miss carries no such
information.

This matters because mastery alone cannot express it. Two learners at identical mastery,
one having missed a criterion once and the other three times, need different things.

It found a real case on the first run: a learner improved 12% → 38% on an HTTP exercise,
fixing the **surface detail** (what a 400 means) while twice missing the **underlying
concept** (idempotency). The score said "improving"; the trajectory said the actual gap had
not moved.

**Where:** `cognith_student/history.py` (`CriterionTrajectory.persistent`,
`PERSISTENT_AFTER`), `cognith_learning/knowledge.py`, `cognith_learning/loop.py`.

**Revisit when:** there is data on how often a second miss predicts a third. The threshold
is authored judgement standing in for a measurement, and the evidence log makes that
measurement possible.

---

## D44 — "Responds to feedback" is a signal about the learner, and is None when unknown

**Phase 13.**

**Decision:** `responds_to_feedback()` returns the share of criteria that were unmet and
later became met — and returns **None**, not 0.0, when nothing has been retried.

**Why the signal:** every other number in the system describes a capability. This one
describes the person: someone who reliably fixes what they are told about needs feedback,
and someone who does not needs a different explanation rather than more of the same. That
is a teaching decision no capability estimate can inform.

**Why None:** a student who has never attempted anything twice has not failed to respond to
feedback — there is simply no evidence either way. Reporting 0% would be a claim about them
that the data does not support, which is the same error D12 avoided by making `mastery`
nullable rather than defaulting it to zero. The CLI says so explicitly: *"That is a gap in
what we know about them, not a judgement about them."*

**Where:** `cognith_student/history.py` (`responds_to_feedback`), `learner.py`.

**Revisit when:** enough retries exist to calibrate the bands. The 0.7 / 0.4 thresholds for
"reliably / sometimes / has not been able to" are presentation, not policy.

---

## D45 — The app is a shell; it contains no logic

**Phase 14.**

**Decision:** `app.py` is one interactive entry point, and every screen calls an engine or
renderer that already exists. The fifteen command-line tools are kept.

**Why:** the temptation with a front end is to reimplement "what should happen next"
inside it, because that is where the user is. That produces two loops which drift, and the
one in the app wins by being the one people see — so the real policy quietly stops being
the policy.

The test to keep applying: if a screen in `app.py` looks like it is deciding something, the
decision belongs in the layer that owns it. Selection is `AdaptiveLoop`, assessment is
`assess()`, retrieval is `GapResolver`, consequences are `MissionEngine`, progress is
`MilestoneProgress`.

The CLIs are kept rather than replaced because they are better for scripting, for debugging
one layer, and for the checks that should run without a human: `mission.py --calibrate`,
`onboard.py --verify`, `capabilities.py --validate`. A front end is not a reason to delete
a test harness.

**Where:** `app.py`.

**Revisit when:** a screen needs behaviour no layer provides. That is a signal the layer is
missing something, not that the app should grow it.

---

## D46 — A multi-line answer ends on two blank lines, not one

**Phase 14.**

**Decision:** `.` alone, or two consecutive blank lines. Not a single blank line.

**Why:** a single blank line is the obvious rule and it is wrong. A scenario answer is
prose, prose has paragraphs, and people paste. Ending on the first blank line would
**silently truncate a pasted answer at its first paragraph break** — keeping the first
paragraph, discarding the rest, and assessing the fragment as though it were the whole
answer. The learner would be marked down for criteria they had actually met.

Silent truncation of input is the worst class of this bug because nothing looks wrong: the
assessment runs, the verdicts are plausible, and the profile updates with a number that
should not exist.

The first version of this file documented "finish with an empty line" while the code
required two — worse than either rule on its own, since the message and the behaviour
disagreed. Both now say two.

**Where:** `app.py` (`ask_lines`).

**Revisit when:** an editor-based input is offered instead (`$EDITOR`), which sidesteps the
question entirely and would be the better answer for long responses.

---

## D47 — The engine goes behind HTTP; persistence behind one seam

**Phase 15.** Reverses the Q2 closure.

**Decision:** a FastAPI layer in `api/` that adds no learning logic, and a `Storage`
protocol (`cognith_student/storage.py`) that every profile and evidence-log read/write
goes through.

**Why:** the Google AI Builder Cup requires a deployed web app, and Cloud Run's disk is
per-instance and ephemeral. The engine opened `data/students` and `data/evidence` from
seven places; Firestore would have meant editing all of them. Now it is one class with
five methods, and the record shapes are unchanged, so the engine cannot tell the backends
apart.

**Where:** `api/main.py`, `api/schemas.py`, `cognith_student/storage.py`.

**Revisit when:** a third kind of learner state needs persisting (mission sessions are
still file-only and not exposed over HTTP).

---

## D48 — Three skill states on the wire, four inside

**Phase 15.**

**Decision:** the API reports `mastered | developing | unknown`. Engine `claimed` and
`unknown` both map to `unknown`; the claim survives as `selfRated`.

**Why:** the product plan and the pitch use three states, and "unknown is not failure"
is a stated acceptance criterion. Collapsing claimed into unknown loses nothing — the
self-rating is still there for the UI to show — while keeping the learner-facing story
simple.

**Where:** `api/main.py` (`state_of`).

---

## D49 — Lessons ask what to understand, not how to do

**Phase 15.**

**Decision:** `GapResolver.build_question` asks "What do I need to understand about X to
be able to …?" instead of "How do I …?".

**Why:** measured across the ten teachable capabilities — 6/10 answered before, 7/10
after. "How do I explain and debug an HTTP request" was refused because no excerpt gives
a debugging procedure, though the retrieved sections on methods, status codes and headers
(scores 0.68–0.80) were exactly what to teach. Retrieval was never the problem; the
question demanded more than the corpus claims to cover.

**Where:** `cognith_learning/knowledge.py`.

**Revisit when:** the three remaining abstentions (databases, scalability, reliability)
get corpus material — they are content gaps, and abstaining on them is correct.

---

## D50 — `assess()` now numbers attempts

**Phase 15.** A defect fix.

**Decision:** `assess()` sets `Evidence.attempt` from `attempt_number()`.

**Why:** `attempt_number()` existed and was never called, so every stored attempt was
`1`. Retry detection was unaffected (it orders the log by time), but the API reports the
attempt number to the learner.

**Where:** `cognith_student/evidence.py`.

---

## D51 — Lessons are aimed at what was missed, with a general fallback in parallel

**Phase 15.**

**Decision:** `GapResolver.knowledge_for` asks a targeted question (general question +
the learner's missed criteria) and the general question at the same time, and keeps the
targeted answer if the grounding contract accepted it.

**Why:** the first UI tested learners and never taught them — a lesson did not know what
the learner had just got wrong. Measured over eight real gaps: targeted alone answered
4/8, general alone 6/8, both in parallel 7/8. The targeted form fails when a criterion is
scenario-specific ("five retries can create five orders") because no excerpt mentions the
scenario; falling back keeps the lesson honest rather than improvised. Parallel calls cost
no extra wait, only a second request.

**Where:** `cognith_learning/knowledge.py`; `targeted` and `missed` on the Lesson contract.

**Revisit when:** the corpus grows worked examples for the diagnostic scenarios — then
the targeted form should win far more often.

---

## D52 — Follow-up challenges are generated; diagnostics stay authored

**Phase 15.**

**Decision:** after a lesson, the learner gets a challenge Gemini writes from the same
course excerpts the lesson used (`cognith_learning/generator.py`), aimed at what they
missed and explicitly not the situation they just failed. Diagnostics remain authored.

**Why:** re-asking the missed question tests memory, not transfer — and the plan's own
acceptance criterion asks for "a different follow-up challenge". Only 9 of 17
capabilities had a second authored activity. Diagnostics stay authored because the first
measurement must be the same instrument for every learner, or "two learners, same goal,
different result" stops being a fair comparison (D22 still holds there).

**Guard rails:** 3–5 criteria; every criterion cites an excerpt that was actually sent,
or the whole challenge is rejected and regenerated once with the reasons; all criteria
are tagged with the target capability; persisted write-once with model and timestamp so
evidence stays traceable to the exact prompt and rubric. Gemini writes questions; it does
not score — judging and the mastery arithmetic are unchanged.

**Measured 2026-10-14:** 7/7 capabilities produced a valid challenge first time, ~12 s
each, including reliability and scalability whose lessons abstain.

**Where:** `cognith_learning/generator.py`, `POST /api/learners/{id}/challenges`,
`ExperienceType.GENERATED`, storage `save_activity`/`list_activities`.

**Revisit when:** evidence from generated challenges should weigh less than authored
ones — today they count the same.

---

## D53 — Lessons are guided exchanges, not pages

**Phase 15.**

**Decision:** a lesson is 2–5 concepts, each run as: a gentle **probe** first (with "I'm
not sure yet"); if right, a **confirm** question in a different situation and the
explanation is skipped; otherwise **teach** (explanation, worked example, drawn diagram)
then **check**; a wrong check calls `/lessons/reexplain`, which explains the idea
differently and addresses the misconception the chosen answer reveals, then gives a new
check. Per-concept outcomes (met / partial / unmet) are posted to `/lessons/result` as
**light evidence**: `assess(..., max_observed=0.6)` so multiple-choice checks can move a
skill to developing but never to mastered. The written challenge (with a grounded hint)
remains what proves a skill.

**Why:** the product vision's learning style — diagnose gently even for beginners, teach
only what is needed, check immediately, respond to the misconception rather than the
wrong answer, verify on a new situation. Earlier versions were a wall of text, then
cards, then a page plus an end quiz; none responded to what the learner got wrong.

**Where:** `cognith_learning/microlesson.py`, `api/main.py` (`/lessons/reexplain`,
`/lessons/result`, `/hint`), `frontend/components/GuidedLesson.tsx`.

---

## D54 — Guided help during challenges; help makes evidence "assisted"

**Phase 15.**

**Decision:** challenges (not diagnostics) get a tutor panel with graduated help — 1 nudge
(guiding question), 2 key idea, 3 similar worked example on different values — unlocked in
order, plus free questions. The model is given the marking criteria as things it must not
state, sees only course excerpts as facts, and self-flags a reply that would reveal the
answer (replaced). Each request is counted and sent with the answer; any help caps the
observed score (1 → 0.85, 2 → 0.75, 3+ → 0.65) and the explanation says the attempt was
assisted.

**Why:** the vision wants an AI tutor available during challenges as guidance, and also
that "a competency remains incomplete" until applied independently. Uncapped help would
let a learner reach mastery on an answer the tutor walked them through.

**Where:** `cognith_learning/guide.py`, `POST /api/learners/{id}/help`,
`AttemptRequest.help_used`, `frontend/components/GuidedHelp.tsx`.

---

## D55 — Remediation teaches only what was missed

**Phase 15.**

**Decision:** when a learner has evidence on a capability, a lesson is FOCUSED: the
missed points are the criteria their last answer to the activity did not fully meet
(`from_activity_id`), or else the gap's unmet criteria; retrieval searches for those
points; the lesson is 1–2 concepts on exactly them; the follow-up challenge is told to
test only them (2–3 criteria). A full lesson happens only with no evidence yet, or when
the learner asks for it (`full`).

**Why:** "Teach me Sets" after missing only inclusion–exclusion opened the whole Sets
lesson from the start — the learner would re-learn everything to fix one point. The
vision: "focus on that distinction rather than repeat everything". Measured on that exact
case: one concept on inclusion–exclusion; challenges whose every criterion was about it
(previously one criterion in three).

**Where:** `api/main.py` (`missed_points`, `focused_hits`), `microlesson.generate(focus=)`,
`ChallengeGenerator.generate(focused=)`.
