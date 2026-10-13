// Typed client for the Cognith backend. Types mirror backend/api/schemas.py
// (see backend/docs/api.md). Keep the two in step when the contract changes.

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type SkillState = "mastered" | "developing" | "unknown";
export type StepKind =
  | "onboard" | "diagnose" | "learn" | "practise" | "apply" | "mission" | "nothing";
export type Verdict = "met" | "partial" | "unmet";

export interface Option { id: string; label: string }
export interface OnboardingOptions {
  goals: Option[]; levels: Option[]; technologies: string[];
  examples: string[]; topicsLabel: string;
}
export interface OnboardingRequest {
  name: string; goal: string; technologies: string[];
  knows: string; built: string; level: string;
}
export interface SkillCounts { mastered: number; developing: number; unknown: number; total: number }
export interface LearnerSummary { id: string; name: string; goal: string | null; counts: SkillCounts }
export interface Skill {
  capabilityId: string; name: string; area: string; statement: string;
  state: SkillState; mastery: number | null; selfRated: number | null;
  evidenceCount: number; lastAssessedAt: string | null; explanation: string;
}
export interface SkillProfile { learner: LearnerSummary; position: string; skills: Skill[] }
export interface LearnerCreated {
  learner: LearnerSummary;
  goal: { text: string; goalId: string; goalName: string; supported: boolean };
  initialEstimates: { capabilityId: string; name: string; selfRated: number; reason: string }[];
  unrecognisedTechnologies: string[];
  profile: SkillProfile;
}
export interface Step {
  kind: StepKind; title: string; reason: string;
  capabilityId: string | null; capabilityName: string | null;
  activityId: string | null; minutes: number;
}
export interface NextActivities {
  stage: string; steps: Step[];
  heldBack: { capabilityId: string; name: string; reason: string }[];
}
export interface Criterion { id: string; criterion: string; capabilityId: string }
export interface Activity {
  id: string; type: string; title: string; capabilityId: string; capabilityIds: string[];
  level: string; minutes: number; prompt: string; criteria: Criterion[];
  /** An authored data file, or "generated from <citations>". */
  source: string;
}
export interface Diagnostic {
  targets: { capabilityId: string; name: string; notes: string[] }[];
  activities: Activity[]; minutes: number;
}
export interface CriterionResult extends Criterion { verdict: Verdict; justification: string }
export interface SkillChange {
  capabilityId: string; name: string; score: number;
  masteryBefore: number | null; masteryAfter: number;
  stateBefore: SkillState; stateAfter: SkillState;
}
export interface TeachHint { capabilityId: string; name: string; missed: string[] }
export interface AttemptResult {
  attempt: number; criteria: CriterionResult[]; changes: SkillChange[];
  explanation: string; teach: TeachHint | null; profile: SkillProfile; next: NextActivities;
}
export interface Source {
  chunkId: string; citation: string; excerpt: string; score: number;
  reference: string | null; cited: boolean;
}
export interface Lesson {
  capabilityId: string; name: string; question: string; answered: boolean;
  explanation: string; sources: Source[]; prerequisitesFirst: string[]; gate: string;
  missed: string[]; targeted: boolean; retryActivityId: string | null;
  /** Structured lesson; null when the material couldn't support one (use `explanation`). */
  hook: string | null; sections: LessonSection[] | null;
}
export interface Diagram {
  type: "none" | "venn" | "mapping" | "table" | "flow"; caption: string;
  sets: string[]; onlyFirst: string[]; onlySecond: string[]; both: string[]; outside: string[];
  shade: "none" | "union" | "intersection" | "first_minus_second" | "second_minus_first" | "complement_first";
  fromLabel: string; toLabel: string; domain: string[]; codomain: string[]; arrows: string[][];
  headers: string[]; rows: string[][]; steps: string[];
}
export interface LessonSection {
  title: string; probe: QuizQuestion; explanation: string; example: string;
  diagram: Diagram; check: QuizQuestion; sources: string[];
}
export interface QuizQuestion { question: string; options: string[]; answerIndex: number; explanation: string }
export interface TutorAnswer { question: string; answered: boolean; answer: string; sources: Source[]; gate: string }
export interface EvidenceEntry {
  activityId: string; attempt: number; createdAt: string; response: string;
  criteria: CriterionResult[]; changes: SkillChange[]; explanation: string;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new Error(`Cannot reach the Cognith backend at ${BASE}. Is it running?`);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

const post = <T>(path: string, body: unknown) =>
  call<T>(path, { method: "POST", body: JSON.stringify(body) });

// Activity ids contain '#' and '.', so they must always be encoded in a path.
const enc = encodeURIComponent;

export const api = {
  options: () => call<OnboardingOptions>("/api/onboarding/options"),
  learners: () => call<LearnerSummary[]>("/api/learners"),
  createLearner: (req: OnboardingRequest) => post<LearnerCreated>("/api/learners", req),
  profile: (id: string) => call<SkillProfile>(`/api/learners/${enc(id)}/profile`),
  next: (id: string, limit = 4) => call<NextActivities>(`/api/learners/${enc(id)}/next?limit=${limit}`),
  diagnostic: (id: string) => call<Diagnostic>(`/api/learners/${enc(id)}/diagnostic`),
  activity: (activityId: string) => call<Activity>(`/api/activities/${enc(activityId)}`),
  attempt: (id: string, activityId: string, response: string) =>
    post<AttemptResult>(`/api/learners/${enc(id)}/attempts`, { activityId, response }),
  challenge: (id: string, capabilityId: string, avoidActivityId?: string | null) =>
    post<Activity>(`/api/learners/${enc(id)}/challenges`, { capabilityId, avoidActivityId }),
  reexplain: (id: string, body: { capabilityId: string; concept: string; explanation: string;
                                  question: string; chosen: string; correct: string }) =>
    post<{ answered: boolean; explanation: string; check: QuizQuestion | null; sources: string[] }>(
      `/api/learners/${enc(id)}/lessons/reexplain`, body),
  lessonResult: (id: string, body: { capabilityId: string;
                                     concepts: { title: string; verdict: Verdict; note: string }[] }) =>
    post<AttemptResult>(`/api/learners/${enc(id)}/lessons/result`, body),
  hint: (id: string, activityId: string) =>
    post<{ answered: boolean; hint: string; sources: string[] }>(`/api/learners/${enc(id)}/hint`, { activityId }),
  lesson: (id: string, capabilityId: string) =>
    post<Lesson>(`/api/learners/${enc(id)}/lessons`, { capabilityId }),
  tutor: (id: string, question: string, capabilityId?: string) =>
    post<TutorAnswer>(`/api/learners/${enc(id)}/tutor`, { question, capabilityId }),
  evidence: (id: string) => call<EvidenceEntry[]>(`/api/learners/${enc(id)}/evidence`),
};

/** Where a recommended step takes the learner, or null if it cannot be started here. */
export function stepHref(learnerId: string, step: Step): string | null {
  const base = `/learn/${enc(learnerId)}`;
  switch (step.kind) {
    case "learn":
      return step.capabilityId ? `${base}/lesson/${enc(step.capabilityId)}` : null;
    case "diagnose":
    case "practise":
    case "apply":
      return step.activityId ? `${base}/activity/${enc(step.activityId)}` : null;
    case "onboard":
      return "/";
    default:
      return null; // mission: not exposed over HTTP yet
  }
}

export const activityHref = (learnerId: string, activityId: string) =>
  `/learn/${enc(learnerId)}/activity/${enc(activityId)}`;

export const lessonHref = (learnerId: string, capabilityId: string, retry?: string | null) =>
  `/learn/${enc(learnerId)}/lesson/${enc(capabilityId)}${retry ? `?retry=${enc(retry)}` : ""}`;

/** Route params may arrive encoded or decoded depending on the router; ids never contain '%'. */
export function param(value: string | string[] | undefined): string {
  const v = Array.isArray(value) ? value[0] : value ?? "";
  try { return decodeURIComponent(v); } catch { return v; }
}

export const pct = (x: number | null | undefined) => (x == null ? "—" : `${Math.round(x * 100)}%`);
