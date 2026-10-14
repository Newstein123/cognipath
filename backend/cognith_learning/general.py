"""When the course material does not answer a tutor question: explain generally, or refuse.

The grounded tutor abstains when the curated corpus does not cover a question — right for
facts the course teaches, but a dead end for harmless questions like "why do we translate
English into logic?". So after an abstention there is a second, LABELLED step:

    in scope   → a general explanation, shown as "Not in your course material", no sources
    off topic  → a refusal that names what the course does cover

"In scope" is judged against the course's own capability map, so each course pack defines
its own boundary without code: material science is off-topic for discrete mathematics; a
database index is in scope for the backend course.

This is ONLY for the free tutor. Assessment, rubrics, lessons and generated challenges stay
grounded — nothing a learner is graded on comes from outside their material. The label is
the point: the original RAG spike's objection was to answering from pretraining SILENTLY.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from cognith_capability.graph import CapabilityGraph
from cognith_rag.config import GENERATION_MODEL
from cognith_rag.embeddings import get_client
from cognith_rag.generate import repair_latex_escapes


class GeneralAnswer(BaseModel):
    in_scope: bool = Field(description="True if the question is about this course's subject.")
    answer: str = Field(description="If in scope: a clear explanation, at most ~150 words. "
                                    "Otherwise empty.")


SYSTEM_INSTRUCTION = """\
You support students in ONE course. Decide whether the student's question belongs to the \
course's subject (its topics below, the ideas behind them, why they matter, how they \
connect). Questions about other subjects are out of scope, even if they sound academic.

If in scope, answer clearly and correctly for a student, at most ~150 words, with a short \
example if it helps. Use standard terminology; say plainly if conventions vary between \
courses. Maths in Unicode, never LaTeX. If out of scope, set in_scope=false and leave the \
answer empty."""


def course_scope(graph: CapabilityGraph, course_name: str) -> str:
    topics = "\n".join(f"- {c.name}: {c.statement}" for c in graph.capabilities.values())
    return f"COURSE: {course_name}\nTOPICS:\n{topics}"


def general_answer(question: str, scope: str, learner: str = "",
                   model: str | None = None) -> GeneralAnswer:
    interaction = get_client().interactions.create(
        model=model or GENERATION_MODEL,
        system_instruction=SYSTEM_INSTRUCTION,
        input=f"{scope}\n\n" + (f"{learner}\n\n" if learner else "") + f"STUDENT QUESTION: {question}",
        response_format={"type": "text", "mime_type": "application/json",
                         "schema": GeneralAnswer.model_json_schema()},
        generation_config={"temperature": 0.2, "thinking_level": "low",
                           "max_output_tokens": 2000},
    )
    r = GeneralAnswer.model_validate_json(interaction.output_text)
    r.answer = repair_latex_escapes(r.answer)
    return r
