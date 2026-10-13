#!/usr/bin/env python3
"""Phase 2 — inspect a student's capability state. No LLM, no network.

  python students.py                       the demo fixture profile
  python students.py --unverified          claimed but never demonstrated
  python students.py --calibration         where the claim exceeds the evidence
  python students.py --blocked             capabilities with unmet prerequisites
  python students.py --summary             counts by status
  python students.py --records             the §19 collection shape as JSON
  python students.py --save                write data/students/<id>.json
  python students.py --load student-001    read a saved profile back

The fixture is a FIXTURE. Claude.md §21 Phase 3 builds real onboarding; until then this
gives Phase 2 something concrete to inspect. Its self-reported numbers are §9's example
capability map verbatim.
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  — must precede project imports

import argparse
import json
import sys
import textwrap
from datetime import timedelta

from cognith_capability.graph import CapabilityGraph
from cognith_student.models import (
    DEMONSTRATED_AT,
    MasteryStatus,
    Student,
    StudentCapability,
    utcnow,
)
from cognith_student import capability_map as cmap
from cognith_student.profile import CapabilityProfile

RULE = "─" * 78

#: Self-reported confidence, taken from Claude.md §9's example capability map.
DEMO_CONFIDENCE = {
    "api-design": 0.75,
    "databases": 0.80,
    "authentication": 0.70,
    "debugging": 0.65,
    "system-design": 0.50,
    "scalability": 0.35,
    "trade-off-analysis": 0.40,
    "http": 0.85,
}

#: Two illustrative assessment outcomes, so both sides of the §6.2 distinction are
#: visible in one profile. Phase 6 produces these for real; these are hand-set.
DEMO_ASSESSED = {
    "http": (0.78, 2),
    "system-design": (0.22, 1),
}


def build_demo(graph: CapabilityGraph) -> CapabilityProfile:
    student = Student(
        id="student-001",
        name="Demo Student",
        goal="Backend Software Engineer",
    )
    profile = CapabilityProfile(student, [], graph)
    for cid, confidence in DEMO_CONFIDENCE.items():
        profile.set_confidence(cid, confidence)
    at = utcnow() - timedelta(days=3)
    for cid, (mastery, evidence) in DEMO_ASSESSED.items():
        profile.record_assessment(cid, mastery, evidence_added=evidence, at=at)
    return profile


def pct(value: float | None) -> str:
    return "  —" if value is None else f"{round(value * 100):3d}%"


def show_table(p: CapabilityProfile) -> None:
    """The numeric view. Phase 4's map is the default; this stays for evidence counts."""
    s = p.student
    print(f"\n{RULE}\n{s.name}   [{s.id}]")
    if s.goal:
        print(f"Goal: {s.goal}")
    print(RULE)
    print(textwrap.fill(
        "confidence is SELF-REPORTED — what the student says. mastery is DEMONSTRATED — "
        "what evidence supports. A dash under mastery means never assessed, which is not "
        "the same as zero (Claude.md §6.2).", 78))

    print(f"\n{'capability':26} {'self-rep':>9} {'demonstr':>9} {'status':>14} {'ev':>3}  gap")
    print(f"{'-' * 26} {'-' * 9} {'-' * 9} {'-' * 14} {'-' * 3}  {'-' * 6}")

    for area_id, area_name in p.graph.areas.items():
        print(f"\n{area_name}")
        for cap in p.graph.by_area(area_id):
            r = p.row_for(cap.id)
            gap = r.calibration_gap
            gap_s = "" if gap is None else f"{gap:+.2f}"
            flag = " <" if gap is not None and gap >= 0.20 else ""
            print(f"  {cap.name:24} {pct(r.confidence):>9} {pct(r.mastery):>9} "
                  f"{r.status.value:>14} {r.evidence_count:>3}  {gap_s}{flag}")

    print(f"\n{RULE}")
    summary = p.summary()
    print("  " + "   ".join(f"{k} {v}" for k, v in summary["by_status"].items()))
    print(f"  mean self-reported {pct(summary['mean_confidence'])}"
          f"   mean demonstrated {pct(summary['mean_mastery'])}"
          f"   evidence {summary['evidence_total']}")
    print(f"\n  '<' marks a self-report at least 0.20 above the evidence.")
    print(f"  'demonstrated' means mastery >= {DEMONSTRATED_AT:.2f}.\n")


def show_unverified(p: CapabilityProfile) -> None:
    rows = p.unverified()
    print(f"\n{RULE}\nUNVERIFIED — claimed, never assessed  ({len(rows)})\n{RULE}\n")
    print(textwrap.fill(
        "These are claims, not findings. §9 says the initial map should be presented as "
        "an estimate to be verified; this is that list, boldest claim first, which is "
        "where a diagnostic is most informative.", 78))
    print()
    for r in rows:
        cap = p.capability(r.capability_id)
        print(f"  {pct(r.confidence)}  {cap.name:26} [{cap.level.value}]")
    if not rows:
        print("  none")
    print()


def show_calibration(p: CapabilityProfile) -> None:
    rows = p.calibration_gaps()
    print(f"\n{RULE}\nCALIBRATION — claim vs evidence  ({len(rows)} assessed)\n{RULE}\n")
    print(textwrap.fill(
        "Only computable where both numbers exist. Positive means the student claims "
        "more than the evidence supports; negative means they undersell themselves. "
        "Neither is a verdict — it is a signal Phase 5 may use to target diagnostics.", 78))
    print()
    if not rows:
        print("  nothing assessed yet — no gap is computable\n")
        return
    for r in rows:
        cap = p.capability(r.capability_id)
        gap = r.calibration_gap or 0.0
        note = "over-claimed" if gap > 0 else ("under-claimed" if gap < 0 else "calibrated")
        print(f"  {gap:+.2f}  {cap.name:26} self {pct(r.confidence)}  "
              f"evidence {pct(r.mastery)}   {note}")
    print()


def show_blocked(p: CapabilityProfile) -> None:
    blocked = p.blocked()
    print(f"\n{RULE}\nBLOCKED — unmet prerequisites  ({len(blocked)})\n{RULE}\n")
    print(textwrap.fill(
        "A prerequisite counts as met only when DEMONSTRATED. This is why Phase 1 stored "
        "prerequisites as data: §10 says the diagnostic should verify prerequisites "
        "rather than test everything, and this is the query that makes that possible.", 78))
    print()
    for cid, unmet in sorted(blocked.items()):
        cap = p.capability(cid)
        print(f"  {cap.name}")
        for prereq in unmet:
            r = p.row_for(prereq.id)
            print(f"      needs {prereq.name:24} {r.status.value:>14} "
                  f"(mastery {pct(r.mastery)})")
    if not blocked:
        print("  none")
    print(f"\n  threshold: mastery >= {DEMONSTRATED_AT:.2f}\n")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Inspect a student's capability state.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--load", metavar="ID", help="load a saved profile instead of the fixture")
    ap.add_argument("--save", action="store_true", help="write the profile to data/students/")
    ap.add_argument("--unverified", action="store_true")
    ap.add_argument("--calibration", action="store_true")
    ap.add_argument("--blocked", action="store_true")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--table", action="store_true",
                    help="numeric table instead of the capability map")
    ap.add_argument("--verify-next", action="store_true",
                    help="what is least substantiated (Phase 4)")
    ap.add_argument("--records", action="store_true", help="the §19 shape as JSON")
    args = ap.parse_args()

    graph = CapabilityGraph.load()

    # Default to the saved profile when there is one. Every other CLI in the project
    # (diagnose.py, assess.py) operates on student-001, and having this one silently show
    # an in-memory fixture instead made an assessment look like it had no effect.
    target = args.load or "student-001"
    try:
        profile = CapabilityProfile.load(target, graph)
    except FileNotFoundError as exc:
        if args.load:
            print(exc, file=sys.stderr)
            return 1
        profile = build_demo(graph)

    if args.save:
        profile.save()
        print(f"\nsaved {profile.student.id} "
              f"({len(profile.to_records()['student_capabilities'])} rows with data)\n")
        return 0
    if args.records:
        print(json.dumps(profile.to_records(), indent=2))
        return 0
    if args.summary:
        print(json.dumps(profile.summary(), indent=2))
        return 0
    if args.unverified:
        show_unverified(profile)
        return 0
    if args.calibration:
        show_calibration(profile)
        return 0
    if args.blocked:
        show_blocked(profile)
        return 0
    if args.verify_next:
        print()
        print(cmap.render_verification_queue(profile))
        print()
        return 0
    if args.table:
        show_table(profile)
        return 0

    print()
    print(cmap.render(profile))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
