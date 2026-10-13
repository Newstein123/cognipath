"""Capability and CapabilityEdge — the Phase 1 data model.

The rows themselves live in data/capabilities.yaml, per Claude.md §7: relationships are
stored as data, not hard-coded into business logic. What lives here is the *vocabulary* —
which relation types exist and what each one means to the engines built on top.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Level(str, Enum):
    """Expected difficulty band of a capability.

    An authoring estimate, not a measurement of any student. The diagnostic engine
    (Phase 5) reads it to decide what to verify first; it says nothing about mastery.
    """

    FOUNDATION = "foundation"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class RelationType(str, Enum):
    """The four relation types from Claude.md §7.

    A closed set. The edges are data, but their MEANING is code — an engine has to know
    that a missing prerequisite blocks assessment while a missing contributor does not.

    How much evidence propagates along each edge is NOT decided here. That is a Phase 6
    policy question; Phase 1 only records that the relationship exists.
    """

    PREREQUISITE_FOR = "prerequisite_for"
    """A must be developed before B is worth assessing. Blocking, and the only type that
    must stay acyclic — a prerequisite cycle would make the graph unorderable."""

    CONTRIBUTES_TO = "contributes_to"
    """A is a component of B. Non-blocking: B can be attempted with A undeveloped, it
    just will not go well."""

    SUPPORTS = "supports"
    """A is a technique or mechanism that serves B. B can be achieved by other means, so
    lacking A is not a gap in B."""

    APPLIES_TO = "applies_to"
    """A is cross-cutting and exercised inside B's context. The bidirectional one:
    evidence produced while working on B may also be evidence for A."""


#: Relation types that must not form a cycle. Only prerequisites imply an ordering.
ACYCLIC_RELATIONS = frozenset({RelationType.PREREQUISITE_FOR})

#: One-line semantics per relation type, for display and for reviewers of the data file.
#: Kept as a mapping rather than member docstrings because enum members do not carry
#: their own __doc__ — `RelationType.SUPPORTS.__doc__` returns the class docstring.
RELATION_SEMANTICS: dict[RelationType, str] = {
    RelationType.PREREQUISITE_FOR: (
        "A must be developed before B is worth assessing. Blocking, and the only type "
        "required to stay acyclic."
    ),
    RelationType.CONTRIBUTES_TO: (
        "A is a component of B. Non-blocking: B can be attempted with A undeveloped, it "
        "just will not go well."
    ),
    RelationType.SUPPORTS: (
        "A is a technique or mechanism that serves B. B can be achieved by other means, "
        "so lacking A is not itself a gap in B."
    ),
    RelationType.APPLIES_TO: (
        "A is cross-cutting and exercised inside B's context. Evidence produced while "
        "working on B may also be evidence for A."
    ),
}


@dataclass(frozen=True)
class Capability:
    """Something a learner can do (Claude.md §6.1).

    `statement` is the part that matters. A capability named "Caching" is a topic; a
    capability stating "Can decide where to cache, what to cache, and how to invalidate
    it" is something a piece of evidence can confirm or contradict. Later phases assess
    the statement, not the name.
    """

    id: str
    name: str
    statement: str
    description: str
    domain: str
    area: str
    level: Level
    #: `id:` values from knowledge/*.md frontmatter — documents that teach this
    #: capability. A separate vocabulary from capability ids, per decisions.md Q1/D9.
    #: Document ids, NOT the corpus's coarser `capability:` tags. Read by no code until
    #: Phase 7. Empty means the corpus has no material for this capability.
    knowledge_docs: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, d: dict[str, Any], domain: str) -> "Capability":
        return cls(
            id=d["id"],
            name=d["name"],
            statement=d["statement"].strip(),
            description=(d.get("description") or "").strip(),
            domain=domain,
            area=d["area"],
            level=Level(d["level"]),
            knowledge_docs=tuple(d.get("knowledge_docs") or ()),
        )

    def to_record(self) -> dict[str, Any]:
        """Shape for the `capabilities/` collection in Claude.md §19."""
        return {
            "id": self.id,
            "name": self.name,
            "statement": self.statement,
            "description": self.description,
            "domain": self.domain,
            "area": self.area,
            "level": self.level.value,
            "knowledgeDocs": list(self.knowledge_docs),
        }


@dataclass(frozen=True)
class CapabilityEdge:
    """A directed, typed relationship between two capabilities.

    `source` records where the edge came from: "claude-md-7" for the six examples given
    verbatim in the spec, otherwise authored for this phase. It exists so a reviewer can
    tell the specified edges from the proposed ones.
    """

    source_id: str
    relation: RelationType
    target_id: str
    origin: str = "authored"
    note: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CapabilityEdge":
        return cls(
            source_id=d["from"],
            relation=RelationType(d["relation"]),
            target_id=d["to"],
            origin=d.get("source", "authored"),
            note=(d.get("note") or "").strip(),
        )

    def __str__(self) -> str:
        return f"{self.source_id} --{self.relation.value}--> {self.target_id}"

    def to_record(self) -> dict[str, Any]:
        """Shape for the `capability_edges/` collection in Claude.md §19."""
        return {
            "id": f"{self.source_id}__{self.relation.value}__{self.target_id}",
            "from": self.source_id,
            "relation": self.relation.value,
            "to": self.target_id,
            "origin": self.origin,
        }


class GraphValidationError(ValueError):
    """Raised when data/capabilities.yaml is internally inconsistent.

    Carries every problem found, not just the first — fixing authored data one error per
    run is miserable.
    """

    def __init__(self, problems: list[str]):
        self.problems = problems
        joined = "\n".join(f"  - {p}" for p in problems)
        super().__init__(
            f"{len(problems)} problem(s) in the capability graph:\n{joined}"
        )
