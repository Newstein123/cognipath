# Capability model

**Status:** Phases 1–2 complete — `Capability`, `CapabilityEdge`, `StudentCapability`.
**Last updated:** 2026-09-22 (Phase 2)
**Owns:** Claude.md §21 Phases 1 and 2.

Two layers, kept apart:

- **§§1–8 — the capability graph** (Phase 1). *What capabilities exist, and how do they
  relate?* Nothing about any student.
- **§§11–17 — student capability state** (Phase 2). *What do we currently believe about
  one learner?* Nothing that computes mastery from evidence — that is Phase 6.

---

## 1. What was built

```
data/capabilities.yaml          the authored graph — 16 capabilities, 21 relationships
cognith_capability/
├── __init__.py                 package boundary
├── models.py                   Level, RelationType, Capability, CapabilityEdge
└── graph.py                    CapabilityGraph — load, validate, query
capabilities.py                 CLI for inspecting it
```

No existing file changed. `cognith_capability/` imports **nothing** from
`cognith_rag/` — Claude.md §5 keeps "what should the learner be able to do?" separate
from "what knowledge should they receive?", and that separation is enforced by the absence
of an import rather than by a comment.

---

## 2. Why the graph is data and not code

§7 requires relationships to be stored as data. The reason becomes concrete at Phase 5:
the diagnostic engine picks what to verify by walking prerequisite edges. If those edges
were `if` statements, changing the curriculum would mean changing the engine.

So `data/capabilities.yaml` holds every capability and every edge, and no Python file
duplicates any of it. What *does* live in code is the **vocabulary**: which relation types
exist and what each one means. An engine has to know that a missing prerequisite blocks
assessment while a missing contributor does not — that is logic, not data.

---

## 3. Data model

### Capability

```python
@dataclass(frozen=True)
class Capability:
    id: str                          # "scalability"
    name: str                        # "Scalability"          — for display
    statement: str                   # "Can identify the bottleneck limiting a system's
                                     #  throughput and choose a change that removes it."
    description: str
    domain: str                      # "software-engineering"
    area: str                        # "system-design"        — one of four groupings
    level: Level                     # foundation | intermediate | advanced
    knowledge_docs: tuple[str, ...]  # knowledge/*.md ids — see §7 below
```

**`statement` is the field that matters.** §6.1 is explicit that a capability is something
a learner can *do*, and that naming capabilities as bare topics is the wrong model.
"Caching" is a topic. "Can decide where to cache, what to cache, and how to invalidate it"
is something a piece of evidence can confirm or contradict. Later phases assess the
statement, not the name.

This is enforced, not just documented: loading fails if a statement does not begin with
"Can ". It is a crude proxy, but it catches the actual failure mode — someone pasting the
topic name into the statement field.

`level` is an **authoring estimate of the capability's difficulty**, not a measurement of
any student. Phase 5 reads it to decide what to verify first. Student state does not exist
in this phase.

### CapabilityEdge

```python
@dataclass(frozen=True)
class CapabilityEdge:
    source_id: str
    relation: RelationType
    target_id: str
    origin: str = "authored"   # "claude-md-7" for the six examples given in the spec
```

`origin` exists so a reviewer can tell the six edges §7 specifies verbatim from the
fifteen authored for this phase. The CLI marks them `§7`.

### Areas are groupings, not capabilities

§7's tree has four second-level nodes — Programming, Backend, Engineering, System Design.
**"Backend" is not something a learner can do**, so it gets no row. `area` is a string
grouping on `Capability`, and hierarchy is stored once, as that field, rather than
duplicated as edges that could drift out of sync with it.

### The System Design wrinkle

§7 lists System Design as an area containing Scalability, Caching, and so on. But §7's own
relationship examples use it as an edge *target* (`Databases → prerequisite_for → System
Design`), §9's capability map lists it as a percentage, and §10's diagnostic treats it as
something a student can claim.

So System Design is **both**: an area, and the integrative capability inside that area.
That is why there are 16 capabilities where the tree shows 15 leaves.

---

## 4. Relation semantics

Four types, from §7. A closed enum — unknown types are rejected at load.

| Relation | Meaning | Blocking? |
|---|---|---|
| `prerequisite_for` | A must be developed before B is worth assessing | yes |
| `contributes_to` | A is a component of B | no |
| `supports` | A is a technique that serves B; B is achievable by other means | no |
| `applies_to` | A is cross-cutting, exercised inside B's context — evidence in B may also be evidence for A | no |

**How much evidence propagates along each edge is not decided here.** That is a Phase 6
policy question. Phase 1 records only that the relationship exists. Writing a propagation
weight into this phase would put assessment logic in the wrong layer.

Only `prerequisite_for` must stay acyclic — it is the only type that implies an ordering.
`applies_to` cycles are legitimate (two cross-cutting capabilities can each be exercised
inside the other) and are allowed.

Current distribution: `prerequisite_for` 10, `contributes_to` 5, `applies_to` 4,
`supports` 2.

---

## 5. Validation

Hand-authored graph data drifts. A renamed id leaves a dangling edge, and nothing complains
until something downstream silently returns nothing. The corpus already has exactly this
bug — `database-indexing.md` declares a prerequisite on a document that does not exist
([decisions.md](decisions.md) Q3). The capability graph refuses to inherit it.

`CapabilityGraph.load()` raises `GraphValidationError` on:

| Rule | Why |
|---|---|
| unknown `from`/`to` id | the dangling-edge bug above |
| duplicate capability id | silent overwrite otherwise |
| unknown `area` | typo becomes an invisible orphan |
| statement missing or not starting with "Can " | §6.1's topic-vs-capability failure |
| self-edge | meaningless, and creates a trivial cycle |
| duplicate edge | double-counts in any future propagation |
| `prerequisite_for` cycle | prerequisites must be orderable |

Every problem is collected and raised together, not one per run — fixing authored data one
error at a time is miserable.

---

## 6. Queries, and who needs them

`graph.py` exposes only queries a later phase has an identified use for. It is deliberately
not a general graph library.

| Query | Needed by |
|---|---|
| `get`, `by_area`, `by_level`, `tree` | Phase 4 — rendering the capability map |
| `prerequisites_of`, `unlocked_by` | Phase 5 — direct ordering |
| `prerequisite_closure` | **Phase 5** — every transitive prerequisite, furthest upstream first. If a student claims System Design, this is what says to verify Databases before Scalability |
| `contributors_to` | Phase 6 — gap explanation. Weak Scalability is only actionable once you know it is built from Caching, Load Balancing, Trade-off Analysis and Debugging |
| `isolated` | authoring hygiene — capabilities no graph-driven recommendation can reach |
| `without_knowledge` | Phase 7 — the corpus work queue |
| `to_records` | the §19 Firestore shape, for whenever the backend lands |

Storage is YAML → dataclasses in memory, mirroring the corpus's existing
`YAML → dataclass → artifact` pattern. Not Firestore yet: there is no backend and no
credentials ([decisions.md](decisions.md) Q2), and §7 says Firestore is *sufficient*, not
required now. `to_records()` emits both §19 collections, so that migration is a
serialization change rather than a redesign.

---

## 7. The knowledge join — and a correction

Each capability carries `knowledge_docs`: the `id:` values of the `knowledge/*.md`
documents that can teach it. This resolves [decisions.md](decisions.md) **Q1** as data,
with no code dependency between the layers.

The first attempt used the corpus's `capability:` frontmatter tags, and **testing showed
that cannot work**. Those tags are too coarse: one `system-design` tag is shared by
`caching.md`, `load-balancing.md` and `system-design.md`, so a tag-level mapping made the
Caching capability resolve to `load-balancing.md`. Document ids are 1:1 with files and
precise. Recorded as [decisions.md](decisions.md) **D9**.

This also means the existing `Store.search(capability=...)` filter is **not** the Phase 7
join — it filters on the coarse tags. Phase 7 will need document-level filtering.

### Coverage today: 9 of 16

```
python capabilities.py --coverage
```

| Covered | Not covered |
|---|---|
| HTTP, API Design, Databases, System Design, Scalability, Caching, Load Balancing, Reliability, Trade-off Analysis | Programming Fundamentals, Data Structures, Algorithms, Authentication, Testing, Debugging, Git |

**This is a gap in the corpus, not in the graph.** Phase 7 can only retrieve what has been
written, and seven capabilities currently have nothing behind them. All seven knowledge
documents are mapped to at least one capability, so there is no waste in the other
direction.

`--coverage` also validates every `knowledge_docs` reference against the real corpus, so
the Q3 dangling-reference bug cannot silently appear here.

---

## 8. Known gaps, recorded not fixed

**`database-performance` is missing.** §10's diagnostic example tests "Scalability,
Trade-off Analysis, Database Performance" — but Database Performance is not in §7's tree.
`databases` covers modelling and querying; performance is arguably distinct, and
`database-indexing.md` exists to teach it. Not added, because §7 says twice not to build a
large ontology. **Phase 5 should decide** whether it needs its own capability or is a facet
of `databases`.

**`git` has no edges.** It genuinely does not depend on the others, so this is correct
rather than an omission — but an isolated capability cannot be reached by graph-driven
recommendation. `capabilities.py --edges` reports it so it stays visible.

**Fifteen of 21 edges are authored, not specified.** §7 gives six. The rest are a
defensible reading, not ground truth, and are the reviewable part of the data file.

---

## 9. How to test it

No LLM, no network, no API key needed for any of this.

```bash
python capabilities.py               # the §7 tree with statements and levels
python capabilities.py --edges       # all 21 relationships, grouped by type, §7 marked
python capabilities.py --show scalability    # one capability and everything touching it
python capabilities.py --validate    # data file integrity only
python capabilities.py --coverage    # cross-check against knowledge/*.md
python capabilities.py --records     # the §19 Firestore collection shape as JSON
```

Example — `--show scalability`:

```
Direct prerequisites — must come first:
   • Databases                [foundation]

Composed of / exercised through:
   • Caching                  [intermediate]
   • Load Balancing           [intermediate]
   • Trade-off Analysis       [advanced]
   • Debugging                [intermediate]

Knowledge documents (Phase 7 joins on these):
   load-balancing, caching, database-replication
```

Transitive ordering, which is what Phase 5 consumes:

```python
>>> [c.id for c in g.prerequisite_closure("algorithms")]
['programming-fundamentals', 'data-structures']     # furthest upstream first
```

Validation was verified against seven deliberately broken graphs — dangling target,
self-edge, duplicate edge, topic-style statement, unknown area, three-node prerequisite
cycle — and confirmed to allow an `applies_to` cycle, which is legal.

---

## 10. Part two — student capability state (Phase 2)

Everything above describes capabilities in the abstract. Everything below describes what
Cognith believes about one student.

```
cognith_student/            depends on cognith_capability, never the reverse
├── __init__.py
├── models.py                  Student, StudentCapability, MasteryStatus
└── profile.py                 CapabilityProfile + JSON persistence
students.py                    CLI
data/students/<id>.json        saved profiles
```

Dependency arrows stay one-way: `cognith_student → cognith_capability → ∅`, and
`cognith_rag → ∅`. No existing file changed.

---

## 11. Self-reported vs demonstrated

This is the distinction the whole phase exists to preserve. Claude.md §6.2:

> **Self-reported capability** — what the student believes they know.
> **Demonstrated capability** — what evidence shows they can actually do.
> Do not treat self-reported confidence as proof of mastery.

| | `confidence` | `mastery` |
|---|---|---|
| Source | the student says so | evidence supports it |
| Set at | onboarding (Phase 3) | assessment (Phase 6) |
| Can be wrong? | yes, and that is expected | only if the rubric is wrong |
| Missing means | never rated it | **never demonstrated** |
| Is it evidence? | **no** | yes |

They are different kinds of claim and must never be averaged into one number. A profile
straight out of onboarding has every `confidence` set and every `mastery` `None` — which
is exactly §9's "this is an initial estimate based on what you've told us. Let's verify it."

### Why `mastery` is nullable

§6.2's example JSON shows `"mastery": 0.35`, and it would be easy to default the field to
`0.0`. That is wrong, because it makes two opposite states identical:

```
mastery = 0.0     "we have no evidence about this"
mastery = 0.0     "we have evidence, and they cannot do it"
```

The first is ignorance; the second is a finding. Collapsing them lets an unverified
capability read as a measured zero — and worse, it makes a confident self-report look like
it has been checked. So `mastery is None` means **never demonstrated**, and it is the
default. Recorded as [decisions.md](decisions.md) **D12**.

---

## 12. Data model

### Student

```python
@dataclass(frozen=True)
class Student:
    id: str
    name: str
    goal: str | None = None       # §8 fills this properly at Phase 3
    created_at: datetime
```

Minimal on purpose. §8's onboarding adds technologies, experience and background at
Phase 3; only `goal` is here, because Phase 4's capability map needs a heading.

### StudentCapability

One row per (student, capability). Field names follow §6.2.

```python
@dataclass(frozen=True)
class StudentCapability:
    student_id: str
    capability_id: str
    confidence: float | None = None       # self-reported, 0..1
    mastery: float | None = None          # evidence-based, 0..1, None = never assessed
    evidence_count: int = 0
    last_assessed_at: datetime | None = None
```

`evidence_count` is defined as *pieces of evidence incorporated into the current mastery
estimate* — not "evidence collected". Defined that way so it cannot drift away from
`mastery`.

Frozen, like `Capability`. State changes return a new row via `with_confidence()` or
`record_assessment()`, so a row cannot be mutated into an inconsistent state halfway
through an update.

### Status is derived, never stored

```python
MasteryStatus:  unknown  ->  claimed  ->  developing | demonstrated
```

| Status | Means |
|---|---|
| `unknown` | neither claimed nor assessed |
| `claimed` | self-reported only — a claim, not a finding |
| `developing` | assessed, and the evidence does not yet support the capability |
| `demonstrated` | assessed, and the evidence supports it (mastery ≥ 0.70) |

§6.2 lists `status` as a field, but storing it as authored input would let it contradict
the numbers beside it — `status: demonstrated` next to `evidenceCount: 0`, with no answer
as to which is right. So it is a **computed property**. It is still written into the §19
record shape, because a Firestore query cannot call a Python property, but it is always
recomputed on read and never trusted from storage. [decisions.md](decisions.md) **D13**.

The jump that matters to the product is `claimed → developing|demonstrated`: that is the
moment a belief becomes evidence.

`DEMONSTRATED_AT = 0.70` is a **presentation threshold, not an assessment policy**. Phase 6
decides how mastery is computed and may want a different bar per capability. It is one
named constant so there is exactly one place to change.

---

## 13. Invariants

Enforced at construction, because they are what stops a claim from being read as a finding:

| Rule | Why |
|---|---|
| `mastery is not None` ⟺ `evidence_count > 0` | mastery without evidence is an unsourced number; evidence without mastery is an assessment never applied |
| `mastery is not None` ⟺ `last_assessed_at is not None` | an assessed capability must carry when it was assessed |
| `0.0 ≤ confidence ≤ 1.0`, same for mastery | both are proportions |
| `evidence_count ≥ 0` | — |
| `record_assessment` needs `evidence_added ≥ 1` | an assessment with no evidence is not an assessment |
| row's `student_id` matches the profile's | prevents cross-student contamination |
| `capability_id` exists in the graph | the dangling-reference class of bug from Q3 |
| no duplicate row per capability | silent overwrite otherwise |

Verified against seven deliberately malformed rows; all seven were rejected with a message
naming the capability.

---

## 14. Signals, not policy

`CapabilityProfile` answers questions. It does **not** decide anything — the same boundary
Phase 1 drew by refusing to put propagation weights on edges.

| Query | Signal it provides | Consumer |
|---|---|---|
| `unverified()` | claimed, never assessed — boldest claim first | **Phase 5** — §9's "let's verify it" |
| `calibration_gaps()` | `confidence - mastery`, widest first | **Phase 5** — §10 wants *uncertain* capabilities targeted |
| `blocked(threshold)` | capabilities with a prerequisite not demonstrated | **Phase 5** — §10's "verify prerequisites rather than test everything" |
| `weakest(n)` | lowest demonstrated mastery | Phase 6/7 — the raw ordering gap detection starts from |
| `days_since_assessment()` | staleness | Phase 5 — old evidence may count for less |
| `by_status`, `all_rows`, `summary` | display | Phase 4 |

`blocked()` takes `threshold` as a **parameter**, not a constant, because what counts as
"met" is a Phase 5 policy question. And `calibration_gap` is explicitly *a signal, not a
verdict*: a negative gap means the student underestimates themselves, which is equally
worth knowing.

`blocked()` is the payoff from storing prerequisites as data in Phase 1. In the fixture,
HTTP is demonstrated at 0.78, so API Design and Authentication are **not** blocked — while
System Design and Scalability are, because Databases is only claimed.

---

## 15. Persistence

`data/students/<id>.json`, in the §19 `students/` + `student_capabilities/` shape.

**Only rows carrying information are written.** Persisting 16 empty rows per student would
make storage imply knowledge. An absent row and an all-`None` row mean the same thing, and
`row_for()` returns an empty row for a capability with no data, so callers never have to
handle the two cases separately.

Verified: save → load → save is byte-stable, timestamps survive as timezone-aware UTC, and
`status` is recomputed rather than read back.

---

## 16. How to test it

No LLM, no network, no API key.

```bash
python students.py                    # the full profile table, both columns side by side
python students.py --unverified       # claimed but never demonstrated
python students.py --calibration      # where the claim exceeds the evidence
python students.py --blocked          # unmet prerequisites, via the Phase 1 graph
python students.py --summary          # counts by status
python students.py --records          # the §19 collection shape as JSON
python students.py --save             # write data/students/student-001.json
python students.py --load student-001  # read it back
```

The profile is a **fixture**, clearly labelled as one. Its self-reported numbers are §9's
example capability map verbatim, plus two hand-set assessment outcomes so both sides of the
distinction appear in one table. Phase 3 replaces it with real onboarding.

Example — the shape of the finding this phase makes visible:

```
capability                  self-rep  demonstr         status  ev  gap
HTTP                             85%       78%   demonstrated   2  +0.07
API Design                       75%         —        claimed   0
Databases                        80%         —        claimed   0
System Design                    50%       22%     developing   1  +0.28 <
Scalability                      35%         —        claimed   0

unknown 8   claimed 6   developing 1   demonstrated 1
```

Six capabilities are claimed and unchecked; one self-report sits 0.28 above its evidence.
That gap is the product's entire premise, and it is legible straight out of the data model.

---

## 17. Deliberately absent

- **Evidence → mastery.** `record_assessment()` stores an outcome; it does not compute one.
  The rubric, the Gemini evaluation and the arithmetic are Phase 6.
- **Propagation.** Demonstrating Caching does not move Scalability. The edges exist
  (Phase 1) and the state exists (Phase 2); connecting them is a Phase 6 policy.
- **Gap detection.** `weakest()` is an ordering, not a decision about what to teach next.
- **Onboarding.** Nothing populates `confidence` from a real student yet. Phase 3.
- **Decay.** `days_since_assessment()` reports staleness; nothing acts on it.

---

## 18. Next — Phase 3, Student Onboarding

§8's intake: goal, what they already know, technologies used, what they have built, and
confidence per area. It produces an **initial capability profile** — every `confidence`
set, every `mastery` still `None`. §8 is explicit that this is an estimate, not an
assessment.

The open question Phase 3 has to answer: §8's answers are free text ("PHP, Laravel, MySQL,
Redis"; "built APIs and booking systems"), and the 16 capabilities are structured. Mapping
one to the other is where Gemini would be tempting — and where §26.4 ("do not hide
important logic inside prompts") applies. Expect that to be the main design decision.
