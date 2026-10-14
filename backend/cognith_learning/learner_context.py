"""The learner state every teaching call receives — so Gemini pitches HOW it teaches.

The adaptive engine decides WHAT to teach. This module turns the learner model into a short
context block that tells the learning engine who it is teaching: their level on this
capability (and whether that level is evidence or only a self-rating), and the
misconceptions their answers have shown, repeated ones first.

The level band maps to explicit teaching guidance rather than leaving "adapt to the
learner" to the model: the same lesson for a 0% beginner and a 60% learner should differ in
depth, pace and starting point, and that difference is decided here, testably.
"""

from __future__ import annotations

from dataclasses import dataclass

from cognith_student.models import DEMONSTRATED_AT
from cognith_student.profile import CapabilityProfile

#: (name shown to the learner, guidance given to the model)
PITCH = {
    "new": ("New to this",
            "The learner is NEW to this topic. Start from an everyday analogy or concrete "
            "picture, define every term the first time it appears, take the smallest steps, "
            "and avoid notation until the idea is clear."),
    "struggling": ("Building the basics",
                   "The learner has tried this and is STRUGGLING. Lead with a concrete worked "
                   "example before stating the rule, one idea at a time, and name the "
                   "misconceptions below directly."),
    "partial": ("Filling the gaps",
                "The learner has PARTLY shown this topic. Be concise, do not re-teach basics "
                "they have shown, and go straight at the gaps and misconceptions below."),
    "strong": ("Sharpening",
               "The learner is STRONG on this topic. Be brisk, assume the basics, and focus on "
               "edge cases, precise wording and the reasoning an examiner rewards."),
}


@dataclass(frozen=True)
class LearnerContext:
    band: str
    pitch: str              # short label for the UI
    prompt: str             # block for the model

    def __str__(self) -> str:
        return self.prompt


def learner_context(profile: CapabilityProfile, capability_id: str) -> LearnerContext:
    from cognith_learning.knowledge import GapResolver
    from cognith_student.history import load_history

    row = profile.row_for(capability_id)
    if row.mastery is None:
        band = "new" if (row.confidence or 0.0) <= 0.4 else "partial"
        level = ("no evidence yet" + (f"; self-rated {row.confidence:.0%} (a claim, not evidence)"
                                      if row.confidence is not None else ""))
    else:
        band = ("strong" if row.mastery >= DEMONSTRATED_AT
                else "partial" if row.mastery >= 0.4 else "struggling")
        level = f"{row.mastery:.0%} from {row.evidence_count} piece(s) of evidence"

    repeated = [t.criterion for t in load_history(profile.student.id).persistent_misses()
                if t.capability_id == capability_id]
    gap = next((g for g in GapResolver(profile.graph, profile).gaps()
                if g.capability_id == capability_id), None)
    missed = [m for m in (gap.unmet if gap else ()) if m not in repeated]

    name, guidance = PITCH[band]
    lines = [f"LEARNER STATE — {profile.capability(capability_id).name}: {level}.",
             f"HOW TO TEACH: {guidance}"]
    if repeated:
        lines.append("MISSED MORE THAN ONCE (a blind spot — address it explicitly):\n"
                     + "\n".join(f"- {m}" for m in repeated[:3]))
    if missed:
        lines.append("ALSO MISSED BEFORE:\n" + "\n".join(f"- {m}" for m in missed[:3]))
    return LearnerContext(band=band, pitch=name, prompt="\n".join(lines))
