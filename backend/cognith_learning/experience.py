"""Learning experiences — Claude.md §6.3 and §21 Phase 8.

    "A learning experience is something the student does.
     Each experience should connect to one or more capabilities."

WHY THIS IS A THIN LAYER
------------------------
Two kinds of experience already existed by Phase 7 and neither knew about the other:

    diagnostic scenarios   data/diagnostics.yaml — prompt + rubric, assessable
    corpus exercises       knowledge/*.md, kind: exercise — good prose, NOT assessable
    explanations           produced by the RAG layer at request time, no rubric

Phase 8 does not build a new content system. It gives them one shape, so the adaptive loop
can choose between them, and so `assess()` works on any of them unchanged.

§22 lists "Full LMS" as a non-goal and §21 Phase 8 asks for "the minimum experience types
required for the MVP". §16's progression — explain, example, small practice, guided
challenge, independent challenge, realistic mission — needs three types plus the mission
Phase 9 adds. The other six names in §6.3 are variations that would add vocabulary without
adding behaviour.

THE SHAPE IS DELIBERATELY DiagnosticItem's
------------------------------------------
`LearningExperience` carries `id`, `capability_id`, `prompt` and `rubric`, which is exactly
what Phase 6's `assess()` consumes. So exercises became assessable without touching the
assessment code at all — the widening was a type hint.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from cognith_capability.graph import CapabilityGraph
from cognith_capability.models import Level
from cognith_rag.store import Store
from cognith_student.diagnostic import DiagnosticEngine, RubricCriterion

EXERCISES_PATH = Path(__file__).resolve().parent.parent / "data" / "exercises.yaml"
APPLICATIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "applications.yaml"


class ExperienceError(ValueError):
    """Raised when experience data does not line up with the corpus or the graph."""


class ExperienceType(str, Enum):
    """The MVP's types. §6.3 lists nine; these are the ones that carry behaviour."""

    EXPLANATION = "explanation"
    """Read. Produced by the knowledge layer against a gap. No rubric, no evidence —
    reading is not doing, and §6.5 wants evidence to be observable."""

    EXERCISE = "exercise"
    """Practise. Authored in the corpus, rubric in data/exercises.yaml. Produces evidence."""

    DIAGNOSTIC = "diagnostic"
    """Be measured. Selected by Phase 5. Produces evidence. Differs from an exercise in
    INTENT rather than in form: a diagnostic is chosen to resolve uncertainty, an exercise
    is chosen to close a known gap."""

    APPLY = "apply"
    """Integrate. Several capabilities at once, with nothing in the question naming which
    lever applies — that judgement IS the thing being tested, and practice cannot test it
    because practice puts the lever in the prompt.

    Added in Phase 12, correcting part of D29. The middle names in §16's progression were
    mostly vocabulary; this one was not. It carries behaviour the other types do not: a
    readiness gate (`requires`), because you cannot integrate what you have not practised."""

    MISSION = "mission"
    """Decide under consequences. Phase 9. Declared here so the type is not retrofitted."""

    GENERATED = "generated"
    """Verify transfer. Written by Gemini from course excerpts after a lesson — a NEW
    situation for the capability just taught (generator.py). Never recommended by the
    loop on its own: it is created on request, for one learner's follow-up."""


@dataclass(frozen=True)
class LearningExperience:
    """Something a learner does. §6.3.

    `capability_id` is the primary one, matching `DiagnosticItem`; the full set an
    experience touches is `capability_ids`, derived from its rubric so the two cannot
    disagree.
    """

    id: str
    type: ExperienceType
    title: str
    capability_id: str
    prompt: str
    rubric: tuple[RubricCriterion, ...] = ()
    level: Level = Level.INTERMEDIATE
    minutes: int = 8
    source: str = ""
    #: APPLY only — capabilities this integrates. It unlocks once each has evidence.
    requires: tuple[str, ...] = ()

    @property
    def capability_ids(self) -> tuple[str, ...]:
        """Every capability this experience can produce evidence for."""
        return tuple(dict.fromkeys(c.capability_id for c in self.rubric))

    @property
    def assessable(self) -> bool:
        """An experience with no rubric produces no evidence. §6.5 — evidence is
        observable proof, and there is nothing to observe in having read something."""
        return bool(self.rubric)

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "title": self.title,
            "capabilityId": self.capability_id,
            "capabilityIds": list(self.capability_ids),
            "level": self.level.value,
            "minutes": self.minutes,
            "source": self.source,
            "assessable": self.assessable,
            "requires": list(self.requires),
        }


class ExperienceLibrary:
    """Every experience the system can offer, from both sources, in one shape."""

    def __init__(self, graph: CapabilityGraph, experiences: list[LearningExperience]):
        self.graph = graph
        self.experiences = {e.id: e for e in experiences}

    @classmethod
    def load(cls, graph: CapabilityGraph, path: Path = EXERCISES_PATH) -> "ExperienceLibrary":
        return cls(graph, cls._diagnostics(graph) + cls._exercises(graph, path)
                   + cls._applications(graph) + cls._missions(graph)
                   + cls._generated(graph))

    @staticmethod
    def _generated(graph: CapabilityGraph) -> list[LearningExperience]:
        """Persisted generated challenges, so their rubrics resolve like any other's."""
        from cognith_student.storage import get_storage

        from .generator import from_record

        return [from_record(d) for d in get_storage().list_activities()
                if d.get("capabilityId") in graph.capabilities]

    # --- sources ------------------------------------------------------------------
    @staticmethod
    def _diagnostics(graph: CapabilityGraph) -> list[LearningExperience]:
        """Phase 5's scenarios, adapted. Nothing about them changes."""
        engine = DiagnosticEngine.load(graph)
        return [
            LearningExperience(
                id=item.id,
                type=ExperienceType.DIAGNOSTIC,
                title=f"{graph.get(item.capability_id).name} diagnostic",
                capability_id=item.capability_id,
                prompt=item.prompt,
                rubric=item.rubric,
                level=item.level,
                minutes=item.minutes,
                source="data/diagnostics.yaml",
            )
            for item in engine.items
        ]

    @staticmethod
    def _exercises(graph: CapabilityGraph, path: Path) -> list[LearningExperience]:
        """Corpus exercises joined to their rubrics by chunk id.

        The prompt is read from the CORPUS, never from the rubric file, so there is one
        copy of each exercise. A chunk id that no longer resolves is an error rather than
        a silently missing exercise — the dangling-reference discipline every phase has
        applied since Phase 1.
        """
        if not path.exists():
            return []
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        chunks = {c.id: c for c in Store.load().chunks}

        out: list[LearningExperience] = []
        problems: list[str] = []
        for entry in spec.get("exercises", []):
            chunk = chunks.get(entry["chunk"])
            if chunk is None:
                problems.append(f"exercise {entry['chunk']!r} is not in the index — "
                                f"re-run `python ingest.py`, or the section was renamed")
                continue
            if chunk.metadata.get("kind") != "exercise":
                problems.append(f"{entry['chunk']!r} is tagged "
                                f"{chunk.metadata.get('kind')!r}, not 'exercise'")
            rubric = tuple(RubricCriterion.from_dict(c) for c in entry.get("rubric", []))
            for c in rubric:
                if c.capability_id not in graph.capabilities:
                    problems.append(f"{entry['chunk']!r} criterion {c.id!r} references "
                                    f"unknown capability {c.capability_id!r}")
            caps = entry.get("capabilities") or []
            for cid in caps:
                if cid not in graph.capabilities:
                    problems.append(f"{entry['chunk']!r} lists unknown capability {cid!r}")
            if not rubric:
                problems.append(f"{entry['chunk']!r} has no rubric — it could not be scored")

            # The embedded text carries a "Concept — Heading" prefix for retrieval; strip
            # it so the learner reads the exercise, not the indexing artefact.
            body = chunk.text.split("\n\n", 1)[-1].strip()
            out.append(LearningExperience(
                id=chunk.id,
                type=ExperienceType.EXERCISE,
                title=entry.get("title", chunk.section),
                capability_id=caps[0] if caps else rubric[0].capability_id,
                prompt=body,
                rubric=rubric,
                level=Level(entry.get("level", "intermediate")),
                minutes=int(entry.get("minutes", 8)),
                source=chunk.citation,
            ))

        if problems:
            raise ExperienceError(
                f"{len(problems)} problem(s) in data/exercises.yaml:\n"
                + "\n".join(f"  - {p}" for p in problems))
        return out

    @staticmethod
    def _applications(graph: CapabilityGraph, path: Path = APPLICATIONS_PATH) -> list[LearningExperience]:
        """Integration scenarios. Authored whole — prompt and rubric together."""
        if not path.exists():
            return []
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        out: list[LearningExperience] = []
        problems: list[str] = []
        for entry in spec.get("applications", []):
            rubric = tuple(RubricCriterion.from_dict(c) for c in entry.get("rubric", []))
            requires = tuple(entry.get("requires") or ())
            for cid in (*requires, *(c.capability_id for c in rubric)):
                if cid not in graph.capabilities:
                    problems.append(f"application {entry['id']!r} references unknown "
                                    f"capability {cid!r}")
            if not rubric:
                problems.append(f"application {entry['id']!r} has no rubric")
            if not requires:
                problems.append(f"application {entry['id']!r} requires nothing — an apply "
                                f"scenario that integrates nothing is an exercise")
            out.append(LearningExperience(
                id=entry["id"], type=ExperienceType.APPLY, title=entry["title"],
                capability_id=requires[0] if requires else rubric[0].capability_id,
                prompt=entry["prompt"].strip(), rubric=rubric,
                level=Level(entry.get("level", "intermediate")),
                minutes=int(entry.get("minutes", 15)),
                source="data/applications.yaml", requires=requires,
            ))
        if problems:
            raise ExperienceError(
                f"{len(problems)} problem(s) in data/applications.yaml:\n"
                + "\n".join(f"  - {p}" for p in problems))
        return out

    @staticmethod
    def _missions(graph: CapabilityGraph) -> list[LearningExperience]:
        """Phase 9's missions, adapted. The simulation stays in the mission engine — what
        the library exposes is the assessable surface: the brief as the prompt and the
        rubric to judge the session transcript against.

        Because `LearningExperience` satisfies the `Assessable` protocol (D30), a mission
        is assessed by exactly the same code as a diagnostic or an exercise. Phase 9
        required no change to the assessment layer at all.
        """
        from .mission import MISSIONS_PATH, MissionEngine

        if not MISSIONS_PATH.exists():
            return []
        import yaml
        spec = yaml.safe_load(MISSIONS_PATH.read_text(encoding="utf-8"))
        out: list[LearningExperience] = []
        for entry in spec.get("missions", []):
            m = MissionEngine.load(entry["id"]).mission
            for c in m.rubric:
                if c.capability_id not in graph.capabilities:
                    raise ExperienceError(
                        f"mission {m.id!r} criterion {c.id!r} references unknown "
                        f"capability {c.capability_id!r}")
            out.append(LearningExperience(
                id=m.id, type=ExperienceType.MISSION, title=m.title,
                capability_id=m.capability_id, prompt=m.brief, rubric=m.rubric,
                level=m.level, minutes=m.minutes, source="data/missions.yaml",
            ))
        return out

    # --- queries ------------------------------------------------------------------
    def get(self, experience_id: str) -> LearningExperience:
        try:
            return self.experiences[experience_id]
        except KeyError:
            raise KeyError(f"No experience {experience_id!r}") from None

    def of_type(self, type_: ExperienceType) -> list[LearningExperience]:
        return [e for e in self.experiences.values() if e.type is type_]

    def for_capability(
        self, capability_id: str, type_: ExperienceType | None = None
    ) -> list[LearningExperience]:
        """Every experience that can produce evidence for this capability.

        Includes experiences whose PRIMARY capability is something else but whose rubric
        has a criterion tagged with this one — which is how a single answer moves several
        capabilities (D25), now applied to selection as well as to scoring.
        """
        self.graph.get(capability_id)
        found = [
            e for e in self.experiences.values()
            if capability_id in e.capability_ids
            and (type_ is None or e.type is type_)
        ]
        # Primary first, then by how much of the rubric actually evidences this capability.
        return sorted(
            found,
            key=lambda e: (
                e.capability_id != capability_id,
                -sum(c.weight for c in e.rubric if c.capability_id == capability_id),
            ),
        )

    def ready_to_apply(self, profile) -> list[LearningExperience]:
        """Apply scenarios whose component capabilities all have evidence.

        The gate that makes the four stages a ladder rather than a menu. Evidence, not
        mastery — you may have practised something and done badly; integrating it is still
        a reasonable next move, and often the thing that reveals why you did badly.
        """
        out = []
        for e in self.of_type(ExperienceType.APPLY):
            if all(profile.row_for(c).evidence_count > 0 for c in e.requires):
                out.append(e)
        return out

    def apply_blocked_by(self, experience: LearningExperience, profile) -> list[Capability]:
        """Which of an apply scenario's components have no evidence yet."""
        return [self.graph.get(c) for c in experience.requires
                if profile.row_for(c).evidence_count == 0]

    def practice_for(self, capability_id: str) -> list[LearningExperience]:
        """Exercises only — what to offer once a gap is known and explained."""
        return self.for_capability(capability_id, ExperienceType.EXERCISE)

    def uncovered(self) -> list[str]:
        """Capabilities no assessable experience reaches. The content work queue."""
        reached = {cid for e in self.experiences.values() for cid in e.capability_ids}
        return [c.id for c in self.graph.capabilities.values() if c.id not in reached]

    def __len__(self) -> int:
        return len(self.experiences)
