"""Evidence and assessment — Claude.md §11, §14 and §21 Phase 6.

    Student Response -> Evidence -> Rubric -> Evaluation -> Assessment -> Capability Update

§11 is explicit about what this must NOT be:

    "Do NOT simply ask Gemini: 'How good is this student?'"
    "Do not create a single opaque AI score as the student's identity."

So the division of labour is structural, not a matter of prompt discipline:

    Gemini judges  ONE CRITERION AT A TIME, met / partial / unmet, with a justification
                   quoting the student. It never sees a mastery value, never returns a
                   score, and never gives an overall verdict.

    We compute     the capability score from the criterion judgements, the mastery update
                   from that score, and the explanation from which criteria were met.
                   All deterministic, all inspectable, all replayable from stored evidence.

If the model were removed entirely, `ManualEvaluator` produces the same structures — which
is the test of whether the AI is doing a bounded job or holding the system up.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from cognith_capability.graph import CapabilityGraph

from .diagnostic import RubricCriterion
from .models import DEMONSTRATED_AT, StudentCapability, utcnow
from .profile import CapabilityProfile

EVIDENCE_DIR = Path(__file__).resolve().parent.parent / "data" / "evidence"

#: Minimum weight a new observation carries in the mastery update, however much prior
#: evidence exists.
#:
#: A plain running mean would let three-month-old evidence outvote what a student just
#: demonstrated, which is wrong for a LEARNING platform — people improve, and the recent
#: observation is the better estimate of what they can do now. The floor keeps old evidence
#: informative without letting it dominate. One constant, one line, fully inspectable.
EVIDENCE_WEIGHT_FLOOR = 0.35

#: Mastery a given amount of evidence can establish at most:  base + step * n.
#:
#: Found by testing, not by design. A single flawless answer to one scenario was scoring
#: 100% mastery, because with no prior evidence the observation stood alone. That
#: contradicts §6.2 — "Do NOT treat mastery as an absolute truth" — since one scenario
#: shows a student is CAPABLE, not that they have mastered anything.
#:
#: With these values: 1 piece of evidence tops out at 0.70, which is exactly
#: DEMONSTRATED_AT. One excellent answer earns "demonstrated" and nothing more; 2 reaches
#: 0.85; 3 removes the ceiling. It only ever caps, so a weak answer is never lifted.
EVIDENCE_CEILING_BASE = 0.55
EVIDENCE_CEILING_STEP = 0.15


def mastery_ceiling(evidence_count: int) -> float:
    """The highest mastery `evidence_count` observations can justify."""
    return min(1.0, EVIDENCE_CEILING_BASE + EVIDENCE_CEILING_STEP * max(0, evidence_count))


class Verdict(str, Enum):
    """§14's three-state judgement, which the spec already writes as ✓ △ ✗."""

    MET = "met"
    PARTIAL = "partial"
    UNMET = "unmet"

    @property
    def value_(self) -> float:
        return {"met": 1.0, "partial": 0.5, "unmet": 0.0}[self.value]

    @property
    def mark(self) -> str:
        return {"met": "✓", "partial": "△", "unmet": "✗"}[self.value]


@dataclass(frozen=True)
class CriterionResult:
    """One criterion, judged. The justification is what makes this reviewable.

    A verdict with no justification is an opaque score wearing a structured hat — §11's
    objection applies to it exactly as much as to a single number.
    """

    criterion_id: str
    verdict: Verdict
    justification: str = ""

    def to_record(self) -> dict[str, Any]:
        return {
            "criterionId": self.criterion_id,
            "verdict": self.verdict.value,
            "justification": self.justification,
        }


@dataclass(frozen=True)
class Evidence:
    """Observable proof produced by the learner — Claude.md §6.5.

    The student's raw response is stored verbatim and never discarded. §11: "The system
    should preserve the underlying evidence." Every downstream number can be recomputed
    from this record, so a change to the scoring rules can be replayed rather than
    reapplied blindly.
    """

    student_id: str
    experience_id: str          # the diagnostic item id
    capability_id: str          # the item's primary capability
    type: str                   # "diagnostic_response" for now; missions add more
    response: str               # verbatim
    results: tuple[CriterionResult, ...] = ()
    #: Which attempt at this experience this is, starting at 1. Assigned from the log
    #: rather than passed in, so it cannot disagree with what is stored.
    attempt: int = 1
    created_at: datetime = field(default_factory=utcnow)

    def to_record(self) -> dict[str, Any]:
        return {
            "id": f"{self.student_id}__{self.experience_id}",
            "studentId": self.student_id,
            "experienceId": self.experience_id,
            "capabilityId": self.capability_id,
            "type": self.type,
            "attempt": self.attempt,
            "response": self.response,
            "results": [r.to_record() for r in self.results],
            "createdAt": self.created_at.isoformat(),
        }

    @classmethod
    def from_record(cls, d: dict[str, Any]) -> "Evidence":
        return cls(
            student_id=d["studentId"],
            experience_id=d["experienceId"],
            capability_id=d["capabilityId"],
            type=d["type"],
            attempt=int(d.get("attempt", 1)),
            response=d["response"],
            results=tuple(
                CriterionResult(r["criterionId"], Verdict(r["verdict"]), r.get("justification", ""))
                for r in d.get("results", [])
            ),
            created_at=datetime.fromisoformat(d["createdAt"]),
        )


@dataclass(frozen=True)
class CapabilityOutcome:
    """What one piece of evidence concluded about one capability."""

    capability_id: str
    score: float
    met: tuple[str, ...]
    partial: tuple[str, ...]
    unmet: tuple[str, ...]
    mastery_before: float | None
    mastery_after: float
    weight: float

    @property
    def delta(self) -> float:
        return self.mastery_after - (self.mastery_before or 0.0)


@dataclass
class Assessment:
    """The interpretation of one piece of evidence. Claude.md §14."""

    evidence: Evidence
    outcomes: list[CapabilityOutcome]
    explanation: str = ""

    def to_record(self) -> dict[str, Any]:
        return {
            "studentId": self.evidence.student_id,
            "experienceId": self.evidence.experience_id,
            "createdAt": self.evidence.created_at.isoformat(),
            "outcomes": [
                {
                    "capabilityId": o.capability_id,
                    "score": round(o.score, 4),
                    "masteryBefore": o.mastery_before,
                    "masteryAfter": round(o.mastery_after, 4),
                    "met": list(o.met),
                    "partial": list(o.partial),
                    "unmet": list(o.unmet),
                }
                for o in self.outcomes
            ],
            "explanation": self.explanation,
        }


# --- evaluation ------------------------------------------------------------------
class Assessable(Protocol):
    """Anything with a prompt and a rubric: a diagnostic scenario, a corpus exercise, or
    (Phase 9) a mission. Structural rather than a base class, so Phase 8 could make
    exercises assessable without this module learning that exercises exist."""

    id: str
    capability_id: str
    prompt: str
    rubric: tuple[RubricCriterion, ...]


class Evaluator(Protocol):
    """Judges a response against a rubric. Returns judgements, never a score."""

    def evaluate(self, item: Assessable, response: str) -> list[CriterionResult]: ...


class ManualEvaluator:
    """Judgements supplied by a person.

    Not a stub for the model — a human assessor is a legitimate evaluator, and §11's
    requirement is that criteria be structured, not that a model apply them. It also makes
    every downstream computation testable with no API key and no quota.
    """

    def __init__(self, verdicts: dict[str, Verdict | str], justification: str = "manual"):
        self.verdicts = {k: Verdict(v) for k, v in verdicts.items()}
        self.justification = justification

    def evaluate(self, item: Assessable, response: str) -> list[CriterionResult]:
        return [
            CriterionResult(
                c.id,
                self.verdicts.get(c.id, Verdict.UNMET),
                self.justification if c.id in self.verdicts else "not supplied; treated as unmet",
            )
            for c in item.rubric
        ]


class _Judgement(BaseModel):
    criterion_id: str = Field(description="The exact id of the criterion being judged.")
    verdict: str = Field(description="One of: met, partial, unmet.")
    justification: str = Field(
        description="One sentence. Quote or paraphrase the part of the response that "
                    "decided it. If unmet, say what was missing."
    )


class _Judgements(BaseModel):
    judgements: list[_Judgement]


SYSTEM_INSTRUCTION = """\
You are the assessment layer of Cognith, a capability-based learning platform.

You judge a student's written response against a fixed list of rubric criteria. Each \
criterion is judged INDEPENDENTLY.

Rules, in priority order:

1. You do NOT score the student, rate them, or give an overall verdict. You judge one \
criterion at a time. Any summary judgement is someone else's job.

2. For each criterion return exactly one verdict:
   met     - the response clearly does this
   partial - the response gestures at this but does not actually do it, or does it without
             the reasoning the criterion asks for
   unmet   - the response does not do this

3. Judge ONLY what the response actually says. Do not credit the student for something you
assume they know, and do not penalise them for anything the criterion does not ask about.
A strong answer to a different question is still unmet.

4. Reasoning is the thing being assessed, not vocabulary. A response that names the right
term without justifying it is `partial`. A response that reaches the right conclusion by
sound reasoning in plain language is `met`.

5. Justify every verdict in one sentence, quoting or paraphrasing the part of the response \
that decided it. For `unmet`, say specifically what was missing.

Return a judgement for every criterion given, using its exact id."""


class GeminiEvaluator:
    """Gemini applied to one bounded job: judging criteria.

    It is given the scenario, the response, and the criteria. It is NOT given the student's
    profile, their claimed confidence, their mastery, or any other criterion's outcome —
    there is nothing for it to anchor on, and no way for it to produce "how good is this
    student" even if asked.
    """

    def __init__(self, model: str | None = None, thinking: str | None = None):
        from cognith_rag.config import GENERATION_MODEL
        self.model = model or GENERATION_MODEL
        #: "low" for short in-lesson tasks, where a fast verdict matters more than depth.
        self.thinking = thinking

    def evaluate(self, item: Assessable, response: str) -> list[CriterionResult]:
        from cognith_rag.embeddings import get_client

        criteria_block = "\n".join(
            f"- id: {c.id}\n  criterion: {c.criterion}" for c in item.rubric
        )
        prompt = (
            f"SCENARIO PUT TO THE STUDENT\n{item.prompt}\n\n"
            f"--- END SCENARIO ---\n\n"
            f"STUDENT'S RESPONSE\n{response}\n\n"
            f"--- END RESPONSE ---\n\n"
            f"CRITERIA ({len(item.rubric)}). Judge each one independently.\n"
            f"{criteria_block}\n"
        )
        interaction = get_client().interactions.create(
            model=self.model,
            system_instruction=SYSTEM_INSTRUCTION,
            input=prompt,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": _Judgements.model_json_schema(),
            },
            generation_config={"temperature": 0.0,
                               **({"thinking_level": self.thinking} if self.thinking else {})},
        )
        parsed = _Judgements.model_validate_json(interaction.output_text)

        by_id = {j.criterion_id: j for j in parsed.judgements}
        results: list[CriterionResult] = []
        for c in item.rubric:
            j = by_id.get(c.id)
            if j is None:
                # A missing judgement is not an unmet criterion. Saying so is honest;
                # silently scoring it zero would let an API hiccup look like a weak student.
                results.append(CriterionResult(c.id, Verdict.UNMET, "NOT JUDGED — model omitted this criterion"))
                continue
            try:
                verdict = Verdict(j.verdict.strip().lower())
            except ValueError:
                results.append(CriterionResult(c.id, Verdict.UNMET, f"NOT JUDGED — unrecognised verdict {j.verdict!r}"))
                continue
            results.append(CriterionResult(c.id, verdict, j.justification.strip()))
        return results


def attempt_number(student_id: str, experience_id: str) -> int:
    """Which attempt this would be. Counts what is already logged, plus one.

    Derived rather than stored on the profile: the evidence log is the record of what
    happened, and anything computed from it cannot drift away from it.
    """
    from .storage import get_storage

    log = get_storage().load_evidence(student_id)
    return 1 + sum(1 for e in log if e["evidence"]["experienceId"] == experience_id)


# --- assessment ------------------------------------------------------------------
def score_criteria(rubric: tuple[RubricCriterion, ...], results: list[CriterionResult]) -> dict[str, float]:
    """Weighted share of criteria met, per capability. Deterministic."""
    by_id = {r.criterion_id: r for r in results}
    totals: dict[str, list[float]] = {}
    for c in rubric:
        r = by_id.get(c.id)
        if r is None:
            continue
        earned, possible = totals.setdefault(c.capability_id, [0.0, 0.0])
        totals[c.capability_id] = [earned + c.weight * r.verdict.value_, possible + c.weight]
    return {cid: (e / p if p else 0.0) for cid, (e, p) in totals.items()}


def next_mastery(previous: float | None, observed: float, evidence_count: int) -> float:
    """Blend a new observation into the running estimate.

    alpha = max(1 / (n + 1), EVIDENCE_WEIGHT_FLOOR)

    With no prior evidence alpha is 1.0 and the observation stands alone. It then decays as
    evidence accumulates, but never below the floor — see EVIDENCE_WEIGHT_FLOOR for why a
    learning platform must not let old evidence outvote new.

    The result is then capped by `mastery_ceiling(n + 1)`, so thin evidence cannot claim
    more than it supports.
    """
    if previous is None or evidence_count == 0:
        blended = observed
    else:
        alpha = max(1.0 / (evidence_count + 1), EVIDENCE_WEIGHT_FLOOR)
        blended = previous * (1.0 - alpha) + observed * alpha
    # Cap by how much evidence now supports the estimate. Capping never lifts a weak
    # result — it only stops thin evidence claiming more than it can.
    return round(min(blended, mastery_ceiling(evidence_count + 1)), 4)


def explain(outcomes: list[CapabilityOutcome], graph: CapabilityGraph,
            rubric: tuple[RubricCriterion, ...]) -> str:
    """§14: "The system should explain WHY it changed."

    Assembled from the criterion judgements, not from a second model call. We already know
    exactly which criteria carried and which did not; asking a model to narrate that would
    add cost, latency and a chance of contradicting the data.
    """
    text = {c.id: c.criterion for c in rubric}
    parts: list[str] = []
    for o in sorted(outcomes, key=lambda x: -x.delta):
        cap = graph.get(o.capability_id)
        if o.mastery_before is None:
            # A first measurement has not risen or held steady — there was nothing to
            # move from. Saying "held steady from unmeasured" would imply prior evidence.
            line = f"{cap.name} measured at {o.mastery_after:.0%} for the first time."
        else:
            direction = (
                "rose" if o.delta > 0.01 else "fell" if o.delta < -0.01 else "held steady"
            )
            line = (f"{cap.name} {direction} from {o.mastery_before:.0%} "
                    f"to {o.mastery_after:.0%}.")
        # Criteria are written as what a good answer does ("Says retrying is not
        # safe…"), so they are quoted as-is. Splicing them into a sentence produced
        # "You showed says retrying…".
        if o.met:
            line += " What you got right: " + "; ".join(
                f'"{text[m]}"' for m in o.met[:2]) + "."
        if o.unmet:
            line += " Still to develop: " + "; ".join(
                f'"{text[u]}"' for u in o.unmet[:2]) + "."
        parts.append(line)
    return "\n\n".join(parts)


def assess(
    profile: CapabilityProfile,
    item: Assessable,
    response: str,
    evaluator: Evaluator,
    *,
    apply: bool = True,
    max_observed: float | None = None,
    decisive: bool = False,
    mastery_cap: float | None = None,
) -> Assessment:
    """Response -> Evidence -> Assessment -> capability update.

    The order matters: evidence is constructed and kept BEFORE any number is derived from
    it, so the record survives independently of whatever scoring rules were current.

    `decisive`: a written challenge settles the state on its own (decisions.md D61). A pass
    lifts the skill to at least this answer's score; a fail drops it to at most that score.
    Without this, weak early lesson evidence outvoted a flawless challenge.

    `mastery_cap`: the skill may not rise above this, while the outcome keeps the raw
    score. Diagnosis uses it: one placement answer shows where to start, not mastery.
    """
    results = evaluator.evaluate(item, response)
    evidence = Evidence(
        student_id=profile.student.id,
        experience_id=item.id,
        capability_id=item.capability_id,
        type=getattr(item, "type", None) and f"{item.type.value}_response" or "diagnostic_response",
        response=response,
        results=tuple(results),
        attempt=attempt_number(profile.student.id, item.id),
    )

    scores = score_criteria(item.rubric, results)
    if max_observed is not None:
        # Light evidence (e.g. multiple-choice concept checks) may show progress but must
        # not claim mastery on its own — a written challenge has to do that.
        scores = {cid: min(v, max_observed) for cid, v in scores.items()}
    by_id = {r.criterion_id: r for r in results}
    outcomes: list[CapabilityOutcome] = []

    for cid, score in scores.items():
        row: StudentCapability = profile.row_for(cid)
        after = next_mastery(row.mastery, score, row.evidence_count)
        if decisive:
            ceiling = mastery_ceiling(row.evidence_count + 1)
            after = round(min(max(after, score) if score >= DEMONSTRATED_AT else min(after, score),
                              ceiling), 4)
        if mastery_cap is not None and after > mastery_cap:
            # Never lifts past the cap, but never takes away a level already earned either.
            after = min(after, max(mastery_cap, row.mastery or 0.0))
        criteria = [c for c in item.rubric if c.capability_id == cid]
        outcomes.append(CapabilityOutcome(
            capability_id=cid,
            score=score,
            met=tuple(c.id for c in criteria if by_id.get(c.id) and by_id[c.id].verdict is Verdict.MET),
            partial=tuple(c.id for c in criteria if by_id.get(c.id) and by_id[c.id].verdict is Verdict.PARTIAL),
            unmet=tuple(c.id for c in criteria if by_id.get(c.id) and by_id[c.id].verdict is Verdict.UNMET),
            mastery_before=row.mastery,
            mastery_after=after,
            weight=sum(c.weight for c in criteria),
        ))
        if apply:
            profile.record_assessment(cid, after, evidence_added=1,
                                      at=evidence.created_at)

    outcomes.sort(key=lambda o: -o.weight)
    return Assessment(
        evidence=evidence,
        outcomes=outcomes,
        explanation=explain(outcomes, profile.graph, item.rubric),
    )


def save_evidence(assessment: Assessment) -> None:
    """Append to the student's evidence log. Append-only: evidence is never rewritten."""
    from .storage import get_storage

    get_storage().append_evidence(assessment.evidence.student_id, {
        "evidence": assessment.evidence.to_record(),
        "assessment": assessment.to_record(),
    })
