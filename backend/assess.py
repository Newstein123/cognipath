#!/usr/bin/env python3
"""Phase 6 — turn a response into evidence, and evidence into a capability update.

Claude.md §11 and §14.

  python assess.py --rubric scale-api-001            show what an experience is judged on
  python assess.py --demo weak                       assess a built-in sample response
  python assess.py --demo strong --gemini            same, judged by Gemini
  python assess.py --item ID --response-file a.txt --gemini
  python assess.py --item ID --response-file a.txt --manual "growth-changes-shape=met,..."
  python assess.py --history                         the student's evidence log

Only --gemini makes a network call. Everything else runs offline.
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  — must precede project imports

import argparse
import sys
import textwrap
from pathlib import Path

from cognith_capability.graph import CapabilityGraph
from cognith_student.capability_map import pct
from cognith_learning.experience import ExperienceLibrary
from cognith_student.evidence import (
    Assessment,
    GeminiEvaluator,
    ManualEvaluator,
    Verdict,
    assess,
    save_evidence,
)
from cognith_student.history import load_history
from cognith_student.profile import CapabilityProfile
from cognith_student.storage import get_storage

RULE = "─" * 78

#: Two sample responses to the scalability scenario, for demonstrating the pipeline
#: without inventing a student. The weak one is deliberately plausible-sounding — it names
#: the right technologies with no reasoning, which is exactly what §10 says a diagnostic
#: must see through.
DEMO_RESPONSES = {
    "weak": (
        "I would add more servers and use Redis for caching. I would also use a load "
        "balancer to spread the traffic. Kubernetes would help with autoscaling. "
        "Probably switch to a NoSQL database since those scale better."
    ),
    "strong": (
        "First I would not change anything — 250ms at 100 req/sec with the database at "
        "45% CPU does not tell me what breaks at 10,000. I would load test against a "
        "copy and watch where latency goes non-linear.\n\n"
        "My expectation is the database goes first. At 100x the read volume, 45% CPU is "
        "not 45% of headroom — connection limits and lock contention usually bite before "
        "raw CPU does. I would look at the slowest queries under load and their plans.\n\n"
        "The application tier is the easy part: if it is stateless I can run many copies "
        "behind a load balancer, and that is mostly a cost question. But that makes the "
        "database problem worse, not better, because every new instance opens more "
        "connections.\n\n"
        "So: read replicas for read-heavy traffic, and a cache in front of whatever is "
        "read most and changes least. The risk with caching is that I now have two "
        "sources of truth and stale reads become a product decision, not just a technical "
        "one. And replicas do nothing for writes — if the write path is the real "
        "constraint, all of this buys me nothing and I would need to look at sharding, "
        "which is a much bigger change and a much bigger bill."
    ),
}
DEMO_ITEM = "scale-api-001"


def show_rubric(item, graph: CapabilityGraph) -> None:
    print(f"\n{RULE}\nRUBRIC — {item.id}\n{RULE}\n")
    print(f"  {item.title}   [{item.type.value}]   {item.minutes} min\n")
    print(textwrap.indent(item.prompt, "  "))
    probes = getattr(item, "probes", ())
    if probes:
        # Diagnostic scenarios name the reasoning dimensions they expose; corpus
        # exercises do not carry that field.
        print(f"\n  probes: {', '.join(probes)}")
    caps = ", ".join(graph.get(c).name for c in
                     dict.fromkeys(x.capability_id for x in item.rubric))
    print(f"\n  evidences: {caps}")
    print(f"\n{RULE}\nJudged on {len(item.rubric)} criteria\n{RULE}\n")
    for c in item.rubric:
        print(f"  [{graph.get(c.capability_id).name:20}] weight {c.weight}")
        print(textwrap.fill(c.criterion, 74, initial_indent="      ", subsequent_indent="      "))
        print()
    print(textwrap.fill(
        "Each criterion is judged independently as met / partial / unmet. Nothing "
        "produces an overall score — the capability scores are computed from these "
        "judgements afterwards (§11).", 78, initial_indent="  ", subsequent_indent="  "))
    print()


def show_assessment(a: Assessment, graph: CapabilityGraph, item) -> None:
    text = {c.id: c for c in item.rubric}
    attempt = a.evidence.attempt
    label = f"attempt {attempt}" if attempt > 1 else "first attempt"
    print(f"\n{RULE}\nEVIDENCE — {item.title}  [{item.type.value}]  {label}\n{RULE}\n")
    print(textwrap.fill(a.evidence.response, 78, initial_indent="  > ",
                        subsequent_indent="  > ")[:1400])

    print(f"\n\n{RULE}\nCRITERION JUDGEMENTS\n{RULE}\n")
    for r in a.evidence.results:
        c = text[r.criterion_id]
        print(f"  {r.verdict.mark}  {c.criterion}")
        print(f"      [{graph.get(c.capability_id).name}]  {r.justification}")
        print()

    print(f"{RULE}\nCAPABILITY UPDATE\n{RULE}\n")
    print(f"  {'capability':24} {'score':>6} {'before':>8} {'after':>7}   change")
    print(f"  {'-' * 24} {'-' * 6} {'-' * 8} {'-' * 7}   {'-' * 8}")
    for o in a.outcomes:
        cap = graph.get(o.capability_id)
        before = "unmeasured" if o.mastery_before is None else pct(o.mastery_before)
        arrow = "+" if o.delta > 0 else ""
        print(f"  {cap.name:24} {o.score:6.2f} {before:>8} {pct(o.mastery_after):>7}   "
              f"{arrow}{o.delta:.2f}")

    print(f"\n{RULE}\nWHY IT CHANGED\n{RULE}\n")
    for para in a.explanation.split("\n\n"):
        print(textwrap.fill(para, 78, initial_indent="  ", subsequent_indent="  "))
        print()


def show_history(student_id: str, graph: CapabilityGraph) -> int:
    log = get_storage().load_evidence(student_id)
    if not log:
        print(f"No evidence recorded for {student_id}.", file=sys.stderr)
        return 1
    print(f"\n{RULE}\nEVIDENCE LOG — {student_id}   ({len(log)} entries)\n{RULE}\n")
    for entry in log:
        ev, asmt = entry["evidence"], entry["assessment"]
        marks = {"met": "✓", "partial": "△", "unmet": "✗"}
        summary = " ".join(marks[r["verdict"]] for r in ev["results"])
        print(f"  {ev['createdAt'][:19]}  {ev['experienceId']}")
        print(f"     {summary}")
        for o in asmt["outcomes"]:
            before = "—" if o["masteryBefore"] is None else f"{o['masteryBefore']:.0%}"
            print(f"     {graph.get(o['capabilityId']).name:24} {before:>5} -> "
                  f"{o['masteryAfter']:.0%}")
        print()
    print("  Responses are stored verbatim; every number above can be recomputed from")
    print("  them if the scoring rules change (§11).\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Assess a response against its rubric and update the capability profile.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--student", default="student-001")
    ap.add_argument("--item", help="diagnostic item id")
    ap.add_argument("--rubric", metavar="ID", help="show a scenario's rubric and exit")
    ap.add_argument("--demo", choices=sorted(DEMO_RESPONSES), help="use a built-in response")
    ap.add_argument("--response-file", type=Path)
    ap.add_argument("--gemini", action="store_true", help="judge with Gemini (network call)")
    ap.add_argument("--manual", metavar="SPEC",
                    help='judgements, e.g. "crit-id=met,other-id=partial"')
    ap.add_argument("--history", action="store_true")
    ap.add_argument("--save", action="store_true", help="append to the evidence log")
    ap.add_argument("--dry-run", action="store_true", help="do not update the profile")
    args = ap.parse_args()

    graph = CapabilityGraph.load()
    library = ExperienceLibrary.load(graph)

    if args.history:
        return show_history(args.student, graph)

    if args.rubric:
        try:
            item = library.get(args.rubric)
        except KeyError:
            print(f"No experience {args.rubric!r}. Run `python practice.py --list`.",
                  file=sys.stderr)
            return 1
        if not item.assessable:
            print(f"{args.rubric!r} has no rubric and cannot be assessed.", file=sys.stderr)
            return 1
        show_rubric(item, graph)
        return 0

    item_id = args.item or (DEMO_ITEM if args.demo else None)
    if item_id is None:
        print("Give --item ID, or --demo weak|strong.", file=sys.stderr)
        return 1
    try:
        item = library.get(item_id)
    except KeyError:
        print(f"No experience {item_id!r}. Run `python practice.py --list`.",
              file=sys.stderr)
        return 1

    if args.demo:
        response = DEMO_RESPONSES[args.demo]
    elif args.response_file:
        response = args.response_file.read_text(encoding="utf-8")
    else:
        print("Give --demo, or --response-file.", file=sys.stderr)
        return 1

    if args.manual:
        verdicts = {}
        for pair in args.manual.split(","):
            if "=" not in pair:
                continue
            k, v = pair.split("=", 1)
            try:
                verdicts[k.strip()] = Verdict(v.strip())
            except ValueError:
                print(f"Bad verdict {v!r}. Use met|partial|unmet.", file=sys.stderr)
                return 1
        evaluator = ManualEvaluator(verdicts)
    elif args.gemini:
        evaluator = GeminiEvaluator()
    else:
        print("Choose an evaluator: --gemini (network) or --manual SPEC (offline).",
              file=sys.stderr)
        return 1

    try:
        profile = CapabilityProfile.load(args.student, graph)
    except FileNotFoundError as exc:
        print(f"{exc}\nRun `python onboard.py --save --student-id {args.student}` first.",
              file=sys.stderr)
        return 1

    try:
        assessment = assess(profile, item, response, evaluator, apply=not args.dry_run)
    except Exception as exc:  # noqa: BLE001 — surfaced, not swallowed
        print(f"\nEvaluation failed: {type(exc).__name__}: {exc}\n"
              f"The profile was not modified.\n", file=sys.stderr)
        return 1

    show_assessment(assessment, graph, item)

    if not args.dry_run and args.save:
        # Show what moved since last time. A retry is only useful to the learner if they
        # can see which of the things they were told about actually changed.
        history = load_history(args.student, library)
        attempts = history.experiences.get(item.id)
        if attempts and attempts.attempts > 1:
            print(f"{RULE}\nSINCE YOUR LAST ATTEMPT\n{RULE}\n")
            fixed = [t for t in history.trajectories.values()
                     if t.experience_id == item.id and t.fixed]
            stuck = [t for t in history.trajectories.values()
                     if t.experience_id == item.id and t.persistent]
            back = [t for t in history.trajectories.values()
                    if t.experience_id == item.id and t.regressed]
            for t in fixed:
                print(f"  fixed      {t.marks()}  {t.criterion}")
            for t in stuck:
                print(f"  still      {t.marks()}  {t.criterion}")
            for t in back:
                print(f"  slipped    {t.marks()}  {t.criterion}")
            print(f"\n  score {attempts.scores[-2]:.0%} -> {attempts.scores[-1]:.0%} "
                  f"({attempts.delta:+.0%})")
            if stuck:
                print(textwrap.fill(
                    "The 'still' items have now been missed more than once. That makes "
                    "them a blind spot rather than a slip, and they are what a lesson "
                    "should target.", 78, initial_indent="\n  ",
                    subsequent_indent="  "))
            print()

    if not args.dry_run:
        profile.save()
        print(f"  Profile updated. {RULE[:20]}")
    if args.save:
        path = save_evidence(assessment)
        print(f"  Evidence appended to {path.name}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
