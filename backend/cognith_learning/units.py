"""Unit plans — every idea in a capability's material, taught and tracked.

A lesson used to be written from the 5 sections retrieval ranked highest, so a 20-section
unit was taught from a quarter of its material and nothing recorded what was skipped. A
skill could look "developing" — even "mastered" — after a lesson that never reached half
the course. Now the material itself is the syllabus:

    concepts   every core section of the unit's documents, in the author's order
    examples   each "Worked example / Example / Proof / Practice" section, attached to
               the concept it is most similar to (embedding cosine; falls back to the
               preceding concept)
    context    "Why this matters" (part 1) and "Common mistakes" (last part) ride along
    skipped    "Summary" (restates) and "Exercise:" sections (they are activities)
    parts      concepts in order, PART_SIZE at a time — one sitting each

Coverage is per learner, from guided-lesson outcomes (`/lessons/result` stores the
concept ids it reports on). A concept is covered once it has an outcome: known (probe
passed), learned, learned after a second explanation, or still unclear. So "covered" is
known by construction rather than inferred from what a lesson happened to retrieve.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np

PART_SIZE = 3
MAX_EXAMPLES = 2

_EXAMPLE = re.compile(r"^(worked example|example|proof|practice)\b", re.I)
_SKIP = re.compile(r"^(summary|exercise\s*:)", re.I)
_INTRO = re.compile(r"^why (this|it) matters", re.I)
_MISTAKES = re.compile(r"^common mistakes", re.I)


@dataclass
class Concept:
    id: str                      # chunk id of its core section ("auth.md#writing-the-check")
    title: str                   # the section heading
    chunk_ids: list[str]         # core section chunks (long sections split into several)
    example_ids: list[str] = field(default_factory=list)


@dataclass
class UnitPlan:
    capability_id: str
    concepts: list[Concept]
    intro_ids: list[str]
    mistake_ids: list[str]

    @property
    def parts(self) -> list[list[Concept]]:
        cs = self.concepts
        if len(cs) <= PART_SIZE + 1:
            return [cs] if cs else []
        return [cs[i:i + PART_SIZE] for i in range(0, len(cs), PART_SIZE)]

    def part_of(self, concept_id: str) -> int:
        for n, part in enumerate(self.parts):
            if any(c.id == concept_id for c in part):
                return n
        return -1

    def chunk_ids_for(self, part: list[Concept], last: bool, first: bool) -> list[str]:
        ids = list(self.intro_ids) if first else []
        for c in part:
            ids += c.chunk_ids + c.example_ids
        if last:
            ids += self.mistake_ids
        return list(dict.fromkeys(ids))


def _sections(store, docs: list[str]) -> list[tuple[str, str, list]]:
    """(doc, heading, [chunks]) in document order, grouping split sections."""
    out: list[tuple[str, str, list]] = []
    for doc in docs:
        for ch in store.chunks:
            if ch.doc != doc:
                continue
            if out and out[-1][0] == doc and out[-1][1] == ch.section:
                out[-1][2].append(ch)
            else:
                out.append((doc, ch.section, [ch]))
    return out


def build_plan(capability, store, mapping: dict[str, str] | None = None) -> UnitPlan:
    """`mapping`: example chunk id -> concept id, from the pack's units.yaml (written by
    build_pack.py and reviewable by a teacher). Without one, embeddings decide."""
    docs = [f"{d}.md" for d in capability.knowledge_docs]
    concepts: list[Concept] = []
    examples: list[tuple[int, list]] = []   # (index of preceding concept, chunks)
    intro, mistakes = [], []
    for doc, heading, chunks in _sections(store, docs):
        if chunks[0].metadata.get("kind") == "exercise" or _SKIP.match(heading):
            continue
        ids = [c.id for c in chunks]
        if _INTRO.match(heading):
            intro += ids
        elif _MISTAKES.match(heading):
            mistakes += ids
        elif _EXAMPLE.match(heading):
            examples.append((len(concepts) - 1, chunks))
        else:
            concepts.append(Concept(id=ids[0], title=heading, chunk_ids=ids))
    if not concepts:
        return UnitPlan(capability.id, [], intro, mistakes)

    # Attach each worked example to the concept it illustrates: best cosine match, at
    # most MAX_EXAMPLES per concept (otherwise one central concept collects them all),
    # strongest matches assigned first. Without embeddings: the preceding concept.
    by_id = {c.id: c for c in concepts}
    if mapping:
        for preceding, chunks in examples:
            target = by_id.get(mapping.get(chunks[0].id, ""))
            (target or concepts[max(preceding, 0)]).example_ids += [c.id for c in chunks]
        return UnitPlan(capability.id, concepts, intro, mistakes)
    vec = {c.id: np.asarray(c.embedding, dtype=np.float32)
           for c in store.chunks if c.embedding is not None}
    core = [vec.get(c.id) for c in concepts]
    if all(v is not None for v in core) and all(vec.get(ch[0].id) is not None for _, ch in examples):
        sims = [(float(core[i] @ vec[ch[0].id]), e, i)
                for e, (_, ch) in enumerate(examples) for i in range(len(concepts))]
        taken: dict[int, int] = {}
        placed: set[int] = set()
        for _, e, i in sorted(sims, reverse=True):
            if e in placed or taken.get(i, 0) >= MAX_EXAMPLES:
                continue
            concepts[i].example_ids += [c.id for c in examples[e][1]]
            taken[i] = taken.get(i, 0) + 1
            placed.add(e)
    else:
        for preceding, chunks in examples:
            concepts[max(preceding, 0)].example_ids += [c.id for c in chunks]
    return UnitPlan(capability.id, concepts, intro, mistakes)


@lru_cache
def _plan_cached(course: str, capability_id: str) -> UnitPlan | None:
    from cognith_capability.graph import CapabilityGraph

    graph = CapabilityGraph.load()
    cap = graph.get(capability_id)
    if not cap.knowledge_docs:
        return None
    return build_plan(cap, _store(course), _mappings(course).get(capability_id))


@lru_cache
def _mappings(course: str) -> dict[str, dict[str, str]]:
    import yaml

    from cognith_course import path

    f = path("units.yaml")
    return (yaml.safe_load(f.read_text(encoding="utf-8")) or {}) if f.exists() else {}


def map_examples(capability, store) -> dict[str, str]:
    """Ask Gemini, once at build time, which concept each worked example illustrates."""
    from pydantic import BaseModel

    from cognith_rag.config import GENERATION_MODEL
    from cognith_rag.embeddings import get_client

    plan = build_plan(capability, store, mapping={"__none__": ""})  # concepts only, in order
    secs = _sections(store, [f"{d}.md" for d in capability.knowledge_docs])
    exs = [(chunks[0].id, heading, chunks[0].text[:500]) for _, heading, chunks in secs
           if _EXAMPLE.match(heading) and chunks[0].metadata.get("kind") != "exercise"]
    if not exs or not plan.concepts:
        return {}

    class Link(BaseModel):
        example_id: str
        concept_id: str

    class Links(BaseModel):
        links: list[Link]

    text = "CONCEPTS:\n" + "\n".join(
        f"- {c.id}: {c.title} — {next(ch.text for ch in store.chunks if ch.id == c.id)[:300]}"
        for c in plan.concepts) + "\n\nWORKED EXAMPLES:\n" + "\n".join(
        f"- {eid}: {h} — {t}" for eid, h, t in exs)
    interaction = get_client().interactions.create(
        model=GENERATION_MODEL,
        system_instruction="For each worked example, choose the ONE concept it best illustrates "
                           "— the idea a student must understand to follow it. Use the ids given. "
                           "Spread examples sensibly; at most 2 per concept unless unavoidable.",
        input=text,
        response_format={"type": "text", "mime_type": "application/json",
                         "schema": Links.model_json_schema()},
        generation_config={"temperature": 0.0, "thinking_level": "low"},
    )
    links = Links.model_validate_json(interaction.output_text).links
    valid = {c.id for c in plan.concepts}
    return {l.example_id: l.concept_id for l in links if l.concept_id in valid}


@lru_cache
def _store(course: str):
    from cognith_rag.store import Store

    return Store.load()


def plan_for(capability_id: str) -> UnitPlan | None:
    """The unit plan for a capability in the active course (cached per course)."""
    from cognith_course import current

    return _plan_cached(current(), capability_id)


def coverage(student_id: str, plan: UnitPlan) -> dict[str, str]:
    """concept id -> latest outcome (met | partial | unmet) for this learner."""
    from cognith_student.storage import get_storage

    store = get_storage()
    concept_ids_by_activity = {r["id"]: r.get("concept_ids") for r in store.list_activities()
                               if r.get("concept_ids")}
    wanted = {c.id for c in plan.concepts}
    out: dict[str, str] = {}
    for entry in store.load_evidence(student_id):
        ev = entry["evidence"]
        ids = concept_ids_by_activity.get(ev["experienceId"])
        if not ids:
            continue
        for cid, result in zip(ids, ev.get("results", [])):
            if cid in wanted:
                out[cid] = result["verdict"]
    return out


@dataclass
class UnitProgress:
    plan: UnitPlan
    covered: dict[str, str]

    @property
    def total(self) -> int:
        return len(self.plan.concepts)

    @property
    def done(self) -> int:
        return sum(1 for c in self.plan.concepts if c.id in self.covered)

    @property
    def complete(self) -> bool:
        return self.total > 0 and self.done == self.total

    def next_part(self) -> int | None:
        for n, part in enumerate(self.plan.parts):
            if any(c.id not in self.covered for c in part):
                return n
        return None


def progress(student_id: str, capability_id: str) -> UnitProgress | None:
    plan = plan_for(capability_id)
    if plan is None or not plan.concepts:
        return None
    return UnitProgress(plan, coverage(student_id, plan))
