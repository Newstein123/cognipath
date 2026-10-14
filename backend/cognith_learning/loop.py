"""The adaptive loop — Claude.md §15, §21 Phase 10, §27.

    Goal -> Onboarding -> Initial map -> Diagnostic -> Evidence -> Capability profile
         -> Gap -> Knowledge -> Practice -> Mission -> Evidence -> Updated profile
         -> Next experience

Every arrow above was built in Phases 1-9. The last one was not: nothing decided what a
learner should do next, so a person had to choose the command. This module is that
decision, and it is deliberately NOT new machinery — it is a policy over signals the
earlier phases each surfaced and then refused to act on:

    profile.unverified()            Phase 2
    profile.calibration_gaps()      Phase 2
    profile.blocked()               Phase 2
    GapResolver.gaps()              Phase 7
    ExperienceLibrary.for_capability() Phase 8
    DiagnosticEngine.score()        Phase 5

TWO RULES SHAPE EVERYTHING HERE
-------------------------------
1. Never recommend what cannot be delivered. Five capabilities have no corpus material and
   no experience; recommending one is a dead end that makes the system look broken. They
   are reported as a CONTENT BACKLOG instead, which is a fact about the product, not about
   the learner.

2. Every step must be actionable now. A plan is a short ordered list of things the learner
   can start immediately, not a roadmap with dependencies between its own items.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from cognith_capability.graph import CapabilityGraph
from cognith_capability.milestone import MilestoneMap
from cognith_capability.models import Capability
from cognith_student.diagnostic import DiagnosticEngine
from cognith_student.models import DEMONSTRATED_AT, MasteryStatus
from cognith_student.onboarding import OnboardingEngine
from cognith_student.profile import CapabilityProfile
from cognith_student.progress import (
    MilestoneProgress,
    RequirementState,
    active,
    path_for,
)

from .experience import ExperienceLibrary, ExperienceType, LearningExperience
from .knowledge import Gap, GapResolver

#: Every claim at or below this means "I'm new to all of it". There is nothing to
#: verify, so the loop teaches from the foundations instead of diagnosing — testing
#: someone on material they have told us they have never learned measures nothing.
NEW_TO_IT_AT = 0.15


class StepKind(str, Enum):
    ONBOARD = "onboard"
    DIAGNOSE = "diagnose"
    LEARN = "learn"
    PRACTISE = "practise"
    APPLY = "apply"
    MISSION = "mission"
    NOTHING = "nothing"


@dataclass(frozen=True)
class NextStep:
    """One thing to do next, why, and the command that does it.

    `why` is written for the learner. §14 asks the system to explain why a capability
    changed; the same obligation applies to why it is asking for something — a
    recommendation the learner cannot interrogate is indistinguishable from a guess.
    """

    kind: StepKind
    title: str
    why: str
    command: str
    capability_id: str | None = None
    experience_id: str | None = None
    minutes: int = 0


@dataclass
class LoopState:
    """Where the learner stands, and what to do about it."""

    stage: str
    summary: dict[str, Any]
    #: The learner's whole path for their goal, and the milestone they are on.
    path: list[MilestoneProgress] = field(default_factory=list)
    milestone: MilestoneProgress | None = None
    steps: list[NextStep] = field(default_factory=list)
    #: Capabilities that would be worth working on but cannot be delivered. A fact about
    #: the product's content, surfaced rather than hidden.
    backlog: list[tuple[Capability, str]] = field(default_factory=list)


class AdaptiveLoop:
    def __init__(self, graph: CapabilityGraph, profile: CapabilityProfile):
        self.graph = graph
        self.profile = profile
        self.resolver = GapResolver(graph, profile)
        self.library = ExperienceLibrary.load(graph)
        self.path: list[MilestoneProgress] = []
        self.milestone: MilestoneProgress | None = None
        self._load_path()

    def _load_path(self) -> None:
        """The learner's milestone path, if their goal maps to one.

        Missing milestone data is not fatal — the loop worked before milestones existed
        and still does, just without a destination to steer toward.
        """
        if not self.profile.student.goal:
            return
        try:
            goals = OnboardingEngine.load(self.graph).goals
            key = next((k for k, spec in goals.items()
                        if spec["name"] == self.profile.student.goal), None)
            if key is None:
                return
            self.path = path_for(self.profile, MilestoneMap.load(self.graph), key)
            self.milestone = active(self.path)
        except (FileNotFoundError, KeyError):
            self.path, self.milestone = [], None

    def stalled(self) -> set[str]:
        """Experiences retried with no improvement.

        Offering one of these a third time is unlikely to help — the learner has already
        seen the feedback twice and not moved. Something else should come first.
        """
        from cognith_student.history import load_history

        return {e.experience_id
                for e in load_history(self.profile.student.id, self.library).stalled()}

    def completed(self) -> set[str]:
        """Experience ids this learner has already produced evidence for.

        Read from the Phase 6 evidence log. Used to stop offering a rung they have
        already climbed — the ladder should advance, not loop.
        """
        from cognith_student.storage import get_storage

        return {e["evidence"]["experienceId"]
                for e in get_storage().load_evidence(self.profile.student.id)}

    def _in_milestone(self, capability_id: str) -> bool:
        """Is this capability part of what the learner is currently working toward?

        With no milestone everything counts, which is how the loop behaved before
        Phase 11 — a learner without a destination gets undirected help rather than none.
        """
        if self.milestone is None:
            return True
        return capability_id in self.milestone.milestone.capability_ids

    def mission_prerequisites(self, mission: LearningExperience) -> list[Capability]:
        """What a mission assumes, DERIVED from the capability graph.

        A learner should not be pointed at the flagship mission until the capabilities it
        rests on are demonstrated rather than claimed — §16: an advanced student starts
        later in the progression, a beginner earlier, same engine.

        Derived rather than listed, because Phase 1 already stores this. Hardcoding
        ("databases", "http") would have produced the same answer today and silently
        drifted the moment an edge changed.
        """
        needed: dict[str, Capability] = {}
        for cid in mission.capability_ids:
            for prereq in self.graph.prerequisites_of(cid):
                if prereq.id not in mission.capability_ids:
                    needed[prereq.id] = prereq
        return sorted(needed.values(), key=lambda c: c.id)

    # --- deliverability -------------------------------------------------------------
    def _can_teach(self, capability_id: str) -> bool:
        return bool(self.graph.get(capability_id).knowledge_docs)

    def _can_practise(self, capability_id: str) -> list[LearningExperience]:
        return [
            e for e in self.library.for_capability(capability_id)
            if e.type is ExperienceType.EXERCISE
        ]

    def _can_diagnose(self, capability_id: str) -> list[LearningExperience]:
        return [
            e for e in self.library.for_capability(capability_id)
            if e.type is ExperienceType.DIAGNOSTIC
        ]

    # --- the policy -------------------------------------------------------------------
    def recommend(self, limit: int = 3) -> LoopState:
        rows = self.profile.all_rows()
        assessed = [r for r in rows if r.mastery is not None]
        claimed = [r for r in rows if r.is_unverified]
        demonstrated = [r for r in rows if r.is_demonstrated]
        gaps = self.resolver.gaps()

        summary = {
            "capabilities": len(rows),
            "demonstrated": len(demonstrated),
            "assessed": len(assessed),
            "claimed_unverified": len(claimed),
            "gaps": len(gaps),
        }

        steps: list[NextStep] = []
        backlog: list[tuple[Capability, str]] = []
        student = self.profile.student.id

        # --- stage 0: no self-report at all -----------------------------------------
        # With a goal, "nothing claimed" means "nothing known yet": teach, don't ask.
        if not assessed and not claimed and self.profile.student.goal:
            return self._start_from_foundations(summary, limit)
        if not assessed and not claimed:
            return LoopState(
                stage="not started",
                summary=summary, path=self.path, milestone=self.milestone,
                steps=[NextStep(
                    kind=StepKind.ONBOARD,
                    title="Tell us what you are working toward",
                    why="We know nothing about you yet. Onboarding produces an initial "
                        "estimate — a starting point to verify, not an assessment.",
                    command=f"python onboard.py --interactive --save --student-id {student}",
                )],
            )

        # --- stage 0b: claims exist, but every one says "I don't know this yet" --------
        if not assessed and all((r.confidence or 0.0) <= NEW_TO_IT_AT for r in claimed):
            return self._start_from_foundations(summary, limit)

        # --- stage 1: claims exist, nothing has been verified ------------------------
        # §9: "This is an initial estimate based on what you've told us. Let's verify it."
        # Until something is demonstrated there is no gap to teach TO — an unverified
        # claim is an unknown, and the honest response to an unknown is a diagnostic.
        if not assessed:
            stage = "claimed, unverified"
            # Order by what the MILESTONE most needs verified, when there is one. A bold
            # claim outside the current milestone is less informative than a modest claim
            # the milestone depends on.
            if self.milestone is not None:
                order = [self.profile.row_for(r.capability_id)
                         for r in self.milestone.next_to_verify()
                         if r.state is RequirementState.CLAIMED]
                order += [r for r in self.profile.unverified()
                          if not self._in_milestone(r.capability_id)]
            else:
                order = self.profile.unverified()
            for row in order:
                if len(steps) >= limit:
                    break
                cap = self.graph.get(row.capability_id)
                items = self._can_diagnose(cap.id)
                if not items:
                    backlog.append((cap, "no diagnostic scenario written"))
                    continue
                item = items[0]
                unmet_prereqs = self.profile.blocked().get(cap.id, [])
                why = (f"You rated yourself {row.confidence:.0%} here and nothing has "
                       f"checked it.")
                if unmet_prereqs:
                    why += (f" It also rests on "
                            f"{', '.join(p.name for p in unmet_prereqs)}, which is "
                            f"unproven — this will test both.")
                steps.append(NextStep(
                    kind=StepKind.DIAGNOSE, title=f"Verify {cap.name}", why=why,
                    command=f"python diagnose.py --student {student}",
                    capability_id=cap.id, experience_id=item.id, minutes=item.minutes,
                ))
            return LoopState(stage=stage, summary=summary, steps=steps,
                             backlog=backlog, path=self.path,
                             milestone=self.milestone)

        # --- stage 2: evidence exists -------------------------------------------------
        stage = "learning"

        # Decide about the top of the ladder first, so a slot can be reserved for it.
        # Gaps would otherwise fill every slot and a ready learner would never be told
        # the next rung exists.
        #
        # APPLY comes before MISSION: it is the lower rung, and a learner who has not
        # integrated several capabilities without scaffolding is not ready for one that
        # also carries state and a budget.
        done = self.completed()
        ready_apply: LearningExperience | None = None
        for e in self.library.of_type(ExperienceType.APPLY):
            blocked = self.library.apply_blocked_by(e, self.profile)
            if blocked:
                backlog.append((
                    self.graph.get(e.capability_id),
                    f"'{e.title}' locked — no evidence yet in "
                    f"{', '.join(c.name for c in blocked)}",
                ))
            elif e.id not in done and ready_apply is None:
                ready_apply = e

        missions = self.library.of_type(ExperienceType.MISSION)
        ready_mission: LearningExperience | None = None
        for m in missions:
            unproven = [
                c for c in self.mission_prerequisites(m)
                if (self.profile.row_for(c.id).mastery or 0.0) < DEMONSTRATED_AT
            ]
            if unproven:
                # Recorded whether or not there is room in the plan — this explains an
                # absence rather than competing for a slot.
                backlog.append((
                    self.graph.get(m.capability_id),
                    f"mission held back — {', '.join(c.name for c in unproven)} "
                    f"not yet demonstrated",
                ))
            elif ready_mission is None:
                ready_mission = m

        # One reserved slot, taken by the highest rung the learner has actually earned.
        top_rung = ready_apply or ready_mission
        gap_budget = limit - 1 if top_rung is not None else limit

        # 2a. Demonstrated gaps first. This is the part of the loop that actually
        #     teaches, and §5's flow — gap, knowledge, practice — is one recommendation
        #     followed by another, not a single step.
        # Gaps inside the current milestone come first — closing one moves the learner
        # toward their stated destination, and closing one outside it does not.
        ordered_gaps = sorted(gaps, key=lambda g: not self._in_milestone(g.capability_id))
        for gap in ordered_gaps:
            if len(steps) >= gap_budget:
                break
            cap = self.graph.get(gap.capability_id)
            teachable = self._can_teach(cap.id)
            practice = self._can_practise(cap.id)
            if not teachable and not practice:
                backlog.append((cap, "no corpus material and no exercise"))
                continue

            missing = gap.unmet[0].removeprefix("Understands: ") if gap.unmet else None
            detail = f' Still not shown: "{missing}".' if missing else ""
            if gap.persistent:
                # A criterion missed more than once is what a lesson should target. Say
                # so, because "you keep missing this" is more actionable than "you scored
                # 25%" and it is the thing the learner has evidence they cannot self-correct.
                detail = (f' You have missed this more than once: '
                          f'"{gap.persistent[0]}".')

            # Coverage decides the shape: while the unit is open, keep teaching it (a
            # challenge would test material never taught); once every idea is covered,
            # prove it — another lesson is only needed if the evidence shows misses.
            up = self._unit(cap.id) if teachable else None
            unit_open = bool(up and not up.complete)
            unit_done = bool(up and up.complete)
            if teachable and (unit_open or not unit_done or gap.unmet):
                steps.append(NextStep(
                    kind=StepKind.LEARN,
                    title=self._gap_title(cap) if unit_open else f"Review {cap.name}",
                    why=(self._continue_why(cap, up) if unit_open
                         else f"You demonstrated {gap.mastery:.0%} here.{detail}"),
                    command=f"python learn.py --student {student} --gap {cap.id}",
                    capability_id=cap.id,
                ))
            if unit_open:
                continue
            stalled = self.stalled()
            practice = [e for e in practice if e.id not in stalled] or practice
            if practice and len(steps) < gap_budget:
                e = practice[0]
                why = (f"You've covered all {up.total} ideas in {cap.name}. Prove it on a "
                       f"question you haven't seen — that is what makes the skill mastered."
                       if unit_done and not gap.unmet else
                       f"A practice question on {cap.name}: your answer is evidence, and it's "
                       f"what moves the skill toward mastered.")
                steps.append(NextStep(
                    kind=StepKind.PRACTISE, title=e.title, why=why,
                    command=(f"python practice.py --show '{e.id}'"),
                    capability_id=cap.id, experience_id=e.id, minutes=e.minutes,
                ))

        # 2b. The flagship mission, once its foundations are real. §16 — an advanced
        #     learner starts later in the progression.
        if ready_apply is not None:
            a = ready_apply
            names = ", ".join(self.graph.get(c).name for c in a.requires)
            steps.append(NextStep(
                kind=StepKind.APPLY, title=a.title,
                why=(f"You have evidence in {names}. This combines them, and nothing in "
                     f"the question tells you which one matters — working that out is the "
                     f"part practice cannot test."),
                command=f"python practice.py --show '{a.id}'",
                capability_id=a.capability_id, experience_id=a.id, minutes=a.minutes,
            ))
        elif ready_mission is not None:
            m = ready_mission
            steps.append(NextStep(
                kind=StepKind.MISSION, title=m.title,
                why=("Your foundations are demonstrated, not just claimed. This puts "
                     "them under real constraints where the decisions interact."),
                command=f"python mission.py --student {student} --brief",
                capability_id=m.capability_id, experience_id=m.id, minutes=m.minutes,
            ))

        # 2c. Still room? Verify the boldest remaining claim.
        if len(steps) < limit:
            for row in self.profile.unverified():
                if len(steps) >= limit:
                    break
                cap = self.graph.get(row.capability_id)
                if any(s.capability_id == cap.id for s in steps):
                    continue
                items = self._can_diagnose(cap.id)
                if not items:
                    if not any(c.id == cap.id for c, _ in backlog):
                        backlog.append((cap, "no diagnostic scenario written"))
                    continue
                steps.append(NextStep(
                    kind=StepKind.DIAGNOSE, title=f"Verify {cap.name}",
                    why=(f"Still taken on trust — you rated yourself "
                         f"{row.confidence:.0%} and nothing has checked it."),
                    command=f"python diagnose.py --student {student}",
                    capability_id=cap.id, experience_id=items[0].id,
                    minutes=items[0].minutes,
                ))

        # 2c'. Units started but not fully covered: continue them. A skill is not done
        # until every concept in its material has been taught (cognith_learning/units.py),
        # even if an answer was strong.
        if len(steps) < limit:
            for cap in self.graph.capabilities.values():
                if len(steps) >= limit:
                    break
                if any(st.capability_id == cap.id for st in steps) or not self._can_teach(cap.id):
                    continue
                up = self._unit(cap.id)
                if up and up.done and not up.complete:
                    n = up.next_part()
                    steps.append(NextStep(
                        kind=StepKind.LEARN,
                        title=f"Continue {cap.name} — Part {n + 1} of {len(up.plan.parts)}",
                        why=self._continue_why(cap, up),
                        command=f"python learn.py --student {student} --gap {cap.id}",
                        capability_id=cap.id,
                    ))

        # 2d. Still room? The next topic the learner has not started. Without this, a
        # learner who claimed nothing at onboarding and then mastered one topic was told
        # "nothing outstanding" with most of their path untouched. Prerequisite order;
        # topics whose prerequisites are already demonstrated come first.
        if len(steps) < limit:
            for cap in self._untouched_in_order():
                if len(steps) >= limit:
                    break
                prereqs = self.graph.prerequisites_of(cap.id)
                done = [p for p in prereqs
                        if (self.profile.row_for(p.id).mastery or 0.0) >= DEMONSTRATED_AT]
                win = self._recent_win(prereqs)
                if win:
                    why = (f"You showed \"{win[1]}\" in {win[0]}. {cap.name} builds on that: "
                           f"next you'll learn to {self._purpose(cap)}.")
                elif done:
                    why = (f"You've mastered {', '.join(p.name for p in done)}, and "
                           f"{cap.name} builds on it — it's next on your path.")
                elif prereqs:
                    why = (f"Comes after {', '.join(p.name for p in prereqs)} — it builds on "
                           f"that, so you'll learn to {self._purpose(cap)}.")
                else:
                    why = f"Not started yet — {cap.name} is a foundation later topics build on."
                steps.append(NextStep(
                    kind=StepKind.LEARN, title=self._learn_title(cap), why=why,
                    command=f"python learn.py --student {student} --gap {cap.id}",
                    capability_id=cap.id,
                ))

        if not steps:
            stage = "nothing outstanding"
            steps.append(NextStep(
                kind=StepKind.NOTHING,
                title="Nothing outstanding",
                why=("Every capability the corpus can reach is either demonstrated or "
                     "has no material behind it. What is left is a content problem, not "
                     "a learning one — see the backlog."),
                command="python practice.py --coverage",
            ))
        return LoopState(stage=stage, summary=summary, steps=steps[:limit],
                         backlog=backlog, path=self.path,
                         milestone=self.milestone)

    def _start_from_foundations(self, summary: dict[str, Any], limit: int) -> LoopState:
        """Lessons in prerequisite order: what nothing else rests on comes first.

        Restricted to capabilities with course material — a lesson is the only thing that
        makes sense for someone starting out, and it needs something to teach from. Within
        a prerequisite depth, the graph's own order (its authored order) breaks ties.
        """
        order = list(self.graph.capabilities)
        teachable = [c for c in self.graph.capabilities.values()
                     if self._can_teach(c.id) and self._in_milestone(c.id)]
        teachable.sort(key=lambda c: (len(self.graph.prerequisite_closure(c.id)),
                                      order.index(c.id)))
        steps = []
        for cap in teachable[:limit]:
            prereqs = self.graph.prerequisites_of(cap.id)
            why = ("You said you're new to this, so there's nothing to test yet — we start "
                   "by teaching. ")
            why += (f"{cap.name} builds on {', '.join(p.name for p in prereqs)}, so it "
                    f"comes after those." if prereqs else
                    f"{cap.name} is a foundation: later topics build on it.")
            steps.append(NextStep(
                kind=StepKind.LEARN, title=self._learn_title(cap), why=why,
                command=f"python learn.py --student {self.profile.student.id} --gap {cap.id}",
                capability_id=cap.id,
            ))
        return LoopState(stage="starting from scratch", summary=summary, steps=steps,
                         path=self.path, milestone=self.milestone)

    def _unit(self, capability_id: str):
        try:
            from .units import progress

            return progress(self.profile.student.id, capability_id)
        except Exception:  # noqa: BLE001 — no index / no material: no unit plan
            return None

    def _recent_win(self, among: list[Capability] | None = None) -> tuple[str, str] | None:
        """(capability name, what was shown) from the learner's most recent met evidence —
        optionally only on `among`. Lets a reason say what the learner just demonstrated."""
        from cognith_student.storage import get_storage

        wanted = {c.id for c in among} if among is not None else None
        criteria = {c.id: c for e in self.library.experiences.values() for c in e.rubric}
        for entry in reversed(get_storage().load_evidence(self.profile.student.id)):
            for r in entry["evidence"].get("results", []):
                c = criteria.get(r["criterionId"])
                if r["verdict"] != "met" or c is None:
                    continue
                if wanted is not None and c.capability_id not in wanted:
                    continue
                text = c.criterion.removeprefix("Understands: ").rstrip(".")
                if len(text) > 90:
                    text = text[:87].rstrip() + "…"
                return self.graph.get(c.capability_id).name, text
        return None

    def _purpose(self, cap: Capability) -> str:
        s = cap.statement.strip().rstrip(".")
        s = s[4:] if s.lower().startswith("can ") else s
        return s[0].lower() + s[1:]

    def _continue_why(self, cap: Capability, up) -> str:
        n = up.next_part()
        upcoming = [c.title for c in up.plan.parts[n] if c.id not in up.covered]
        win = self._recent_win([cap])
        lead = f"You showed \"{win[1]}\". " if win else ""
        return (f"{lead}You've covered {up.done} of {up.total} ideas in this unit. "
                f"Next up in Part {n + 1}: {', '.join(upcoming)}.")

    def _gap_title(self, cap: Capability) -> str:
        up = self._unit(cap.id)
        if up and not up.complete:
            n = up.next_part()
            return f"Continue {cap.name} — Part {n + 1} of {len(up.plan.parts)}"
        return f"Read up on {cap.name}"

    def _unit_note(self, capability_id: str) -> str:
        up = self._unit(capability_id)
        if up and not up.complete:
            n = up.next_part()
            upcoming = [c.title for c in up.plan.parts[n] if c.id not in up.covered]
            return (f" You've covered {up.done} of {up.total} ideas in this unit; "
                    f"next up: {', '.join(upcoming)}.")
        return ""

    def _learn_title(self, cap: Capability) -> str:
        up = self._unit(cap.id)
        if up and len(up.plan.parts) > 1:
            return f"Learn {cap.name} — Part 1 of {len(up.plan.parts)}"
        return f"Learn {cap.name}"

    def _untouched_in_order(self) -> list[Capability]:
        """Teachable, in the current milestone, never rated and never assessed — ready
        ones (all prerequisites demonstrated, or none) first, then by depth."""
        order = list(self.graph.capabilities)

        def ready(cid: str) -> bool:
            return all((self.profile.row_for(p.id).mastery or 0.0) >= DEMONSTRATED_AT
                       for p in self.graph.prerequisites_of(cid))

        caps = [c for c in self.graph.capabilities.values()
                if self._can_teach(c.id) and self._in_milestone(c.id)
                and self.profile.row_for(c.id).status is MasteryStatus.UNKNOWN]
        return sorted(caps, key=lambda c: (not ready(c.id),
                                           len(self.graph.prerequisite_closure(c.id)),
                                           order.index(c.id)))

    # --- narrative --------------------------------------------------------------------
    def position(self) -> str:
        """One sentence on where the learner is in §27's loop."""
        rows = self.profile.all_rows()
        assessed = sum(1 for r in rows if r.mastery is not None)
        claimed = sum(1 for r in rows if r.is_unverified)
        demonstrated = sum(1 for r in rows if r.is_demonstrated)
        if not assessed and not claimed:
            return "Nothing known yet."
        if not assessed:
            return (f"{claimed} capabilities claimed, none verified — "
                    f"entirely self-reported so far.")
        base = (f"{demonstrated} of {len(rows)} demonstrated, {assessed} assessed, "
                f"{claimed} still taken on trust.")
        if self.milestone is not None:
            base += f"\n  {self.milestone.summary()}"
        elif self.path:
            # Every milestone on the path is complete. Saying so matters — the loop will
            # still find gaps in capabilities outside the path, and without this they
            # would read as unfinished business rather than as optional further work.
            done = ", ".join(p.milestone.name for p in self.path)
            base += (f"\n  Goal reached — {done} complete. "
                     f"Anything below is optional depth, not a requirement.")
        return base
