# Learning experiences

**Status:** Phase 8 complete.
**Last updated:** 2026-09-22 (Phase 8)
**Owns:** Claude.md §21 Phase 8, §6.3. Phase 9 (Mission) extends this file.

> "A learning experience is something the student does. Each experience should connect to
> one or more capabilities." — §6.3

---

## 1. What was built

```
data/exercises.yaml                      rubrics for the 7 exercises already in the corpus
cognith_learning/experience.py        ExperienceType, LearningExperience, ExperienceLibrary
practice.py                              CLI
cognith_student/evidence.py     EDIT  one Protocol, so assess() takes any experience
assess.py                          EDIT  resolves any experience id, not just diagnostics
learn.py                           EDIT  offers assessable practice, not raw chunks
```

---

## 2. The problem, stated plainly

By Phase 7 the system had three kinds of thing a student could encounter, and **none of
them knew about the others**:

| | Where | Assessable? |
|---|---|---|
| Diagnostic scenarios | `data/diagnostics.yaml` | yes — prompt + rubric |
| Corpus exercises | `knowledge/*.md`, `kind: exercise` | **no** |
| Explanations | produced at request time by the RAG layer | no, and correctly so |

The seven corpus exercises were the sharp edge. They are good — real situations demanding
a decision and a justification — and they had been **visible since Phase 7 and impossible
to do**. `learn.py` would list them as "practice available" and there was no way to
practise.

Phase 8 is not a new content system. It gives the existing things one shape.

---

## 3. Three types, not nine

§6.3 lists nine possible types. §21 Phase 8 asks for "the minimum experience types required
for the MVP", and §22 lists "Full LMS" among the non-goals.

| Type | Count | Produces evidence |
|---|---|---|
| `explanation` | on demand | **no** |
| `exercise` | 7 | yes |
| `diagnostic` | 12 | yes |
| `mission` | Phase 9 | yes |

§16's progression — explain, example, small practice, guided challenge, independent
challenge, realistic mission — is covered by these. The remaining six names in §6.3 (quiz,
coding challenge, case study, project, reflection, interactive example) would add
vocabulary without adding behaviour: each would be an experience with a prompt and a
rubric, which is what `exercise` already is.

`mission` is declared now, unimplemented, so Phase 9 slots in rather than retrofits.

### Explanation deliberately produces no evidence

§6.5 defines evidence as **observable proof**, and there is nothing to observe in having
read something. An explanation has no rubric and no `assessable` flag, and `learn.py` says
so on screen:

> Reading an explanation produces no evidence. Answering one of these does.

This is the distinction §4 draws between Cognith and a content platform — content
completion is not capability.

### Exercise vs diagnostic

Identical in form, different in **intent**: a diagnostic is chosen to resolve uncertainty
(Phase 5's selection policy), an exercise is chosen to close a known gap. The same code
assesses both, which is the point.

---

## 4. The data model

```python
@dataclass(frozen=True)
class LearningExperience:
    id: str
    type: ExperienceType
    title: str
    capability_id: str              # primary
    prompt: str
    rubric: tuple[RubricCriterion, ...] = ()
    level: Level
    minutes: int
    source: str
```

`capability_ids` is **derived from the rubric**, not stored — so the capabilities an
experience claims to exercise and the capabilities it can actually evidence cannot
disagree. `assessable` is simply "has a rubric".

### The shape is deliberately `DiagnosticItem`'s

`id`, `capability_id`, `prompt`, `rubric` — exactly what Phase 6's `assess()` consumes.
So making exercises assessable required **no change to the assessment code**. The entire
edit was replacing a concrete type with a Protocol:

```python
class Assessable(Protocol):
    id: str
    capability_id: str
    prompt: str
    rubric: tuple[RubricCriterion, ...]
```

Structural rather than a base class, so `cognith_student` never learns that exercises
exist. Phase 9's mission will satisfy the same Protocol.

---

## 5. Exercise prose stays in the corpus

`data/exercises.yaml` is keyed by **chunk id**, and the prompt is read from the corpus at
load time:

```yaml
- chunk: database-indexing.md#exercise-diagnose-the-slow-query
  title: Diagnose the slow query
  capabilities: [database-performance, trade-off-analysis]
  rubric:
    - id: leading-column
      criterion: Explains that the index is unusable because the query does not filter on its leading column
      capability: database-performance
      weight: 2.0
```

Copying the prose into the rubric file would create two versions of each exercise, and
editing `knowledge/*.md` would silently stop matching. Same reasoning as D25 keeping
diagnostic rubrics inside their scenario — here the id is the join, and the loader
**verifies it resolves**:

```
exercise 'foo.md#bar' is not in the index — re-run `python ingest.py`,
or the section was renamed
```

The dangling-reference discipline every phase has applied since Phase 1.

### And the capability tags are restated

Each entry lists `capabilities` explicitly because the corpus's own `capability:`
frontmatter is too coarse (D9) — the caching exercise is tagged `system-design`, which is
three documents wide. 30 criteria across 7 exercises, each naming the capability it
evidences.

---

## 6. Selection is weighted, not just tagged

`practice_for(capability)` ranks by **how much of each rubric actually evidences that
capability**:

```
$ python practice.py --for database-performance

  Diagnose the slow query (primary)
      exercise, intermediate, 10 min   — 5.0 of 6.5 rubric weight evidences this capability
  Route the reads
      exercise, intermediate, 8 min    — 3.0 of 6.0 rubric weight evidences this capability
  Defend a decision
      exercise, advanced, 12 min       — 1.5 of 7.5 rubric weight evidences this capability
```

An experience whose primary target is something else still counts. That is the same
criterion-level tagging from D25 that lets one answer move several capabilities, now
applied to **selection** as well as to scoring.

---

## 7. It works end to end

A student who had answered the diagnostic poorly (Database Performance 25%) then did the
corpus exercise:

```
✓ Explains that the index is unusable because the query does not filter on its leading column
    "a composite index can only be used from its leading column onward" and the query
    lacks a predicate on "customer_id"
✓ Proposes an index the query could actually use, on created_at
✓ States the write-path cost — every insert and update must also maintain the new index
✓ Names a concrete situation where they would decline to add it
    the query runs "once a month for a report while orders is taking heavy sustained writes"

capability                score   before   after   change
Database Performance       1.00      25%     62%   +0.38
Trade-off Analysis         1.00 unmeasured     70%   +0.70
```

25% → 62%, not → 100%: the weak first attempt is blended in, and two pieces of evidence
cap at 0.85 (D24). The exercise is corpus prose that had been unusable an hour earlier, and
it moved two capabilities.

---

## 8. Coverage — the same five, again

```
12 of 17 capabilities can produce evidence.
No experience at all: Programming Fundamentals, Data Structures, Algorithms, Testing, Git
```

These are **the same five** with no corpus material (architecture.md §13) and no diagnostic
scenario (assessment.md §8). Three separate coverage reports, arrived at independently,
naming the identical set.

That is worth stating plainly before Phase 10: a capability with no experience cannot be
assessed and cannot be taught, so it **cannot enter the loop at all**. The adaptive loop
must not silently exclude them or, worse, recommend them and then have nothing to offer.

---

## 9. How to test it

No LLM, no network for any of this.

```bash
python practice.py                       # all 19 experiences, grouped by type
python practice.py --for scalability     # what would evidence one capability
python practice.py --show 'http.md#exercise-read-a-failing-request'
python practice.py --coverage
python practice.py --next --student demo # practice for the weakest demonstrated gap
python assess.py --rubric 'rest-api.md#exercise-critique-an-endpoint'
```

Then to actually do one (this part calls Gemini):

```bash
python assess.py --item 'database-indexing.md#exercise-diagnose-the-slow-query' \
                 --response-file answer.txt --gemini --save
```

The sharpest check is that `assess.py --rubric ID` works identically for a diagnostic id
and an exercise id. They go through the same code.

---

## 10. Next — Phase 9, the flagship mission

§12 and §21 Phase 9: **Scale a Backend API**. 100 → 10,000 req/sec, under 200ms, under
$2,000/month.

The difference from everything so far: a mission has **state and consequences**. §13 is
emphatic —

> "Do NOT let Gemini randomly decide the consequences of every student action. Mission
> mechanics should be deterministic where possible."

So the simulation is a rule table: add app servers → capacity up, database load up; add
replicas → read capacity up, write bottleneck remains. Gemini's role stays exactly where
D23 put it — judging the learner's *reasoning* against rubric criteria, never deciding what
the system does.

Two things to settle first: whether a mission is one `LearningExperience` with a rubric
over the whole session, or a sequence of decisions each producing evidence; and how the
simulation state is represented so consequences are inspectable rather than buried in code.

---
---

# Part two — APPLY (Phase 12)

**Status:** Phase 12 complete.
**Owns:** the rung between practice and mission.

---

## 11. Correcting part of D29

D29 collapsed §6.3's nine experience types to three, arguing the middle names in §16's
progression — *small practice → guided challenge → independent challenge → realistic
mission* — were vocabulary rather than behaviour.

That was right about most of them and **wrong about one**. `APPLY` carries behaviour the
others do not, and the difference is not a matter of size:

| | Scope | What the question tells you | State |
|---|---|---|---|
| `exercise` | one capability | **the lever is named in the prompt** | none |
| `apply` | **several, combined** | **nothing — you decide what is relevant** | none |
| `mission` | several, plus a budget | nothing | **yes, decisions compound** |

A practice exercise says *"Explain why the existing index does not help."* An apply
scenario says *"Checkout got slow. Here is what you know."* — **and indexing might not be
the answer.** Working out *which* lever applies is a capability practice cannot test,
because practice puts the lever in the question.

---

## 12. The readiness gate

`requires` lists the capabilities an apply scenario integrates, and it unlocks only when
**each of them has evidence**:

```
fresh:  0 of 4 unlocked
    Checkout got slow      locked — no evidence yet in Database Performance, Debugging, Caching

demo:   2 of 4 unlocked
    Checkout got slow            UNLOCKED
    An API two teams disagree    locked — no evidence yet in API Design, HTTP, Authentication
```

That gate is what makes the four stages a **ladder rather than a menu**. You cannot
integrate what you have not practised.

**Evidence, not mastery.** You may have practised something and done badly; integrating it
is still a reasonable next move, and often the thing that reveals *why* you did badly.
Requiring demonstrated mastery would make apply unreachable for exactly the learners it
helps most.

---

## 13. The ladder in the loop

```
LEARN → PRACTISE → APPLY → MISSION → (milestone complete) → NEXT LEVEL
```

One slot in the plan is reserved for the highest rung the learner has **earned**, and
`APPLY` takes precedence over `MISSION` — a learner who has not yet integrated several
capabilities without scaffolding is not ready for one that also carries state and a budget.

```
  1. [do]    Diagnose uneven load                    ~8 min
  2. [read]  Read up on Trade-off Analysis
  3. [apply] Checkout got slow                       ~15 min
        You have evidence in Database Performance, Debugging, Caching. This
        combines them, and nothing in the question tells you which one matters —
        working that out is the part practice cannot test.
```

Completed rungs are read from the Phase 6 evidence log, so the ladder **advances rather
than loops** — after finishing "Checkout got slow" the plan offered "A spike you did not
plan for".

Level progression needs nothing new: Phase 11's milestones already advance when their
requirements are demonstrated, and apply scenarios produce evidence like any other
experience.

---

## 14. It tests what it claims to

A strong answer to *Checkout got slow* — a scenario where the obvious fixes are wrong:

```
✓ Recognises that 40% more volume and 37% more rows do not explain a 13x latency increase
    "40% more traffic and 37% more rows should cost maybe 1.5x, not 13x"
✓ Considers lock contention on the constantly-written stock table, not only read volume
✓ Treats the existing catalogue cache as something to check rather than assume is helping
    "suspicious of rather than reassured by" — synchronised expiry could stampede at peak
✓ Explicitly says why adding an index or more cache may not be the fix here
    "the one thing you cannot cache is the thing that is slow"
✗ Gives an order of investigation where each step rules something out
    reasons well, but does not lay out a sequential method

Debugging             0% -> 29%
Database Performance 66% -> 78%
Trade-off Analysis   56% -> 72%
```

The `✗` is the useful one. The answer was strong on *judgement* and weak on *method*, and
those are separable — which is the whole reason for criterion-level rubrics (D25). One
15-minute answer moved three capabilities.

---

## 15. Validation

Two rules beyond the usual capability-reference check:

```
- application 'x' references unknown capability 'not-a-capability'
- application 'y' requires nothing — an apply scenario that integrates nothing is an exercise
```

The second is a design rule expressed as a validation: an apply scenario with no `requires`
has no readiness gate and integrates nothing, which makes it an exercise wearing the wrong
label.

---

## 16. How to test it

```bash
python practice.py                            # 29 experiences across 5 types
python practice.py --show apply-slow-checkout
python assess.py --rubric apply-traffic-spike
python cognith.py --student demo           # the ladder, with the earned rung
python cognith.py --student demo --backlog # what is locked and what would unlock it
python cognith.py --student demo --loop    # now includes an Apply stage
```
