"""Micro-lessons — a lesson as 3–5 short cards, each with a worked example and a quick
check, instead of one long explanation.

Why: a single grounded explanation is correct but reads as a wall of text, and reading
produces no retrieval practice. Each card is one idea (≈60 words), one worked example,
then a multiple-choice check answered on the spot with an explanation — the learner
recalls before moving on.

Same contract as the knowledge layer and the challenge generator:

    1. ONLY from the supplied course excerpts.
    2. Every card cites the excerpt(s) it is built from; a card citing an id that was not
       sent rejects the lesson, which then falls back to the plain explanation.
    3. `answerable: false` is a legitimate outcome — the caller falls back.

Quick checks are practice, not evidence: they never touch mastery. The evidence comes
from the follow-up challenge, judged by the per-criterion evaluator as before.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from cognith_capability.models import Capability
from cognith_rag.config import GENERATION_MODEL
from cognith_rag.embeddings import get_client
from cognith_rag.prompts import build_context
from cognith_rag.store import Hit

MIN_CARDS, MAX_CARDS = 3, 5


class Check(BaseModel):
    question: str
    options: list[str] = Field(description="Exactly 4 options.")
    answer_index: int = Field(description="0-based index of the correct option.")
    explanation: str = Field(description="Why the right option is right, 1–2 sentences.")


class Card(BaseModel):
    title: str = Field(description="3–6 words.")
    idea: str = Field(description="The one idea, at most ~60 words, plain and direct.")
    example: str = Field(description="A short worked example with its steps, at most ~90 words.")
    check: Check
    excerpt_ids: list[str] = Field(description="Ids of the excerpts this card is built from.")


class MicroLesson(BaseModel):
    answerable: bool = Field(description="False if the excerpts cannot support a lesson.")
    hook: str = Field(description="One sentence on why this matters to the learner.")
    cards: list[Card]


SYSTEM_INSTRUCTION = f"""\
You turn course excerpts into a MICRO-LESSON for a student: {MIN_CARDS}-{MAX_CARDS} short \
cards, taught in order from simplest to hardest.

Rules, in priority order:

1. Use ONLY the numbered excerpts. Every fact, definition and example must come from \
them. If they cannot support a lesson, set answerable=false and return no cards.
2. One idea per card. `idea` at most ~60 words. `example` is a concrete worked example \
with its steps, at most ~90 words — reuse the excerpts' own examples where possible.
3. Each card ends with a multiple-choice `check` testing THAT card's idea: exactly 4 \
options, one correct, wrong options are realistic mistakes. `explanation` says why.
4. `excerpt_ids` lists the excerpts each card is built from. Never cite an id that was \
not supplied.
5. If the learner's missed points are given, the cards must address them.
6. Write maths with Unicode symbols (∈ ∉ ⊆ ⊂ ∪ ∩ ∅ ∀ ∃ ¬ ∧ ∨ → ↔ ≡ ≠ ≤ ≥ ² ⁿ), \
never LaTeX or backslashes.
7. Friendly and direct, like a good tutor. No filler."""


def validate(lesson: MicroLesson, sent_ids: set[str]) -> list[str]:
    problems = []
    if not MIN_CARDS <= len(lesson.cards) <= MAX_CARDS:
        problems.append(f"{len(lesson.cards)} cards, need {MIN_CARDS}-{MAX_CARDS}")
    for i, c in enumerate(lesson.cards, 1):
        if not c.excerpt_ids or any(e not in sent_ids for e in c.excerpt_ids):
            problems.append(f"card {i} cites excerpts that were not supplied: {c.excerpt_ids}")
        if len(c.check.options) != 4 or not 0 <= c.check.answer_index < len(c.check.options):
            problems.append(f"card {i} check needs 4 options and a valid answer_index")
    return problems


def generate(cap: Capability, question: str, hits: list[Hit], missed: list[str] = (),
             model: str | None = None) -> MicroLesson | None:
    """A validated micro-lesson, or None — the caller then shows the plain explanation."""
    if not hits:
        return None
    parts = [
        f"{len(hits)} excerpts follow. They are the only information you may use.\n\n"
        f"{build_context(hits)}\n\n--- END OF EXCERPTS ---",
        f"TOPIC: {cap.name} — {cap.statement}",
        f"WHAT THE LEARNER WANTS TO KNOW: {question}",
    ]
    if missed:
        parts.append("THE LEARNER PREVIOUSLY MISSED:\n" + "\n".join(f"- {m}" for m in missed[:3]))
    interaction = get_client().interactions.create(
        model=model or GENERATION_MODEL,
        system_instruction=SYSTEM_INSTRUCTION,
        input="\n\n".join(parts),
        response_format={"type": "text", "mime_type": "application/json",
                         "schema": MicroLesson.model_json_schema()},
        generation_config={"temperature": 0.3, "thinking_level": "low"},
    )
    lesson = MicroLesson.model_validate_json(interaction.output_text)
    if not lesson.answerable or validate(lesson, {h.chunk.id for h in hits}):
        return None
    return lesson
