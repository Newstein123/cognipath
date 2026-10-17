#!/usr/bin/env python3
"""Cognith — the interactive session. One entry point.

    python app.py

Everything the fifteen command-line tools do, in one conversation you can leave and come
back to. State already persisted between commands, so resuming is free.

THIS FILE ADDS NO LOGIC. Every screen calls an engine or a renderer that already exists —
selection, assessment, retrieval, the simulation, the milestone maths. If something here
looks like a decision being made, it is a bug: the decision belongs in the layer that owns
it. The individual CLIs remain for scripting and debugging.
"""

from __future__ import annotations

import _bootstrap  # noqa: F401  — must precede project imports

import sys
import textwrap
from pathlib import Path

from cognith_capability.graph import CapabilityGraph
from cognith_capability.milestone import MilestoneMap
from cognith_learning.experience import (
    ExperienceLibrary,
    ExperienceType,
    LearningExperience,
)
from cognith_learning.knowledge import GapResolver
from cognith_learning.loop import AdaptiveLoop, StepKind
from cognith_student import capability_map as cmap
from cognith_student.evidence import GeminiEvaluator, assess, save_evidence
from cognith_student.history import load_history
from cognith_student.onboarding import OnboardingAnswers, OnboardingEngine
from cognith_student.profile import CapabilityProfile
from cognith_student.storage import get_storage
from cognith_student.progress import active, path_for

RULE = "═" * 74
THIN = "─" * 74


# --- input helpers ----------------------------------------------------------------
def ask(prompt: str, default: str = "") -> str:
    """One line of input. Ctrl-C and Ctrl-D leave cleanly rather than traceback."""
    try:
        value = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print("\n\n  Progress is saved. See you.\n")
        raise SystemExit(0)
    return value or default


def ask_lines(prompt: str) -> str:
    """A multi-line answer. This is what replaces --response-file.

    Ends on '.' alone, or on two consecutive blank lines.

    NOT on a single blank line, even though that is the obvious rule. A scenario answer is
    prose, prose has paragraphs, and people paste. Ending on the first blank line would
    silently truncate a pasted answer at its first paragraph break — losing most of it,
    with no indication that anything was lost.
    """
    print(prompt)
    print("  (end with '.' on its own line, or two blank lines · 'cancel' to go back)\n")
    lines: list[str] = []
    while True:
        try:
            line = input("  ")
        except (EOFError, KeyboardInterrupt):
            print("\n\n  Progress is saved. See you.\n")
            raise SystemExit(0)
        if line.strip().lower() == "cancel":
            return ""
        if line.strip() == ".":
            break
        if not line.strip():
            if lines and not lines[-1].strip():
                break
            if not lines:
                continue
        lines.append(line)
    return "\n".join(lines).strip()


def confirm(prompt: str) -> bool:
    return ask(f"  {prompt} [y/N] ").lower().startswith("y")


def pick(options: list[tuple[str, str]], prompt: str = "  > ") -> str | None:
    """Numbered choice. Returns the chosen key, or None for back."""
    for n, (_, label) in enumerate(options, 1):
        print(f"    {n}. {label}")
    print(f"    b. back")
    while True:
        choice = ask(prompt)
        if choice.lower() in ("b", "back", ""):
            return None
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1][0]
        print("    Pick a number, or 'b'.")


def pause() -> None:
    ask("\n  [enter to continue] ")


def wrap(text: str, indent: str = "  ") -> str:
    out = []
    for para in text.split("\n\n"):
        out.append(textwrap.fill(para, 72, initial_indent=indent,
                                 subsequent_indent=indent))
    return "\n\n".join(out)


# --- session ------------------------------------------------------------------------
class Session:
    def __init__(self, student_id: str):
        self.graph = CapabilityGraph.load()
        self.library = ExperienceLibrary.load(self.graph)
        self.student_id = student_id
        self.profile = CapabilityProfile.load(student_id, self.graph)

    def reload(self) -> None:
        self.profile = CapabilityProfile.load(self.student_id, self.graph)

    @property
    def loop(self) -> AdaptiveLoop:
        return AdaptiveLoop(self.graph, self.profile)

    @property
    def resolver(self) -> GapResolver:
        return GapResolver(self.graph, self.profile)

    def goal_key(self) -> str | None:
        if not self.profile.student.goal:
            return None
        goals = OnboardingEngine.load(self.graph).goals
        return next((k for k, s in goals.items()
                     if s["name"] == self.profile.student.goal), None)

    def milestone_path(self):
        key = self.goal_key()
        if key is None:
            return []
        try:
            return path_for(self.profile, MilestoneMap.load(self.graph), key)
        except (FileNotFoundError, KeyError):
            return []


# --- onboarding ---------------------------------------------------------------------
def onboard(graph: CapabilityGraph, student_id: str) -> bool:
    """§8's five questions, asked one at a time."""
    engine = OnboardingEngine.load(graph)
    print(f"\n{RULE}\n  Let's find out where you are.\n{RULE}\n")
    print(wrap("Five questions. Nothing here is a test — it produces an initial "
               "estimate that we will then verify together."))
    print()

    name = ask("  Your name: ") or "Student"

    print("\n  What are you working toward?")
    keys = list(engine.goals)
    goal = pick([(k, engine.goals[k]["name"]) for k in keys], "  > ")
    if goal is None:
        return False

    knows = ask("\n  What do you already know? ")
    techs = ask("  What technologies have you used? (comma separated) ")
    built = ask("  What have you built? ")

    print("\n  How confident are you overall?")
    levels = list(engine.levels)
    level = pick([(k, engine.levels[k]["label"]) for k in levels], "  > ")
    if level is None:
        return False

    answers = OnboardingAnswers(
        student_name=name, goal=goal,
        technologies=tuple(t.strip() for t in techs.split(",") if t.strip()),
        knows=knows, built=built, self_rated_level=level,
    )
    profile, result = engine.build_profile(answers, student_id=student_id)
    profile.save()

    print(f"\n{RULE}")
    print(cmap.render(profile, focus=engine.focus_for(goal),
                      title="YOUR INITIAL MAP — an estimate, not an assessment"))
    if result.unrecognised_technologies:
        print(f"\n  Not recognised: {', '.join(result.unrecognised_technologies)}")
    pause()
    return True


# --- answering an experience ---------------------------------------------------------
def do_experience(s: Session, experience: LearningExperience) -> None:
    """Show a scenario, take the answer here, assess it. Replaces --response-file."""
    print(f"\n{RULE}\n  {experience.title}   [{experience.type.value}]\n{RULE}\n")
    caps = ", ".join(s.graph.get(c).name for c in experience.capability_ids)
    print(f"  about {experience.minutes} minutes · evidences {caps}\n")
    print(textwrap.indent(experience.prompt, "  "))
    print(f"\n{THIN}")

    response = ask_lines("\n  Your answer:")
    if not response:
        print("\n  Cancelled — nothing was recorded.\n")
        return

    print(f"\n{THIN}")
    print(wrap(f"This will be judged against {len(experience.rubric)} criteria by Gemini. "
               "That is a network call."))
    if not confirm("Assess it now?"):
        print("\n  Not assessed. Your answer was not saved.\n")
        return

    print("\n  Judging...\n")
    try:
        assessment = assess(s.profile, experience, response, GeminiEvaluator())
    except Exception as exc:  # noqa: BLE001
        print(f"  Assessment failed: {type(exc).__name__}: {exc}")
        print("  Your profile was not changed.\n")
        return

    import assess as assess_cli
    assess_cli.show_assessment(assessment, s.graph, experience)
    s.profile.save()
    save_evidence(assessment)

    history = load_history(s.student_id, s.library)
    attempts = history.experiences.get(experience.id)
    if attempts and attempts.attempts > 1:
        print(f"{THIN}\n  SINCE YOUR LAST ATTEMPT\n{THIN}\n")
        for t in history.trajectories.values():
            if t.experience_id != experience.id:
                continue
            tag = ("fixed  " if t.fixed else "still  " if t.persistent
                   else "slipped" if t.regressed else None)
            if tag:
                print(f"  {tag}  {t.marks()}  {t.criterion[:54]}")
        print(f"\n  score {attempts.scores[-2]:.0%} -> {attempts.scores[-1]:.0%} "
              f"({attempts.delta:+.0%})")
    s.reload()
    pause()


def choose_experience(s: Session, kind: ExperienceType, empty: str) -> None:
    items = [e for e in s.library.of_type(kind) if e.assessable]
    if kind is ExperienceType.APPLY:
        ready = {e.id for e in s.library.ready_to_apply(s.profile)}
        locked = [e for e in items if e.id not in ready]
        items = [e for e in items if e.id in ready]
        if locked:
            from cognith_learning.mastery import mastered_skills

            won = mastered_skills(s.profile, s.library)
            print("\n  Locked until you have evidence in their components:")
            for e in locked:
                need = ", ".join(c.name for c in s.library.apply_blocked_by(e, won))
                print(f"    {e.title}  — needs {need}")
    if not items:
        print(f"\n  {empty}\n")
        pause()
        return
    print()
    chosen = pick([(e.id, f"{e.title}  ({e.level.value}, {e.minutes} min)")
                   for e in items])
    if chosen:
        do_experience(s, s.library.get(chosen))


# --- screens -------------------------------------------------------------------------
def screen_map(s: Session) -> None:
    print()
    print(cmap.render(s.profile))
    pause()


def screen_milestones(s: Session) -> None:
    path = s.milestone_path()
    if not path:
        print("\n  No milestones for this goal.\n")
        pause()
        return
    import milestones as m_cli
    print()
    m_cli.show_path(path, s.graph, s.profile)
    pause()


def screen_diagnose(s: Session) -> None:
    from cognith_student.diagnostic import DiagnosticEngine

    path = s.milestone_path()
    current = active(path)
    relevance = current.relevance() if current else None
    diagnostic = DiagnosticEngine.load(s.graph).build(s.profile, relevance=relevance)
    if not diagnostic.items:
        print("\n  Nothing worth verifying right now.\n")
        pause()
        return

    print(f"\n{RULE}\n  DIAGNOSTIC\n{RULE}\n")
    if current:
        print(f"  Aiming at: {current.summary()}\n")
    print(wrap("These were chosen because they are the parts of your profile being taken "
               "most on trust. You can answer one now and come back for the rest."))
    print()
    for cand in diagnostic.selected:
        cap = s.graph.get(cand.capability_id)
        print(f"    {cap.name}")
        for note in cand.notes:
            print(f"        · {note}")
    print()
    chosen = pick([(i.id, f"{s.graph.get(i.capability_id).name}  ({i.minutes} min)")
                   for i in diagnostic.items])
    if chosen:
        do_experience(s, s.library.get(chosen))


def screen_learn(s: Session) -> None:
    gaps = s.resolver.gaps()
    if not gaps:
        print("\n  No demonstrated gaps yet — take a diagnostic first so there is "
              "something real to teach to.\n")
        pause()
        return
    print(f"\n{RULE}\n  WHAT YOU COULD LEARN\n{RULE}\n")
    labels = []
    for g in gaps:
        cap = s.graph.get(g.capability_id)
        tag = f"  ({len(g.persistent)} blind spot)" if g.persistent else ""
        labels.append((cap.id, f"{cap.name}  — demonstrated {g.mastery:.0%}{tag}"))
    chosen = pick(labels)
    if chosen is None:
        return
    gap = next(g for g in gaps if g.capability_id == chosen)
    print(wrap("\nThis retrieves from the learning materials and asks Gemini to explain "
               "what was found. That is a network call."))
    if not confirm("Go ahead?"):
        return
    print("\n  Retrieving...\n")
    try:
        knowledge = s.resolver.knowledge_for(gap)
    except Exception as exc:  # noqa: BLE001
        print(f"  Retrieval failed: {type(exc).__name__}: {exc}\n")
        return
    import learn as learn_cli
    learn_cli.show_knowledge(knowledge, s.graph)
    pause()


def screen_mission(s: Session) -> None:
    import mission as mission_cli
    from cognith_learning.mission import MissionEngine, MissionError

    engine = MissionEngine.load()
    M = engine.mission
    session = mission_cli.load_session(s.student_id, engine)

    while True:
        state = mission_cli.state_of(session)
        print(f"\n{RULE}\n  {M.title}\n{RULE}\n")
        mission_cli.show_metrics(engine, state)
        print(f"\n  {len(session['steps'])} step(s) taken.\n")
        choice = pick([
            ("brief", "Read the brief"),
            ("look", "Investigate something (free)"),
            ("act", "Make a change"),
            ("log", "Review what I have done"),
            ("submit", "Submit for assessment"),
        ])
        if choice is None:
            return
        if choice == "brief":
            print()
            print(wrap(M.brief))
            pause()
        elif choice == "look":
            print()
            which = pick([(i.id, i.name) for i in M.investigations.values()])
            if which:
                inv = M.investigations[which]
                session["steps"].append({
                    "kind": "investigate", "ref": inv.id, "name": inv.name,
                    "reasoning": "", "text": inv.reveals, "after": None,
                    "at": __import__("datetime").datetime.now().isoformat()})
                mission_cli.save_session(session, engine)
                print(f"\n{THIN}\n{wrap(inv.reveals)}\n{THIN}")
                pause()
        elif choice == "act":
            print()
            which = pick([(a.id, a.name) for a in M.actions.values()])
            if not which:
                continue
            why = ask("\n  Why this change? ")
            if not why:
                print("\n  Every change needs a reason — nothing was recorded.\n")
                continue
            action = M.actions[which]
            before = engine.meets_target(state)[2]
            try:
                new_state = engine.apply(state, which)
            except MissionError as exc:
                print(f"\n  {exc}\n")
                pause()
                continue
            after = engine.meets_target(new_state)[2]
            session["state"] = new_state.to_record()
            session["steps"].append({
                "kind": "act", "ref": action.id, "name": action.name,
                "reasoning": why, "text": action.consequence,
                "before": before.to_record(), "after": after.to_record(),
                "at": __import__("datetime").datetime.now().isoformat()})
            mission_cli.save_session(session, engine)
            print(f"\n{THIN}\n{wrap(action.consequence)}")
            print(f"\n  latency {before.latency_ms:.0f}ms -> {after.latency_ms:.0f}ms   "
                  f"cost ${before.cost_month:,.0f} -> ${after.cost_month:,.0f}")
            pause()
        elif choice == "log":
            mission_cli.show_transcript(session, engine)
            pause()
        elif choice == "submit":
            if not session["steps"]:
                print("\n  You have not done anything yet.\n")
                pause()
                continue
            transcript = mission_cli.build_transcript_text(session, engine)
            print(f"\n{THIN}\n{textwrap.indent(transcript, '  ')}\n{THIN}")
            if not confirm("Submit this for assessment? (network call)"):
                continue
            experience = s.library.get(M.id)
            print("\n  Judging...\n")
            try:
                assessment = assess(s.profile, experience, transcript, GeminiEvaluator())
            except Exception as exc:  # noqa: BLE001
                print(f"  Assessment failed: {type(exc).__name__}: {exc}\n")
                continue
            import assess as assess_cli
            assess_cli.show_assessment(assessment, s.graph, experience)
            s.profile.save()
            save_evidence(assessment)
            s.reload()
            pause()
            return


def screen_me(s: Session) -> None:
    import learner as learner_cli
    print()
    learner_cli.show(load_history(s.student_id, s.library), s.graph, s.library,
                     s.profile.student.name)
    pause()


# --- the main loop --------------------------------------------------------------------
ICON = {StepKind.ONBOARD: "start", StepKind.DIAGNOSE: "test", StepKind.LEARN: "read",
        StepKind.PRACTISE: "do", StepKind.APPLY: "apply", StepKind.MISSION: "mission",
        StepKind.NOTHING: "—"}


def home(s: Session) -> None:
    loop = s.loop
    state = loop.recommend()
    student = s.profile.student
    print(f"\n{RULE}")
    print(f"  {student.name}" + (f"  —  {student.goal}" if student.goal else ""))
    print(RULE)
    print(f"\n  {loop.position()}\n")

    top = state.steps[0] if state.steps else None
    if top and top.kind is not StepKind.NOTHING:
        mins = f", ~{top.minutes} min" if top.minutes else ""
        print(f"  Suggested next: [{ICON[top.kind]}] {top.title}{mins}")
        print(wrap(top.why, "      "))
        print()


def run(s: Session) -> None:
    while True:
        home(s)
        print("  What would you like to do?  [enter = the suggestion above]\n")
        actions = [
            ("next", "Do the suggested next thing"),
            ("map", "My capability map"),
            ("milestones", "My milestones — how far I have come"),
            ("diagnose", "Take a diagnostic"),
            ("learn", "Learn something I am weak at"),
            ("practise", "Practise one capability"),
            ("apply", "Apply several together"),
            ("mission", "The mission"),
            ("me", "What you have learned about me"),
        ]
        for n, (_, label) in enumerate(actions, 1):
            print(f"    {n}. {label}")
        print("    q. quit\n")

        raw = ask("  > ", "next").lower()
        if raw in ("q", "quit", "exit"):
            print("\n  Progress is saved. See you.\n")
            return
        key = None
        if raw.isdigit() and 1 <= int(raw) <= len(actions):
            key = actions[int(raw) - 1][0]
        else:
            key = next((k for k, _ in actions if k.startswith(raw)), None)
        if key is None:
            print("  Not sure what that means — pick a number.\n")
            continue

        if key == "next":
            state = s.loop.recommend()
            step = state.steps[0] if state.steps else None
            if step is None or step.kind is StepKind.NOTHING:
                print("\n  Nothing outstanding.\n")
                pause()
                continue
            key = {StepKind.DIAGNOSE: "diagnose", StepKind.LEARN: "learn",
                   StepKind.PRACTISE: "practise", StepKind.APPLY: "apply",
                   StepKind.MISSION: "mission"}.get(step.kind, "map")
            if step.experience_id and key in ("practise", "apply"):
                do_experience(s, s.library.get(step.experience_id))
                continue

        {
            "map": screen_map, "milestones": screen_milestones,
            "diagnose": screen_diagnose, "learn": screen_learn,
            "mission": screen_mission, "me": screen_me,
        }.get(key, lambda _s: None)(s)

        if key == "practise":
            choose_experience(s, ExperienceType.EXERCISE, "No exercises available.")
        elif key == "apply":
            choose_experience(s, ExperienceType.APPLY,
                              "Nothing unlocked yet — practise the components first.")


def main() -> int:
    print(f"\n{RULE}\n  Cognith\n{RULE}")
    graph = CapabilityGraph.load()
    existing = get_storage().list_students()

    if existing:
        print("\n  Who are you?\n")
        for n, sid in enumerate(existing, 1):
            print(f"    {n}. {sid}")
        print(f"    n. someone new\n")
        raw = ask("  > ")
        if raw.isdigit() and 1 <= int(raw) <= len(existing):
            student_id = existing[int(raw) - 1]
        else:
            student_id = ask("\n  Choose an id for yourself: ") or "student-001"
            if not onboard(graph, student_id):
                return 0
    else:
        student_id = ask("\n  Choose an id for yourself: ") or "student-001"
        if not onboard(graph, student_id):
            return 0

    try:
        session = Session(student_id)
    except FileNotFoundError:
        if not onboard(graph, student_id):
            return 0
        session = Session(student_id)

    run(session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
