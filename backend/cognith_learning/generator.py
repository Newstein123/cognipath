"""Generated follow-up challenges — step 6's "verify transfer" with a NEW situation.

Diagnostics stay authored (decisions.md D22): the first measurement must be the same
instrument for every learner. After a lesson, though, re-asking the question the learner
just missed tests memory, not understanding — and only 9 of 17 capabilities have a second
authored activity. So the follow-up is written by Gemini, under the same contract as the
knowledge layer:

    1. ONLY from retrieved course excerpts — the excerpts the lesson taught from.
    2. Every rubric criterion cites the excerpt it is grounded in. A criterion citing an
       id that was not sent, or no id, rejects the whole challenge.
    3. Every criterion is tagged with the target capability, so evidence lands where the
       lesson was.

Gemini still never decides mastery. It writes the question and criteria; judging is the
existing per-criterion evaluator, and the number comes from `score_criteria` and
`next_mastery` exactly as for authored activities.

Generated challenges are persisted (storage `save_activity`) because evidence must stay
traceable to the exact prompt and rubric the learner answered.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from cognith_capability.graph import CapabilityGraph
from cognith_capability.models import Capability, Level
from cognith_rag.config import GENERATION_MODEL
from cognith_rag.embeddings import get_client
from cognith_rag.prompts import build_context
from cognith_rag.store import Hit
from cognith_student.diagnostic import RubricCriterion

from .experience import ExperienceType, LearningExperience

MIN_CRITERIA, MAX_CRITERIA = 3, 5


class GenerationError(RuntimeError):
    """Gemini could not produce a challenge that passes validation."""


class _Criterion(BaseModel):
    criterion: str = Field(description="What a good answer does, e.g. 'Explains that …'.")
    excerpt_id: str = Field(description="Id of the excerpt this criterion is grounded in.")


class _Challenge(BaseModel):
    title: str = Field(description="Short, concrete title, max 8 words.")
    prompt: str = Field(description="The scenario and the question(s) put to the learner.")
    criteria: list[_Criterion]
    minutes: int = Field(description="Realistic minutes to answer, 4-12.")


SYSTEM_INSTRUCTION = f"""\
You write ONE practice challenge for Cognith, a learning platform for software \
engineering students. It checks whether a learner can APPLY what they were just taught \
in a situation they have not seen.

Rules, in priority order:

1. Use ONLY the numbered excerpts supplied. Every fact a good answer needs must be in \
them. Never require knowledge the excerpts do not contain.

2. Write a short, realistic scenario — a system, a symptom, a decision — and ask the \
learner to reason about it in prose. It must NOT be the same situation as the original \
question you are shown, and must not restate the excerpts as a quiz.

3. No code execution, no multiple choice, no trivia. Answerable in a few paragraphs.

4. Write {MIN_CRITERIA}-{MAX_CRITERIA} assessment criteria. Each describes what a good \
answer DOES ("Explains that …", "Identifies …"), can be judged independently, and cites \
in `excerpt_id` the one excerpt it is grounded in. Never cite an id that was not supplied.

5. Aim the criteria at the points the learner missed, when they are given — that is what \
this challenge exists to check."""


def _build_prompt(cap: Capability, hits: list[Hit], missed: list[str],
                  avoid_prompt: str | None) -> str:
    parts = [
        f"{len(hits)} excerpts from the course material follow. They are the only "
        f"information you may use.\n\n{build_context(hits)}\n\n--- END OF EXCERPTS ---\n",
        f"CAPABILITY TO CHECK: {cap.name} — {cap.statement}",
    ]
    if missed:
        parts.append("THE LEARNER PREVIOUSLY MISSED:\n" + "\n".join(f"- {m}" for m in missed))
    if avoid_prompt:
        parts.append(f"ORIGINAL QUESTION — do NOT reuse this situation:\n{avoid_prompt}")
    parts.append("Write the challenge.")
    return "\n\n".join(parts)


def validate(raw: _Challenge, sent_ids: set[str], avoid_prompt: str | None) -> list[str]:
    """Problems that reject a challenge. Empty means it may be shown to a learner."""
    problems = []
    if not MIN_CRITERIA <= len(raw.criteria) <= MAX_CRITERIA:
        problems.append(f"{len(raw.criteria)} criteria, need {MIN_CRITERIA}-{MAX_CRITERIA}")
    bad = [c.excerpt_id for c in raw.criteria if c.excerpt_id not in sent_ids]
    if bad:
        problems.append(f"criteria cite excerpts that were not supplied: {bad}")
    if not 60 <= len(raw.prompt.strip()) <= 2000:
        problems.append(f"prompt length {len(raw.prompt.strip())} outside 60-2000")
    if not raw.title.strip():
        problems.append("empty title")
    if avoid_prompt and raw.prompt.strip()[:80] == avoid_prompt.strip()[:80]:
        problems.append("prompt repeats the original question")
    return problems


def to_experience(raw: _Challenge, cap: Capability, hits: list[Hit]) -> LearningExperience:
    by_id = {h.chunk.id: h.chunk for h in hits}
    eid = f"gen-{cap.id}-{uuid.uuid4().hex[:8]}"
    cited = list(dict.fromkeys(by_id[c.excerpt_id].citation for c in raw.criteria))
    return LearningExperience(
        id=eid,
        type=ExperienceType.GENERATED,
        title=raw.title.strip(),
        capability_id=cap.id,
        prompt=raw.prompt.strip(),
        rubric=tuple(
            RubricCriterion(id=f"{eid}-c{i}", criterion=c.criterion.strip(),
                            capability_id=cap.id, weight=1.0)
            for i, c in enumerate(raw.criteria, 1)
        ),
        level=cap.level,
        minutes=max(4, min(12, raw.minutes)),
        source="generated from " + "; ".join(cited),
    )


def to_record(e: LearningExperience, model: str) -> dict[str, Any]:
    return {
        **e.to_record(),
        "prompt": e.prompt,
        "rubric": [{"id": c.id, "criterion": c.criterion, "capability": c.capability_id,
                    "weight": c.weight} for c in e.rubric],
        "model": model,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }


def from_record(d: dict[str, Any]) -> LearningExperience:
    return LearningExperience(
        id=d["id"], type=ExperienceType.GENERATED, title=d["title"],
        capability_id=d["capabilityId"], prompt=d["prompt"],
        rubric=tuple(RubricCriterion.from_dict(c) for c in d["rubric"]),
        level=Level(d["level"]), minutes=int(d["minutes"]), source=d.get("source", ""),
    )


class ChallengeGenerator:
    def __init__(self, graph: CapabilityGraph, model: str | None = None, attempts: int = 2):
        self.graph = graph
        self.model = model or GENERATION_MODEL
        self.attempts = attempts

    def generate(self, capability_id: str, hits: list[Hit], missed: list[str] = (),
                 avoid_prompt: str | None = None) -> LearningExperience:
        cap = self.graph.get(capability_id)
        if not hits:
            raise GenerationError(f"No course material for {cap.name} to write a challenge from.")
        sent = {h.chunk.id for h in hits}
        prompt = _build_prompt(cap, hits, list(missed)[:3], avoid_prompt)
        problems: list[str] = []
        for _ in range(self.attempts):
            feedback = ("" if not problems else
                        "\n\nYOUR PREVIOUS ATTEMPT WAS REJECTED: " + "; ".join(problems))
            interaction = get_client().interactions.create(
                model=self.model,
                system_instruction=SYSTEM_INSTRUCTION,
                input=prompt + feedback,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": _Challenge.model_json_schema(),
                },
                generation_config={"temperature": 0.4, "thinking_level": "low"},
            )
            raw = _Challenge.model_validate_json(interaction.output_text)
            problems = validate(raw, sent, avoid_prompt)
            if not problems:
                return to_experience(raw, cap, hits)
        raise GenerationError("Generated challenge failed validation: " + "; ".join(problems))
