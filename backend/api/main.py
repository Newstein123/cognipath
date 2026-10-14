"""Cognith HTTP API — the engine behind a web contract.

    uvicorn api.main:app --reload

LIKE app.py, THIS ADDS NO LEARNING LOGIC. Every endpoint calls an engine that already
exists and translates its result into api/schemas.py. If a route looks like it is
deciding something about a learner, the decision belongs in the engine.

Endpoints that call Gemini (attempts, lessons, tutor) are plain `def`, so FastAPI runs
them in its threadpool rather than blocking the event loop.
"""

from __future__ import annotations

import os
import re
import uuid
from functools import lru_cache

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import cognith_course as courses
from cognith_capability.graph import CapabilityGraph
from cognith_learning.experience import ExperienceLibrary, LearningExperience
from cognith_learning.generator import ChallengeGenerator, GenerationError, to_record
from cognith_learning.learner_context import learner_context
from cognith_learning.knowledge import Gap, GapResolver
from cognith_learning.loop import AdaptiveLoop, LoopState
from cognith_rag.config import GENERATION_MODEL, TOP_K
from cognith_rag.generate import Result, answer
from cognith_rag.store import Hit, Store
from cognith_student.diagnostic import DiagnosticEngine
from cognith_student.evidence import Evaluator, GeminiEvaluator, assess, save_evidence
from cognith_student.models import DEMONSTRATED_AT, MasteryStatus, StudentCapability
from cognith_student.onboarding import OnboardingAnswers, OnboardingEngine, OnboardingError
from cognith_student.profile import CapabilityProfile
from cognith_student.progress import active
from cognith_student.storage import get_storage

from . import schemas as s

load_dotenv()

#: Goal matching, examples and labels come from data/onboarding.yaml, so a course pack
#: (e.g. a university module) brings its own without code changes:
#:
#:   goals.<key>.keywords   free-text words that select this goal; first match wins
#:   goals.<key>.supported  false for goals onboarding accepts but content does not cover
#:   ui.examples            example goals shown on the start page
#:   ui.topics_label        label for the technologies/topics picker
#:
#: With no keyword match, the FIRST goal is used — the one the content is built for.

app = FastAPI(title="Cognith API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("COGNITH_CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- shared, read-only engine data — one cache entry per course pack -------------------
# Every request runs with one course active (cognith_course): set from the learner's
# record in load_profile, or from ?course= on routes that have no learner.
@lru_cache
def _graph(course: str) -> CapabilityGraph:
    return CapabilityGraph.load()


@lru_cache
def _library(course: str) -> ExperienceLibrary:
    return ExperienceLibrary.load(_graph(course))


@lru_cache
def _onboarding(course: str) -> OnboardingEngine:
    return OnboardingEngine.load(_graph(course))


@lru_cache
def _store(course: str) -> Store:
    return Store.load()


def graph() -> CapabilityGraph:
    return _graph(courses.current())


def library() -> ExperienceLibrary:
    return _library(courses.current())


library.cache_clear = _library.cache_clear  # generated challenges join the library


def onboarding() -> OnboardingEngine:
    return _onboarding(courses.current())


def store() -> Store:
    return _store(courses.current())


def use_course(course_id: str | None) -> str:
    """Activate a course for this request (404 if there is no such pack)."""
    try:
        courses.set_course(course_id or courses.all_courses()[0]["id"])
    except courses.UnknownCourse:
        raise HTTPException(404, f"No course {course_id!r}") from None
    return courses.current()


def evaluator() -> Evaluator:
    """Overridden in tests with a ManualEvaluator, so they need no API key."""
    return GeminiEvaluator()


def load_profile(learner_id: str) -> CapabilityProfile:
    """The learner's profile — and, first, their course becomes the active one."""
    record = get_storage().load_profile(learner_id)
    if record is None:
        raise HTTPException(404, f"No learner {learner_id!r}")
    use_course(record["student"].get("course") or courses.LEGACY_COURSE)
    try:
        return CapabilityProfile.load(learner_id, graph())
    except FileNotFoundError:
        raise HTTPException(404, f"No learner {learner_id!r}") from None


def get_activity(activity_id: str) -> LearningExperience:
    try:
        return library().get(activity_id)
    except KeyError:
        pass
    # Generated after the cached library was built, possibly by another instance.
    library.cache_clear()
    try:
        return library().get(activity_id)
    except KeyError:
        raise HTTPException(404, f"No activity {activity_id!r}") from None


# --- translation: engine -> contract ----------------------------------------------------
def state_of(status: MasteryStatus) -> s.SkillState:
    if status is MasteryStatus.DEMONSTRATED:
        return s.SkillState.MASTERED
    if status is MasteryStatus.DEVELOPING:
        return s.SkillState.DEVELOPING
    return s.SkillState.UNKNOWN


def state_of_mastery(mastery: float | None) -> s.SkillState:
    if mastery is None:
        return s.SkillState.UNKNOWN
    return s.SkillState.MASTERED if mastery >= DEMONSTRATED_AT else s.SkillState.DEVELOPING


def counts(profile: CapabilityProfile) -> s.SkillCounts:
    states = [state_of(r.status) for r in profile.all_rows()]
    return s.SkillCounts(
        mastered=states.count(s.SkillState.MASTERED),
        developing=states.count(s.SkillState.DEVELOPING),
        unknown=states.count(s.SkillState.UNKNOWN),
        total=len(states),
    )


def course_model(course_id: str | None = None) -> s.Course:
    c = courses.info(course_id or courses.current())
    return s.Course(id=c["id"], name=c.get("name", c["id"]), subject=c.get("subject", ""),
                    description=c.get("description", ""), inline_math=bool(c.get("inline_math")))


def summary(profile: CapabilityProfile) -> s.LearnerSummary:
    st = profile.student
    return s.LearnerSummary(id=st.id, name=st.name, goal=st.goal, counts=counts(profile),
                            course=course_model())


def explain_skill(row: StudentCapability, gap: Gap | None) -> str:
    n = row.evidence_count
    pieces = f"{n} piece{'s' if n != 1 else ''} of evidence"
    if row.status is MasteryStatus.DEMONSTRATED:
        text = f"Demonstrated at {row.mastery:.0%} across {pieces}."
        if gap and gap.unmet:
            text += f' One thing still missed: "{gap.unmet[0]}".'
        return text
    if row.status is MasteryStatus.DEVELOPING:
        text = f"Demonstrated {row.mastery:.0%} so far, from {pieces}."
        if gap and gap.unmet:
            text += f' Still to develop: "{gap.unmet[0]}".'
        return text
    if row.status is MasteryStatus.CLAIMED:
        return (f"You rated yourself {row.confidence:.0%}. Not verified yet — "
                f"that is a starting estimate, not a result.")
    return "Nothing known yet. Not a weakness — just unexplored."


def skill_profile(profile: CapabilityProfile, loop: AdaptiveLoop | None = None) -> s.SkillProfile:
    from cognith_learning import units

    loop = loop or AdaptiveLoop(graph(), profile)
    gaps = {g.capability_id: g for g in loop.resolver.gaps()}
    skills = []
    for row in profile.all_rows():
        cap = graph().get(row.capability_id)
        state, why = state_of(row.status), explain_skill(row, gaps.get(cap.id))
        up = units.progress(profile.student.id, cap.id) if cap.knowledge_docs else None
        if up and up.done:
            why += f" Covered {up.done} of {up.total} ideas in this unit."
            # Mastery means the whole unit, not a strong answer on part of it.
            if state is s.SkillState.MASTERED and not up.complete:
                state = s.SkillState.DEVELOPING
                why += " Finish the unit to master it."
        skills.append(s.Skill(
            capability_id=cap.id, name=cap.name, area=cap.area, statement=cap.statement,
            state=state, mastery=row.mastery, self_rated=row.confidence,
            evidence_count=row.evidence_count,
            last_assessed_at=row.last_assessed_at.isoformat() if row.last_assessed_at else None,
            explanation=why,
        ))
    return s.SkillProfile(learner=summary(profile), position=loop.position(), skills=skills)


def next_activities(state: LoopState) -> s.NextActivities:
    steps = []
    for st in state.steps:
        cap = graph().get(st.capability_id) if st.capability_id else None
        steps.append(s.Step(
            kind=s.StepKind(st.kind.value), title=st.title, reason=st.why,
            capability_id=st.capability_id, capability_name=cap.name if cap else None,
            activity_id=st.experience_id, minutes=st.minutes,
        ))
    held = [s.HeldBack(capability_id=c.id, name=c.name, reason=why) for c, why in state.backlog]
    return s.NextActivities(stage=state.stage, steps=steps, held_back=held)


def activity(e: LearningExperience) -> s.Activity:
    return s.Activity(
        id=e.id, type=e.type.value, title=e.title, capability_id=e.capability_id,
        capability_ids=list(e.capability_ids), level=e.level.value, minutes=e.minutes,
        prompt=e.prompt,
        criteria=[s.Criterion(id=c.id, criterion=c.criterion, capability_id=c.capability_id)
                  for c in e.rubric],
        source=e.source,
    )


def sources(hits: list[Hit], cited: list[str]) -> list[s.Source]:
    return [
        s.Source(chunk_id=h.chunk.id, citation=h.chunk.citation, excerpt=h.chunk.text,
                 score=round(h.score, 4), reference=h.chunk.metadata.get("source"),
                 cited=h.chunk.id in cited)
        for h in hits
    ]


def criterion_text() -> dict[str, tuple[str, str]]:
    library.cache_clear()  # include generated challenges' criteria
    return {c.id: (c.criterion, c.capability_id)
            for e in library().experiences.values() for c in e.rubric}


def estimate_reason(signal) -> str:
    """Onboarding's provenance in learner language. Derived sources read
    "Caching --supports--> Scalability" or "Caching <--prerequisite_for-- HTTP";
    either way the first name is the capability the estimate came from."""
    if signal.kind == "technology":
        return f"You've used {signal.source}"
    if signal.kind == "phrase":
        return f"You mentioned {signal.source}"
    origin = re.split(r" <?--", signal.source, maxsplit=1)[0]
    return f"Inferred from your {origin} experience"


def match_goal(text: str) -> str:
    goals = onboarding().goals
    lowered = f" {text.lower()} "
    for key, spec in goals.items():
        if any(w.lower() in lowered for w in spec.get("keywords", [])):
            return key
    return next(iter(goals))


def course_for_goal(text: str) -> str:
    """The course whose goal keywords the text mentions; else the default course."""
    lowered = f" {text.lower()} "
    for c in courses.all_courses():
        with courses.using(c["id"]):
            goals = _onboarding(c["id"]).goals
        if any(w.lower() in lowered for g in goals.values() for w in g.get("keywords", [])):
            return c["id"]
    return courses.all_courses()[0]["id"]


def onboarding_ui() -> dict:
    import yaml

    from cognith_course import path as course_path

    return yaml.safe_load(course_path("onboarding.yaml").read_text(encoding="utf-8")).get("ui", {}) or {}


def new_learner_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24] or "learner"
    return f"{slug}-{uuid.uuid4().hex[:6]}"


# --- routes ----------------------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    return {"ok": True, "storage": os.environ.get("COGNITH_STORAGE", "file"),
            "model": GENERATION_MODEL}


@app.get("/api/courses", response_model=list[s.Course])
def list_courses():
    return [course_model(c["id"]) for c in courses.all_courses()]


@app.get("/api/onboarding/options", response_model=s.OnboardingOptions)
def onboarding_options(course: str | None = None):
    use_course(course)
    eng = onboarding()
    return s.OnboardingOptions(
        course=course_model(),
        goals=[s.Option(id=k, label=v["name"]) for k, v in eng.goals.items()],
        levels=[s.Option(id=k, label=v["label"]) for k, v in eng.levels.items()],
        technologies=sorted(eng.technologies),
        examples=onboarding_ui().get("examples", []),
        topics_label=onboarding_ui().get("topics_label", "Technologies you have used"),
    )


@app.post("/api/learners", response_model=s.LearnerCreated, status_code=201)
def create_learner(req: s.OnboardingRequest):
    use_course(req.course or course_for_goal(req.goal))
    eng = onboarding()
    goal_key = match_goal(req.goal)
    answers = OnboardingAnswers(
        student_name=req.name.strip(), goal=goal_key,
        technologies=tuple(t.strip() for t in req.technologies if t.strip()),
        knows=req.knows, built=req.built, self_rated_level=req.level,
    )
    try:
        profile, result = eng.build_profile(answers, student_id=new_learner_id(req.name))
    except OnboardingError as exc:
        raise HTTPException(400, str(exc)) from None
    profile.save()
    return s.LearnerCreated(
        learner=summary(profile),
        goal=s.GoalMatch(text=req.goal, goal_id=goal_key,
                         goal_name=eng.goals[goal_key]["name"],
                         supported=eng.goals[goal_key].get("supported", True)),
        initial_estimates=[
            s.InitialEstimate(capability_id=e.capability_id,
                              name=graph().get(e.capability_id).name,
                              self_rated=e.confidence,
                              reason=estimate_reason(e.chosen))
            for e in result.estimates
        ],
        unrecognised_technologies=result.unrecognised_technologies,
        profile=skill_profile(profile),
    )


@app.get("/api/learners", response_model=list[s.LearnerSummary])
def list_learners(course: str | None = None):
    """Every learner (each loaded in their own course), or only one course's."""
    out = []
    for i in get_storage().list_students():
        out.append(summary(load_profile(i)))
    return [l for l in out if course is None or l.course.id == course]


@app.get("/api/learners/{learner_id}/profile", response_model=s.SkillProfile)
def get_profile(learner_id: str):
    return skill_profile(load_profile(learner_id))


@app.get("/api/learners/{learner_id}/next", response_model=s.NextActivities)
def get_next(learner_id: str, limit: int = 3):
    profile = load_profile(learner_id)  # sets the learner's course first
    loop = AdaptiveLoop(graph(), profile)
    # The loop reserves its LAST slot for the top rung, so with limit=1 that rung would
    # displace the gap step. Plan at least three, then trim, so steps[0] never depends
    # on how many the client asked for.
    plan = next_activities(loop.recommend(limit=max(3, min(limit, 10))))
    plan.steps = plan.steps[:max(1, limit)]
    return plan


@app.get("/api/learners/{learner_id}/diagnostic", response_model=s.Diagnostic)
def get_diagnostic(learner_id: str):
    profile = load_profile(learner_id)
    loop = AdaptiveLoop(graph(), profile)
    current = active(loop.path)
    diag = DiagnosticEngine.load(graph()).build(
        profile, relevance=current.relevance() if current else None)
    return s.Diagnostic(
        targets=[s.DiagnosticTarget(capability_id=c.capability_id,
                                    name=graph().get(c.capability_id).name,
                                    notes=list(c.notes))
                 for c in diag.selected],
        activities=[activity(library().get(i.id)) for i in diag.items],
        minutes=diag.minutes,
    )


@app.get("/api/activities/{activity_id}", response_model=s.Activity)
def get_activity_route(activity_id: str, learner: str | None = None, course: str | None = None):
    """Activities belong to a course: pass the learner (preferred) or the course."""
    if learner:
        load_profile(learner)
    else:
        use_course(course or courses.LEGACY_COURSE)
    return activity(get_activity(activity_id))


@app.post("/api/learners/{learner_id}/attempts", response_model=s.AttemptResult)
def submit_attempt(learner_id: str, req: s.AttemptRequest,
                   judge: Evaluator = Depends(evaluator)):
    profile = load_profile(learner_id)
    item = get_activity(req.activity_id)
    if not item.assessable:
        raise HTTPException(400, f"{item.id!r} has no rubric, so it cannot be assessed")
    cap_for_help = {0: None, 1: 0.85, 2: 0.75}.get(req.help_used, 0.65)
    try:
        result = assess(profile, item, req.response, judge, max_observed=cap_for_help)
    except Exception as exc:  # noqa: BLE001
        # Nothing is saved: a failed judgement must not look like a weak answer.
        raise HTTPException(502, f"Assessment failed, profile unchanged: "
                                 f"{type(exc).__name__}: {exc}") from None
    if req.help_used:
        n = req.help_used
        result.explanation = (f"You used guided help {n} time{'s' if n != 1 else ''}, so this "
                              "counts as assisted — try a new challenge without help to prove "
                              "it independently.\n\n" + result.explanation)
    profile.save()
    save_evidence(result)
    return attempt_result(profile, item, result)


def attempt_result(profile: CapabilityProfile, item: LearningExperience, result) -> s.AttemptResult:
    texts = {c.id: c.criterion for c in item.rubric}
    caps = {c.id: c.capability_id for c in item.rubric}
    loop = AdaptiveLoop(graph(), profile)
    teachable = [o for o in result.outcomes
                 if (o.unmet or o.partial) and graph().get(o.capability_id).knowledge_docs]
    weakest = min(teachable, key=lambda o: o.score, default=None)
    return s.AttemptResult(
        attempt=result.evidence.attempt,
        criteria=[s.CriterionResult(id=r.criterion_id, criterion=texts[r.criterion_id],
                                    capability_id=caps[r.criterion_id],
                                    verdict=s.Verdict(r.verdict.value),
                                    justification=r.justification)
                  for r in result.evidence.results],
        changes=[s.SkillChange(capability_id=o.capability_id,
                               name=graph().get(o.capability_id).name,
                               score=round(o.score, 4), mastery_before=o.mastery_before,
                               mastery_after=o.mastery_after,
                               state_before=state_of_mastery(o.mastery_before),
                               state_after=state_of_mastery(o.mastery_after))
                 for o in result.outcomes],
        explanation=result.explanation,
        teach=s.TeachHint(capability_id=weakest.capability_id,
                          name=graph().get(weakest.capability_id).name,
                          missed=[texts[c] for c in (*weakest.unmet, *weakest.partial)])
        if weakest else None,
        profile=skill_profile(profile, loop),
        next=next_activities(loop.recommend()),
    )


def missed_points(learner_id: str, cap_id: str, activity_id: str | None, gap: Gap) -> list[str]:
    """What to teach when the learner has evidence: the criteria their answer to
    `activity_id` did not fully meet, or else the gap's unmet criteria. Empty means no
    evidence yet — teach the whole topic."""
    if activity_id:
        texts = criterion_text()
        for entry in reversed(get_storage().load_evidence(learner_id)):
            ev = entry["evidence"]
            if ev["experienceId"] != activity_id:
                continue
            pts = [texts[r["criterionId"]][0] for r in ev.get("results", [])
                   if r["verdict"] != "met" and r["criterionId"] in texts
                   and texts[r["criterionId"]][1] == cap_id]
            if pts:
                return pts[:3]
            break
    return list(gap.unmet[:3]) if gap.mastery is not None else []


def focused_hits(cap, points: list[str]):
    """Course sections about the missed points themselves, not the whole topic."""
    from cognith_rag.embeddings import embed_query

    return store().search(embed_query(" ".join(points)), k=TOP_K,
                          docs=[f"{d}.md" for d in cap.knowledge_docs])


@app.post("/api/learners/{learner_id}/lessons", response_model=s.Lesson)
def create_lesson(learner_id: str, req: s.LessonRequest):
    profile = load_profile(learner_id)
    try:
        cap = graph().get(req.capability_id)
    except KeyError:
        raise HTTPException(404, f"No capability {req.capability_id!r}") from None
    resolver = GapResolver(graph(), profile)
    resolver._store = store()
    row = profile.row_for(cap.id)
    gap = next((g for g in resolver.gaps(include_unverified=True)
                if g.capability_id == cap.id),
               Gap(capability_id=cap.id, mastery=row.mastery, confidence=row.confidence))
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace

    from cognith_learning import microlesson

    from cognith_learning import units
    from cognith_rag.store import Hit

    ctx = learner_context(profile, cap.id)
    up = units.progress(learner_id, cap.id)
    # Coverage first: until every concept in the material has been taught, a lesson is the
    # next part of the unit. Remediation from a specific answer (from_activity_id) still
    # goes straight at what that answer missed.
    part_n: int | None = None
    if up and not req.from_activity_id and (req.part or not up.complete):
        part_n = (req.part - 1) if req.part else up.next_part()
        part_n = max(0, min(part_n if part_n is not None else 0, len(up.plan.parts) - 1))
    part = up.plan.parts[part_n] if part_n is not None else None
    focus = ([] if req.full or part is not None
             else missed_points(learner_id, cap.id, req.from_activity_id, gap))
    if focus:
        gap = replace(gap, unmet=tuple(focus))

    def cards():
        kk = GapResolver(graph(), profile)
        kk._store = store()
        retrieved = kk.knowledge_for(gap, explain=False)
        concepts = None
        if part is not None:
            chunk = {c.id: c for c in store().chunks}
            ids = up.plan.chunk_ids_for(part, first=part_n == 0,
                                        last=part_n == len(up.plan.parts) - 1)
            hits = [Hit(chunk[i], 1.0) for i in ids if i in chunk]
            concepts = [(c.title, c.chunk_ids + c.example_ids) for c in part]
        elif focus and cap.knowledge_docs:
            hits = focused_hits(cap, focus)
        else:
            hits = retrieved.hits
        try:
            return microlesson.generate(cap, retrieved.question, hits, missed=list(gap.unmet),
                                        focus=focus or None, learner=str(ctx),
                                        concepts=concepts), hits
        except Exception:  # noqa: BLE001 — the plain explanation is the fallback
            return None, hits

    # Cards and the full explanation at the same time: one wait, not two.
    import contextvars

    with ThreadPoolExecutor(2) as pool:
        # Worker threads don't inherit context vars — carry the active course across.
        card_job = pool.submit(contextvars.copy_context().run, cards)
        k = resolver.knowledge_for(gap)
        micro, card_hits = card_job.result()
    citation = {h.chunk.id: h.chunk.citation for h in card_hits}
    res: Result | None = k.result
    # Most recent assessable activity where this capability was missed.
    retry = next((e for e in reversed(gap.from_evidence)
                  if e in library().experiences and library().get(e).assessable), None)
    return s.Lesson(
        capability_id=cap.id, name=cap.name, question=k.question,
        answered=k.answered,
        explanation=res.answer if res else
        "There is no learning material for this capability yet.",
        sources=sources(k.hits, res.citations if res else []),
        prerequisites_first=[c.name for c in k.prerequisites_first],
        missed=list(gap.unmet[:3]), targeted=k.targeted,
        retry_activity_id=req.from_activity_id or retry, focused=bool(focus) and micro is not None,
        pitch=ctx.pitch, teach_first=ctx.band in ("new", "struggling"),
        hook=micro.hook if micro else None,
        unit=unit_info(up, part_n),
        sections=[s.LessonSection(
            concept_id=part[n].id if part is not None and n < len(part) else None,
            title=x.title, probe=s.QuizQuestion(**x.probe.model_dump()),
            explanation=x.explanation, example=x.example,
            diagram=s.Diagram(**x.diagram.model_dump()),
            check=s.QuizQuestion(**x.check.model_dump()),
            sources=[citation[e] for e in x.excerpt_ids if e in citation])
            for n, x in enumerate(micro.sections)] if micro else None,
        gate=res.gate if res else "no_corpus",
    )


def unit_info(up, part_n: int | None) -> s.UnitInfo | None:
    if up is None:
        return None
    return s.UnitInfo(
        part=(part_n + 1) if part_n is not None else 0, parts=len(up.plan.parts),
        covered=up.done, total=up.total,
        concepts=[s.UnitConcept(id=c.id, title=c.title, part=up.plan.part_of(c.id) + 1,
                                status=up.covered.get(c.id)) for c in up.plan.concepts])


@app.get("/api/learners/{learner_id}/units/{capability_id}", response_model=s.UnitInfo)
def get_unit(learner_id: str, capability_id: str):
    """Every concept in the capability's material, and which this learner has covered."""
    from cognith_learning import units

    load_profile(learner_id)
    capability_or_404(capability_id)
    up = units.progress(learner_id, capability_id)
    if up is None:
        raise HTTPException(404, "No course material for this capability")
    nxt = up.next_part()
    return unit_info(up, nxt)


def generator() -> ChallengeGenerator:
    """Overridden in tests, so they need no API key.

    Built WITHOUT a graph: FastAPI resolves dependencies before the endpoint body runs,
    i.e. before load_profile has switched to the learner's course. The endpoint attaches
    the right course's graph after loading the profile."""
    return ChallengeGenerator(None)


@app.post("/api/learners/{learner_id}/challenges", response_model=s.Activity, status_code=201)
def create_challenge(learner_id: str, req: s.ChallengeRequest,
                     gen: ChallengeGenerator = Depends(generator)):
    """A NEW challenge for one capability, written from its course material and aimed
    at what the learner missed. Persisted so its evidence stays traceable."""
    profile = load_profile(learner_id)
    if hasattr(gen, "graph"):
        gen.graph = graph()  # the learner's course, now that it is active
    try:
        cap = graph().get(req.capability_id)
    except KeyError:
        raise HTTPException(404, f"No capability {req.capability_id!r}") from None
    if not cap.knowledge_docs:
        raise HTTPException(400, f"No course material for {cap.name} to write a challenge from")
    avoid = get_activity(req.avoid_activity_id).prompt if req.avoid_activity_id else None

    resolver = GapResolver(graph(), profile)
    resolver._store = store()
    row = profile.row_for(cap.id)
    gap = next((g for g in resolver.gaps(include_unverified=True) if g.capability_id == cap.id),
               Gap(capability_id=cap.id, mastery=row.mastery, confidence=row.confidence))
    k = resolver.knowledge_for(gap, explain=False)  # the same excerpts the lesson used
    hits = focused_hits(cap, req.focus) if req.focus else k.hits
    if not req.focus:
        # Draw on the WHOLE unit the learner has covered, not the top-5 search hits: one
        # core section per covered concept, spread evenly, at most 8.
        from cognith_learning import units
        from cognith_rag.store import Hit

        up = units.progress(learner_id, cap.id)
        if up and up.done:
            covered = [c for c in up.plan.concepts if c.id in up.covered]
            step = max(1, len(covered) // 8 + (len(covered) % 8 > 0))
            chunk = {c.id: c for c in store().chunks}
            hits = [Hit(chunk[c.chunk_ids[0]], 1.0) for c in covered[::step][:8]
                    if c.chunk_ids[0] in chunk] or hits
    try:
        experience = gen.generate(cap.id, hits, missed=req.focus or list(gap.unmet),
                                  avoid_prompt=avoid, focused=bool(req.focus),
                                  learner=str(learner_context(profile, cap.id)))
    except GenerationError as exc:
        raise HTTPException(502, str(exc)) from None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Challenge generation failed: {type(exc).__name__}: {exc}") from None
    get_storage().save_activity(to_record(experience, gen.model))
    library.cache_clear()
    return activity(experience)


def capability_or_404(capability_id: str):
    try:
        return graph().get(capability_id)
    except KeyError:
        raise HTTPException(404, f"No capability {capability_id!r}") from None


def retrieve_for(profile: CapabilityProfile, cap, query: str | None = None):
    """Course excerpts for one capability — by its gap, or by a free query."""
    docs = [f"{d}.md" for d in cap.knowledge_docs]
    if query and docs:
        from cognith_rag.embeddings import embed_query

        return store().search(embed_query(query), k=TOP_K, docs=docs)
    resolver = GapResolver(graph(), profile)
    resolver._store = store()
    row = profile.row_for(cap.id)
    return resolver.knowledge_for(
        Gap(capability_id=cap.id, mastery=row.mastery, confidence=row.confidence),
        explain=False).hits


@app.post("/api/learners/{learner_id}/lessons/reexplain", response_model=s.Reexplanation)
def reexplain_concept(learner_id: str, req: s.ReexplainRequest):
    """Wrong answer after teaching → the same idea explained differently, aimed at the
    misconception the chosen answer reveals, plus a new check."""
    from cognith_learning import microlesson

    profile = load_profile(learner_id)
    cap = capability_or_404(req.capability_id)
    hits = retrieve_for(profile, cap, f"{req.concept} {req.question}")
    try:
        r = microlesson.reexplain(cap, req.concept, req.explanation, req.question,
                                  req.chosen, req.correct, hits,
                                  learner=str(learner_context(profile, cap.id)))
    except Exception:  # noqa: BLE001
        r = None
    cite = {h.chunk.id: h.chunk.citation for h in hits}
    if r is None:
        return s.Reexplanation(answered=False, check=None, sources=[],
                               explanation="I couldn't find a different way to explain this "
                                           "in the course material. Try the tutor below.")
    return s.Reexplanation(answered=True, explanation=r.explanation,
                           check=s.QuizQuestion(**r.check.model_dump()),
                           sources=[cite[e] for e in r.excerpt_ids if e in cite])


@app.post("/api/learners/{learner_id}/lessons/followup", response_model=s.FollowUp)
def concept_followup(learner_id: str, req: s.FollowUpRequest):
    """Re-teach the concept the learner is reading: simpler, another example, or common
    mistakes. A teaching move, not a Q&A lookup — the Q&A grounding contract refused
    "explain more simply" because no excerpt contains a simpler version."""
    from cognith_learning import microlesson

    profile = load_profile(learner_id)
    cap = capability_or_404(req.capability_id)
    hits = retrieve_for(profile, cap, f"{req.concept} {req.explanation[:300]}")
    try:
        r = microlesson.followup(cap, req.concept, req.explanation, req.kind, hits,
                                 learner=str(learner_context(profile, cap.id)))
    except Exception:  # noqa: BLE001
        r = None
    if r is None:
        return s.FollowUp(answered=False, sources=[],
                          text="I couldn't find more on this in the course material — try asking "
                               "the tutor a specific question below.")
    cite = {h.chunk.id: h.chunk.citation for h in hits}
    return s.FollowUp(answered=True, text=r.text,
                      sources=[cite[e] for e in r.excerpt_ids if e in cite])


@app.post("/api/learners/{learner_id}/lessons/result", response_model=s.AttemptResult)
def lesson_result(learner_id: str, req: s.LessonResultRequest):
    """Concept-check outcomes as LIGHT evidence: they can move a skill to developing, never
    to mastered (observed score capped at 0.6). Persisted as an activity so the evidence
    stays traceable to what was asked."""
    import uuid

    from cognith_learning.experience import ExperienceType
    from cognith_learning.generator import to_record
    from cognith_student.diagnostic import RubricCriterion
    from cognith_student.evidence import ManualEvaluator

    profile = load_profile(learner_id)
    cap = capability_or_404(req.capability_id)
    eid = f"checks-{cap.id}-{uuid.uuid4().hex[:8]}"
    rubric = tuple(RubricCriterion(id=f"{eid}-c{i}", criterion=f"Understands: {c.title}",
                                   capability_id=cap.id)
                   for i, c in enumerate(req.concepts, 1))
    item = LearningExperience(
        id=eid, type=ExperienceType.GENERATED, title=f"Guided lesson checks — {cap.name}",
        capability_id=cap.id, rubric=rubric, level=cap.level, minutes=5,
        prompt="Concept checks inside a guided lesson: " + "; ".join(c.title for c in req.concepts),
        source="guided lesson (multiple-choice checks)")
    record = to_record(item, "guided-lesson")
    record["concept_ids"] = [c.concept_id for c in req.concepts]  # coverage (units.py)
    get_storage().save_activity(record)
    library.cache_clear()
    judge = ManualEvaluator({r.id: c.verdict.value for r, c in zip(rubric, req.concepts)},
                            justification="guided-lesson check")
    response = "\n".join(f"{c.title}: {c.verdict.value}" + (f" — {c.note}" if c.note else "")
                          for c in req.concepts)
    result = assess(profile, item, response, judge, max_observed=0.6)
    profile.save()
    save_evidence(result)
    return attempt_result(profile, item, result)


@app.post("/api/learners/{learner_id}/help", response_model=s.Help)
def challenge_help(learner_id: str, req: s.HelpRequest):
    """Guided help during a challenge: nudge → key idea → similar example, or a reply to
    the learner's own question. Helps them think; never gives the answer."""
    from cognith_learning.guide import guide

    profile = load_profile(learner_id)
    item = get_activity(req.activity_id)
    cap = capability_or_404(item.capability_id)
    hits = retrieve_for(profile, cap, f"{req.message} {item.prompt[:400]}")
    if not req.level and not req.message.strip():
        raise HTTPException(400, "Give a help level or a message")
    try:
        r = guide(item.prompt, [c.criterion for c in item.rubric], hits, level=req.level,
                  message=req.message, history=[(t.role, t.text) for t in req.history],
                  learner=str(learner_context(profile, cap.id)))
    except Exception:  # noqa: BLE001
        r = None
    if r is None:
        return s.Help(answered=False, sources=[],
                      reply="I can't find material on this in the course notes. Try rereading "
                            "the lesson, or ask in a different way.")
    cite = {h.chunk.id: h.chunk.citation for h in hits}
    return s.Help(answered=True, reply=r.reply,
                  sources=[cite[e] for e in r.excerpt_ids if e in cite])


@app.post("/api/learners/{learner_id}/tutor", response_model=s.TutorAnswer)
def ask_tutor(learner_id: str, req: s.TutorRequest):
    profile = load_profile(learner_id)
    from cognith_rag.embeddings import embed_query

    docs = None
    if req.capability_id:
        try:
            docs = [f"{d}.md" for d in graph().get(req.capability_id).knowledge_docs] or None
        except KeyError:
            raise HTTPException(404, f"No capability {req.capability_id!r}") from None
    hits = store().search(embed_query(req.question), k=TOP_K, docs=docs)
    res = answer(req.question, hits)
    if res.answered or res.gate == "api_error":
        return s.TutorAnswer(question=req.question, answered=res.answered, answer=res.answer,
                             sources=sources(res.hits, res.citations), gate=res.gate,
                             kind="course")

    # Not in the course material: a labelled general explanation if the question belongs
    # to the course's subject, a refusal if it does not (cognith_learning/general.py).
    from cognith_learning.general import course_scope, general_answer

    course = profile.student.goal or "this course"
    try:
        g = general_answer(req.question, course_scope(graph(), course))
    except Exception:  # noqa: BLE001 — keep the grounded abstention
        g = None
    if g is None:
        return s.TutorAnswer(question=req.question, answered=False, answer=res.answer,
                             sources=[], gate=res.gate, kind="course")
    if not g.in_scope:
        topics = ", ".join(c.name for c in list(graph().capabilities.values())[:6])
        return s.TutorAnswer(
            question=req.question, answered=False, sources=[], gate="off_topic", kind="off_topic",
            answer=f"That's outside {course}, so I can't help with it here. I can help with "
                   f"{topics} and the rest of this course.")
    return s.TutorAnswer(question=req.question, answered=True, answer=g.answer, sources=[],
                         gate="general", kind="general")


@app.get("/api/learners/{learner_id}/evidence", response_model=list[s.EvidenceEntry])
def get_evidence(learner_id: str):
    load_profile(learner_id)
    texts = criterion_text()
    out = []
    for entry in get_storage().load_evidence(learner_id):
        ev, asmt = entry["evidence"], entry["assessment"]
        out.append(s.EvidenceEntry(
            activity_id=ev["experienceId"], attempt=ev.get("attempt", 1),
            created_at=ev["createdAt"], response=ev["response"],
            criteria=[s.CriterionResult(
                id=r["criterionId"],
                criterion=texts.get(r["criterionId"], (r["criterionId"], ""))[0],
                capability_id=texts.get(r["criterionId"], ("", ev["capabilityId"]))[1],
                verdict=s.Verdict(r["verdict"]), justification=r.get("justification", ""))
                for r in ev.get("results", [])],
            changes=[s.SkillChange(
                capability_id=o["capabilityId"], name=graph().get(o["capabilityId"]).name,
                score=o["score"], mastery_before=o["masteryBefore"],
                mastery_after=o["masteryAfter"],
                state_before=state_of_mastery(o["masteryBefore"]),
                state_after=state_of_mastery(o["masteryAfter"]))
                for o in asmt.get("outcomes", [])],
            explanation=asmt.get("explanation", ""),
        ))
    return out
