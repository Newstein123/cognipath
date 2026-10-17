"""Which skills are mastered — one rule for the profile, its counts and the plan.

decisions.md D61, D62 and D64: a skill is mastered when its evidence reaches
DEMONSTRATED_AT *and* either the skill has no unit material, its whole unit has been
taught, or the latest challenge on that skill itself was passed. Evidence alone can reach 0.70 without that —
e.g. learners assessed before D62, or one strong answer on part of a unit — and is then
"developing".

Before this module the API applied the rule to each skill's badge, while the summary
counts and the plan read the bare number: one learner was "8 mastered" in the header,
"2 mastered" in the skill list, and told "You have mastered Scalability…" beside a
Developing badge.
"""

from __future__ import annotations

from typing import Any

from cognith_student.models import DEMONSTRATED_AT
from cognith_student.profile import CapabilityProfile

from .experience import ExperienceLibrary, ExperienceType


def passed_own_challenge(log: list[dict[str, Any]], capability_id: str, library: ExperienceLibrary) -> bool:
    """Was the latest exercise or generated challenge *for this skill* passed (70%+ of its
    points fully met)? A criterion inside another skill's exercise, a capstone, a diagnosis
    or lesson checks is evidence for the skill, never its challenge (D64)."""
    for entry in reversed(log):
        ev = entry["evidence"]
        exp = library.experiences.get(ev["experienceId"])
        if (exp is None or ev["experienceId"].startswith("checks-") or exp.capability_id != capability_id
                or exp.type not in (ExperienceType.EXERCISE, ExperienceType.GENERATED)):
            continue
        outcome = next((o for o in entry["assessment"].get("outcomes", []) if o["capabilityId"] == capability_id), None)
        if outcome is None:
            continue
        points = len(outcome.get("met", [])) + len(outcome.get("partial", [])) + len(outcome.get("unmet", []))
        return bool(points) and len(outcome.get("met", [])) / points >= DEMONSTRATED_AT
    return False


def mastered_skills(profile: CapabilityProfile, library: ExperienceLibrary) -> set[str]:
    """Capability ids this learner has mastered under D62/D64."""
    from cognith_student.storage import get_storage

    from .units import progress

    log = get_storage().load_evidence(profile.student.id)
    won: set[str] = set()
    for row in profile.all_rows():
        if not row.is_demonstrated:
            continue
        if profile.graph.get(row.capability_id).knowledge_docs:
            try:
                unit = progress(profile.student.id, row.capability_id)
            except Exception:  # noqa: BLE001 — no index / no material: no unit to finish
                unit = None
            if unit and not unit.complete and not passed_own_challenge(log, row.capability_id, library):
                continue
        won.add(row.capability_id)
    return won
