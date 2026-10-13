"""Grounded answer generation: similarity floor, grounding contract, citation check."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from .config import ABSTAIN_MESSAGE, GENERATION_MODEL, MIN_SCORE
from .embeddings import get_client
from .prompts import SYSTEM_INSTRUCTION, build_prompt
from .store import Hit


class GroundedAnswer(BaseModel):
    """Structured output schema returned by Gemini."""

    answerable: bool = Field(
        description="True only if the excerpts contain enough to answer the question."
    )
    answer: str = Field(description="The answer, or an empty string if not answerable.")
    citations: list[str] = Field(
        description="Ids of exactly the excerpts used. Empty if not answerable."
    )
    reasoning: str = Field(description="Brief note on why you could or could not answer.")


@dataclass
class Result:
    """What the harness prints and what eval.py asserts against."""

    question: str
    answered: bool
    answer: str
    hits: list[Hit]
    citations: list[str] = field(default_factory=list)
    reasoning: str = ""
    # Which layer produced the outcome: score_floor | model | citation_check | api_error
    gate: str = ""
    prompt: str | None = None
    raw: dict[str, Any] | None = None

    @property
    def cited_hits(self) -> list[Hit]:
        return [h for h in self.hits if h.chunk.id in self.citations]


_CONTROL = {"\x0c": "\\f", "\x08": "\\b", "\t": "\\t", "\r": "\\r"}
_NEWLINE_COMMAND = re.compile(r"\n(?=(?:eq|eg|otin|ot|abla|subseteq|exists|e)\b)")


def repair_latex_escapes(text: str) -> str:
    """Undo JSON escapes that ate LaTeX backslashes.

    The model writes `\\forall` inside a JSON string; if it emits `\forall`, JSON decodes
    `\f` as a form feed and the student sees "orall". Same for \\to/\\times (tab),
    \\beta (backspace), \\rightarrow (carriage return) and \\neq/\\neg/\\notin
    (newline). Those control characters never belong in an answer, so put the backslash
    back.
    """
    for ch, fixed in _CONTROL.items():
        text = text.replace(ch, fixed)
    return _NEWLINE_COMMAND.sub(r"\\n", text)


def _abstain(question, hits, gate, reasoning, prompt=None) -> Result:
    return Result(
        question=question,
        answered=False,
        answer=ABSTAIN_MESSAGE,
        hits=hits,
        reasoning=reasoning,
        gate=gate,
        prompt=prompt,
    )


def answer(question: str, hits: list[Hit], min_score: float = MIN_SCORE) -> Result:
    """Two independent abstention layers, then a citation validity check."""

    # --- Layer 1: similarity floor (pre-LLM) --------------------------------
    # Nothing in the corpus is close enough. Refuse deterministically and save a call.
    if not hits or hits[0].score < min_score:
        best = f"{hits[0].score:.3f}" if hits else "no hits"
        return _abstain(
            question,
            hits,
            "score_floor",
            f"Best chunk scored {best}, below the {min_score:.2f} floor.",
        )

    # --- Layer 2: grounding contract (in-LLM) -------------------------------
    prompt = build_prompt(question, hits)
    try:
        interaction = get_client().interactions.create(
            model=GENERATION_MODEL,
            system_instruction=SYSTEM_INSTRUCTION,
            input=prompt,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": GroundedAnswer.model_json_schema(),
            },
            generation_config={"temperature": 0.0},
        )
        parsed = GroundedAnswer.model_validate_json(interaction.output_text)
    except Exception as exc:  # noqa: BLE001 - deliberate catch-all
        # Fallback behaviour (spec Appendix A): degrade to retrieval-only rather
        # than crash, so a failed AI call never breaks the learning experience.
        result = _abstain(
            question,
            hits,
            "api_error",
            f"{type(exc).__name__}: {exc}",
            prompt=prompt,
        )
        result.answer = (
            "The AI service is unavailable, so this answer is not generated. "
            "Here are the most relevant excerpts from the learning materials."
        )
        return result

    if not parsed.answerable:
        r = _abstain(question, hits, "model", parsed.reasoning, prompt=prompt)
        r.raw = parsed.model_dump()
        return r

    # --- Citation validity check --------------------------------------------
    # A cited id that was never sent means the model drifted off-corpus. The
    # similarity floor cannot catch this; only checking the ids can.
    sent_ids = {h.chunk.id for h in hits}
    invalid = [c for c in parsed.citations if c not in sent_ids]
    if invalid or not parsed.citations:
        reason = (
            f"Fabricated citation ids: {invalid}"
            if invalid
            else "Claimed answerable but cited no excerpt."
        )
        r = _abstain(question, hits, "citation_check", reason, prompt=prompt)
        r.raw = parsed.model_dump()
        return r

    return Result(
        question=question,
        answered=True,
        answer=repair_latex_escapes(parsed.answer),
        hits=hits,
        citations=parsed.citations,
        reasoning=parsed.reasoning,
        gate="model",
        prompt=prompt,
        raw=parsed.model_dump(),
    )
