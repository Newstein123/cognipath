"""Milestones — "where do I want to reach?"

Before this, a goal was a string plus a list of capability ids that added 0.15 to
diagnostic scoring. It could not say how far along a learner was, what remained, or what
"done" meant. A milestone is that missing target: a set of capabilities each at a TARGET
MASTERY.

WHY A TARGET PER CAPABILITY RATHER THAN MEMBERSHIP
--------------------------------------------------
Membership gives a binary "relevant / not", which is what the focus list already gave.
A target gives a DISTANCE, and distance is what makes progress computable — and computable
progress is what makes a question worth asking. The most valuable thing to test is a
capability the milestone requires, the learner claims, and nothing has checked: that is
precisely where the progress estimate is most likely wrong.

A "level" needs no separate concept. `after` chains one milestone to another, and a level
is a milestone whose predecessor is complete.

This module knows nothing about students. Progress against a profile lives in
cognith_student/progress.py, keeping the dependency arrow pointing one way.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .graph import CapabilityGraph

MILESTONES_PATH = Path(__file__).resolve().parent.parent / "data" / "milestones.yaml"


class MilestoneError(ValueError):
    """Raised when milestone data does not line up with the capability graph."""


@dataclass(frozen=True)
class Requirement:
    """One capability a milestone needs, and how much of it."""

    capability_id: str
    target: float

    def to_record(self) -> dict[str, Any]:
        return {"capabilityId": self.capability_id, "target": self.target}


@dataclass(frozen=True)
class Milestone:
    id: str
    goal: str
    level: int
    name: str
    summary: str
    requires: tuple[Requirement, ...]
    after: str | None = None

    def requirement_for(self, capability_id: str) -> Requirement | None:
        return next((r for r in self.requires if r.capability_id == capability_id), None)

    @property
    def capability_ids(self) -> tuple[str, ...]:
        return tuple(r.capability_id for r in self.requires)

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id, "goal": self.goal, "level": self.level, "name": self.name,
            "summary": self.summary, "after": self.after,
            "requires": [r.to_record() for r in self.requires],
        }


class MilestoneMap:
    """Every milestone, validated against the capability graph."""

    def __init__(self, graph: CapabilityGraph, milestones: list[Milestone]):
        self.graph = graph
        self.milestones = {m.id: m for m in milestones}
        self._validate()

    @classmethod
    def load(cls, graph: CapabilityGraph, path: Path = MILESTONES_PATH) -> "MilestoneMap":
        if not path.exists():
            raise FileNotFoundError(f"No milestone data at {path}")
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(graph, [
            Milestone(
                id=m["id"], goal=m["goal"], level=int(m["level"]), name=m["name"],
                summary=(m.get("summary") or "").strip(), after=m.get("after"),
                requires=tuple(
                    Requirement(r["capability"], float(r["target"]))
                    for r in m["requires"]
                ),
            )
            for m in spec.get("milestones", [])
        ])

    def _validate(self) -> None:
        """The same dangling-reference discipline as every other loader since Phase 1."""
        problems: list[str] = []
        for m in self.milestones.values():
            if not m.requires:
                problems.append(f"milestone {m.id!r} requires nothing — it is already complete")
            seen: set[str] = set()
            for r in m.requires:
                if r.capability_id not in self.graph.capabilities:
                    problems.append(
                        f"milestone {m.id!r} requires unknown capability "
                        f"{r.capability_id!r}")
                if r.capability_id in seen:
                    problems.append(f"milestone {m.id!r} lists {r.capability_id!r} twice")
                seen.add(r.capability_id)
                if not 0.0 < r.target <= 1.0:
                    problems.append(
                        f"milestone {m.id!r} target for {r.capability_id!r} is "
                        f"{r.target} — must be within (0, 1]")
            if m.after and m.after not in self.milestones:
                problems.append(f"milestone {m.id!r} follows unknown milestone {m.after!r}")
            if m.after == m.id:
                problems.append(f"milestone {m.id!r} follows itself")

        # A chain that loops would make "next level" non-terminating.
        for m in self.milestones.values():
            seen_chain, cur = {m.id}, m.after
            while cur and cur in self.milestones:
                if cur in seen_chain:
                    problems.append(f"milestone chain loops at {cur!r}")
                    break
                seen_chain.add(cur)
                cur = self.milestones[cur].after

        if problems:
            raise MilestoneError(
                f"{len(problems)} problem(s) in milestone data:\n"
                + "\n".join(f"  - {p}" for p in problems))

    # --- queries ---------------------------------------------------------------------
    def get(self, milestone_id: str) -> Milestone:
        try:
            return self.milestones[milestone_id]
        except KeyError:
            raise KeyError(
                f"No milestone {milestone_id!r}. Known: "
                f"{', '.join(sorted(self.milestones))}") from None

    def for_goal(self, goal: str) -> list[Milestone]:
        """The milestones for a goal, in level order — the learner's path."""
        return sorted(
            (m for m in self.milestones.values() if m.goal == goal),
            key=lambda m: m.level,
        )

    def goals(self) -> list[str]:
        return sorted({m.goal for m in self.milestones.values()})

    def unreached(self) -> list[str]:
        """Capabilities no milestone requires.

        Not an error — the graph may reasonably contain more than any one path needs —
        but worth seeing, because nothing will ever steer a learner toward them.
        """
        needed = {r.capability_id for m in self.milestones.values() for r in m.requires}
        return [c.id for c in self.graph.capabilities.values() if c.id not in needed]

    def __len__(self) -> int:
        return len(self.milestones)
