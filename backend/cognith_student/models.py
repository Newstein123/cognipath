"""Student and StudentCapability — the Phase 2 data model.

Field names follow Claude.md §6.2. The one deliberate departure from the example JSON
there is that `mastery` is NULLABLE, and that is the most important decision in this
phase — see the note on StudentCapability.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any

#: Mastery at or above this counts as demonstrated for display and summary purposes.
#:
#: A presentation threshold, NOT an assessment policy. Phase 6 decides how mastery is
#: computed from evidence and may well want a different bar per capability or per level.
#: Kept here as a single named constant so that when Phase 6 replaces it, there is exactly
#: one place to look.
DEMONSTRATED_AT = 0.70


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MasteryStatus(str, Enum):
    """How much Cognith actually knows about one capability for one student.

    DERIVED, never stored as authored input. A stored status can contradict the numbers
    beside it — `status: demonstrated` next to `evidenceCount: 0` — and then there is no
    answer to which one is right. `StudentCapability.status` computes it every time.

    The ordering below is the progression a capability moves through, and the jump that
    matters to the product is CLAIMED -> DEVELOPING/DEMONSTRATED: that is the moment a
    belief becomes evidence.
    """

    UNKNOWN = "unknown"
    """Neither claimed nor assessed. We know nothing."""

    CLAIMED = "claimed"
    """Self-reported only. A claim, not a finding — §9's "initial estimate"."""

    DEVELOPING = "developing"
    """Assessed, and the evidence does not yet support the capability."""

    DEMONSTRATED = "demonstrated"
    """Assessed, and the evidence supports the capability."""


@dataclass(frozen=True)
class Student:
    """A learner.

    Minimal on purpose. Claude.md §8 adds goal, technologies, experience and background at
    Phase 3 (onboarding); `goal` is present here only because it is the one field §21
    Phase 2 implies and Phase 4's capability map needs a heading. Everything else waits.
    """

    id: str
    name: str
    goal: str | None = None
    created_at: datetime = field(default_factory=utcnow)

    def to_record(self) -> dict[str, Any]:
        """Shape for the `students/` collection in Claude.md §19."""
        return {
            "id": self.id,
            "name": self.name,
            "goal": self.goal,
            "createdAt": self.created_at.isoformat(),
        }

    @classmethod
    def from_record(cls, d: dict[str, Any]) -> "Student":
        return cls(
            id=d["id"],
            name=d["name"],
            goal=d.get("goal"),
            created_at=datetime.fromisoformat(d["createdAt"]),
        )


class InvalidStudentCapability(ValueError):
    """Raised when a row would misrepresent what is actually known about a student."""


@dataclass(frozen=True)
class StudentCapability:
    """What Cognith currently believes about one student and one capability.

    WHY `mastery` IS NULLABLE
    -------------------------
    Claude.md §6.2's example shows `"mastery": 0.35`, and it would be easy to default the
    field to 0.0. That would be wrong, because it makes two opposite states identical:

        mastery = 0.0   "we have no evidence about this"
        mastery = 0.0   "we have evidence, and they cannot do it"

    The first is ignorance, the second is a finding. Collapsing them is exactly the error
    §6.2 warns about — it lets an unverified capability be read as a measured zero, and a
    confident student's self-report then looks like it has been checked.

    So `mastery is None` means NEVER DEMONSTRATED, and it is the default. A profile
    straight out of onboarding has every `confidence` set and every `mastery` None.

    confidence  0..1, self-reported. What the student says. Never evidence.
    mastery     0..1 or None, evidence-based. What Cognith can defend.
    """

    student_id: str
    capability_id: str
    #: Self-reported. None means the student never rated this capability.
    confidence: float | None = None
    #: Evidence-based estimate. None means never assessed — NOT zero ability.
    mastery: float | None = None
    #: Pieces of evidence incorporated into the current mastery estimate. Defined that
    #: way (rather than "evidence collected") so it cannot drift from `mastery`.
    evidence_count: int = 0
    #: When `mastery` was last updated. None whenever mastery is None.
    last_assessed_at: datetime | None = None

    def __post_init__(self) -> None:
        for name, value in (("confidence", self.confidence), ("mastery", self.mastery)):
            if value is not None and not 0.0 <= value <= 1.0:
                raise InvalidStudentCapability(
                    f"{self.capability_id}: {name} must be within 0.0-1.0, got {value}"
                )
        if self.evidence_count < 0:
            raise InvalidStudentCapability(
                f"{self.capability_id}: evidence_count cannot be negative"
            )
        # The two biconditionals below are what stop a claim from being mistaken for a
        # finding. Mastery without evidence is an unsourced number; evidence without
        # mastery is an assessment that was never applied.
        if (self.mastery is None) != (self.evidence_count == 0):
            raise InvalidStudentCapability(
                f"{self.capability_id}: mastery={self.mastery} with "
                f"evidence_count={self.evidence_count} — mastery exists if and only if "
                "evidence supports it"
            )
        if (self.mastery is None) != (self.last_assessed_at is None):
            raise InvalidStudentCapability(
                f"{self.capability_id}: mastery={self.mastery} with "
                f"last_assessed_at={self.last_assessed_at} — an assessed capability must "
                "carry the time it was assessed"
            )

    # --- derived state ------------------------------------------------------------
    @property
    def status(self) -> MasteryStatus:
        if self.mastery is None:
            return MasteryStatus.CLAIMED if self.confidence is not None else MasteryStatus.UNKNOWN
        return (
            MasteryStatus.DEMONSTRATED
            if self.mastery >= DEMONSTRATED_AT
            else MasteryStatus.DEVELOPING
        )

    @property
    def is_demonstrated(self) -> bool:
        return self.status is MasteryStatus.DEMONSTRATED

    @property
    def is_unverified(self) -> bool:
        """Claimed but never assessed — the state a diagnostic exists to resolve."""
        return self.mastery is None and self.confidence is not None

    @property
    def calibration_gap(self) -> float | None:
        """confidence - mastery, or None if either side is missing.

        Positive means the student claims more than the evidence supports; negative means
        they are underselling themselves. Both are useful and neither is a verdict — it is
        a SIGNAL. Phase 5 decides what to do with it; §10 wants the diagnostic to target
        uncertain capabilities, and a large gap is one definition of uncertain.
        """
        if self.mastery is None or self.confidence is None:
            return None
        return round(self.confidence - self.mastery, 4)

    def days_since_assessment(self, now: datetime | None = None) -> float | None:
        """Staleness. None if never assessed. Phase 5 may treat old evidence as weaker."""
        if self.last_assessed_at is None:
            return None
        return ((now or utcnow()) - self.last_assessed_at).total_seconds() / 86400

    # --- transitions ---------------------------------------------------------------
    def with_confidence(self, confidence: float | None) -> "StudentCapability":
        """Record a self-report. Deliberately cannot touch mastery or evidence."""
        return replace(self, confidence=confidence)

    def record_assessment(
        self,
        mastery: float,
        *,
        evidence_added: int = 1,
        at: datetime | None = None,
    ) -> "StudentCapability":
        """Apply an assessment result, returning a new row.

        This is the MECHANICS of updating state, not the policy that produced `mastery`.
        Phase 6 owns the rubric, the Gemini evaluation and the arithmetic that turns
        evidence into this number; it then calls this to store the outcome.
        """
        if evidence_added < 1:
            raise InvalidStudentCapability(
                "an assessment must incorporate at least one piece of evidence"
            )
        return replace(
            self,
            mastery=mastery,
            evidence_count=self.evidence_count + evidence_added,
            last_assessed_at=at or utcnow(),
        )

    # --- persistence ----------------------------------------------------------------
    def to_record(self) -> dict[str, Any]:
        """Shape for the `student_capabilities/` collection in Claude.md §19.

        `status` is written out for queryability even though it is derived — a Firestore
        query cannot call a Python property. It is always recomputed on read, never
        trusted from storage.
        """
        return {
            "id": f"{self.student_id}__{self.capability_id}",
            "studentId": self.student_id,
            "capabilityId": self.capability_id,
            "confidence": self.confidence,
            "mastery": self.mastery,
            "status": self.status.value,
            "evidenceCount": self.evidence_count,
            "lastAssessedAt": (
                self.last_assessed_at.isoformat() if self.last_assessed_at else None
            ),
        }

    @classmethod
    def from_record(cls, d: dict[str, Any]) -> "StudentCapability":
        raw_at = d.get("lastAssessedAt")
        return cls(
            student_id=d["studentId"],
            capability_id=d["capabilityId"],
            confidence=d.get("confidence"),
            mastery=d.get("mastery"),
            evidence_count=d.get("evidenceCount", 0),
            last_assessed_at=datetime.fromisoformat(raw_at) if raw_at else None,
        )
