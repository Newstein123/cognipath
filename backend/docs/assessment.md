# Assessment

**Status:** Phase 5 complete — the diagnostic engine.
**Last updated:** 2026-09-22 (Phase 5)
**Owns:** Claude.md §21 Phases 5 and 6. Phase 6 (Evidence + Assessment) extends this file.

Phase 5 decides **what is worth verifying** and assembles a short diagnostic. It does not
score anything — turning responses into evidence and evidence into mastery is Phase 6.

---

## 1. What was built

```
data/diagnostics.yaml                selection weights + 12 authored scenarios
cognith_student/diagnostic.py     DiagnosticItem, Candidate, Diagnostic, engine
diagnose.py                          CLI
data/diagnostics/<student>.json      persisted sessions, status "pending"
data/capabilities.yaml               EDIT — added `database-performance` + 4 edges
data/onboarding.yaml                 EDIT — signals for the new capability
```

---

## 2. The deferred question, decided

Phase 1 recorded an open question: §10's diagnostic example names **Database Performance**
as a target, but §7's capability tree does not contain it. Phase 1 declined to invent it
and handed the decision here.

**Decided: it gets its own capability.** `databases` is modelling and querying;
`database-performance` is behaviour under load — indexes, execution plans, read/write
split, and knowing which of those the evidence points at. They are separately assessable,
§12's flagship mission turns on the second, and `database-indexing.md` already exists to
teach it.

```yaml
- id: database-performance
  statement: Can diagnose why a query or database is slow and choose a change that fixes it.
  area: backend
  level: intermediate
  knowledge_docs: [database-indexing, database-replication]
```

Edges: `databases → prerequisite_for →`, `→ contributes_to → system-design`,
`→ supports → scalability`, `debugging → applies_to →`.

The graph is now **17 capabilities, 25 relationships**, and `onboard.py --verify` still
passes §9 conformance at an unchanged 0.025 deviation — adding a capability disturbed no
existing estimate.

---

## 3. What §10 actually specifies

```
"Student says they are intermediate in system design.
 Cognith tests: Scalability, Trade-off Analysis, Database Performance."
```

Note what it does **not** do: it does not test System Design. The student already told you
about System Design — that is the claim. What is unknown is whether anything underneath it
is real.

So a bold, unverified claim is a reason to examine **what that claim rests on**: its
contributors and its prerequisites. That is the `claim_support` factor, and it is the
third time Phase 1's decision to store relationships as data has paid for itself.

---

## 4. The selection policy

Six weighted factors, weights in `data/diagnostics.yaml`, logic in code.

| Factor | Weight | What it measures |
|---|---|---|
| `uncertainty` | 0.30 | How little we know. Claimed-but-unverified = 1.0; never mentioned = 0.35; already assessed = 0.15 |
| `stake` | 0.20 | How bold the claim is. Verifying an 80% claim tells you more than a 20% one, because more of the student's plan rests on it |
| `goal_relevance` | 0.15 | In the goal's `focus` list from §8 |
| `claim_support` | 0.15 | **§10's rule** — boost what an unverified claim rests on |
| `leverage` | 0.10 | How many capabilities depend on this one |
| `calibration` | 0.10 | Already assessed and the claim sat above the evidence |

Plus one constraint. Testing a capability whose own prerequisites are unproven measures
the prerequisite, not the capability — so those candidates are **scaled by 0.55**, not
excluded. Excluding them would leave a student with nothing verified with no diagnostic at
all.

That penalty is visible in the ranking as `·`:

```
 ->HTTP                      0.802   0.30  0.14  0.15  0.10  0.00  0.11   claimed
 ->Databases                 0.764   0.30  0.16  0.15  0.08  0.00  0.08   claimed
   Programming Fundamentals  0.762   0.30  0.14  0.15  0.08  0.00  0.10   claimed
 ->Trade-off Analysis        0.646   0.30  0.08  0.15  0.04  0.00  0.08   claimed
 · Authentication            0.393   0.30  0.14  0.15  0.01  0.00  0.11   claimed
 · Scalability               0.336   0.30  0.07  0.15  0.01  0.00  0.08   claimed
```

Foundations rise, everything downstream is held back until its prerequisites are proven.
That is §10's "verify prerequisites rather than test everything", falling out of the data
rather than being coded as a rule.

### Every selection carries its reasoning

`Candidate.factors` records each factor's contribution, and it is persisted with the
session. A diagnostic that cannot say why it is asking is a quiz (§26.7).

---

## 5. It adapts as evidence accumulates

The same student, same goal, re-running the diagnostic after each round of evidence:

```
round 1 (nothing proven)   ->  HTTP, Databases, Trade-off Analysis
round 2 (HTTP + DB proven) ->  Authentication, Caching, Database Performance
round 3 (backend proven)   ->  Caching, Database Performance, Scalability
```

The diagnostic walks **up** the capability graph. At round 3 the student's remaining
unverified claim is System Design, and the engine is testing what that claim rests on —
which is §10's worked example.

### Honest comparison with §10's list

Under §10's premise (foundations proven, System Design claimed), the engine selects
**Caching, Database Performance, Scalability** as primary targets. §10 lists Scalability,
Trade-off Analysis, Database Performance.

Two of three match as primaries. Trade-off Analysis ranks fourth and is **exercised as a
secondary capability** by two of the three chosen scenarios, so all three of §10's
capabilities are covered by the diagnostic:

```
primary targets : Caching, Database Performance, Scalability
also exercised  : Databases, Debugging, Reliability, Trade-off Analysis
```

Caching outranks Trade-off Analysis because the student claimed 70% for it against 40% for
Trade-off Analysis, and `stake` weighs that. **I did not tune the weights to force an
exact match with §10.** The example is an illustration; making the numbers reproduce it
would mean fitting six weights to one worked example, and the result would look principled
while being arbitrary. The divergence is recorded here instead.

---

## 6. Scenarios are authored, not generated

12 scenarios in `data/diagnostics.yaml`, each a situation requiring a decision and a
justification. §10: *"Avoid relying only on memorization questions."* A scenario
answerable by recalling a definition does not belong in the bank.

```yaml
- id: dbperf-slow-001
  capability: database-performance
  also_exercises: [debugging, databases]
  probes: [decomposition, reasoning, application]
  prompt: |
    An endpoint that was fast last month now takes 4 seconds. Nothing in its code has
    changed. The table it reads has grown from 50,000 rows to 4 million.

    How would you find the cause? Describe what you would look at, in order, and what
    each thing would tell you.
```

**Why authored rather than model-generated.** This was the first real opening for Gemini,
and it was declined for one specific reason: §11 requires structured rubrics, Phase 6
authors them, and **a scenario generated independently of its rubric cannot be scored
against one.** `probes` is the bridge — it names the reasoning dimensions the scenario is
meant to expose (§10's decomposition / reasoning / decision / trade-offs / application),
and Phase 6's rubric criteria will be written against those same dimensions.

Recorded as [decisions.md](decisions.md) **D22**.

---

## 7. Two defects found by testing, and fixed

Both were caught by running the engine against §10's premise rather than by reading it.

**A capability could vanish silently.** Programming Fundamentals ranked **first** in one
run and simply did not appear in the diagnostic, because no scenario is authored for it.
A capability disappearing with no explanation is indistinguishable from a scoring bug, so
`Diagnostic.skipped_no_scenario` now records them and the CLI reports:

```
Ranked high but no scenario authored yet: Programming Fundamentals, Testing, Git
(a content gap, not a scoring decision — see --coverage)
```

**Secondary coverage was treated as full coverage.** A scenario's `also_exercises` list
marked those capabilities as covered, which let Trade-off Analysis lose its own primary
slot because one chosen scenario touched it in passing. Now secondary coverage applies a
**0.70 discount** and the ranking is recomputed after each pick, rather than excluding
outright.

---

## 8. Scenario coverage

12 of 17 capabilities have a scenario targeting them. Missing: Programming Fundamentals,
Data Structures, Algorithms, Testing, Git.

That is a **content gap, not an engine gap** — and it overlaps almost exactly with the
seven capabilities the knowledge corpus cannot teach either (Phase 1 §7). The same five
capabilities lack both material and scenarios, which is worth knowing before Phase 7
assumes the corpus can support a gap it detects.

```bash
python diagnose.py --coverage
```

---

## 9. What Phase 5 does not do

- **No scoring.** A `Diagnostic` is persisted with `status: "pending"` and no responses.
- **No mastery updates.** Nothing touches `StudentCapability`.
- **No rubrics.** Phase 6 authors them, against `probes`.
- **No Gemini.** See §6.

---

## 10. How to test it

No LLM, no network, no API key.

```bash
python onboard.py --save --student-id student-001   # a profile to diagnose
python diagnose.py                  # the diagnostic, with why-these and the scenarios
python diagnose.py --ranking        # every capability scored, all six factors
python diagnose.py --explain        # per-selection breakdown
python diagnose.py --coverage       # which capabilities have scenarios
python diagnose.py --save           # persist as pending
python diagnose.py -n 2             # ask for fewer capabilities
```

The sharpest check is `--ranking`: every number that produced the selection is on screen,
and the `·` markers should mark exactly those capabilities whose prerequisites are unproven.

---

## 11. Next — Phase 6, Evidence + Assessment

§11 and §21 Phase 6:

```
Student Response -> Evidence -> Rubric -> Gemini Evaluation -> Assessment -> Capability Update
```

§11 is explicit that this must **not** be "ask Gemini how good is this student". It needs
structured rubric criteria, per capability, like §11's example:

```json
{"capability": "scalability",
 "criteria": ["recognizes traffic growth", "identifies bottlenecks",
              "considers horizontal scaling", "considers database constraints",
              "considers cost", "explains trade-offs"]}
```

This is where Gemini finally earns its place — not deciding a score, but judging a
response against **authored criteria**, returning structured JSON per criterion. The
arithmetic from criteria to mastery stays deterministic, and the evidence is preserved
(§11: "Do not create a single opaque AI score as the student's identity").

Two things to settle first: whether rubric criteria are authored per scenario or per
capability (the `probes` field suggests per scenario, hitting capability-level dimensions),
and how a criterion judgement becomes a mastery number — which must be inspectable, since
it is the one place a model's output moves a student's profile.

---
---

# Part two — evidence and assessment (Phase 6)

**Status:** Phase 6 complete.
**Owns:** Claude.md §21 Phase 6, §11, §14.

```
Student Response -> Evidence -> Rubric -> Evaluation -> Assessment -> Capability Update
```

---

## 12. What was built

```
data/diagnostics.yaml              EDIT  + 62 rubric criteria across the 12 scenarios
cognith_student/evidence.py     NEW   Verdict, CriterionResult, Evidence, Assessment,
                                         GeminiEvaluator, ManualEvaluator, the arithmetic
assess.py                          NEW   CLI
data/evidence/<student>.json       NEW   append-only evidence log
students.py                        EDIT  default profile (see §19)
```

---

## 13. What §11 forbids, made structural

> "Do NOT simply ask Gemini: 'How good is this student?'"
> "Do not create a single opaque AI score as the student's identity."

The division of labour is enforced by what each side can see, not by prompt discipline:

| | Gemini | Us |
|---|---|---|
| Judges one criterion at a time | ✓ | |
| Sees the student's profile, claimed confidence, or mastery | **never** | |
| Returns a score, a mastery value, or an overall verdict | **never** | |
| Computes capability scores from judgements | | ✓ |
| Computes the mastery update | | ✓ |
| Writes the explanation | | ✓ |

The model is given the scenario, the response, and the criteria. Nothing else. There is
nothing for it to anchor on and no way for it to produce "how good is this student" even
if asked.

**The test of whether that is real:** `ManualEvaluator` produces the same structures from
human judgements, and every downstream number is identical. If the model were removed the
system would still work — it would just need a person to judge the criteria. An AI doing a
bounded job can be swapped for a human doing the same bounded job; an AI holding the
system up cannot.

---

## 14. Rubrics live with their scenario

62 criteria, authored inside each `items:` entry in `data/diagnostics.yaml`.

```yaml
- id: scale-api-001
  capability: scalability
  rubric:
    - id: measure-first
      criterion: Says they would measure or profile to locate the bottleneck before changing anything
      capability: scalability
      weight: 1.5
    - id: db-constraint
      criterion: Identifies the database as a likely constraint and gives a reason (connections, CPU, contention)
      capability: database-performance
      weight: 1.0
    - id: names-downside
      criterion: Names a specific way their own chosen approach could fail or fall short
      capability: trade-off-analysis
      weight: 1.5
```

Two reasons for this shape.

**Not a separate file.** A criterion like *"identifies the database as the likely first
bottleneck"* is meaningless apart from the scenario that sets up the bottleneck. Keeping
them together is the same argument that kept scenarios out of a model's hands
([decisions.md](decisions.md) D22): a question and its rubric are one artefact and must not
drift.

**Each criterion names the capability it evidences.** That is how one scenario produces
evidence for several capabilities — finally cashing in `also_exercises`. §11's rubric
example is keyed by capability; this reaches the same place from the other direction, and
lets a single 10-minute answer move three capabilities at once.

Across the bank, Trade-off Analysis has 12 criteria spread over 8 scenarios, which is what
a genuinely cross-cutting capability should look like.

---

## 15. Judgement, then arithmetic

§14 already specifies the scale, writing it as `✓ △ ✗`:

```
met 1.0   partial 0.5   unmet 0.0
```

`partial` carries weight: it is for a response that names the right thing without the
reasoning the criterion asks for. §10 wants reasoning tested rather than recall, and
`partial` is where that distinction is actually made.

```
capability score = Σ(weight × verdict) / Σ(weight)   over criteria tagged with it
alpha            = max(1 / (n + 1), 0.35)
blended          = mastery_old × (1 − alpha) + score × alpha
mastery_new      = min(blended, ceiling(n + 1))
ceiling(n)       = min(1.0, 0.55 + 0.15 × n)
```

**Why the recency floor (0.35).** A plain running mean lets three-month-old evidence
outvote what a student just demonstrated. That is wrong for a *learning* platform — people
improve, and the recent observation is the better estimate of what they can do now.

**Why the ceiling — found by testing, not design.** The first live Gemini run on a strong
response scored every criterion `met`, and mastery came out at **100%**. One scenario
cannot establish mastery, and §6.2 says so directly: *"Do NOT treat mastery as an absolute
truth."* The ceiling fixes it:

| Evidence | Ceiling | A flawless student reaches |
|---|---|---|
| 1 | 0.70 | 0.70 — exactly `DEMONSTRATED_AT`, and no further |
| 2 | 0.85 | 0.85 |
| 3 | 1.00 | 0.90 |
| 4 | 1.00 | 0.94 |

One excellent answer earns "demonstrated" and nothing more. The ceiling **only caps** — a
weak answer scoring 0.12 stays at 0.12 however many times it is repeated.

---

## 16. §14's "explain WHY it changed"

Assembled deterministically from which criteria were met and unmet. No second model call:
we already know exactly which criteria carried, and asking a model to narrate that would
add cost, latency, and a chance of contradicting the data.

```
Scalability measured at 70% for the first time. You showed recognises that 100x growth
changes which component fails first, rather than treating it as 'more of the same'; says
they would measure or profile to locate the bottleneck before changing anything.
```

A first measurement says *"measured at X for the first time"* rather than *"rose"* or
*"held steady"* — there was nothing to move from, and implying otherwise would suggest
prior evidence that does not exist.

---

## 17. It works, and it discriminates

Tested live against Gemini on two responses to the same scenario. The weak one is
deliberately plausible — it names the right technologies with no reasoning, which is
exactly what §10 says a diagnostic must see through.

**Weak** — *"I would add more servers and use Redis for caching… probably switch to a NoSQL database since those scale better."*

```
✗ Recognises that 100x growth changes which component fails first
    The response does not mention the 100x traffic increase…
△ Identifies the database as a likely constraint and gives a reason
    Gestures at a database scaling issue by suggesting NoSQL "since those scale better",
    but fails to reason about connections, CPU, or contention.
✗ Names a specific way their own chosen approach could fail

Scalability 0.12   Trade-off Analysis 0.00   Database Performance 0.50
```

**Strong** — the response that says it would *measure first*:

```
✓ Says they would measure or profile before changing anything
    The student states they "would not change anything" initially, choosing first to
    "load test against a copy and watch where latency goes non-linear."
✓ Proposes horizontal scaling, and notes it does not help a shared database
    …points out that "makes the database problem worse, not better, because every new
    instance opens more connections."

Scalability 1.00   Trade-off Analysis 1.00   Database Performance 1.00
```

Two things worth noting. Every justification **quotes the response** — there is no verdict
a reviewer cannot check. And Gemini's six judgements on the weak answer matched the six
hand-written `ManualEvaluator` judgements exactly, which is the cheapest available evidence
that the rubric is well-posed rather than that the model is agreeable.

### The end-to-end result

```
BEFORE   Scalability          ░░░░░░░············  claimed         — / 35%
AFTER    Scalability          █████████████······  under-claimed  70% / 35%
```

The student claimed 35% and demonstrated 70%. The map labels it **under-claimed** — the
diagnostic found they were *better* than they thought, which the two-material bar makes
visible without a word of explanation.

And the next diagnostic has moved on: Scalability, Trade-off Analysis and Database
Performance now have evidence, so the engine selects HTTP, Databases and Reliability
instead. That is the adaptive loop turning one revolution.

---

## 18. Evidence is preserved, and replayable

§11: *"The system should preserve the underlying evidence."*

`data/evidence/<student>.json` is **append-only**. Each entry holds the verbatim response,
every criterion judgement with its justification, and the resulting mastery change.

```
2026-09-22T16:30:09  scale-api-001
   ✓ ✓ ✓ ✓ ✓ ✓
   Scalability                  — -> 70%
   Trade-off Analysis           — -> 70%
   Database Performance         — -> 70%
```

Because the raw response is kept, every number can be **recomputed** if the scoring rules
change — a rubric revision can be replayed against past evidence rather than applied
blindly going forward. Evidence is constructed and stored *before* any number is derived
from it, so the record does not depend on whatever arithmetic was current when it was
collected.

---

## 19. A defect this phase surfaced

`students.py` defaulted to an **in-memory fixture** while `diagnose.py` and `assess.py`
default to the saved `student-001`. So running an assessment and then looking at the map
showed no change — the assessment had worked perfectly and the viewer was reading a
different student.

Fixed: `students.py` now loads the saved profile when one exists and falls back to the
fixture only when it does not. Worth recording because the symptom looked like a data-loss
bug in the assessment path and was actually a CLI default.

A missing judgement is handled with the same instinct: if the model omits a criterion, the
result is recorded as `NOT JUDGED — model omitted this criterion` rather than scored zero.
An API hiccup must not be able to look like a weak student.

---

## 20. How to test it

```bash
python assess.py --rubric scale-api-001    # what a scenario is judged on — offline
python assess.py --demo weak   --manual "db-constraint=partial" --dry-run   # offline
python assess.py --demo strong --gemini --save                             # network
python assess.py --history                 # the evidence log
python students.py                         # the map, updated
```

Only `--gemini` makes a network call. The whole pipeline — scoring, blending, ceiling,
explanation, persistence — is exercisable with `--manual` and no API key.

---

## 21. Next — Phase 7, RAG integration

§21 Phase 7 and §5:

```
Capability Gap -> Relevant Knowledge -> RAG Retrieval -> Gemini -> Learning Experience
```

The gap detection now exists for real: `weakest()` over *demonstrated* mastery, and the
unmet criteria on each piece of evidence, which are far more specific than a capability
name — *"did not say they would measure before changing anything"* points at particular
material in a way *"weak at scalability"* does not.

Three things to settle:

1. **The join.** [decisions.md](decisions.md) D9 established `knowledge_docs`, and noted
   that the existing `Store.search(capability=...)` filter is **not** it — that filters on
   the corpus's coarse tags. Phase 7 needs document-level filtering, which `store.py` does
   not currently expose.
2. **Coverage.** 7 of 17 capabilities have no corpus material at all, and they overlap
   almost exactly with the 5 that have no diagnostic scenario. Phase 7 must handle a
   detected gap the corpus cannot teach — and the RAG system's abstention behaviour
   (architecture.md §7) is already the right mechanism for saying so honestly.
3. **Q3, still open.** The corpus's `prerequisites` frontmatter is read by no code and has
   one dangling reference. Phase 7 is where it either gets used or gets removed.
