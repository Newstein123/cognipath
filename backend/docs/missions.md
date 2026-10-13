# Missions

**Status:** Phase 9 complete — the flagship mission.
**Last updated:** 2026-09-22 (Phase 9)
**Owns:** Claude.md §21 Phase 9, §12, §13, §23.

> "A mission is a realistic problem or situation where the learner must make decisions."
> — §6.4

---

## 1. What was built

```
data/missions.yaml                  the mission, its model parameters, actions, rubric
cognith_learning/mission.py      MissionState, Metrics, MissionEngine — the simulation
mission.py                          CLI
data/missions/<student>__<id>.json  session state and transcript
cognith_learning/experience.py   EDIT  missions registered as experiences
```

---

## 2. What makes a mission different

Everything before this was a question. A mission has **state**: the system changes as the
learner acts, and later decisions are made against a system their earlier decisions
produced. Adding servers before a load balancer is not a wrong answer to be marked — it is
a system with idle servers, which the next decision has to live with.

That is why §23 describes the demo as *"student investigates and makes architectural
decisions… system shows consequences… student adapts."* Adaptation needs something to
adapt to.

---

## 3. The simulation is arithmetic, not a model

§13 is the constraint that shaped this phase:

> "Do NOT let Gemini randomly decide the consequences of every student action. Mission
> mechanics should be deterministic where possible."

Nothing in `cognith_learning/mission.py` calls a model. The whole simulation is one
readable function over parameters in `data/missions.yaml`:

```
usable_servers   = app_servers if load_balancer else 1
app_capacity     = usable_servers × 2500
effective_reads  = rps × 0.85 × (0.15 if cache else 1.0)
read_capacity    = tier.reads × (1 + replicas)      # replicas add READS only
write_capacity   = tier.writes                      # §13: "write bottleneck remains"
db_util          = max(read_util, write_util)
latency          = 40ms + 115ms / (1 − db_util)     # queueing, not a line
```

`evaluate()` is deliberately **not** split across helpers. §13 wants mission mechanics
*controlled* by application logic, and logic assembled from six places is not controlled,
it is merely located.

Every action declares its own effects and its own **authored** consequence text, so the
learner gets the same honest account every time:

```yaml
- id: add-replica
  effect: {replicas: 1}
  consequence: |
    Read capacity increases. The write bottleneck remains — replicas take no writes.
    Reads served from a replica may be slightly stale.
```

### The latency curve is the lesson

`115 / (1 − util)` rather than a straight line. The system is fine until it is not: at 45%
utilisation the database contributes 209ms; at 90% it contributes 1,150ms. `--explain`
shows the arithmetic, because a simulation whose consequences cannot be explained teaches
the wrong thing.

---

## 4. Calibration is the acceptance test

§12 states the starting system exactly, so the model can be checked against it. `python
mission.py --calibrate` runs offline and exits non-zero on any mismatch:

```
§12's starting system: 100 req/sec, 250ms, 45% database CPU, $500/month

  served req/sec     want    100   got   100.0   ok
  latency ms         want    250   got   249.4   ok
  database CPU %     want     45   got    45.0   ok
  cost $/month       want    500   got   500.0   ok
```

It then checks that **every single-lever strategy fails**, which is §13's set of rules
turned into assertions:

| Strategy | Result | Why |
|---|---|---|
| application servers alone | 222 rps, 5790ms | adding servers does not relieve the database |
| servers + load balancer | 222 rps, 5790ms | the database is still the binding constraint |
| biggest database, no cache | 6,671 rps, 5790ms | cannot reach 10,000 without reducing read volume |
| replicas instead of a cache | 10,000 rps, 193ms, **$4,860** | works, and blows the budget |
| spend everything | 10,000 rps, 190ms, **$4,980** | more is not better |
| **servers + balancer + cache + large db** | **10,000 rps, 190ms, $1,680** | the intended solution |

There is **exactly one affordable path**: reduce read volume with a cache, then buy the
database capacity the remaining writes need. Caching is not the fast answer, it is the
*only* answer that fits the budget — and that is arithmetic, not a model's opinion.

---

## 5. A mission is one experience

`LearningExperience(type=MISSION)` with the brief as its prompt and the mission rubric.
Because that satisfies the `Assessable` protocol from D30, **Phase 9 required no change to
the assessment layer at all** — the same `assess()` that scores a diagnostic scores a
mission.

The response is the **session transcript**: every investigation, every decision, the
reasoning given for it, and the consequence that followed.

```
2. DECISION: Put a load balancer in front
   REASONING: so the extra servers actually receive traffic
   RESULT: Traffic can now be distributed across application servers...
   SYSTEM NOW: 5790ms at 10,000 req/sec, $860/month, serving 222 req/sec
```

§6.5 wants decision and reasoning preserved; the transcript preserves them verbatim.
Assessing each decision separately would need a rubric and a model call per decision, for
a worse result — the capability §12 tests is the **shape of the whole plan**, which no
individual step shows.

### Investigation is free, and recorded

§23 says the student *investigates* before deciding. Four investigations cost nothing and
are logged, because whether someone looked before acting is itself evidence — the first
rubric criterion is exactly that.

---

## 6. What the assessment caught

A learner solved the mission — 10,000 rps, 190ms, $1,680, all three requirements met — and
still scored `△` and `✗` on three criteria. Two are worth quoting.

**It read the order of decisions, not just the outcome:**

> △ *Identified the database as the binding constraint*
> "The student noted the database was the slowest component at 115ms, but still prioritized
> scaling the application tier across steps 3 to 6 before addressing the database."

Only the transcript reveals that. A final-state check would have passed it.

**It refused to credit the student for something the simulation said:**

> ✗ *Acknowledged cache invalidation or staleness as a cost*
> "The student never mentioned cache invalidation or staleness in their reasoning; **it
> only appeared in the system-generated result text.**"

The authored consequence for `add-cache` says invalidation is now a consideration. The
model distinguished the system's words from the learner's, and gave no credit. That is
precisely the boundary D23 draws — the model judges what the student demonstrated, and the
simulation is not the student.

### And a capability went down

```
capability                score   before   after   change
Scalability                1.00 unmeasured     70%   +0.70
Load Balancing             1.00 unmeasured     70%   +0.70
System Design              1.00 unmeasured     70%   +0.70
Caching                    0.60 unmeasured     60%   +0.60
Database Performance       0.71      62%     66%   +0.03
Trade-off Analysis         0.43      70%     56%   -0.14
```

Trade-off Analysis **fell**. The learner had scored well on it in an earlier exercise, but
their mission reasoning never named what the architecture gives up. The recency-weighted
blend (D24) reflects that rather than keeping the flattering earlier number. A profile that
can only go up is not a measurement.

---

## 7. How to test it

Everything except `--submit --gemini` is offline.

```bash
python mission.py --calibrate                  # the acceptance test, exits 1 on mismatch
python mission.py --brief                      # the situation, current state, options
python mission.py --student me --investigate request-mix
python mission.py --student me --act add-cache --why "reads are 85% of traffic"
python mission.py --student me --status
python mission.py --student me --explain       # the latency arithmetic
python mission.py --student me --transcript
python mission.py --student me --submit        # preview what would be assessed
python mission.py --student me --submit --gemini   # judge it, update capabilities
python mission.py --student me --reset
```

`--act` without `--why` is refused. §12: *"The learner must explain why they made the
decision"* — a decision with no stated reason produces nothing assessable, so the CLI will
not record one.

---

## 8. Next — Phase 10, the adaptive loop

Every piece now exists:

```
Goal -> Onboarding -> Initial map -> Diagnostic -> Evidence -> Profile
     -> Gap -> Knowledge -> Practice -> Mission -> Evidence -> Updated profile -> ?
```

The `?` is Phase 10, and it is the only thing left: **nothing recommends the next step.**
The learner picks the command. §15's loop ends with "Select Next Experience", and that
selector does not exist.

Everything it needs is built — `gaps()`, `unverified()`, `calibration_gaps()`,
`blocked()`, `prerequisite_closure()`, the diagnostic scorer, the experience library, and
corpus coverage. Phase 10 is a **policy over existing signals**, not new machinery, which
is what every prior phase was deliberately leaving room for.

Two things to settle: what the loop does when the best next step for a student is a
capability with no experience and no corpus material — the same five keep appearing — and
whether "next" is a single recommendation or a short ordered plan.
