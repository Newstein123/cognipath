"""The HTTP contract. Every request and response body the frontend sees is defined here.

Field names are camelCase on the wire to match the existing record shapes
(`to_record()` everywhere in the engine) and the TypeScript side.

Skill states are the three the product talks about. The engine has four internally;
`claimed` and `unknown` both surface as `unknown` here, with `selfRated` carrying the
claim so the UI can still say "you rated yourself 70% — not yet verified".
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SkillState(str, Enum):
    MASTERED = "mastered"
    DEVELOPING = "developing"
    UNKNOWN = "unknown"


class StepKind(str, Enum):
    ONBOARD = "onboard"
    DIAGNOSE = "diagnose"
    LEARN = "learn"
    PRACTISE = "practise"
    APPLY = "apply"
    MISSION = "mission"
    NOTHING = "nothing"


class Verdict(str, Enum):
    MET = "met"
    PARTIAL = "partial"
    UNMET = "unmet"


# --- onboarding -----------------------------------------------------------------------
class Option(Model):
    id: str
    label: str


class OnboardingOptions(Model):
    goals: list[Option]
    levels: list[Option]
    technologies: list[str]
    #: Example goals for the start page.
    examples: list[str] = []
    #: Label for the technologies picker — "Technologies you have used", or a course's own.
    topics_label: str = "Technologies you have used"


class OnboardingRequest(Model):
    name: str = Field(min_length=1, max_length=80)
    #: Free text — "I want to build production-ready REST APIs".
    goal: str = Field(min_length=1, max_length=500)
    technologies: list[str] = []
    knows: str = Field("", max_length=2000)
    built: str = Field("", max_length=2000)
    #: One of OnboardingOptions.levels[].id
    level: str = "intermediate"


class GoalMatch(Model):
    text: str
    goal_id: str
    goal_name: str
    #: False for goals other than the demo domain. The learner is still created.
    supported: bool


class InitialEstimate(Model):
    capability_id: str
    name: str
    self_rated: float
    #: Where the number came from — "listed technology: postgres".
    reason: str


# --- learners and skill profile -----------------------------------------------------
class SkillCounts(Model):
    mastered: int
    developing: int
    unknown: int
    total: int


class LearnerSummary(Model):
    id: str
    name: str
    goal: str | None
    counts: SkillCounts


class Skill(Model):
    capability_id: str
    name: str
    area: str
    #: "Can decide where to cache, what to cache, and how to invalidate it."
    statement: str
    state: SkillState
    #: 0..1 from evidence. Null means never assessed — NOT zero.
    mastery: float | None
    #: 0..1 self-reported at onboarding. Never evidence.
    self_rated: float | None
    evidence_count: int
    last_assessed_at: str | None
    #: One sentence for the learner on why the skill is in this state.
    explanation: str


class SkillProfile(Model):
    learner: LearnerSummary
    #: "8 of 17 demonstrated, 9 assessed, 5 still taken on trust."
    position: str
    skills: list[Skill]


class LearnerCreated(Model):
    learner: LearnerSummary
    goal: GoalMatch
    initial_estimates: list[InitialEstimate]
    unrecognised_technologies: list[str]
    profile: SkillProfile


# --- next activities ------------------------------------------------------------------
class Step(Model):
    kind: StepKind
    title: str
    #: Written for the learner — the "why" behind the recommendation.
    reason: str
    capability_id: str | None
    capability_name: str | None
    #: Set for diagnose/practise/apply/mission: GET /api/activities/{activityId}.
    #: For learn: POST /api/learners/{id}/lessons with capabilityId.
    activity_id: str | None
    minutes: int


class HeldBack(Model):
    capability_id: str
    name: str
    reason: str


class NextActivities(Model):
    #: "not started" | "claimed, unverified" | "learning" | "nothing outstanding"
    stage: str
    steps: list[Step]
    held_back: list[HeldBack]


# --- activities and attempts ------------------------------------------------------------
class Criterion(Model):
    id: str
    criterion: str
    capability_id: str


class Activity(Model):
    id: str
    #: diagnostic | exercise | apply | mission | generated
    type: str
    title: str
    capability_id: str
    capability_ids: list[str]
    level: str
    minutes: int
    prompt: str
    #: The explicit rubric the answer is judged against.
    criteria: list[Criterion]
    #: Where it came from — an authored data file, or "generated from <citations>".
    source: str


class ChallengeRequest(Model):
    capability_id: str
    #: The activity the learner just missed — the new one must be a different situation.
    avoid_activity_id: str | None = None


class DiagnosticTarget(Model):
    capability_id: str
    name: str
    #: Why this capability was picked — "claimed 70%, never checked".
    notes: list[str]


class Diagnostic(Model):
    targets: list[DiagnosticTarget]
    activities: list[Activity]
    minutes: int


class AttemptRequest(Model):
    activity_id: str
    response: str = Field(min_length=1, max_length=10000)


class CriterionResult(Model):
    id: str
    criterion: str
    capability_id: str
    verdict: Verdict
    justification: str


class SkillChange(Model):
    capability_id: str
    name: str
    #: Score on this attempt alone, 0..1.
    score: float
    mastery_before: float | None
    mastery_after: float
    state_before: SkillState
    state_after: SkillState


class TeachHint(Model):
    """What to learn right after this attempt: the weakest teachable capability."""
    capability_id: str
    name: str
    #: Criterion texts not (fully) met on this attempt, for that capability.
    missed: list[str]


class AttemptResult(Model):
    attempt: int
    criteria: list[CriterionResult]
    changes: list[SkillChange]
    #: Assembled from the criterion verdicts, not a second model call.
    explanation: str
    #: Null when everything was met or nothing missed has course material.
    teach: TeachHint | None
    profile: SkillProfile
    next: NextActivities


# --- grounded teaching ------------------------------------------------------------------
class Source(Model):
    chunk_id: str
    #: "caching.md § Cache invalidation"
    citation: str
    excerpt: str
    score: float
    #: The trusted source the document was written from — a book chapter or spec.
    reference: str | None
    #: True when the generated answer actually relied on this excerpt.
    cited: bool


class QuickCheck(Model):
    question: str
    options: list[str]
    answer_index: int
    explanation: str


class LessonCard(Model):
    title: str
    idea: str
    example: str
    check: QuickCheck
    #: Course sections the card is built from.
    sources: list[str]


class LessonRequest(Model):
    capability_id: str


class Lesson(Model):
    capability_id: str
    name: str
    question: str
    answered: bool
    #: Grounded explanation, or the abstention message.
    explanation: str
    sources: list[Source]
    #: Capabilities to demonstrate first — shown as a hint, never a block.
    prerequisites_first: list[str]
    #: What the learner's evidence says they missed. Empty if never assessed.
    missed: list[str]
    #: True when the explanation addresses `missed` directly.
    targeted: bool
    #: An activity where the learner missed this — "try it again" after the lesson.
    retry_activity_id: str | None
    #: The micro-lesson: 3–5 cards, each one idea + worked example + quick check. Null when
    #: the material could not support one; `explanation` is always there as the fallback
    #: and the "read it all" view. Quick checks are practice — they never change mastery.
    hook: str | None = None
    cards: list[LessonCard] | None = None
    #: Why it was or was not answered: score_floor | model | citation_check | api_error | no_corpus
    gate: str


class TutorRequest(Model):
    question: str = Field(min_length=1, max_length=2000)
    #: Restrict retrieval to this capability's documents (e.g. inside a lesson).
    capability_id: str | None = None


class TutorAnswer(Model):
    question: str
    answered: bool
    answer: str
    sources: list[Source]
    gate: str


# --- history ----------------------------------------------------------------------------
class EvidenceEntry(Model):
    activity_id: str
    attempt: int
    created_at: str
    response: str
    criteria: list[CriterionResult]
    changes: list[SkillChange]
    explanation: str
