#!/usr/bin/env python3
"""Phase 13 — what repeated attempts have taught us about the learner.

Offline. Reads the evidence log; stores nothing of its own.

  python learner.py --student demo          what we have learned about them
  python learner.py --student demo --blind  blind spots only
  python learner.py --student demo --log    every attempt, in order
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  — must precede project imports

import argparse
import sys
import textwrap

from cognith_capability.graph import CapabilityGraph
from cognith_learning.experience import ExperienceLibrary
from cognith_student.history import PERSISTENT_AFTER, LearnerHistory, load_history
from cognith_student.profile import CapabilityProfile

RULE = "═" * 78
THIN = "─" * 78


def show(h: LearnerHistory, graph: CapabilityGraph, library: ExperienceLibrary,
         name: str) -> None:
    print(f"\n{RULE}\n  WHAT WE HAVE LEARNED ABOUT {name.upper()}\n{RULE}\n")
    if not h.experiences:
        print("  Nothing yet — no experience has been attempted.\n")
        return

    retried = h.retried()
    print(f"  {len(h.experiences)} experience(s) attempted, {h.total_attempts} attempt(s) "
          f"in total, {len(retried)} retried.")

    responds = h.responds_to_feedback()
    if responds is None:
        print(textwrap.fill(
            "Nothing has been attempted twice yet, so there is no evidence about how this "
            "learner responds to feedback. That is a gap in what we know about them, not "
            "a judgement about them.", 76, initial_indent="\n  ", subsequent_indent="  "))
    else:
        verdict = ("acts on feedback reliably" if responds >= 0.7
                   else "acts on feedback sometimes" if responds >= 0.4
                   else "has not been able to act on the feedback given")
        print(f"\n  Responds to feedback: {responds:.0%} — {verdict}.")
        print(textwrap.fill(
            "Share of criteria that were unmet and later became met. This is a signal "
            "about the learner rather than about any capability: someone who reliably "
            "fixes what they are told about needs feedback, and someone who does not "
            "needs a different explanation.", 76, initial_indent="  ",
            subsequent_indent="  "))

    blind = h.persistent_misses()
    if blind:
        print(f"\n{THIN}\n  BLIND SPOTS — missed {PERSISTENT_AFTER}+ times\n{THIN}\n")
        print(textwrap.fill(
            "Missed once is a slip. Missed again, after being told exactly what was "
            "wrong, is something they cannot yet self-correct. These are what a lesson "
            "should target.", 76, initial_indent="  ", subsequent_indent="  "))
        print()
        by_cap = h.persistent_by_capability()
        for cid, items in by_cap.items():
            label = graph.get(cid).name if cid else "unattributed"
            print(f"  {label}")
            for t in items:
                print(f"      {t.marks()}  {t.criterion}")
            print()

    fixed = h.fixed_on_retry()
    if fixed:
        print(f"{THIN}\n  FIXED ON RETRY\n{THIN}\n")
        for t in fixed:
            print(f"  {t.marks()}  {t.criterion}")
        print()

    regressed = h.regressions()
    if regressed:
        print(f"{THIN}\n  SLIPPED BACK\n{THIN}\n")
        print("  Met before, not met now — the earlier pass may have been a fluke.\n")
        for t in regressed:
            print(f"  {t.marks()}  {t.criterion}")
        print()

    if retried:
        print(f"{THIN}\n  RETRIES\n{THIN}\n")
        for e in retried:
            try:
                title = library.get(e.experience_id).title
            except KeyError:
                title = e.experience_id
            trend = ("improving" if e.improving
                     else "no improvement — try something else" if e.stalled else "flat")
            scores = " -> ".join(f"{s:.0%}" for s in e.scores)
            print(f"  {title:30} {e.attempts} attempts   {scores}   {trend}")
        print()


def show_log(h: LearnerHistory, library: ExperienceLibrary) -> None:
    print(f"\n{RULE}\n  EVERY ATTEMPT\n{RULE}\n")
    rows = sorted(h.experiences.values(), key=lambda e: e.first_at)
    for e in rows:
        try:
            title = library.get(e.experience_id).title
        except KeyError:
            title = e.experience_id
        print(f"  {title}")
        for n, score in enumerate(e.scores, 1):
            print(f"      attempt {n}   {score:.0%}")
        trajectories = [t for t in h.trajectories.values()
                        if t.experience_id == e.experience_id]
        for t in sorted(trajectories, key=lambda x: x.criterion_id):
            print(f"      {t.marks()}  {t.criterion[:58]}")
        print()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="What repeated attempts reveal about a learner.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--student", default="student-001")
    ap.add_argument("--blind", action="store_true", help="blind spots only")
    ap.add_argument("--log", action="store_true", help="every attempt, in order")
    args = ap.parse_args()

    graph = CapabilityGraph.load()
    library = ExperienceLibrary.load(graph)
    try:
        profile = CapabilityProfile.load(args.student, graph)
        name = profile.student.name
    except FileNotFoundError:
        name = args.student

    history = load_history(args.student, library)

    if args.log:
        show_log(history, library)
        return 0
    if args.blind:
        blind = history.persistent_misses()
        print(f"\n  {len(blind)} blind spot(s) for {name}\n")
        for t in blind:
            label = graph.get(t.capability_id).name if t.capability_id else "—"
            print(f"  {t.marks()}  [{label}]  {t.criterion}")
        print()
        return 0

    show(history, graph, library, name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
