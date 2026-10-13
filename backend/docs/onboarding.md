# Onboarding

**Status:** Phase 3 complete — §8's intake produces §9's initial capability map.
**Last updated:** 2026-09-22 (Phase 3)
**Owns:** Claude.md §21 Phase 3. Phase 4 (Capability Map) extends this file.

Phase 3 turns five questions into an initial capability profile. That profile is a
**self-report**, not an assessment: it sets `confidence` and leaves every `mastery` as
`None`.

---

## 1. What was built

```
data/onboarding.yaml               levels, goals, technologies, concepts, propagation rules
cognith_student/onboarding.py   OnboardingAnswers, Signal, InitialEstimate, engine
onboard.py                         CLI
```

No existing file changed. Output feeds straight into Phase 2's `CapabilityProfile`, so
`students.py --load` reads an onboarded profile with no glue.

---

## 2. No Gemini in this phase, deliberately

The obvious design is to hand §8's free-text answers to Gemini and ask for capability
estimates. Phase 3 does not, for four reasons:

1. **§26.4 — do not hide important logic inside prompts.** The technology-to-capability
   mapping *is* domain knowledge. It belongs in data next to the capability graph, where
   it can be reviewed and argued with, not inside a prompt string.
2. **§26.7 — preserve provenance.** Every number here can be explained back to the answer
   that produced it: *"Databases 80% because you listed MySQL."* A model's guess cannot be
   traced, and this is the number the student is about to be shown and asked to confirm.
3. **The output is a claim, not a finding.** §9 frames it as "an initial estimate based on
   what you've told us." Inferring beyond what the student actually said makes it less
   clear what they said — and Phase 5 exists precisely to test these claims.
4. **It is free to test.** No API key, no quota, no network.

Gemini's jobs in this product are rubric-based evaluation (Phase 6) and explanation
(Phase 7). Guessing profiles is not one of them.

An LLM extraction layer could be added later *on top* of this, emitting signals with their
own `kind` so its contribution stays separately attributable. Recorded as
[decisions.md](decisions.md) **D15**.

---

## 3. How an estimate is produced

Four steps. Nothing is hidden.

```
§8 answers
    │
    ├── technologies ────────────► DIRECT signals        (table lookup)
    ├── free text ───────────────► DIRECT signals        (phrase match, × 0.85)
    │                                    │
    │                                    ▼
    │                              DERIVED signals       (one hop along the Phase 1 graph,
    │                                    │               discounted per relation)
    ▼                                    ▼
self-rated level ──► ceiling      combine by MAX per capability
                         │                │
                         └────────► cap ──┴──► confidence + provenance
```

### Step 1 — direct signals

Each listed technology contributes a per-capability signal, meaning *"what confidence does
competent use of this technology imply for this capability?"* Values are deliberately
moderate: using a tool is not the same as being able to reason about it.

```yaml
laravel:
  signals: {api-design: 0.75, authentication: 0.70, http: 0.70,
            databases: 0.55, programming-fundamentals: 0.65}
```

Free-text answers (§8's "What do you already know?" and "What have you built?") are scanned
for known phrases and contribute the same signals **discounted to 0.85** — saying "I built
APIs" in prose is a weaker claim than listing a framework. Longer aliases match first, so
`"booking system"` wins over a bare `"system"`.

Unrecognised technologies are **reported, not silently dropped** — the CLI lists them so
the student can see that "COBOL" contributed nothing.

### Step 2 — derived signals, and why direction matters

Signals propagate **one hop** along the Phase 1 capability graph, with a discount per
relation type. The discounts are **asymmetric**, and that asymmetry is the interesting part:

| Relation | forward | backward | Reasoning |
|---|---|---|---|
| `prerequisite_for` | — | 0.90 | If you can design APIs you know HTTP. Knowing HTTP says **nothing** about whether you can design an API, so forward is omitted entirely rather than set low |
| `contributes_to` | 0.70 | 0.60 | A component implies something about the whole, and vice versa |
| `supports` | 0.50 | 0.55 | A supporting technique is weaker evidence either way |
| `applies_to` | 0.50 | 0.80 | Cross-cutting: exercising a capability inside another's context works strongly backward |

**Derived signals propagate only from direct signals, never from other derived ones.**
Without that rule, `Docker → system-design → reliability → testing` would invent a testing
claim the student never made. It is the single most important constraint in the file.

Verified: in §8's example, `trade-off-analysis` = 0.40, computed from System Design's
**direct** 0.50 (Docker) × 0.80 — not from its **derived** 0.525, which would have given
0.42.

### Step 3 — combine by `max`, not sum

```
System Design, from §8's example:
  -> 0.52  derived    API Design --contributes_to--> System Design
     0.50  technology Docker
     0.47  phrase     "booking systems"
     0.24  derived    Reliability --contributes_to--> System Design
```

Summing would give 1.73 → clipped to 1.0, i.e. "you are certainly an expert at system
design" from three weak hints. Max keeps the number defensible and keeps **exactly one
nameable reason** behind it, which is what the UI shows.

### Step 4 — cap by self-rated level

§8's fourth question is "How confident are you?", answered with one level. That level caps
every estimate:

| Level | Ceiling |
|---|---|
| none | 0.10 |
| beginner | 0.45 |
| intermediate | 0.85 |
| advanced | 0.95 |
| expert | 1.00 |

A beginner who lists Laravel does not get 75% API Design. The pre-cap value is retained in
`ceiling_applied` and displayed as *"capped from 70%"*, so the student is never shown a
number lower than their strongest signal with no explanation.

Ceilings are calibrated so that §8's example (Intermediate) can reach §9's highest value,
Databases at 80%.

---

## 4. The spec contains its own acceptance test

§8 gives an example input and §9 gives an example output. So conformance is checkable:

```bash
python onboard.py --verify
```

```
capability                 §9   ours   delta   reason
api-design               0.75   0.75   +0.00   technology: Laravel
databases                0.80   0.80   +0.00   technology: MySQL
authentication           0.70   0.70   +0.00   technology: Laravel
debugging                0.65   0.65   +0.00   technology: PHP
system-design            0.50   0.53   +0.03   derived: API Design --contributes_to--> …
scalability              0.35   0.35   +0.00   derived: Caching --supports--> Scalability
trade-off-analysis       0.40   0.40   +0.00   derived: System Design <--applies_to-- …

max deviation 0.025, tolerance 0.05  ->  PASS
```

Five of seven land exactly. `system-design` comes out at 0.53 rather than 0.50 because
API Design `contributes_to` System Design (0.75 × 0.70 = 0.525) outranks Docker's direct
0.50 — defensible, and arguably better than the spec's own number.

**Two values come from the capability graph rather than the technology table:**
Scalability via `Caching --supports--> Scalability`, and Trade-off Analysis via
`applies_to` backward. Neither is in the table at all. That is Phase 1's graph doing work
Phase 3 would otherwise have had to hard-code, and it is the clearest evidence so far that
storing relationships as data (§7) was worth it.

---

## 5. Data model

```python
@dataclass(frozen=True)
class OnboardingAnswers:
    student_name: str
    goal: str                              # a key in onboarding.yaml `goals`
    technologies: tuple[str, ...] = ()     # §8 Q2
    knows: str = ""                        # §8 Q1 — prose
    built: str = ""                        # §8 Q3 — prose
    self_rated_level: str = "intermediate" # §8 Q4
```

Prose answers are stored **verbatim** as well as scanned. §26.7 — the raw answer is
provenance, and later phases may want what the student actually wrote (a diagnostic's
framing, an assessment's context).

```python
@dataclass(frozen=True)
class Signal:
    capability_id: str
    value: float
    kind: str      # "technology" | "phrase" | "derived"
    source: str    # "MySQL" | '"booking systems"' | "Caching --supports--> Scalability"

@dataclass(frozen=True)
class InitialEstimate:
    capability_id: str
    confidence: float
    chosen: Signal                      # the winning signal
    considered: tuple[Signal, ...]       # everything weighed, strongest first
    ceiling_applied: float | None        # pre-cap value, if the level reduced it
```

`considered` exists so the UI can show not just the winning reason but what else was in
play. That is the difference between a score and an explanation.

### Goals never change estimates

`goals.<id>.focus` lists the capabilities that matter for a goal. It is used **only** to
order and star the capability map. A goal must never inflate a self-report — wanting to be
a backend engineer is not evidence of backend capability.

---

## 6. Validation

Same dangling-reference discipline as Phases 1 and 2. `OnboardingEngine` refuses to
construct if the vocabulary references a capability that does not exist:

```
2 problem(s) in onboarding vocabulary:
  - technologies.php references unknown capability 'not-a-capability'
  - goals.other.focus references unknown capability 'also-not-real'
```

Unknown relation types in `rules.propagation` are rejected too. Unknown goals and levels
are rejected at estimate time with the valid options listed.

A typo would otherwise silently drop a signal, and nothing downstream would notice — the
same failure mode as the corpus's dangling `prerequisites` ([decisions.md](decisions.md) Q3).

---

## 7. What onboarding never does

- **It never sets `mastery`.** Asserted in `build_profile()`. Onboarding produces claims;
  only evidence produces mastery (§6.2, [decisions.md](decisions.md) D12).
- **It never invents a signal.** An empty intake produces **zero** estimates, not sixteen
  zeroes. Capabilities with no signal stay unrated, and `--explain` says so explicitly:
  *"That is an honest absence, not a score of zero."*
- **It never chains derived signals.** See §3 step 2.
- **It never lets the goal affect a number.** See §5.

In §8's example, 13 of 16 capabilities are estimated; Data Structures, Algorithms and Git
are left unrated because nothing in the answers speaks to them.

---

## 8. How to test it

No LLM, no network, no API key.

```bash
python onboard.py                      # §8's example intake -> §9's map
python onboard.py --verify             # conformance against §9, exits 1 on failure
python onboard.py --explain databases  # full provenance for one capability
python onboard.py --explain git        # an unrated capability
python onboard.py --vocabulary         # what is recognised and what it contributes
python onboard.py --interactive        # answer the five questions yourself
python onboard.py --save --student-id student-002
```

### End-to-end with Phase 2

```bash
python onboard.py --save --student-id student-002
python students.py --load student-002 --summary
```

```json
{"capabilities": 16,
 "by_status": {"unknown": 3, "claimed": 13, "developing": 0, "demonstrated": 0},
 "evidence_total": 0, "mean_confidence": 0.557, "mean_mastery": null}
```

13 claimed, **0 demonstrated**, `mean_mastery: null`, and
`students.py --load student-002 --calibration` correctly reports *"nothing assessed yet —
no gap is computable"*. That is §9's premise, holding across the layer boundary without
any special-casing.

### The ceiling, visible

Running `--interactive` and answering *beginner* caps everything, with the reason shown:

```
 * Programming Fundamentals  45%  ███████████·············  technology, capped from 70%
 * Databases                 45%  ███████████·············  technology, capped from 80%
```

---

## 9. Next — Phase 4, Capability Map

§21 Phase 4 and §9: display the profile, **clearly distinguishing self-reported from
demonstrated**. Most of the presentation already exists in `students.py` and `onboard.py`;
Phase 4's real work is making the distinction unmissable rather than merely present, and
deciding how a capability with a claim but no evidence should look next to one with both.

The open question: §9 says the UI should communicate *"this is an initial estimate. Let's
verify it."* — which means Phase 4 needs to point at what Phase 5 will test, without
building Phase 5's selection policy. Phase 2's `unverified()` and `calibration_gaps()` are
the signals available for that.

---
---

# Part two — the capability map (Phase 4)

**Status:** Phase 4 complete.
**Owns:** Claude.md §21 Phase 4 and §9.

---

## 10. The problem Phase 4 actually had to solve

Phases 2 and 3 both already displayed a profile, and both already showed self-reported and
demonstrated side by side:

```
capability                  self-rep  demonstr         status  ev  gap
API Design                       75%         —        claimed   0
```

That satisfies §21 Phase 4 literally — the distinction is *present*. But a reader has to
notice a dash in the second column and work out what it implies. It is legible, not
obvious. And there were now **two renderers drifting apart**, one in `students.py` and one
in `onboard.py`, both encoding §9's most important idea.

So Phase 4 did two things: made the distinction structural rather than columnar, and
collapsed both renderers into one.

---

## 11. Two materials on one axis

```
█  demonstrated        — evidence supports it
░  claimed, unverified — the student's word alone
·  nothing
```

The bar draws demonstrated mastery in solid, then the unverified remainder of the claim in
shade. The result is that **a profile fresh from onboarding renders with no solid blocks at
all**:

```
 * API Design               ░░░░░░░░░░░░░░·····  claimed         — / 75%
 * Databases                ░░░░░░░░░░░░░░░····  claimed         — / 80%
 * System Design            ░░░░░░░░░░·········  claimed         — / 52%

  0 of 16 capabilities verified   (0 assessed, 13 claimed but unchecked)
  81% of this map rests on what you told us, not on what you have shown.
```

And the same three capabilities after assessment:

```
   Databases                ████████████████···  verified       82% / 80%
   API Design               █████████████░·····  verified       71% / 75%
   System Design            █████░░░░░·········  over-claimed   24% / 52%

  2 of 16 capabilities verified   (3 assessed, 10 claimed but unchecked)
  62% of this map rests on what you told us, not on what you have shown.
```

The over-claim on System Design is a **wide band of shade**, not a number the reader has to
subtract. Databases went slightly *past* its claim, so the solid simply runs beyond where
the shade would have ended — no special case needed, and under-claiming reads correctly as
a good outcome.

### The headline number

```
  2 of 16 capabilities verified   (3 assessed, 10 claimed but unchecked)
  62% of this map rests on what you told us, not on what you have shown.
```

One line, because the point of the phase is that a reader should not have to tally 16 rows
to discover that most of their map is unproven. When nothing has been assessed at all, §9's
exact framing is printed verbatim: *"This is an initial estimate based on what you have
told us. Nothing here has been verified yet — let's verify it."*

### Labels are the reader's vocabulary, not the model's

`MasteryStatus` has four values (`unknown`, `claimed`, `developing`, `demonstrated`). The
map shows five labels — `not rated`, `claimed`, `developing`, `verified`, plus
`over-claimed` / `under-claimed` when the gap exceeds 0.15. The data model's vocabulary and
the reader's do not have to match, and forcing them to would have meant either a worse
enum or a worse display.

`NOTABLE_GAP = 0.15` is **presentation only**. Phase 5 owns what counts as a gap worth
acting on.

---

## 12. "Let's verify it" without doing Phase 5's job

§9 says the UI should communicate *"let's verify it"*, which means pointing at something.
`students.py --verify-next`:

```
  Claim sits above the evidence:
    +0.28  System Design            claimed  50%, shown  22%

  Claimed but never checked (boldest claim first):
     80%  Databases                [foundation]
     75%  API Design               [intermediate]
     65%  Debugging                [intermediate]   — rests on Programming Fundamentals
```

This **orders signals**. It does not select a diagnostic, and it says so on screen:

> This is a signal, not a diagnostic: Phase 5 selects what to actually test, using the
> capability graph and prerequisites as well as these numbers.

§10 is explicit that selection weighs the student's goal, capability relationships,
uncertainty and prerequisites. Putting that here would bury the policy in a display module
— the same boundary Phase 1 kept by not putting propagation weights on edges, and Phase 2
kept by not computing mastery.

The `— rests on` annotation comes free from Phase 2's `blocked()`, and it is quietly
correct: API Design is **not** annotated, because HTTP is demonstrated at 78%.

---

## 13. One renderer

```
cognith_student/capability_map.py     render, render_verification_queue,
                                         render_verified_share, bar, label_for, pct
```

`students.py` and `onboard.py` both call it. Their own map-drawing code is gone —
`onboard.py`'s `bar()` was deleted and its `pct()` now imports from the renderer.

This edits two existing files, which earlier phases avoided. It is in scope rather than the
unrelated refactoring §26.10 forbids: **display is exactly what Phase 4 owns**, and those
files contained display code this phase supersedes. No data-layer file was touched —
`models.py`, `profile.py`, `onboarding.py`, `graph.py` and both YAML files are unchanged,
and `onboard.py --verify` still passes §9 conformance at the same 0.025 deviation, which
confirms the change was presentational.

The numeric table survives as `students.py --table`, because it carries evidence counts the
bar does not.

---

## 14. What Phase 4 is not

- **Not a web UI.** §18 specifies React/Next.js eventually, but there is no backend to
  serve one (decisions.md Q2), and §22 lists dashboards among the non-goals. A frontend now
  is the premature infrastructure §26.9 warns against. The renderer returns strings, so
  whatever renders the map later consumes the same structure.
- **Not a dashboard.** One map, one verification queue.
- **Not a decision.** Nothing here chooses, scores, or updates anything.

---

## 15. How to test it

```bash
python onboard.py                          # the map, straight out of onboarding — all shade
python students.py                         # the map for a saved profile
python students.py --verify-next           # §9's "let's verify it"
python students.py --table                 # the numeric view, with evidence counts
python students.py --load student-002      # an onboarded profile
python onboard.py --verify                 # §9 conformance, unchanged by Phase 4
```

The clearest single check is running `python onboard.py` and confirming there is **not one
solid block** anywhere in the output. That is the phase working.

---

## 16. Next — Phase 5, Diagnostic Engine

§10 and §21 Phase 5: select a small number of capabilities to verify, then produce a
diagnostic that tests **reasoning rather than recall**.

Everything it needs as input now exists: `unverified()`, `calibration_gaps()`, `blocked()`,
`prerequisite_closure()`, per-capability `level`, and the goal's `focus` list. Phase 5's
own work is the **selection policy** that weighs them — deliberately left unwritten by
Phases 1–4, each of which surfaced a signal and refused to act on it.

The design question to settle first: §10's example diagnostic is a written scenario
("traffic goes from 100 to 10,000 req/sec — what do you investigate first?"). Generating
those is the first genuine use for Gemini in this system. The constraint from §26.4 is that
*which capabilities to test* must stay deterministic and inspectable; only the prose of the
scenario should come from a model, and the rubric it will be judged against (Phase 6) has
to be authored, not generated alongside it.
