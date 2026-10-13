"""Structured lessons — LEARN (sections with examples and diagrams), then a QUIZ.

Why: one grounded explanation is correct but reads as a wall of text. A lesson is now
2–5 short sections — explanation, worked example, and a diagram where one helps — followed
by a 4–6 question quiz with instant feedback. The written challenge comes after.

Diagrams are DATA, not pictures: the model chooses a type and fills its fields, and the
frontend draws it deterministically. Asking a model for SVG gives inconsistent images;
asking for "which elements are in A ∩ B" gives a Venn diagram that is right or checkably
wrong. Types: venn (2–3 sets), mapping (arrow diagram between two sets), table (truth
tables, membership tables), flow (steps of a method or proof).

Same contract as the knowledge layer and the challenge generator:

    1. ONLY from the supplied course excerpts.
    2. Every section cites the excerpt(s) it is built from; a section citing an id that
       was not sent rejects the lesson, which falls back to the plain explanation.
    3. `answerable: false` is a legitimate outcome — the caller falls back.
    4. A malformed diagram is dropped; it never rejects the lesson.

Quiz questions are practice, not evidence: they never touch mastery. The evidence comes
from the follow-up challenge, judged by the per-criterion evaluator as before.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from cognith_capability.models import Capability
from cognith_rag.config import GENERATION_MODEL
from cognith_rag.embeddings import get_client
from cognith_rag.prompts import build_context
from cognith_rag.store import Hit

MIN_SECTIONS, MAX_SECTIONS = 2, 5
MAX_OUTPUT_TOKENS = 9000


class Diagram(BaseModel):
    type: Literal["none", "venn", "mapping", "table", "flow"]
    caption: str = ""
    # venn — two sets. Flat fields: the model fills these reliably, nested ones it skipped.
    sets: list[str] = Field(default=[], description="venn: exactly 2 set names, e.g. [\"A\", \"B\"].")
    only_first: list[str] = Field(default=[], description="venn: elements in the first set only.")
    only_second: list[str] = Field(default=[], description="venn: elements in the second set only.")
    both: list[str] = Field(default=[], description="venn: elements in both sets.")
    outside: list[str] = Field(default=[], description="venn: elements in U but in neither set.")
    shade: Literal["none", "union", "intersection", "first_minus_second",
                   "second_minus_first", "complement_first"] = Field(
        default="none", description="venn: the region to shade — the operation being taught.")
    # mapping
    from_label: str = ""
    to_label: str = ""
    domain: list[str] = []
    codomain: list[str] = []
    arrows: list[list[str]] = Field(default=[], description="mapping: [from, to] pairs.")
    # table
    headers: list[str] = []
    rows: list[list[str]] = []
    # flow
    steps: list[str] = Field(default=[], description="flow: 2–6 short steps in order.")


class QuizQuestion(BaseModel):
    question: str
    options: list[str] = Field(description="Exactly 4 options.")
    answer_index: int = Field(description="0-based index of the correct option.")
    explanation: str = Field(description="Why the right option is right, 1–2 sentences.")


class Section(BaseModel):
    """One concept, taught as a short guided exchange (see the module docstring)."""
    title: str = Field(description="3–7 words.")
    probe: QuizQuestion = Field(description="Asked BEFORE teaching: does the learner already "
                                "know this? Plain, everyday wording, no jargon.")
    explanation: str = Field(description="Markdown, at most ~110 words. Bold key terms.")
    example: str = Field(description="A worked example with numbered steps, at most ~100 words.")
    diagram: Diagram
    check: QuizQuestion = Field(description="Asked AFTER teaching: apply the idea in a "
                                "situation different from the probe and the example.")
    excerpt_ids: list[str]


class StructuredLesson(BaseModel):
    answerable: bool = Field(description="False if the excerpts cannot support a lesson.")
    hook: str = Field(description="One sentence on why this matters to the learner.")
    sections: list[Section]


SYSTEM_INSTRUCTION = f"""\
You write a GUIDED LESSON from course excerpts: {MIN_SECTIONS}-{MAX_SECTIONS} concepts, \
simplest first. Each concept is taught as an exchange: a gentle `probe` question first \
(does the learner already know it?), then a short explanation, worked example and \
optional diagram, then a `check` that applies the idea in a new situation.

Rules, in priority order:

1. Use ONLY the numbered excerpts. Every fact, definition and example must come from \
them. If they cannot support a lesson, set answerable=false and return nothing else.
2. Each section: `explanation` is short, clear markdown (at most ~110 words; bold the \
key terms; a bullet list is fine). `example` is a concrete worked example with numbered \
steps (at most ~100 words) — reuse the excerpts' own examples where possible.
3. `diagram`: add one when a picture makes the idea clearer, otherwise type "none".
   - venn: exactly 2 `sets`; fill `only_first`, `only_second`, `both` and `outside` with \
the example's elements; set `shade` to the operation the section teaches (union, \
intersection, first_minus_second, second_minus_first, complement_first). Use it for set \
operations.
   - mapping: `domain`, `codomain` and `arrows` ([from, to] pairs using those exact \
labels). Use it for relations and functions (one-to-one, onto, inverse).
   - table: `headers` and `rows` of strings. Use it for truth tables (T/F) and \
comparisons.
   - flow: 2–6 short `steps` in order. Use it for methods: proof structure, induction, \
a procedure.
   Diagrams must be consistent with the example and the excerpts.
4. `excerpt_ids` lists the excerpts each section is built from. Never cite an id that \
was not supplied.
5. `probe` and `check`: exactly 4 options each, one correct; wrong options are \
realistic MISCONCEPTIONS a learner might hold; `explanation` says why the right one is \
right. The probe is friendly and answerable from everyday intuition where possible; the \
check must use a different situation from both the probe and the example.
6. If the learner's missed points are given, the lesson must address them.
7. Maths in Unicode (∈ ∉ ⊆ ⊂ ∪ ∩ ∅ ∀ ∃ ¬ ∧ ∨ → ↔ ≡ ≠ ≤ ≥ ² ⁿ), never LaTeX or backslashes.
8. Friendly and direct, like a good tutor. No filler."""


def clean_diagram(d: Diagram) -> Diagram | None:
    """The diagram if it can be drawn faithfully, else None."""
    if d.type == "venn":
        ok = len(d.sets) == 2 and (d.shade != "none" or d.only_first or d.only_second or d.both)
        return d if ok else None
    if d.type == "mapping":
        dom, cod = set(d.domain), set(d.codomain)
        ok = (d.domain and d.codomain and
              all(len(a) == 2 and a[0] in dom and a[1] in cod for a in d.arrows))
        return d if ok else None
    if d.type == "table":
        ok = d.headers and d.rows and all(len(r) == len(d.headers) for r in d.rows)
        return d if ok else None
    if d.type == "flow":
        return d if 2 <= len(d.steps) <= 8 else None
    return None


def validate(lesson: StructuredLesson, sent_ids: set[str]) -> list[str]:
    problems = []
    if not MIN_SECTIONS <= len(lesson.sections) <= MAX_SECTIONS:
        problems.append(f"{len(lesson.sections)} sections, need {MIN_SECTIONS}-{MAX_SECTIONS}")
    for i, s in enumerate(lesson.sections, 1):
        if not s.excerpt_ids or any(e not in sent_ids for e in s.excerpt_ids):
            problems.append(f"section {i} cites excerpts that were not supplied: {s.excerpt_ids}")
    for i, sec in enumerate(lesson.sections, 1):
        for name, q in (("probe", sec.probe), ("check", sec.check)):
            if len(q.options) != 4 or not 0 <= q.answer_index < 4:
                problems.append(f"section {i} {name} needs 4 options and a valid answer_index")
    return problems


def generate(cap: Capability, question: str, hits: list[Hit], missed: list[str] = (),
             model: str | None = None) -> StructuredLesson | None:
    """A validated lesson, or None — the caller then shows the plain explanation."""
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
    sent = {h.chunk.id for h in hits}
    problems: list[str] = []
    for _ in range(2):  # one retry, told what was wrong
        feedback = ("" if not problems else
                    "\n\nYOUR PREVIOUS ATTEMPT WAS REJECTED: " + "; ".join(problems))
        try:
            interaction = get_client().interactions.create(
                model=model or GENERATION_MODEL,
                system_instruction=SYSTEM_INSTRUCTION,
                input="\n\n".join(parts) + feedback,
                response_format={"type": "text", "mime_type": "application/json",
                                 "schema": StructuredLesson.model_json_schema()},
                # The cap stops a degenerate repetition loop (seen once: 234k characters
                # over five minutes) from holding the lesson hostage.
                generation_config={"temperature": 0.3, "thinking_level": "low",
                                   "max_output_tokens": MAX_OUTPUT_TOKENS},
            )
            lesson = StructuredLesson.model_validate_json(interaction.output_text)
        except Exception as exc:  # noqa: BLE001 — truncated or malformed JSON
            problems = [f"output was not valid JSON ({type(exc).__name__}); keep it concise"]
            continue
        if not lesson.answerable:
            return None
        problems = validate(lesson, sent)
        if not problems:
            for sec in lesson.sections:
                sec.diagram = clean_diagram(sec.diagram) or Diagram(type="none")
            return lesson
    return None


# --- explain it differently --------------------------------------------------------
class Reexplanation(BaseModel):
    answerable: bool
    explanation: str = Field(description="A NEW explanation, at most ~100 words.")
    check: QuizQuestion = Field(description="A new question on the same idea.")
    excerpt_ids: list[str]


REEXPLAIN_INSTRUCTION = """A learner just answered a question wrongly after being taught a concept. Explain the \
concept AGAIN, differently: simpler words, a different angle or analogy, and address the \
specific misconception their wrong answer reveals — say what that answer gets wrong and \
why. Then write one new 4-option question on the same idea, in a new situation.

Use ONLY the supplied excerpts for facts. Never cite an id that was not supplied. Maths in \
Unicode, never LaTeX. If the excerpts cannot support it, set answerable=false."""


def reexplain(cap: Capability, concept: str, explanation: str, question: str,
              chosen: str, correct: str, hits: list[Hit],
              model: str | None = None) -> Reexplanation | None:
    if not hits:
        return None
    prompt = (
        f"{len(hits)} excerpts follow. They are the only information you may use.\n\n"
        f"{build_context(hits)}\n\n--- END OF EXCERPTS ---\n\n"
        f"TOPIC: {cap.name}\nCONCEPT: {concept}\n\nHOW IT WAS EXPLAINED:\n{explanation}\n\n"
        f"QUESTION: {question}\nTHE LEARNER CHOSE: {chosen}\nTHE RIGHT ANSWER: {correct}"
    )
    interaction = get_client().interactions.create(
        model=model or GENERATION_MODEL,
        system_instruction=REEXPLAIN_INSTRUCTION,
        input=prompt,
        response_format={"type": "text", "mime_type": "application/json",
                         "schema": Reexplanation.model_json_schema()},
        generation_config={"temperature": 0.4, "thinking_level": "low",
                           "max_output_tokens": 3000},
    )
    r = Reexplanation.model_validate_json(interaction.output_text)
    sent = {h.chunk.id for h in hits}
    if (not r.answerable or len(r.check.options) != 4 or not 0 <= r.check.answer_index < 4
            or any(e not in sent for e in r.excerpt_ids)):
        return None
    return r
