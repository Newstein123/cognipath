"""Onboarding — Claude.md §8's intake into §9's initial capability map.

Deterministic. No Gemini call, deliberately: §26.4 says not to hide important logic in
prompts, and the technology-to-capability mapping is domain knowledge that belongs in
data/onboarding.yaml alongside the capability graph. Every resulting number carries the
reason it exists, which §26.7 requires and a model's guess cannot supply.

What this produces is a SELF-REPORT ESTIMATE. It sets `confidence` and never `mastery` —
§9 is explicit that the initial map is "an estimate based on what you've told us", and
decisions.md D12 is what keeps the two apart in the data model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from cognith_capability.graph import CapabilityGraph
from cognith_capability.models import RelationType

from .models import Student, StudentCapability
from .profile import CapabilityProfile

from cognith_course import path as course_path


class OnboardingError(ValueError):
    """Raised when intake answers or the vocabulary file are unusable."""


@dataclass(frozen=True)
class OnboardingAnswers:
    """Claude.md §8's five questions.

    `knows` and `built` are prose and are stored VERBATIM as well as scanned. §26.7 —
    the raw answer is provenance, and later phases (a diagnostic's framing, an
    assessment's context) may want what the student actually wrote.
    """

    student_name: str
    goal: str                              # a key in onboarding.yaml `goals`
    technologies: tuple[str, ...] = ()     # Q2 — "What technologies have you used?"
    knows: str = ""                        # Q1 — "What do you already know?"
    built: str = ""                        # Q3 — "What have you built?"
    self_rated_level: str = "intermediate" # Q4 — "How confident are you?"

    def free_text(self) -> str:
        return f"{self.knows}\n{self.built}"


@dataclass(frozen=True)
class Signal:
    """One reason to believe a student has some confidence in one capability.

    `kind` records where it came from, which is what makes an estimate auditable:

        technology  an explicitly listed technology        — strongest
        phrase      a phrase matched in a free-text answer — discounted
        derived     propagated one hop along the graph     — discounted by relation
    """

    capability_id: str
    value: float
    kind: str
    source: str

    def __str__(self) -> str:
        return f"{self.value:.2f}  {self.kind:10} {self.source}"


@dataclass(frozen=True)
class InitialEstimate:
    """The confidence chosen for one capability, and why.

    `considered` holds every signal that was in play, so the UI can show not just the
    winning reason but what else was weighed. `ceiling_applied` records the pre-cap value
    whenever the self-rated level reduced it — otherwise a student would see a number with
    no explanation for why it is lower than their strongest signal.
    """

    capability_id: str
    confidence: float
    chosen: Signal
    considered: tuple[Signal, ...] = ()
    ceiling_applied: float | None = None


@dataclass
class OnboardingResult:
    answers: OnboardingAnswers
    estimates: list[InitialEstimate] = field(default_factory=list)
    unrecognised_technologies: list[str] = field(default_factory=list)
    matched_phrases: list[str] = field(default_factory=list)

    def by_id(self) -> dict[str, InitialEstimate]:
        return {e.capability_id: e for e in self.estimates}


class OnboardingEngine:
    """Builds an initial capability profile from intake answers."""

    def __init__(self, graph: CapabilityGraph, spec: dict[str, Any]):
        self.graph = graph
        self.levels = spec["levels"]
        self.goals = spec["goals"]
        self.technologies = spec["technologies"]
        self.concepts = spec["concepts"]
        self.rules = spec["rules"]
        self._validate()

    @classmethod
    def load(cls, graph: CapabilityGraph, path: Path | None = None) -> "OnboardingEngine":
        path = path or course_path("onboarding.yaml")
        if not path.exists():
            raise FileNotFoundError(f"No onboarding vocabulary at {path}")
        return cls(graph, yaml.safe_load(path.read_text(encoding="utf-8")))

    def _validate(self) -> None:
        """Every capability id referenced anywhere must exist in the graph.

        The same dangling-reference check as Phase 1 and Phase 2. A typo here would
        silently drop a signal rather than fail, and nothing downstream would notice.
        """
        problems: list[str] = []
        known = set(self.graph.capabilities)

        def check(where: str, ids: Iterable[str]) -> None:
            for cid in ids:
                if cid not in known:
                    problems.append(f"{where} references unknown capability {cid!r}")

        for key, entry in self.technologies.items():
            check(f"technologies.{key}", entry.get("signals", {}))
        for key, entry in self.concepts.items():
            check(f"concepts.{key}", entry.get("signals", {}))
        for key, entry in self.goals.items():
            check(f"goals.{key}.focus", entry.get("focus", []))
        for relation in self.rules["propagation"]:
            try:
                RelationType(relation)
            except ValueError:
                problems.append(f"rules.propagation has unknown relation {relation!r}")
        if problems:
            raise OnboardingError(
                f"{len(problems)} problem(s) in onboarding vocabulary:\n"
                + "\n".join(f"  - {p}" for p in problems)
            )

    # --- signal collection -------------------------------------------------------
    def _direct_signals(self, answers: OnboardingAnswers) -> tuple[list[Signal], list[str], list[str]]:
        """Technology signals plus free-text phrase signals."""
        signals: list[Signal] = []
        unrecognised: list[str] = []
        matched: list[str] = []

        alias_to_tech = {
            alias.lower(): key
            for key, entry in self.technologies.items()
            for alias in entry.get("aliases", [key])
        }

        for raw in answers.technologies:
            key = alias_to_tech.get(raw.strip().lower())
            if key is None:
                unrecognised.append(raw.strip())
                continue
            entry = self.technologies[key]
            for cid, value in entry.get("signals", {}).items():
                signals.append(Signal(cid, float(value), "technology", entry["name"]))

        discount = float(self.rules["free_text_discount"])
        text = answers.free_text().lower()
        if text.strip():
            # Longest aliases first so "booking system" wins over a bare "system".
            for key, entry in self.concepts.items():
                for alias in sorted(entry.get("aliases", []), key=len, reverse=True):
                    if re.search(rf"\b{re.escape(alias.lower())}\b", text):
                        matched.append(alias)
                        for cid, value in entry.get("signals", {}).items():
                            signals.append(
                                Signal(cid, float(value) * discount, "phrase",
                                       f'"{alias}"')
                            )
                        break  # one match per concept is enough
        return signals, unrecognised, matched

    def _derived_signals(self, direct: list[Signal]) -> list[Signal]:
        """Propagate one hop along the graph, from DIRECT signals only.

        Restricting the source to direct signals is what stops a chain from manufacturing
        confidence: without it, Docker -> system-design -> reliability -> testing would
        produce a testing claim the student never made.
        """
        strongest: dict[str, float] = {}
        for s in direct:
            strongest[s.capability_id] = max(strongest.get(s.capability_id, 0.0), s.value)

        propagation = self.rules["propagation"]
        out: list[Signal] = []
        for cid, value in strongest.items():
            for edge in self.graph.edges_from(cid):
                factor = propagation.get(edge.relation.value, {}).get("forward")
                if factor:
                    out.append(Signal(
                        edge.target_id, value * float(factor), "derived",
                        f"{self.graph.get(cid).name} --{edge.relation.value}--> "
                        f"{self.graph.get(edge.target_id).name}",
                    ))
            for edge in self.graph.edges_to(cid):
                factor = propagation.get(edge.relation.value, {}).get("backward")
                if factor:
                    out.append(Signal(
                        edge.source_id, value * float(factor), "derived",
                        f"{self.graph.get(cid).name} <--{edge.relation.value}-- "
                        f"{self.graph.get(edge.source_id).name}",
                    ))
        return out

    # --- estimation ---------------------------------------------------------------
    def estimate(self, answers: OnboardingAnswers) -> OnboardingResult:
        if answers.goal not in self.goals:
            raise OnboardingError(
                f"Unknown goal {answers.goal!r}. Known: {', '.join(self.goals)}"
            )
        if answers.self_rated_level not in self.levels:
            raise OnboardingError(
                f"Unknown level {answers.self_rated_level!r}. "
                f"Known: {', '.join(self.levels)}"
            )

        direct, unrecognised, matched = self._direct_signals(answers)
        all_signals = direct + self._derived_signals(direct)
        ceiling = float(self.levels[answers.self_rated_level]["ceiling"])

        grouped: dict[str, list[Signal]] = {}
        for s in all_signals:
            grouped.setdefault(s.capability_id, []).append(s)

        estimates: list[InitialEstimate] = []
        for cid, signals in grouped.items():
            # max, not sum: combining weak signals into a strong one would manufacture
            # confidence the student never expressed, and max keeps one nameable reason
            # per number.
            best = max(signals, key=lambda s: s.value)
            capped = min(best.value, ceiling)
            estimates.append(InitialEstimate(
                capability_id=cid,
                confidence=round(capped, 3),
                chosen=best,
                considered=tuple(sorted(signals, key=lambda s: -s.value)),
                ceiling_applied=round(best.value, 3) if capped < best.value else None,
            ))

        # Present in §7 tree order rather than by score, so the map reads as a map.
        tree_order = {
            cap.id: i
            for i, cap in enumerate(
                cap for area in self.graph.areas for cap in self.graph.by_area(area)
            )
        }
        estimates.sort(key=lambda e: tree_order.get(e.capability_id, 999))

        return OnboardingResult(
            answers=answers,
            estimates=estimates,
            unrecognised_technologies=unrecognised,
            matched_phrases=matched,
        )

    def build_profile(
        self, answers: OnboardingAnswers, student_id: str = "student-001"
    ) -> tuple[CapabilityProfile, OnboardingResult]:
        """The Phase 3 deliverable: intake answers in, initial profile out.

        Sets `confidence` only. Every `mastery` stays None — onboarding produces claims,
        not evidence (§6.2, decisions.md D12).
        """
        result = self.estimate(answers)
        from cognith_course import current

        student = Student(
            id=student_id,
            name=answers.student_name,
            goal=self.goals[answers.goal]["name"],
            course=current(),
        )
        rows = [
            StudentCapability(
                student_id=student_id,
                capability_id=e.capability_id,
                confidence=e.confidence,
            )
            for e in result.estimates
        ]
        assert all(r.mastery is None for r in rows), "onboarding must not set mastery"
        return CapabilityProfile(student, rows, self.graph), result

    def focus_for(self, goal: str) -> list[str]:
        """Capabilities that matter for a goal — display ordering only.

        Never changes an estimate. A goal must not inflate a self-report.
        """
        return list(self.goals[goal].get("focus", []))
