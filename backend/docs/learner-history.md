# Learner history

**Status:** Phase 13 complete — retries, and what they reveal.
**Last updated:** 2026-09-23 (Phase 13)
**Owns:** attempt tracking and the learner signals derived from it.

Retrying an experience already worked — mastery re-blended correctly (D24). What did not
exist was any record that it **was** a retry, and that record turns out to be worth more
than bookkeeping.

---

## 1. Why a second attempt is worth more than a first

A first attempt measures a capability. A second attempt measures **the learner**.

| Trajectory | Name | What it means |
|---|---|---|
| `✗ → ✓` | **fixed** | they read the feedback and acted on it |
| `✗ → ✗` | **blind spot** | told exactly what was wrong, and still missed it |
| `✓ → ✗` | **regressed** | the first pass may have been a fluke |

The middle one is the valuable one, and it is invisible without attempt history. Two
learners can sit at identical mastery — one having missed a criterion once, the other three
times. **They need completely different things**, and nothing before this could tell them
apart.

---

## 2. What was built

```
cognith_student/history.py       CriterionTrajectory, ExperienceAttempts, LearnerHistory
cognith_student/evidence.py  EDIT  `attempt`, assigned from the log
learner.py                          CLI
cognith_learning/knowledge.py EDIT blind spots lead the gap query
cognith_learning/loop.py     EDIT  names blind spots; avoids stalled experiences
assess.py                       EDIT  shows what changed since last time
```

Everything is **derived from the evidence log**. Nothing is stored twice, so nothing can
disagree with the record — the same reasoning that made `status` a computed property in
D13.

---

## 3. The learner signal

```
Responds to feedback: 25% — has not been able to act on the feedback given.
```

The share of criteria that were unmet and later became met. It is a statement about the
**learner**, not about any capability: someone who reliably fixes what they are told about
needs feedback, and someone who does not needs a **different explanation**.

It returns `None` rather than `0%` when nothing has been retried. Reporting 0% for a
student who has simply never attempted anything twice would be a lie about them, and this
whole phase exists to avoid exactly that kind of claim.

---

## 4. It found something real immediately

A learner attempted *Read a failing request* twice:

```
Read a failing request    2 attempts   12% -> 38%   improving

FIXED ON RETRY
  △ ✓  Explains that a 400 means the request was rejected, so retrying it unchanged
       is pointless rather than dangerous

BLIND SPOTS — missed 2+ times
  HTTP
      ✗ ✗  Says retrying is not safe here, because a 500 does not tell the client
           whether the order was created
      ✗ ✗  Names non-idempotency as the property of POST that makes the retry risky
```

They improved on the **surface detail** — what a 400 means — and twice missed the
**underlying concept**, idempotency. The score went up and the actual gap did not move.
A single mastery number reports "improving" and hides that completely.

---

## 5. Where it changes behaviour

**Gap queries lead with blind spots.** The retrieval query is built from the first few
unmet criteria, so ordering decides what the knowledge layer goes looking for. A criterion
missed twice now leads:

```
HTTP  (2 blind spots of 3 unmet)
    BLIND SPOT  Says retrying is not safe here, because a 500 does not tell...
    BLIND SPOT  Names non-idempotency as the property of POST that makes...
                Explains that a 400 means the request itself was rejected...
```

**The loop names them.** "You demonstrated 20%" becomes:

> You have missed this more than once: *"Says retrying is not safe here, because a 500 does
> not tell the client whether the order was created"*.

More actionable, and it is the thing the learner has evidence they cannot self-correct.

**Stalled experiences drop down the plan.** An experience retried with no improvement is
unlikely to help a third time — the learner has seen the feedback twice and not moved.
Something else comes first.

**Assessment shows the delta.** After a retry, `assess.py` prints what was fixed, what is
still missing, and what slipped, with the score change.

---

## 6. An older bug this exposed

Gap detection looked up criterion text through `DiagnosticEngine`, which holds **only
diagnostic scenarios**. So unmet criteria from exercises, apply scenarios and missions were
invisible — a learner could fail the same exercise criterion repeatedly and the gap would
carry no detail at all.

It dated from Phase 7, when diagnostics were the only assessable thing. Phase 8 made
exercises assessable and nobody noticed; the first **exercise retry** exposed it. Fixed by
reading from `ExperienceLibrary`, which sees all five types.

```
before:  Debugging   0 unmet criteria
after:   Debugging   3 unmet criteria from 2 experience(s)
```

---

## 7. How to test it

Offline.

```bash
python learner.py --student demo          # what we have learned about them
python learner.py --student fresh --blind # blind spots only
python learner.py --student fresh --log   # every attempt, with per-criterion marks
python cognith.py --student fresh      # the loop, now naming blind spots
```

To create a retry: assess the same `--item` twice. The attempt number is assigned from the
log, so it cannot disagree with what is stored.

---

## 8. Not done

**Blind spots do not yet change what is taught, only what is retrieved.** The gap query
leads with them, but the explanation is still generated against the capability statement
(D27). A lesson written specifically for "you keep missing idempotency" would be better and
is a content question, not an engine one.

**`PERSISTENT_AFTER = 2` is authored judgement.** Two, because the second attempt is the
one where the learner had already been told. Whether three would be a better threshold is
measurable once there is real data, and the evidence log makes that measurement possible.
