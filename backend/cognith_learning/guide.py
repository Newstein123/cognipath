"""Guided help during a challenge — a tutor that helps the learner think, never answers.

Three levels, least help first, plus free questions:

    1 nudge    a guiding question that points at where to start
    2 concept  the idea or definition the question rests on, from the course material
    3 example  a worked example of the same idea on DIFFERENT values / a different scenario

The marking criteria are given to the model as things it must NOT state: it needs to know
what the answer looks like in order to avoid giving it away. Facts come only from the
course excerpts; the challenge text is context, not a source.

Help is recorded: an answer submitted after help counts as ASSISTED evidence (capped below
full marks in the API), because the plan's own standard is that a competency stays
incomplete until the learner can apply it independently.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from cognith_rag.config import GENERATION_MODEL
from cognith_rag.embeddings import get_client
from cognith_rag.generate import repair_latex_escapes
from cognith_rag.prompts import build_context
from cognith_rag.store import Hit

LEVELS = {
    1: "Give a NUDGE: one or two short guiding questions that point at where to start. "
       "No definitions, no steps.",
    2: "Explain the KEY IDEA the question rests on — the definition or rule from the "
       "excerpts — in a few sentences. Do not apply it to the question's values.",
    3: "Show a SIMILAR worked example from the excerpts, on DIFFERENT values or a "
       "different scenario from the question, step by step. Then say which step the "
       "learner should now try on their own question.",
}


class GuideReply(BaseModel):
    reply: str
    excerpt_ids: list[str]
    #: The model's own check; a reply it marks as revealing is replaced, not shown.
    reveals_answer: bool


SYSTEM_INSTRUCTION = """\
You are a patient tutor sitting next to a student who is working on a challenge question. \
Your job is to help them THINK, never to do the question for them.

Rules, in priority order:
1. NEVER give the final answer, never complete the student's steps, never state any of the \
HIDDEN MARKING POINTS, and never evaluate a full answer the student pastes in.
2. Facts, definitions and examples come ONLY from the numbered excerpts. The challenge \
text is context, not a source. Put the excerpt ids you used in `excerpt_ids` — never \
in the reply text.
3. Prefer asking a guiding question over telling. Keep it short (under ~120 words).
4. If the student asks for the answer, kindly decline and give the smallest useful hint.
5. Maths in Unicode (∈ ⊆ ∪ ∩ ∀ ∃ ¬ ∧ ∨ → ↔ ≤ ≥ ²), never LaTeX.
6. Set reveals_answer=true if, despite this, your reply would let the student copy the \
answer without thinking."""


def guide(challenge: str, hidden_points: list[str], hits: list[Hit], *,
          level: int | None = None, message: str = "",
          history: list[tuple[str, str]] = (), model: str | None = None,
          learner: str = "") -> GuideReply | None:
    if not hits:
        return None
    turns = "\n".join(f"{who.upper()}: {text}" for who, text in history[-6:])
    task = LEVELS.get(level or 0, "Answer the student's message below as a guide.")
    prompt = (
        f"{len(hits)} excerpts follow — the only facts you may use.\n\n{build_context(hits)}\n\n"
        f"--- END OF EXCERPTS ---\n\nTHE CHALLENGE THE STUDENT IS WORKING ON:\n{challenge}\n\n"
        "HIDDEN MARKING POINTS (never state these):\n"
        + "\n".join(f"- {p}" for p in hidden_points)
        + (f"\n\n{learner}" if learner else "")
        + (f"\n\nCONVERSATION SO FAR:\n{turns}" if turns else "")
        + f"\n\nYOUR TASK: {task}"
        + (f"\n\nSTUDENT: {message}" if message else "")
    )
    interaction = get_client().interactions.create(
        model=model or GENERATION_MODEL,
        system_instruction=SYSTEM_INSTRUCTION,
        input=prompt,
        response_format={"type": "text", "mime_type": "application/json",
                         "schema": GuideReply.model_json_schema()},
        generation_config={"temperature": 0.3, "thinking_level": "low",
                           "max_output_tokens": 2000},
    )
    r = GuideReply.model_validate_json(interaction.output_text)
    sent = {h.chunk.id for h in hits}
    r.excerpt_ids = [e for e in r.excerpt_ids if e in sent]
    # Ids belong in excerpt_ids; strip any the model still wrote into the prose.
    r.reply = re.sub(r"\s*[\(\[]?(?:[\w-]+\.md#[\w.-]+(?:,\s*)?)+[\)\]]?", "",
                     repair_latex_escapes(r.reply))
    if r.reveals_answer:
        r.reply = ("I'd be giving the answer away there. Look again at the key idea: which "
                   "definition from the lesson applies to the first part of the question?")
    return r

