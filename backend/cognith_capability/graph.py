"""CapabilityGraph — loads data/capabilities.yaml, validates it, answers queries.

Validation is the point of this module as much as the queries are. Claude.md §7 requires
relationships to live in data, and hand-authored data drifts: a renamed id leaves a
dangling edge, and nothing complains until something downstream quietly returns nothing.
The knowledge corpus already has exactly that problem (decisions.md Q3 — a prerequisite
pointing at a document that does not exist). Loading refuses rather than inheriting it.
"""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable

import yaml

from .models import (
    ACYCLIC_RELATIONS,
    Capability,
    CapabilityEdge,
    GraphValidationError,
    Level,
    RelationType,
)

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "capabilities.yaml"


class CapabilityGraph:
    """An immutable, validated capability graph held in memory.

    Small by design (16 capabilities, 21 edges), so every query is a plain scan and the
    whole graph is printable. Claude.md §7 rules out a graph database until there is a
    demonstrated need; `to_records()` provides the Firestore shape for when §19's
    collections arrive.
    """

    def __init__(
        self,
        domain: str,
        areas: dict[str, str],
        capabilities: Iterable[Capability],
        edges: Iterable[CapabilityEdge],
        *,
        validate: bool = True,
    ):
        self.domain = domain
        self.areas = dict(areas)
        self.capabilities: dict[str, Capability] = {c.id: c for c in capabilities}
        self.edges: tuple[CapabilityEdge, ...] = tuple(edges)

        self._out: dict[str, list[CapabilityEdge]] = defaultdict(list)
        self._in: dict[str, list[CapabilityEdge]] = defaultdict(list)
        for e in self.edges:
            self._out[e.source_id].append(e)
            self._in[e.target_id].append(e)

        if validate:
            self.validate()

    # --- loading ----------------------------------------------------------------
    @classmethod
    def load(cls, path: Path = DEFAULT_PATH, *, validate: bool = True) -> "CapabilityGraph":
        if not path.exists():
            raise FileNotFoundError(f"No capability data at {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        domain = raw["domain"]
        return cls(
            domain=domain,
            areas=raw.get("areas", {}),
            capabilities=[Capability.from_dict(d, domain) for d in raw["capabilities"]],
            edges=[CapabilityEdge.from_dict(d) for d in raw["edges"]],
            validate=validate,
        )

    # --- validation -------------------------------------------------------------
    def validate(self) -> None:
        """Collect every inconsistency and raise once. Silence means the graph is sound."""
        problems: list[str] = []
        seen: set[str] = set()

        for cap in self.capabilities.values():
            if cap.id in seen:
                problems.append(f"duplicate capability id: {cap.id!r}")
            seen.add(cap.id)
            if cap.area not in self.areas:
                problems.append(
                    f"{cap.id!r} has unknown area {cap.area!r} "
                    f"(known: {sorted(self.areas)})"
                )
            if not cap.statement:
                problems.append(f"{cap.id!r} has no statement (Claude.md §6.1)")
            # A capability named as a bare topic is the failure §6.1 calls out. We cannot
            # detect that reliably, but a statement that does not describe an action is a
            # decent proxy for someone pasting the topic in.
            elif not cap.statement.lower().startswith("can "):
                problems.append(
                    f"{cap.id!r} statement should describe an action and start with "
                    f"'Can ' (§6.1): {cap.statement[:50]!r}"
                )

        for e in self.edges:
            for role, cid in (("from", e.source_id), ("to", e.target_id)):
                if cid not in self.capabilities:
                    problems.append(f"edge {e} has unknown {role} id {cid!r}")
            if e.source_id == e.target_id:
                problems.append(f"self-edge: {e}")

        pairs = [(e.source_id, e.relation, e.target_id) for e in self.edges]
        for p in {p for p in pairs if pairs.count(p) > 1}:
            problems.append(f"duplicate edge: {p[0]} --{p[1].value}--> {p[2]}")

        for relation in ACYCLIC_RELATIONS:
            cycle = self._find_cycle(relation)
            if cycle:
                problems.append(
                    f"{relation.value} cycle: {' -> '.join(cycle)} "
                    "(prerequisites must be orderable)"
                )

        if problems:
            raise GraphValidationError(problems)

    def _find_cycle(self, relation: RelationType) -> list[str] | None:
        """Return one cycle over edges of `relation`, or None. Iterative DFS with colours."""
        WHITE, GREY, BLACK = 0, 1, 2
        colour = {cid: WHITE for cid in self.capabilities}
        parent: dict[str, str | None] = {}

        def successors(cid: str) -> list[str]:
            return [
                e.target_id
                for e in self._out.get(cid, ())
                if e.relation is relation and e.target_id in self.capabilities
            ]

        for start in self.capabilities:
            if colour[start] != WHITE:
                continue
            parent[start] = None
            stack: list[tuple[str, bool]] = [(start, False)]
            while stack:
                node, exiting = stack.pop()
                if exiting:
                    colour[node] = BLACK
                    continue
                if colour[node] != WHITE:
                    continue
                colour[node] = GREY
                stack.append((node, True))
                for nxt in successors(node):
                    if colour[nxt] == GREY:  # back edge — walk the parents home
                        cycle = [nxt]
                        cur: str | None = node
                        while cur is not None and cur != nxt:
                            cycle.append(cur)
                            cur = parent.get(cur)
                        cycle.append(nxt)
                        return list(reversed(cycle))
                    if colour[nxt] == WHITE:
                        parent[nxt] = node
                        stack.append((nxt, False))
        return None

    # --- lookup -----------------------------------------------------------------
    def get(self, capability_id: str) -> Capability:
        try:
            return self.capabilities[capability_id]
        except KeyError:
            raise KeyError(
                f"No capability {capability_id!r}. Known ids: "
                f"{', '.join(sorted(self.capabilities))}"
            ) from None

    def by_area(self, area: str) -> list[Capability]:
        return [c for c in self.capabilities.values() if c.area == area]

    def by_level(self, level: Level | str) -> list[Capability]:
        level = Level(level)
        return [c for c in self.capabilities.values() if c.level is level]

    def tree(self) -> dict[str, list[Capability]]:
        """Capabilities grouped by area, in the §7 tree's order."""
        return {area: self.by_area(area) for area in self.areas}

    # --- edge queries -----------------------------------------------------------
    def edges_from(self, capability_id: str, relation: RelationType | None = None):
        self.get(capability_id)
        return [
            e
            for e in self._out.get(capability_id, ())
            if relation is None or e.relation is relation
        ]

    def edges_to(self, capability_id: str, relation: RelationType | None = None):
        self.get(capability_id)
        return [
            e
            for e in self._in.get(capability_id, ())
            if relation is None or e.relation is relation
        ]

    def prerequisites_of(self, capability_id: str) -> list[Capability]:
        """Direct prerequisites — what must come before this capability."""
        return [
            self.get(e.source_id)
            for e in self.edges_to(capability_id, RelationType.PREREQUISITE_FOR)
        ]

    def unlocked_by(self, capability_id: str) -> list[Capability]:
        """What this capability is a direct prerequisite for."""
        return [
            self.get(e.target_id)
            for e in self.edges_from(capability_id, RelationType.PREREQUISITE_FOR)
        ]

    def prerequisite_closure(self, capability_id: str) -> list[Capability]:
        """Every transitive prerequisite, ordered furthest-upstream first.

        This is what Phase 5 needs: if a student claims System Design, the capabilities
        worth verifying first are the ones everything else rests on. BFS upward, then
        ordered by distance so the deepest foundations come first.
        """
        self.get(capability_id)
        depth: dict[str, int] = {}
        queue = deque([(capability_id, 0)])
        while queue:
            cid, d = queue.popleft()
            for e in self.edges_to(cid, RelationType.PREREQUISITE_FOR):
                if e.source_id not in depth or depth[e.source_id] < d + 1:
                    depth[e.source_id] = d + 1
                    queue.append((e.source_id, d + 1))
        return [
            self.get(cid)
            for cid, _ in sorted(depth.items(), key=lambda kv: (-kv[1], kv[0]))
        ]

    def contributors_to(self, capability_id: str) -> list[Capability]:
        """Capabilities that compose into this one, by any non-prerequisite relation.

        Used later for gap explanation: weak Scalability is only actionable once you know
        Caching and Load Balancing are what it is built from.
        """
        return [
            self.get(e.source_id)
            for e in self.edges_to(capability_id)
            if e.relation is not RelationType.PREREQUISITE_FOR
        ]

    def neighbours(self, capability_id: str) -> list[CapabilityEdge]:
        """Every edge touching this capability, in or out."""
        return self.edges_from(capability_id) + self.edges_to(capability_id)

    def isolated(self) -> list[Capability]:
        """Capabilities with no edges at all — honest output, not an error.

        An isolated capability is not wrong (Git genuinely does not depend on HTTP), but
        it cannot be reached by graph-driven recommendation, so it should be visible.
        """
        return [c for c in self.capabilities.values() if not self.neighbours(c.id)]

    # --- knowledge coverage -----------------------------------------------------
    def knowledge_docs(self) -> dict[str, list[str]]:
        """capability id -> knowledge document ids, for capabilities that have any."""
        return {
            c.id: list(c.knowledge_docs)
            for c in self.capabilities.values()
            if c.knowledge_docs
        }

    def without_knowledge(self) -> list[Capability]:
        """Capabilities the corpus has no material for. Phase 7's work queue."""
        return [c for c in self.capabilities.values() if not c.knowledge_docs]

    # --- export -----------------------------------------------------------------
    def to_records(self) -> dict[str, list[dict[str, Any]]]:
        """The two Claude.md §19 collections, ready to write to Firestore.

        Phase 1 keeps the graph in memory (§7: Firestore is sufficient, but there is no
        backend yet — decisions.md Q2). This method is why that migration is a
        serialization change rather than a redesign.
        """
        return {
            "capabilities": [c.to_record() for c in self.capabilities.values()],
            "capability_edges": [e.to_record() for e in self.edges],
        }

    def __len__(self) -> int:
        return len(self.capabilities)

    def __repr__(self) -> str:
        return (
            f"CapabilityGraph(domain={self.domain!r}, "
            f"capabilities={len(self.capabilities)}, edges={len(self.edges)})"
        )
