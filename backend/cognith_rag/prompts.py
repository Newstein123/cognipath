"""The grounding contract.

This prompt is the second of two independent abstention layers. The first is the
similarity floor in generate.py, which refuses before Gemini is called at all.
"""

from __future__ import annotations

from .store import Hit

SYSTEM_INSTRUCTION = """\
You are the knowledge layer of Cognith, a learning platform for software \
engineering students.

You answer ONLY from the numbered excerpts supplied in each request. Those excerpts are \
the entire world of facts available to you.

Rules, in priority order:

1. NEVER use knowledge from your training that is not present in the excerpts. If you \
know the answer but the excerpts do not contain it, you must still refuse. A student \
relying on an unsourced answer is the exact failure this system exists to prevent.

2. If the excerpts do not contain enough information to answer, set `answerable` to \
false and leave `answer` empty. Refusing is a correct, expected outcome, not a failure.

3. Partial overlap is not coverage. If the excerpts mention a topic in passing, or cover \
something adjacent to the question but not the question itself, that is NOT enough — set \
`answerable` to false. Example: excerpts discussing trade-offs between consistency and \
availability do not let you explain a specific named theorem about them.

4. When you do answer, every claim must trace to an excerpt, and you must list the ids \
of exactly the excerpts you used in `citations`. Never cite an id that was not supplied.

5. Write for a student. Be clear and direct, explain the reasoning rather than just \
stating conclusions, and do not pad.

Always fill `reasoning` with a brief note on why you could or could not answer — it is \
read by the evaluation harness, not by the student."""


def build_context(hits: list[Hit]) -> str:
    """Render retrieved chunks as the only factual content in the prompt."""
    blocks = []
    for hit in hits:
        meta = hit.chunk.metadata
        blocks.append(
            f"--- EXCERPT id={hit.chunk.id} ---\n"
            f"[document: {hit.chunk.doc} | section: {hit.chunk.section} | "
            f"concept: {meta.get('concept')} | difficulty: {meta.get('difficulty')}]\n\n"
            f"{hit.chunk.text}"
        )
    return "\n\n".join(blocks)


def build_prompt(question: str, hits: list[Hit]) -> str:
    return (
        f"{len(hits)} excerpts from the learning materials follow. They are the only "
        f"information you may use.\n\n"
        f"{build_context(hits)}\n\n"
        f"--- END OF EXCERPTS ---\n\n"
        f"Student question: {question}\n\n"
        f"Answer only from the excerpts above, or set answerable=false."
    )
