#!/usr/bin/env python3
"""Phase 9 — the flagship mission. Claude.md §12, §13, §21 Phase 9.

The simulation is deterministic and offline. Only --submit --gemini makes a network call,
and it judges your REASONING, never the simulation.

  python mission.py --brief                    the situation
  python mission.py --investigate db-pressure  look before you leap (free)
  python mission.py --act add-cache --why "..." make a change, stating why
  python mission.py --status                   where the system stands
  python mission.py --transcript               everything you did
  python mission.py --submit --gemini          assess the session, update capabilities
  python mission.py --calibrate                verify the model against §12 and §13
  python mission.py --reset
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  — must precede project imports

import argparse
import json
import sys
import textwrap
from datetime import datetime
from pathlib import Path

from cognith_capability.graph import CapabilityGraph
from cognith_learning.mission import (
    MissionEngine,
    MissionError,
    MissionState,
    Metrics,
)
from cognith_student.profile import CapabilityProfile

RULE = "─" * 78
SESSION_DIR = Path(__file__).resolve().parent / "data" / "missions"


# --- session ---------------------------------------------------------------------
def session_path(student: str, mission_id: str) -> Path:
    return SESSION_DIR / f"{student}__{mission_id}.json"


def load_session(student: str, engine: MissionEngine) -> dict:
    path = session_path(student, engine.mission.id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"student": student, "mission": engine.mission.id,
            "state": engine.mission.initial.to_record(), "steps": [],
            "startedAt": datetime.now().isoformat()}


def save_session(session: dict, engine: MissionEngine) -> Path:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    path = session_path(session["student"], engine.mission.id)
    path.write_text(json.dumps(session, indent=2), encoding="utf-8")
    return path


def state_of(session: dict) -> MissionState:
    r = session["state"]
    return MissionState(app_servers=r["appServers"], replicas=r["replicas"],
                        db_tier=r["dbTier"], cache=r["cache"],
                        load_balancer=r["loadBalancer"])


# --- display ---------------------------------------------------------------------
def show_metrics(engine: MissionEngine, state: MissionState) -> None:
    t = engine.mission.target
    ok, checks, m = engine.meets_target(state)
    now = engine.evaluate(state, engine.m["baseline_rps"])

    print(f"  system: {state.app_servers} app server(s)"
          f"{', load balancer' if state.load_balancer else ''}"
          f"{', cache' if state.cache else ''}"
          f", {state.db_tier} database"
          f"{f', {state.replicas} replica(s)' if state.replicas else ''}")
    print(f"\n  at today's 100 req/sec:   {now.latency_ms:>6.0f} ms   "
          f"db {now.db_cpu_pct:>3.0f}%")
    print(f"  at the target 10,000:     {m.latency_ms:>6.0f} ms   "
          f"db {m.db_cpu_pct:>3.0f}%   serving {m.served_rps:,.0f} req/sec")
    print(f"  cost:                     ${m.cost_month:>6,.0f} / month")

    print(f"\n  {'throughput':12} {'10,000 req/sec':>18}   "
          f"{'MET' if checks['throughput'] else 'not met'}")
    print(f"  {'latency':12} {'under 200 ms':>18}   "
          f"{'MET' if checks['latency'] else 'not met'}")
    print(f"  {'cost':12} {'under $2,000/mo':>18}   "
          f"{'MET' if checks['cost'] else 'not met'}")

    for w in m.warnings:
        print(f"\n  ! {textwrap.fill(w, 74, subsequent_indent='    ')}")
    if ok:
        print(f"\n  All three requirements met.")


def explain_latency(engine: MissionEngine, m: Metrics) -> None:
    t = m.terms
    print(f"\n  latency = app {t['app_latency_ms']:.0f}ms + "
          f"db {t['db_latency_base_ms']:.0f}ms / (1 - {t['db_utilisation']:.2f})")
    print(f"          = {t['app_latency_ms']:.0f} + {t['db_component_ms']:.0f}"
          f" = {m.latency_ms:.0f}ms")
    print(f"\n  The database term grows without bound as utilisation approaches 1.")
    print(f"  That is why halving the load matters more than doubling the servers.")


def show_brief(engine: MissionEngine) -> None:
    M = engine.mission
    print(f"\n{RULE}\nMISSION — {M.title}\n{RULE}\n")
    print(textwrap.indent(textwrap.fill(M.brief.replace("\n\n", "\x00"), 76)
                          .replace("\x00", "\n\n  "), "  "))
    print(f"\n{RULE}\nWHERE THINGS STAND\n{RULE}\n")
    show_metrics(engine, M.initial)
    print(f"\n{RULE}\nWHAT YOU CAN LOOK AT  (free)\n{RULE}\n")
    for i in M.investigations.values():
        print(f"  {i.id:20} {i.name}")
    print(f"\n{RULE}\nWHAT YOU CAN CHANGE\n{RULE}\n")
    for a in M.actions.values():
        print(f"  {a.id:20} {a.name}")
    print(f"\n  Every change needs a reason:")
    print(f"    python mission.py --act add-cache --why \"reads dominate the mix\"\n")


def show_transcript(session: dict, engine: MissionEngine) -> None:
    print(f"\n{RULE}\nTRANSCRIPT — {engine.mission.title}\n{RULE}\n")
    if not session["steps"]:
        print("  Nothing yet.\n")
        return
    for n, s in enumerate(session["steps"], 1):
        verb = "LOOKED AT" if s["kind"] == "investigate" else "CHANGED"
        print(f"  {n}. {verb}: {s['name']}")
        if s.get("reasoning"):
            print(textwrap.fill(f'why: "{s["reasoning"]}"', 74,
                                initial_indent="     ", subsequent_indent="          "))
        print(textwrap.indent(textwrap.fill(s["text"], 70), "     > "))
        if s.get("after"):
            a = s["after"]
            print(f"     -> at 10,000 req/sec: {a['latencyMs']}ms, "
                  f"${a['costMonth']:,}/mo, serving {a['servedRps']:,}")
        print()


def build_transcript_text(session: dict, engine: MissionEngine) -> str:
    """The response that gets assessed. Every decision and its stated reasoning."""
    lines = [f"MISSION: {engine.mission.title}", ""]
    if not session["steps"]:
        lines.append("(the learner took no action)")
    for n, s in enumerate(session["steps"], 1):
        verb = "INVESTIGATED" if s["kind"] == "investigate" else "DECISION"
        lines.append(f"{n}. {verb}: {s['name']}")
        if s.get("reasoning"):
            lines.append(f"   REASONING: {s['reasoning']}")
        lines.append(f"   RESULT: {s['text'].strip()}")
        if s.get("after"):
            a = s["after"]
            lines.append(f"   SYSTEM NOW: {a['latencyMs']}ms at 10,000 req/sec, "
                         f"${a['costMonth']}/month, serving {a['servedRps']} req/sec")
        lines.append("")
    state = state_of(session)
    ok, checks, m = engine.meets_target(state)
    lines.append("FINAL ARCHITECTURE: "
                 f"{state.app_servers} app server(s), "
                 f"{'load balancer, ' if state.load_balancer else 'no load balancer, '}"
                 f"{'cache, ' if state.cache else 'no cache, '}"
                 f"{state.db_tier} database, {state.replicas} replica(s)")
    lines.append(f"OUTCOME: {m.latency_ms:.0f}ms, ${m.cost_month:.0f}/month, "
                 f"{m.served_rps:.0f} req/sec — "
                 f"{'all requirements met' if ok else 'requirements NOT met: ' + ', '.join(k for k, v in checks.items() if not v)}")
    return "\n".join(lines)


# --- calibration -----------------------------------------------------------------
def calibrate(engine: MissionEngine) -> int:
    """Acceptance test: §12's starting state, and §13's lessons holding.

    Deterministic, so it either passes or the model is wrong. Runs offline.
    """
    M = engine.mission
    print(f"\n{RULE}\nMODEL CALIBRATION\n{RULE}\n")
    failures = 0

    b = engine.baseline()
    print("§12's starting system: 100 req/sec, 250ms, 45% database CPU, $500/month\n")
    for label, got, want, tol in (
        ("served req/sec", b.served_rps, 100, 1),
        ("latency ms", b.latency_ms, 250, 3),
        ("database CPU %", b.db_cpu_pct, 45, 1),
        ("cost $/month", b.cost_month, 500, 1),
    ):
        ok = abs(got - want) <= tol
        failures += not ok
        print(f"  {label:18} want {want:>6}   got {got:>7.1f}   {'ok' if ok else 'MISMATCH'}")

    print(f"\n{RULE}\n§13's lessons — each single lever must fail\n{RULE}\n")

    def run(actions):
        s = M.initial
        for a in actions:
            s = engine.apply(s, a)
        return engine.meets_target(s)

    cases = [
        ("application servers alone",
         ["add-app-server"] * 3, False,
         "adding servers does not relieve the database"),
        ("servers + load balancer, nothing else",
         ["add-app-server"] * 3 + ["add-load-balancer"], False,
         "the database is still the binding constraint"),
        ("read replicas instead of a cache",
         ["add-app-server"] * 3 + ["add-load-balancer", "upgrade-db-large"]
         + ["add-replica"] * 5, False,
         "works technically, but blows the budget"),
        ("biggest database, no cache",
         ["add-app-server"] * 3 + ["add-load-balancer", "upgrade-db-large"], False,
         "cannot reach 10,000 req/sec without reducing read volume"),
        ("spend everything",
         ["add-app-server"] * 3 + ["add-load-balancer", "add-cache", "upgrade-db-large"]
         + ["add-replica"] * 5, False,
         "over budget — more is not better"),
        ("servers + balancer + cache + large database",
         ["add-app-server"] * 3 + ["add-load-balancer", "add-cache", "upgrade-db-large"],
         True, "the intended solution"),
    ]
    for label, actions, want_pass, why in cases:
        ok, checks, m = run(actions)
        good = ok == want_pass
        failures += not good
        missed = ", ".join(k for k, v in checks.items() if not v) or "—"
        print(f"  {'PASS' if ok else 'fail'}  {label:44} {'ok' if good else 'UNEXPECTED'}")
        print(f"        {m.served_rps:>6,.0f} rps  {m.latency_ms:>6.0f} ms  "
              f"${m.cost_month:>5,.0f}   unmet: {missed}")
        print(f"        {why}")

    print(f"\n{RULE}")
    print(f"  {'all checks passed' if not failures else f'{failures} FAILURE(S)'}")
    print(textwrap.fill(
        "There is exactly one affordable path: reduce read volume with a cache, then buy "
        "the database capacity the remaining writes need. Every other route either leaves "
        "the database saturated or costs more than $2,000. That is the lesson, and it is "
        "arithmetic, not a model's opinion.", 78, initial_indent="\n  ",
        subsequent_indent="  "))
    print()
    return 0 if not failures else 1


# --- main ------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run the flagship mission.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--student", default="student-001")
    ap.add_argument("--mission", default=None)
    ap.add_argument("--brief", action="store_true")
    ap.add_argument("--investigate", metavar="ID")
    ap.add_argument("--act", metavar="ID")
    ap.add_argument("--why", default="", help="your reasoning for this change")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--explain", action="store_true", help="show the latency arithmetic")
    ap.add_argument("--transcript", action="store_true")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--gemini", action="store_true")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    try:
        engine = MissionEngine.load(args.mission)
    except (MissionError, FileNotFoundError) as exc:
        print(exc, file=sys.stderr)
        return 1
    M = engine.mission

    if args.calibrate:
        return calibrate(engine)
    if args.brief:
        show_brief(engine)
        return 0

    session = load_session(args.student, engine)

    if args.reset:
        path = session_path(args.student, M.id)
        path.unlink(missing_ok=True)
        print(f"\n  Session reset. `python mission.py --brief` to start again.\n")
        return 0

    if args.investigate:
        inv = M.investigations.get(args.investigate)
        if inv is None:
            print(f"No investigation {args.investigate!r}. Available: "
                  f"{', '.join(M.investigations)}", file=sys.stderr)
            return 1
        session["steps"].append({
            "kind": "investigate", "ref": inv.id, "name": inv.name,
            "reasoning": args.why, "text": inv.reveals, "after": None,
            "at": datetime.now().isoformat()})
        save_session(session, engine)
        print(f"\n{RULE}\n{inv.name}\n{RULE}\n")
        print(textwrap.indent(textwrap.fill(inv.reveals, 74), "  "))
        print("\n  Looking costs nothing, and it is recorded — investigating before")
        print("  changing is itself part of what is assessed.\n")
        return 0

    if args.act:
        state = state_of(session)
        action = M.actions.get(args.act)
        if action is None:
            print(f"No action {args.act!r}. Available: {', '.join(M.actions)}",
                  file=sys.stderr)
            return 1
        if not args.why:
            print("\n  Every change needs a reason. Add --why \"...\".\n"
                  "  §12: \"The learner must explain why they made the decision.\"\n",
                  file=sys.stderr)
            return 1
        before = engine.meets_target(state)[2]
        try:
            new_state = engine.apply(state, args.act)
        except MissionError as exc:
            print(f"\n  {exc}\n", file=sys.stderr)
            return 1
        after = engine.meets_target(new_state)[2]
        session["state"] = new_state.to_record()
        session["steps"].append({
            "kind": "act", "ref": action.id, "name": action.name,
            "reasoning": args.why, "text": action.consequence,
            "before": before.to_record(), "after": after.to_record(),
            "at": datetime.now().isoformat()})
        save_session(session, engine)

        print(f"\n{RULE}\n{action.name}\n{RULE}\n")
        print(textwrap.indent(textwrap.fill(action.consequence, 74), "  "))
        print(f"\n  latency at 10,000 req/sec: {before.latency_ms:.0f}ms "
              f"-> {after.latency_ms:.0f}ms")
        print(f"  cost: ${before.cost_month:,.0f} -> ${after.cost_month:,.0f} / month")
        print()
        show_metrics(engine, new_state)
        print()
        return 0

    if args.transcript:
        show_transcript(session, engine)
        return 0

    if args.submit:
        from cognith_learning.experience import ExperienceLibrary
        from cognith_student.evidence import (
            GeminiEvaluator, ManualEvaluator, Verdict, assess, save_evidence)

        transcript = build_transcript_text(session, engine)
        if not session["steps"]:
            print("\n  Nothing to submit — you have not done anything yet.\n",
                  file=sys.stderr)
            return 1
        if not args.gemini:
            print(f"\n{RULE}\nWHAT WOULD BE ASSESSED\n{RULE}\n")
            print(textwrap.indent(transcript, "  "))
            print(f"\n{RULE}\n  Add --gemini to have this judged against "
                  f"{len(M.rubric)} criteria.\n")
            return 0

        graph = CapabilityGraph.load()
        try:
            profile = CapabilityProfile.load(args.student, graph)
        except FileNotFoundError as exc:
            print(f"{exc}\nRun `python onboard.py --save --student-id {args.student}` "
                  f"first.", file=sys.stderr)
            return 1
        experience = ExperienceLibrary.load(graph).get(M.id)
        try:
            assessment = assess(profile, experience, transcript, GeminiEvaluator())
        except Exception as exc:  # noqa: BLE001
            print(f"\nEvaluation failed: {type(exc).__name__}: {exc}\n"
                  f"The profile was not modified.\n", file=sys.stderr)
            return 1

        import assess as assess_cli
        assess_cli.show_assessment(assessment, graph, experience)
        profile.save()
        save_evidence(assessment)
        print(f"  Profile updated and evidence recorded.\n")
        return 0

    if args.explain:
        _, _, m = engine.meets_target(state_of(session))
        print(f"\n{RULE}\nHOW LATENCY IS COMPUTED\n{RULE}")
        explain_latency(engine, m)
        print()
        return 0

    print(f"\n{RULE}\n{M.title}\n{RULE}\n")
    show_metrics(engine, state_of(session))
    print(f"\n  {len(session['steps'])} step(s) taken. "
          f"`--transcript` to review, `--brief` for the situation.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
