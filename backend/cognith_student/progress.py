"""Progress against a milestone — "how far have I reached?"

The answer is deliberately TWO numbers, not one.

A single percentage would average demonstrated capability together with capability the
learner merely claimed, which is the exact conflation §6.2 forbids and the two-material
bar in Phase 4 exists to prevent. A learner who claims everything and has shown nothing is
not 80% of the way to a milestone. They are 0% of the way, with an 80% guess attached.

So: `demonstrated` is what evidence supports, and `claimed` is what is being taken on
trust. The gap between them is the size of the question the diagnostic should be asking.

WHY THIS FEEDS THE DIAGNOSTIC
-----------------------------
`relevance()` turns a milestone into per-capability weights for the Phase 5 selector. The
highest weight goes to a requirement that is CLAIMED BUT UNVERIFIED, because that is where
the progress estimate is most likely to be wrong — testing it changes what we believe about
the learner more than testing anything else does.

That is the whole point of having a destination: it tells you which questions matter.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from cognith_capability.milestone import Milestone, Requirement

from .models import StudentCapability
from .profile import CapabilityProfile


class RequirementState(str, Enum):
    """Where one requirement stands. Ordered by how much a diagnostic would tell us."""

    DEMONSTRATED = "demonstrated"
    """Evidence puts mastery at or above the target. Settled."""

    SHORT = "short"
    """Assessed, and below the target. Known, and needs work rather than testing."""

    CLAIMED = "claimed"
    """Self-reported, never checked. The progress estimate depends on it and cannot
    justify it — the most informative thing to test."""

    UNKNOWN = "unknown"
    """Nothing said and nothing shown."""


#: How much a diagnostic would tell us, per state. Consumed by the Phase 5 selector via
#: `relevance()`. A requirement already demonstrated is not worth re-testing; one being
#: taken on trust is worth more than one we simply know nothing about, because the learner
#: is COUNTING on it.
DIAGNOSTIC_VALUE = {
    RequirementState.CLAIMED: 1.0,
    RequirementState.UNKNOWN: 0.6,
    RequirementState.SHORT: 0.45,
    RequirementState.DEMONSTRATED: 0.1,
}


@dataclass(frozen=True)
class RequirementProgress:
    requirement: Requirement
    row: StudentCapability
    state: RequirementState

    @property
    def capability_id(self) -> str:
        return self.requirement.capability_id

    @property
    def shortfall(self) -> float:
        """How far below target, using demonstrated mastery only. Claims count as zero
        here — that is the point of the field."""
        return max(0.0, self.requirement.target - (self.row.mastery or 0.0))


@dataclass
class MilestoneProgress:
    milestone: Milestone
    requirements: list[RequirementProgress]
    #: True when every requirement of every earlier milestone in the chain is met.
    unlocked: bool = True
    locked_by: str | None = None

    # --- the two numbers -------------------------------------------------------------
    @property
    def demonstrated(self) -> int:
        return sum(1 for r in self.requirements
                   if r.state is RequirementState.DEMONSTRATED)

    @property
    def claimed(self) -> int:
        return sum(1 for r in self.requirements if r.state is RequirementState.CLAIMED)

    @property
    def total(self) -> int:
        return len(self.requirements)

    @property
    def demonstrated_fraction(self) -> float:
        return self.demonstrated / self.total if self.total else 0.0

    @property
    def claimed_fraction(self) -> float:
        """What is being taken on trust. Reported ALONGSIDE the demonstrated figure and
        never added to it."""
        return self.claimed / self.total if self.total else 0.0

    @property
    def complete(self) -> bool:
        return self.demonstrated == self.total

    def by_state(self, state: RequirementState) -> list[RequirementProgress]:
        return [r for r in self.requirements if r.state is state]

    def next_to_verify(self) -> list[RequirementProgress]:
        """Requirements worth testing, most informative first. Claims before unknowns,
        and the boldest claim before a timid one."""
        return sorted(
            (r for r in self.requirements
             if r.state in (RequirementState.CLAIMED, RequirementState.UNKNOWN)),
            key=lambda r: (-DIAGNOSTIC_VALUE[r.state], -(r.row.confidence or 0.0)),
        )

    def relevance(self) -> dict[str, float]:
        """Per-capability weights for the Phase 5 diagnostic selector.

        Returned as a plain mapping so `diagnostic.py` never learns what a milestone is —
        it takes numbers, and this one named function is where the policy lives.
        """
        return {r.capability_id: DIAGNOSTIC_VALUE[r.state] for r in self.requirements}

    def summary(self) -> str:
        if self.complete:
            return f"{self.milestone.name}: complete — all {self.total} demonstrated."
        parts = [f"{self.demonstrated} of {self.total} demonstrated"]
        if self.claimed:
            parts.append(f"{self.claimed} claimed but unverified")
        unknown = len(self.by_state(RequirementState.UNKNOWN))
        if unknown:
            parts.append(f"{unknown} untouched")
        return f"{self.milestone.name}: " + ", ".join(parts) + "."


def state_for(row: StudentCapability, requirement: Requirement) -> RequirementState:
    if row.mastery is not None:
        return (RequirementState.DEMONSTRATED if row.mastery >= requirement.target
                else RequirementState.SHORT)
    return RequirementState.CLAIMED if row.confidence is not None else RequirementState.UNKNOWN


def progress_for(
    profile: CapabilityProfile, milestone: Milestone,
    earlier: list["MilestoneProgress"] | None = None,
) -> MilestoneProgress:
    """Where the learner stands against one milestone.

    `earlier` is the chain before it; a milestone is locked until its predecessor is
    complete, which is what makes "next level" mean something.
    """
    requirements = [
        RequirementProgress(
            requirement=req, row=profile.row_for(req.capability_id),
            state=state_for(profile.row_for(req.capability_id), req),
        )
        for req in milestone.requires
    ]
    unlocked, locked_by = True, None
    for prior in earlier or []:
        if not prior.complete:
            unlocked, locked_by = False, prior.milestone.name
            break
    return MilestoneProgress(milestone=milestone, requirements=requirements,
                             unlocked=unlocked, locked_by=locked_by)


def path_for(profile: CapabilityProfile, milestones, goal: str) -> list[MilestoneProgress]:
    """The learner's whole path for a goal, in level order, with locking resolved."""
    out: list[MilestoneProgress] = []
    for m in milestones.for_goal(goal):
        out.append(progress_for(profile, m, earlier=list(out)))
    return out


def active(path: list[MilestoneProgress]) -> MilestoneProgress | None:
    """The milestone the learner is actually on: the first incomplete one.

    When every milestone is complete there is no active one — the goal is reached, and
    saying so is more useful than pointing at the last milestone again.
    """
    return next((p for p in path if not p.complete), None)
