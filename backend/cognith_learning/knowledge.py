"""Capability gap -> retrieved knowledge -> grounded explanation.

THE JOIN
--------
decisions.md D9 established that capabilities map to knowledge DOCUMENTS, not to the
corpus's `capability:` tags — the tags are too coarse, one `system-design` tag covering
caching.md, load-balancing.md and system-design.md. Retrieval is therefore restricted by
`Capability.knowledge_docs`, using the `docs` filter added to `Store.search`.

WHY THE QUERY IS BUILT FROM UNMET CRITERIA
------------------------------------------
Phase 6 produces something far more useful than "weak at scalability": it produces the
specific criteria a student failed to meet. "Did not say they would measure or profile
before changing anything" names material. A capability name does not.

WHAT HAPPENS WHEN THE CORPUS CANNOT HELP
----------------------------------------
Nothing special. The retrieval runs and the RAG system's three abstention gates refuse —
so the tutor says it has no material rather than inventing an explanation. Seven of
seventeen capabilities currently have no corpus at all; this is why that is safe. The
spike's central finding (docs/architecture.md §7) turns out to be exactly the mechanism
the capability layer needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cognith_capability.graph import CapabilityGraph
from cognith_capability.models import Capability
from cognith_rag.config import TOP_K
from cognith_rag.generate import Result, answer
from cognith_rag.store import Hit, Store
from cognith_student.evidence import Verdict
from cognith_student.models import DEMONSTRATED_AT
from cognith_student.profile import CapabilityProfile


@dataclass(frozen=True)
class Gap:
    """A capability the student cannot yet demonstrate, and what specifically is missing.

    `unmet` is the valuable part. A gap that only names a capability can retrieve a topic;
    a gap that carries "did not consider what happens when the cache goes stale" can
    retrieve the paragraph that addresses it.
    """

    capability_id: str
    mastery: float | None
    confidence: float | None
    #: Criterion texts the student did not meet, from Phase 6 evidence. Ordered with
    #: repeatedly-missed criteria first.
    unmet: tuple[str, ...] = ()
    #: Of those, the ones missed more than once — blind spots rather than slips.
    persistent: tuple[str, ...] = ()
    #: Which diagnostic responses those came from.
    from_evidence: tuple[str, ...] = ()
    reason: str = ""

    @property
    def is_demonstrated_gap(self) -> bool:
        """True when evidence established the gap, rather than it merely being unverified."""
        return self.mastery is not None


@dataclass
class KnowledgeForGap:
    """What the knowledge layer could offer for one gap."""

    gap: Gap
    capability: Capability
    query: str
    question: str
    docs: tuple[str, ...]
    hits: list[Hit] = field(default_factory=list)
    exercises: list[Hit] = field(default_factory=list)
    result: Result | None = None
    prerequisites_first: tuple[Capability, ...] = ()
    #: True when `result` answers the targeted question (the learner's missed points),
    #: False when it fell back to the general one.
    targeted: bool = False

    @property
    def has_corpus(self) -> bool:
        return bool(self.docs)

    @property
    def answered(self) -> bool:
        return bool(self.result and self.result.answered)

    def to_record(self) -> dict[str, Any]:
        return {
            "capabilityId": self.gap.capability_id,
            "query": self.query,
            "question": self.question,
            "docs": list(self.docs),
            "retrieved": [
                {"id": h.chunk.id, "citation": h.chunk.citation, "score": round(h.score, 4)}
                for h in self.hits
            ],
            "answered": self.answered,
            "gate": self.result.gate if self.result else "not_attempted",
            "explanation": self.result.answer if self.result else "",
            "citations": list(self.result.citations) if self.result else [],
            "exercises": [h.chunk.citation for h in self.exercises],
        }


class GapResolver:
    """Finds gaps, then asks the knowledge layer what it has for them."""

    def __init__(self, graph: CapabilityGraph, profile: CapabilityProfile):
        self.graph = graph
        self.profile = profile
        self._store: Store | None = None

    @property
    def store(self) -> Store:
        if self._store is None:
            self._store = Store.load()
        return self._store

    # --- gap detection ------------------------------------------------------------
    def _unmet_by_capability(self) -> dict[str, list[tuple[str, str]]]:
        """Read the Phase 6 evidence log for criteria the student did not meet.

        Returns capability id -> [(criterion text, experience id)]. Missing log is not an
        error: a student may have a profile and no evidence yet.
        """
        from cognith_student.storage import get_storage

        log = get_storage().load_evidence(self.profile.student.id)
        if not log:
            return {}
        # Every experience type, not just diagnostics. Using DiagnosticEngine here meant
        # criteria from exercises, apply scenarios and missions were invisible to gap
        # detection — a learner could fail the same exercise criterion repeatedly and the
        # gap would carry no detail at all. Introduced in Phase 7 when diagnostics were
        # the only assessable thing; exposed in Phase 13 by the first exercise retry.
        from .experience import ExperienceLibrary

        library = ExperienceLibrary.load(self.graph)
        criteria = {c.id: c
                    for e in library.experiences.values() for c in e.rubric}

        # Only the MOST RECENT attempt that touched each capability. Accumulating every
        # miss in history meant a learner who later got union and intersection right was
        # still "missing" them, so a remedial lesson re-taught what they had since shown.
        # Repeated blind spots are tracked separately (history.persistent_misses) and
        # reach the learning engine through learner_context.
        # Two kinds of evidence, two rules:
        #   assessments (diagnosis, practice, challenges) — the most recent one per
        #     capability speaks for the whole skill, so its misses are the misses;
        #   lesson checks ("checks-…", one concept each) — each concept keeps its own
        #     latest outcome, so finishing concept 3 does not erase that concept 1 is
        #     still unclear. A concept leaves the list once a later check shows it.
        latest: dict[str, dict] = {}
        concept_state: dict[tuple[str, str], tuple[str, str, str]] = {}
        for entry in log:  # chronological: append-only log
            ev = entry["evidence"]
            lesson = ev["experienceId"].startswith("checks-")
            for r in ev.get("results", []):
                c = criteria.get(r["criterionId"])
                if c is None:
                    continue
                if lesson:
                    concept_state[(c.capability_id, c.criterion)] = (r["verdict"], ev["experienceId"], c.id)
                else:
                    latest[c.capability_id] = ev

        out: dict[str, list[tuple[str, str]]] = {}
        for cap_id, ev in latest.items():
            for r in ev.get("results", []):
                c = criteria.get(r["criterionId"])
                if c is None or c.capability_id != cap_id or r["verdict"] == Verdict.MET.value:
                    continue
                out.setdefault(cap_id, []).append((c.criterion, ev["experienceId"], c.id))
        for (cap_id, text), (verdict, exp_id, cid) in concept_state.items():
            if verdict == Verdict.UNMET.value:
                out.setdefault(cap_id, []).append((text, exp_id, cid))

        # Criteria missed MORE THAN ONCE lead. A criterion missed once is a slip; missed
        # again after the learner was told exactly what was wrong is a blind spot. The
        # retrieval query is built from the first few unmet criteria, so this ordering
        # decides what the knowledge layer actually goes looking for.
        from cognith_student.history import load_history

        repeated = {t.criterion_id
                    for t in load_history(self.profile.student.id).persistent_misses()}
        if repeated:
            for cid, items in out.items():
                items.sort(key=lambda triple: triple[2] not in repeated)
        return out

    def _repeated(self) -> set[str]:
        from cognith_student.history import load_history

        return {t.criterion_id
                for t in load_history(self.profile.student.id).persistent_misses()}

    def gaps(self, threshold: float = DEMONSTRATED_AT, include_unverified: bool = False) -> list[Gap]:
        """Capabilities worth teaching, weakest demonstrated first.

        By default only DEMONSTRATED gaps are returned. A capability the student merely
        claimed is not a gap — it is an unknown, and the honest response to an unknown is
        a diagnostic (Phase 5), not a lesson. `include_unverified` relaxes that for
        callers who want the wider list.
        """
        unmet = self._unmet_by_capability()
        found: list[Gap] = []

        for row in self.profile.all_rows():
            criteria = unmet.get(row.capability_id, [])
            if row.mastery is not None and row.mastery < threshold:
                reason = f"demonstrated {row.mastery:.0%}, below {threshold:.0%}"
            elif criteria and row.mastery is not None:
                reason = "met the capability overall, but specific criteria were missed"
            elif include_unverified and row.is_unverified:
                reason = f"claimed {row.confidence:.0%} but never verified"
            else:
                continue
            found.append(Gap(
                capability_id=row.capability_id,
                mastery=row.mastery,
                confidence=row.confidence,
                unmet=tuple(dict.fromkeys(c for c, _, _ in criteria)),
                persistent=tuple(dict.fromkeys(
                    c for c, _, cid in criteria if cid in self._repeated())),
                from_evidence=tuple(dict.fromkeys(e for _, e, _ in criteria)),
                reason=reason,
            ))

        return sorted(found, key=lambda g: (g.mastery is None, g.mastery or 0.0))

    # --- knowledge ----------------------------------------------------------------
    def build_query(self, gap: Gap) -> str:
        """What to EMBED. Capability statement plus the unmet criteria.

        The criteria are the specific part and they earn their place here: they name the
        exact material that would close the gap, and asymmetric embedding
        (RETRIEVAL_QUERY vs RETRIEVAL_DOCUMENT) is built for matching a need like this
        against the passage that meets it.
        """
        cap = self.graph.get(gap.capability_id)
        return " ".join([cap.statement, *gap.unmet[:4]])

    def build_question(self, gap: Gap) -> str:
        """What to ASK the generator. Deliberately NOT the same string as the query.

        Found by testing. Feeding the rubric criteria to the generator made it abstain on
        material that was plainly relevant: asked to satisfy "identifies the database as a
        likely constraint and gives a reason (connections, CPU, contention)", the
        grounding contract correctly observed that the corpus never discusses connections
        or contention — even though the retrieved excerpts on query plans and missing
        indexes are exactly what this student needs to read.

        A rubric criterion is ASSESSMENT language: it describes what a good answer does.
        A learner needs a QUESTION. Conflating them made the knowledge layer refuse to
        teach material it had. So the criteria steer retrieval, and the question is the
        capability itself, phrased for someone trying to learn it.

        Asked as "what do I need to UNDERSTAND to …", not "how do I …". The second form
        asks for a complete method, and the grounding contract refused HTTP, Scalability
        and Reliability because no excerpt spells out a debugging or bottleneck-finding
        procedure — while the excerpts on methods, status codes and headers were exactly
        the material to teach. Measured 2026-10-14 across the ten teachable capabilities:
        6/10 answered as "how do I", 7/10 as "what do I need to understand". The three
        that still abstain (databases, scalability, reliability) name real corpus gaps.
        """
        cap = self.graph.get(gap.capability_id)
        statement = cap.statement.strip().rstrip(".")
        if statement.lower().startswith("can "):
            statement = statement[4:]
        statement = statement[0].lower() + statement[1:]
        return f"What do I need to understand about {cap.name} to be able to {statement}?"

    def build_targeted_question(self, gap: Gap) -> str | None:
        """The general question, plus what this learner actually missed. None if nothing
        was missed.

        Not a replacement for `build_question`: measured 2026-10-14 over eight real gaps,
        the targeted form answered 4/8 and the general form 6/8. The targeted one
        abstains when a missed criterion is scenario-specific ("five retries can create
        five orders") because no excerpt mentions that scenario. Asked together and
        preferring the targeted answer, 7/8 were answered — see `knowledge_for`.
        """
        if not gap.unmet:
            return None
        missed = "; ".join(gap.unmet[:2])
        return (f"{self.build_question(gap)} In my last answer I missed these points: "
                f"{missed}. Explain the ideas behind them.")

    def knowledge_for(
        self, gap: Gap, k: int = TOP_K, explain: bool = True
    ) -> KnowledgeForGap:
        """Retrieve for one gap, and optionally ask for a grounded explanation.

        `explain=False` stops before the model call, so retrieval can be inspected
        without spending anything — the same split `retrieve.py` and `ask.py` make.
        """
        cap = self.graph.get(gap.capability_id)
        query = self.build_query(gap)
        question = self.build_question(gap)
        docs = tuple(f"{d}.md" for d in cap.knowledge_docs)

        # Prerequisites the student has not demonstrated. The CAPABILITY graph is the
        # source of truth for this, not the corpus's own `prerequisites` frontmatter —
        # see decisions.md Q3/D26. Teaching Scalability to someone who cannot demonstrate
        # Databases is teaching the wrong thing.
        unproven = tuple(
            c for c in self.graph.prerequisites_of(cap.id)
            if (self.profile.row_for(c.id).mastery or 0.0) < DEMONSTRATED_AT
        )

        out = KnowledgeForGap(
            gap=gap, capability=cap, query=query, question=question, docs=docs,
            prerequisites_first=unproven,
        )
        if not docs:
            # No corpus for this capability at all. Say so; do not search the whole
            # corpus and hope, which would retrieve adjacent material and invite the
            # model to improvise around it.
            return out

        from cognith_rag.embeddings import embed_query

        vector = embed_query(query)
        out.hits = self.store.search(vector, k=k, docs=list(docs))
        out.exercises = self.store.search(vector, k=3, docs=list(docs), kind="exercise")
        if explain:
            targeted = self.build_targeted_question(gap)
            if targeted is None:
                out.result = answer(question, out.hits)
                return out
            # Both at once, so the fallback costs no extra wait.
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(2) as pool:
                aimed = pool.submit(answer, targeted, out.hits)
                general = pool.submit(answer, question, out.hits)
                if aimed.result().answered:
                    out.result, out.question, out.targeted = aimed.result(), targeted, True
                else:
                    out.result = general.result()
        return out

    def coverage(self) -> dict[str, list[str]]:
        """Which capabilities the corpus can teach at all. Offline."""
        return {
            cap.id: [f"{d}.md" for d in cap.knowledge_docs]
            for cap in self.graph.capabilities.values()
        }
