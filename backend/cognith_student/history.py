"""What repeated attempts reveal about a learner.

Retrying an experience already worked — mastery re-blends correctly (D24). What did not
exist was any record that it WAS a retry, and that record is worth more than the
bookkeeping suggests, because a second attempt answers questions a first one cannot.

    unmet -> met     FIXED. They read the feedback and acted on it.
    unmet -> unmet   PERSISTENT. A criterion missed once is a slip; missed again after
                     seeing exactly what was wrong is a genuine blind spot.
    met   -> unmet   REGRESSED. The first pass may have been a fluke, or the second
                     answer was rushed.

The persistent case is the valuable one, and it is invisible without attempt history: two
students can sit at the same mastery, one having missed a criterion once and the other
having missed it three times. They need different things.

The aggregate — what share of previously-unmet criteria became met — is a signal about the
LEARNER rather than about any capability. Someone who reliably fixes what they are told
about needs feedback; someone who does not needs a different explanation.

Everything here is DERIVED from the evidence log. Nothing is stored twice, so nothing can
disagree with the record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .evidence import Verdict

#: A criterion has to be missed at least this many times before it counts as a blind spot
#: rather than a slip. Two, because the second attempt is the one where the learner had
#: already been told.
PERSISTENT_AFTER = 2


@dataclass(frozen=True)
class CriterionTrajectory:
    """How one criterion went across every attempt at its experience."""

    criterion_id: str
    capability_id: str
    criterion: str
    experience_id: str
    verdicts: tuple[Verdict, ...]

    @property
    def attempts(self) -> int:
        return len(self.verdicts)

    @property
    def latest(self) -> Verdict:
        return self.verdicts[-1]

    @property
    def fixed(self) -> bool:
        """Ended met, having not been met before. They acted on the feedback."""
        return (self.attempts > 1 and self.latest is Verdict.MET
                and any(v is not Verdict.MET for v in self.verdicts[:-1]))

    @property
    def persistent(self) -> bool:
        """Missed repeatedly. A blind spot, not a slip."""
        misses = sum(1 for v in self.verdicts if v is Verdict.UNMET)
        return misses >= PERSISTENT_AFTER and self.latest is not Verdict.MET

    @property
    def regressed(self) -> bool:
        return (self.attempts > 1 and self.latest is not Verdict.MET
                and any(v is Verdict.MET for v in self.verdicts[:-1]))

    def marks(self) -> str:
        return " ".join(v.mark for v in self.verdicts)


@dataclass(frozen=True)
class ExperienceAttempts:
    experience_id: str
    attempts: int
    first_at: datetime
    last_at: datetime
    #: Share of rubric weight met, per attempt, in order.
    scores: tuple[float, ...] = ()

    @property
    def improving(self) -> bool:
        return len(self.scores) > 1 and self.scores[-1] > self.scores[0] + 0.01

    @property
    def stalled(self) -> bool:
        """Retried and got no better. Repeating it again is unlikely to help."""
        return len(self.scores) > 1 and self.scores[-1] <= self.scores[0] + 0.01

    @property
    def delta(self) -> float:
        return self.scores[-1] - self.scores[0] if len(self.scores) > 1 else 0.0


@dataclass
class LearnerHistory:
    student_id: str
    experiences: dict[str, ExperienceAttempts] = field(default_factory=dict)
    trajectories: dict[str, CriterionTrajectory] = field(default_factory=dict)

    # --- what the retries say ---------------------------------------------------
    def persistent_misses(self) -> list[CriterionTrajectory]:
        """Blind spots, worst first. What a lesson should actually address."""
        return sorted(
            (t for t in self.trajectories.values() if t.persistent),
            key=lambda t: -t.attempts,
        )

    def fixed_on_retry(self) -> list[CriterionTrajectory]:
        return [t for t in self.trajectories.values() if t.fixed]

    def regressions(self) -> list[CriterionTrajectory]:
        return [t for t in self.trajectories.values() if t.regressed]

    def retried(self) -> list[ExperienceAttempts]:
        return sorted((e for e in self.experiences.values() if e.attempts > 1),
                      key=lambda e: -e.attempts)

    def stalled(self) -> list[ExperienceAttempts]:
        return [e for e in self.retried() if e.stalled]

    def responds_to_feedback(self) -> float | None:
        """Share of criteria that were unmet and later became met.

        A signal about the LEARNER, not a capability. None when nothing has been retried,
        because there is nothing to compute it from — and reporting 0% for a student who
        has simply never retried anything would be a lie.
        """
        revisited = [t for t in self.trajectories.values()
                     if t.attempts > 1 and t.verdicts[0] is not Verdict.MET]
        if not revisited:
            return None
        return sum(1 for t in revisited if t.latest is Verdict.MET) / len(revisited)

    def persistent_by_capability(self) -> dict[str, list[CriterionTrajectory]]:
        out: dict[str, list[CriterionTrajectory]] = {}
        for t in self.persistent_misses():
            out.setdefault(t.capability_id, []).append(t)
        return out

    @property
    def total_attempts(self) -> int:
        return sum(e.attempts for e in self.experiences.values())


def load_history(student_id: str, library=None) -> LearnerHistory:
    """Read the evidence log into trajectories.

    `library` supplies criterion text for display; without it the ids still work, so
    history remains readable when the experience data is unavailable.
    """
    from .storage import get_storage

    history = LearnerHistory(student_id=student_id)
    log = get_storage().load_evidence(student_id)
    if not log:
        return history

    criteria = {}
    if library is not None:
        criteria = {c.id: (c, e.id)
                    for e in library.experiences.values() for c in e.rubric}

    ordered: dict[str, list[dict]] = {}
    for entry in log:
        ordered.setdefault(entry["evidence"]["experienceId"], []).append(entry)

    for experience_id, entries in ordered.items():
        entries.sort(key=lambda e: e["evidence"]["createdAt"])
        scores: list[float] = []
        for entry in entries:
            results = entry["evidence"].get("results", [])
            value = {"met": 1.0, "partial": 0.5, "unmet": 0.0}
            scores.append(
                sum(value[r["verdict"]] for r in results) / len(results)
                if results else 0.0
            )
            for r in results:
                key = f"{experience_id}::{r['criterionId']}"
                previous = history.trajectories.get(key)
                spec = criteria.get(r["criterionId"])
                history.trajectories[key] = CriterionTrajectory(
                    criterion_id=r["criterionId"],
                    capability_id=spec[0].capability_id if spec else "",
                    criterion=spec[0].criterion if spec else r["criterionId"],
                    experience_id=experience_id,
                    verdicts=(previous.verdicts if previous else ()) + (Verdict(r["verdict"]),),
                )
        history.experiences[experience_id] = ExperienceAttempts(
            experience_id=experience_id,
            attempts=len(entries),
            first_at=datetime.fromisoformat(entries[0]["evidence"]["createdAt"]),
            last_at=datetime.fromisoformat(entries[-1]["evidence"]["createdAt"]),
            scores=tuple(scores),
        )
    return history
