"""The diagnostic engine — Claude.md §10 and §21 Phase 5.

§10's requirement: "Do not give every student the same long exam. The diagnostic should
identify important or uncertain capabilities and verify them."

So the engine is the SELECTION, not the questions. Given a profile it decides which small
number of capabilities are worth a student's time, and why. The scenarios themselves are
authored content in data/diagnostics.yaml.

WHAT §10's EXAMPLE ACTUALLY SPECIFIES
------------------------------------
    "Student says they are intermediate in system design.
     Cognith tests: Scalability, Trade-off Analysis, Database Performance."

Note what it does NOT do: it does not test System Design. The student already told you
about System Design — that is the claim. What is unknown is whether anything underneath it
is real. So a bold unverified claim is a reason to examine its CONTRIBUTORS AND
PREREQUISITES, which is the `claim_support` factor below and the reason Phase 1 stored
relationships as data.

WHAT THIS PHASE DOES NOT DO
---------------------------
It does not score answers. A Diagnostic is produced and persisted unanswered; turning
responses into evidence and evidence into mastery is Phase 6, which also authors the
rubrics. Scenarios are authored rather than model-generated precisely because a generated
question has no rubric to be scored against (§11).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from cognith_capability.graph import CapabilityGraph
from cognith_capability.models import Capability, Level

from .models import DEMONSTRATED_AT, utcnow
from .profile import CapabilityProfile

from cognith_course import path as course_path
SESSION_DIR = Path(__file__).resolve().parent.parent / "data" / "diagnostics"


class DiagnosticError(ValueError):
    """Raised when the diagnostic data is inconsistent with the capability graph."""


@dataclass(frozen=True)
class RubricCriterion:
    """One thing a good answer to a specific scenario does.

    Authored WITH the scenario rather than in a separate file, because a criterion like
    "identifies the database as the likely first bottleneck" is meaningless apart from the
    scenario that sets up the bottleneck. Keeping them together is the same argument that
    kept scenarios out of a model's hands (decisions.md D22) — a question and its rubric
    are one artefact and must not drift.

    `capability_id` is what lets a single scenario produce evidence for SEVERAL
    capabilities, which is what `also_exercises` promised. §11's rubric example is keyed by
    capability; this reaches the same place from the other direction.
    """

    id: str
    criterion: str
    capability_id: str
    weight: float = 1.0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RubricCriterion":
        return cls(
            id=d["id"],
            criterion=d["criterion"].strip(),
            capability_id=d["capability"],
            weight=float(d.get("weight", 1.0)),
        )


@dataclass(frozen=True)
class DiagnosticItem:
    """One authored scenario.

    `probes` names the reasoning dimensions the scenario is meant to expose (§10:
    decomposition, reasoning, decision, trade-offs, application). Phase 6's rubric
    criteria will be written against these same dimensions — that is what keeps question
    and rubric aligned, and it is why scenarios are authored rather than generated.
    """

    id: str
    capability_id: str
    also_exercises: tuple[str, ...]
    level: Level
    minutes: int
    probes: tuple[str, ...]
    prompt: str
    rubric: tuple[RubricCriterion, ...] = ()

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DiagnosticItem":
        return cls(
            id=d["id"],
            capability_id=d["capability"],
            also_exercises=tuple(d.get("also_exercises") or ()),
            level=Level(d["level"]),
            minutes=int(d.get("minutes", 8)),
            probes=tuple(d.get("probes") or ()),
            prompt=d["prompt"].strip(),
            rubric=tuple(RubricCriterion.from_dict(c) for c in d.get("rubric") or ()),
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "capabilityId": self.capability_id,
            "alsoExercises": list(self.also_exercises),
            "level": self.level.value,
            "minutes": self.minutes,
            "probes": list(self.probes),
            "prompt": self.prompt,
            "rubric": [
                {"id": c.id, "criterion": c.criterion,
                 "capability": c.capability_id, "weight": c.weight}
                for c in self.rubric
            ],
        }


@dataclass(frozen=True)
class Candidate:
    """One capability considered for verification, with its score broken down.

    `factors` is the whole point. A diagnostic that cannot say why it is asking is a quiz,
    and §26.7 requires provenance. The CLI prints this breakdown.
    """

    capability_id: str
    score: float
    factors: dict[str, float]
    notes: tuple[str, ...] = ()
    ready: bool = True

    def top_factors(self, n: int = 3) -> list[tuple[str, float]]:
        return sorted(
            ((k, v) for k, v in self.factors.items() if v > 0),
            key=lambda kv: -kv[1],
        )[:n]


@dataclass
class Diagnostic:
    """A produced, unanswered diagnostic session."""

    student_id: str
    selected: list[Candidate]
    items: list[DiagnosticItem]
    considered: list[Candidate] = field(default_factory=list)
    #: Ranked high enough to select but no scenario is authored for them. Reported rather
    #: than silently dropped — a capability vanishing from a diagnostic with no
    #: explanation is indistinguishable from a scoring bug.
    skipped_no_scenario: list[Candidate] = field(default_factory=list)
    #: Capabilities a selected scenario touches without targeting. Partial coverage.
    secondary_coverage: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=utcnow)

    @property
    def minutes(self) -> int:
        return sum(i.minutes for i in self.items)

    def to_record(self) -> dict[str, Any]:
        """Shape for a `diagnostics/` collection, alongside Claude.md §19's entities.

        Responses are absent by design — Phase 6 collects them and turns them into
        `evidence/`.
        """
        return {
            "studentId": self.student_id,
            "createdAt": self.created_at.isoformat(),
            "status": "pending",
            "selected": [
                {
                    "capabilityId": c.capability_id,
                    "score": round(c.score, 4),
                    "factors": {k: round(v, 4) for k, v in c.factors.items() if v},
                    "notes": list(c.notes),
                }
                for c in self.selected
            ],
            "items": [i.to_record() for i in self.items],
            "secondaryCoverage": list(self.secondary_coverage),
            "skippedNoScenario": [c.capability_id for c in self.skipped_no_scenario],
        }

    def save(self, directory: Path = SESSION_DIR) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.student_id}.json"
        path.write_text(json.dumps(self.to_record(), indent=2), encoding="utf-8")
        return path


class DiagnosticEngine:
    def __init__(self, graph: CapabilityGraph, spec: dict[str, Any]):
        self.graph = graph
        self.selection = spec["selection"]
        self.weights = self.selection["weights"]
        self.items = [DiagnosticItem.from_dict(d) for d in spec["items"]]
        self._validate()

    @classmethod
    def load(cls, graph: CapabilityGraph, path: Path | None = None) -> "DiagnosticEngine":
        path = path or course_path("diagnostics.yaml")
        if not path.exists():
            raise FileNotFoundError(f"No diagnostic data at {path}")
        return cls(graph, yaml.safe_load(path.read_text(encoding="utf-8")))

    def _validate(self) -> None:
        problems: list[str] = []
        seen: set[str] = set()
        for item in self.items:
            if item.id in seen:
                problems.append(f"duplicate item id {item.id!r}")
            seen.add(item.id)
            for cid in (item.capability_id, *item.also_exercises):
                if cid not in self.graph.capabilities:
                    problems.append(f"item {item.id!r} references unknown capability {cid!r}")
            if not item.rubric:
                problems.append(f"item {item.id!r} has no rubric — it could not be scored")
            for c in item.rubric:
                if c.capability_id not in self.graph.capabilities:
                    problems.append(
                        f"item {item.id!r} criterion {c.id!r} references unknown "
                        f"capability {c.capability_id!r}")
                if c.weight <= 0:
                    problems.append(f"item {item.id!r} criterion {c.id!r} has weight <= 0")
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.001:
            problems.append(f"selection weights sum to {total:.3f}, expected 1.0")
        if problems:
            raise DiagnosticError(
                f"{len(problems)} problem(s) in diagnostic data:\n"
                + "\n".join(f"  - {p}" for p in problems)
            )

    # --- scoring ------------------------------------------------------------------
    def _claim_support(self, profile: CapabilityProfile) -> dict[str, float]:
        """THE §10 RULE, as data flowing backwards through the graph.

        For every capability the student claims but has not demonstrated, push a share of
        that claim's confidence onto the things it rests on — its contributors and its
        prerequisites. A bold claim about System Design makes Scalability, Trade-off
        Analysis and Database Performance worth testing, which is §10's worked example.

        A capability that already has evidence contributes nothing here: there is nothing
        left to take on trust.
        """
        support: dict[str, float] = {}
        for row in profile.all_rows():
            if not row.is_unverified or not row.confidence:
                continue
            underpinning = (
                self.graph.contributors_to(row.capability_id)
                + self.graph.prerequisites_of(row.capability_id)
            )
            for cap in underpinning:
                support[cap.id] = max(support.get(cap.id, 0.0), row.confidence)
        return support

    def _leverage(self) -> dict[str, float]:
        """How much of the graph depends on each capability, normalised to 0..1."""
        counts = {
            cid: len(self.graph.unlocked_by(cid)) + len(self.graph.edges_from(cid))
            for cid in self.graph.capabilities
        }
        peak = max(counts.values()) or 1
        return {cid: n / peak for cid, n in counts.items()}

    def score(
        self, profile: CapabilityProfile,
        relevance: dict[str, float] | None = None,
    ) -> list[Candidate]:
        """Score every capability on how much verifying it would tell us.

        `relevance` is a per-capability weight in 0..1 supplied by the caller, and it
        replaced a flat "is this in the goal's focus list" boolean. A milestone knows more
        than membership: a requirement the learner CLAIMS but has never had checked is
        worth more than one already demonstrated, because the progress estimate depends on
        it and cannot justify it.

        Deliberately a plain mapping rather than a milestone object — this module does not
        need to learn what a milestone is, and the policy that produces these numbers lives
        in one named function (`MilestoneProgress.relevance`).
        """
        weights = relevance or {}
        support = self._claim_support(profile)
        leverage = self._leverage()
        blocked = profile.blocked()
        w = self.weights

        candidates: list[Candidate] = []
        for cap in self.graph.capabilities.values():
            row = profile.row_for(cap.id)
            notes: list[str] = []

            # Uncertainty — a claim with no evidence is the whole reason to diagnose.
            # Something already assessed is largely settled; something never mentioned at
            # all is unknown but the student has not staked anything on it.
            if row.is_unverified:
                uncertainty = 1.0
            elif row.mastery is None:
                uncertainty = 0.35
            else:
                uncertainty = 0.15

            stake = row.confidence or 0.0
            goal_relevance = float(weights.get(cap.id, 0.0))
            gap = row.calibration_gap
            calibration = max(0.0, gap) if gap is not None else 0.0

            claim_support = support.get(cap.id, 0.0)
            if claim_support:
                notes.append("underpins an unverified claim")
            if row.is_unverified:
                notes.append(f"claimed {row.confidence:.0%}, never checked")
            if calibration > 0:
                notes.append(f"claim sat {calibration:+.2f} above the evidence")

            factors = {
                "uncertainty": w["uncertainty"] * uncertainty,
                "stake": w["stake"] * stake,
                "goal_relevance": w["goal_relevance"] * goal_relevance,
                "leverage": w["leverage"] * leverage.get(cap.id, 0.0),
                "calibration": w["calibration"] * calibration,
                "claim_support": w["claim_support"] * claim_support,
            }
            total = sum(factors.values())

            # Testing something whose own prerequisites are unproven measures the
            # prerequisite, not the capability. Scale down rather than exclude, so a
            # student with nothing verified still gets a diagnostic.
            unmet = blocked.get(cap.id, [])
            ready = not unmet
            if unmet:
                total *= float(self.selection["unready_penalty"])
                notes.append(
                    f"rests on unproven {', '.join(c.name for c in unmet)}"
                )

            candidates.append(Candidate(
                capability_id=cap.id, score=total, factors=factors,
                notes=tuple(notes), ready=ready,
            ))

        return sorted(candidates, key=lambda c: (-c.score, c.capability_id))

    # --- assembly ------------------------------------------------------------------
    def items_for(self, capability_id: str) -> list[DiagnosticItem]:
        return [i for i in self.items if i.capability_id == capability_id]

    def build(
        self,
        profile: CapabilityProfile,
        relevance: dict[str, float] | None = None,
        limit: int | None = None,
    ) -> Diagnostic:
        """Select a small number of capabilities and assemble scenarios for them."""
        limit = limit or int(self.selection["max_capabilities"])
        min_score = float(self.selection["min_score"])
        discount = float(self.selection.get("secondary_coverage_discount", 1.0))
        ranked = self.score(profile, relevance)

        selected: list[Candidate] = []
        items: list[DiagnosticItem] = []
        skipped: list[Candidate] = []
        secondary: set[str] = set()
        used_items: set[str] = set()
        chosen_ids: set[str] = set()

        # Re-rank after every pick, because choosing a scenario changes what the
        # remaining slots are worth: a capability the chosen scenario already touches is
        # partly covered, so it competes at a discount.
        while len(selected) < limit:
            best: tuple[float, Candidate, DiagnosticItem] | None = None
            for cand in ranked:
                if cand.capability_id in chosen_ids:
                    continue
                effective = cand.score * (discount if cand.capability_id in secondary else 1.0)
                if effective < min_score:
                    continue
                available = [i for i in self.items_for(cand.capability_id)
                             if i.id not in used_items]
                if not available:
                    if cand not in skipped and cand.score >= min_score:
                        skipped.append(cand)
                    continue
                if best is None or effective > best[0]:
                    best = (effective, cand, available[0])
            if best is None:
                break
            _, cand, item = best
            selected.append(cand)
            items.append(item)
            used_items.add(item.id)
            chosen_ids.add(cand.capability_id)
            secondary.update(item.also_exercises)
            secondary.discard(cand.capability_id)

        secondary -= chosen_ids

        return Diagnostic(
            student_id=profile.student.id,
            selected=selected,
            items=items,
            considered=ranked,
            skipped_no_scenario=skipped,
            secondary_coverage=tuple(sorted(secondary)),
        )

    def uncovered(self) -> list[Capability]:
        """Capabilities with no authored scenario — the content work queue."""
        have = {i.capability_id for i in self.items}
        return [c for c in self.graph.capabilities.values() if c.id not in have]
