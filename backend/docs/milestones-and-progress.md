# Milestones and progress

**Status:** Phase 11 complete — "where do I want to reach?" and "how far have I come?"
**Last updated:** 2026-09-23 (Phase 11)
**Owns:** the outer loop. Not in Claude.md's phase list — requested after Phase 10.

Phases 1–10 built the inner loop: learn, practise, apply, evidence, demonstrated?, next
capability. This phase adds what surrounded it — a **destination**, progress toward it, and
the level progression that follows from completing one.

---

## 1. Why it changes more than a progress bar

The stated purpose was *"to know the user well and how far he had reached before asking
questions."* That last clause is the design.

Before this, a goal did almost nothing:

```python
focus_for("backend-engineer")  # -> a list of capability ids
goal_relevance = 1.0 if cap.id in focus else 0.0   # 0.15 of the diagnostic score
```

Membership, binary, with no notion of how much of a capability the goal actually needs. So
the system could say *what to do next* but not *how far along you are*, and — more
importantly — it could not tell which question was worth asking.

A milestone supplies a **target mastery per capability**, and a target gives a distance.
Distance makes progress computable, and computable progress is what makes a question
valuable: the most informative thing to test is a requirement the learner **claims** and
nothing has **checked**, because that is where the progress estimate is most likely wrong.

---

## 2. What was built

```
data/milestones.yaml                      5 milestones across 4 goals
cognith_capability/milestone.py        Requirement, Milestone, MilestoneMap
cognith_student/progress.py            RequirementState, MilestoneProgress
milestones.py                             CLI
data/diagnostics.yaml               EDIT  + 5 scenarios (see §7 — this was mandatory)
cognith_student/diagnostic.py    EDIT  relevance map replaces the focus list
diagnose.py, cognith_learning/loop.py  EDIT  steer toward the active milestone
```

Layering holds: `milestone.py` knows nothing about students, `progress.py` joins the two,
and `diagnostic.py` never learns what a milestone is — it takes a `dict[str, float]`.

---

## 3. The model

```yaml
- id: backend-foundations
  goal: backend-engineer
  level: 1
  requires:
    - {capability: http,           target: 0.70}
    - {capability: authentication, target: 0.60}
- id: backend-at-scale
  level: 2
  after: backend-foundations
```

**Targets are not uniformly 0.70.** `DEMONSTRATED_AT` is the bar for calling a capability
demonstrated at all; a milestone may want more of a central capability and less of a
supporting one. Authoring them identically would waste the distinction.

**"Level" needs no separate concept.** `after` chains milestones, and a level is a
milestone whose predecessor is complete. That is the `NEXT LEVEL` box, with no new type.

Six validations, same discipline as every loader since Phase 1: unknown capability,
duplicate requirement, target outside (0, 1], empty milestone, unknown predecessor, and a
**chain loop** — which would make "next level" non-terminating.

---

## 4. Two numbers, never one

```python
demonstrated_fraction    # what evidence supports
claimed_fraction         # what is being taken on trust
```

A single percentage would average demonstrated capability together with self-report, which
is the conflation §6.2 forbids and Phase 4's two-material bar exists to prevent. **A
learner who claims everything and has shown nothing is not 80% of the way to a milestone.
They are 0% of the way, with an 80% guess attached.**

The milestone bar reuses Phase 4's encoding exactly — solid demonstrated, shade claimed:

```
Level 1 — Backend Foundations   IN PROGRESS
░░░░░░░░░░░░░░░░░░····  0 of 6 demonstrated, 5 on trust

[?] HTTP                     shown   —  claimed  70%  target 70%   never checked
[?] Databases                shown   —  claimed  80%  target 70%   never checked
[~] Debugging                shown   0%  claimed  65%  target 60%   short by 60%

Level 2 — Backend at Scale   LOCKED — finish Backend Foundations first
█████████░░░··········  3 of 7 demonstrated, 1 on trust
```

That output made something visible immediately: this learner had **demonstrated three
Level 2 capabilities while every Level 1 requirement remained unverified.** They had been
proving advanced things on unproven foundations. Nothing before this could show that.

---

## 5. Four states, ordered by what a test would tell us

| State | Meaning | Diagnostic value |
|---|---|---|
| `demonstrated` | mastery ≥ target | **0.10** — settled |
| `short` | assessed, below target | 0.45 — known; needs work, not testing |
| **`claimed`** | **self-reported, never checked** | **1.00** |
| `unknown` | nothing said, nothing shown | 0.60 |

`claimed` outranks `unknown` deliberately: the learner is *counting on* a claimed
capability, so the progress estimate depends on it. An unknown capability is merely absent.

`MilestoneProgress.relevance()` turns these into per-capability weights for the Phase 5
selector. That one function is where the policy lives — `diagnostic.py` receives numbers
and stays ignorant of milestones.

### The effect on question selection

Same learner, same profile, old flat focus list versus milestone-aware:

```
flat focus list   ->  HTTP, Databases, Reliability
milestone-aware   ->  HTTP, Databases, Authentication
```

Reliability is a **Level 2** capability. Testing it before the foundations are proven is
the wrong question at the wrong time. In the new ranking, Reliability, Testing and
Trade-off Analysis all score **0.00** on goal relevance — out of the current milestone,
correctly ignored.

---

## 6. The outer loop closes

```
now                                  L1 0/6           L2 3/7 LOCKED   active: L1
after demonstrating all 6 of L1      L1 6/6 COMPLETE  L2 3/7          active: L2
after demonstrating all 7 of L2      L1 6/6 COMPLETE  L2 7/7 COMPLETE active: none — GOAL REACHED
```

Completing a milestone unlocks the next; completing the last reaches the goal. The loop
then says so explicitly, because it will still find gaps in capabilities outside the path
and those should read as **optional depth, not unfinished business**:

> Goal reached — Backend Foundations, Backend at Scale complete. Anything below is optional
> depth, not a requirement.

---

## 7. What this phase exposed, and why content had to be written

`milestones.py --coverage` asks a question nothing had asked before: *can each requirement
actually be tested?* The first run:

```
9 requirement(s) block a milestone permanently:
    AI Engineering Foundations   needs Programming Fundamentals
    AI Engineering Foundations   needs Data Structures
    AI Engineering Foundations   needs Algorithms
    Backend Foundations          needs Programming Fundamentals
    Frontend Foundations         needs Git
    Engineering Foundations      needs Testing
    …
```

**Every milestone in the system was impossible to complete.** All five.

The five capabilities with no content had been a known footnote since Phase 5 — three
separate coverage reports named them. With milestones they stopped being a footnote: each
milestone required at least one, so no learner could ever finish anything.

That is a broken feature, not a reporting finding. Five diagnostic scenarios were written
(`prog-fundamentals-001`, `data-structures-001`, `algorithms-001`, `testing-001`,
`git-001`), taking the bank to **17 scenarios and 82 criteria**. Now:

```
17 of 17 capabilities have a scenario targeting them.
17 of 17 capabilities can produce evidence.
Every requirement of every milestone can be tested.
```

The content gap that three phases had reported and none had closed was closed by the
feature that made it consequential.

---

## 8. How to test it

Offline, no LLM.

```bash
python milestones.py --student demo          # the path, with progress and locking
python milestones.py --student demo --verify # what to check next, and why it matters most
python milestones.py --all                   # the whole curriculum
python milestones.py --coverage              # can every requirement be tested?
python cognith.py --student demo          # now names the active milestone
python diagnose.py --student demo            # now aims at it
```

The sharpest check is `--coverage`: it must report that every requirement of every
milestone can be tested. If it does not, some learner has a destination they can never
reach.

---

## 9. Still open

**APPLY.** The requested flow has `LEARN → PRACTICE → APPLY → MISSION`, and D29 collapsed
§6.3's nine types to three. APPLY would be a real fourth — larger than an exercise, smaller
than a full simulation. Not built, because it is a genuine design call and it was not
answered.

**Retry.** Redoing an experience works and re-blends mastery correctly, but nothing records
that it *was* a retry. The system cannot say "you have attempted this twice, try a different
angle" or offer a different experience on the second pass.

**Milestones are authored, not derived.** The three non-backend paths are deliberately thin
(§22 rules out a large career ontology). They exist so a learner choosing another goal gets
a real target rather than nothing — not because that curriculum has been designed.
