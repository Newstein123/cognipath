"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError, param, stepHref, type NextActivities, type Skill, type SkillProfile, type SkillState, type Step, type UnitInfo } from "@/lib/api";
import { ErrorBox, KindBadge, Loading, StateLabel, StepCard } from "@/components/ui";

/** Home as a learning journey: where the learner is going, the one thing to do now and
 *  why, then every skill in the course's own order, grouped by its area. Everything shown
 *  comes from the profile, the plan and (for a lesson) its unit — nothing here is
 *  generated, so Home never spends AI quota. */

const EVIDENCE_KIND: Record<string, string> = {
  lesson: "Lesson checks", practice: "Practice", challenge: "Challenge", diagnosis: "Diagnosis",
};
const CONCEPT: Record<string, string> = {
  met: "Shown", partial: "Shown after a second explanation", unmet: "Covered, not shown yet",
};
const STATE_ICON: Record<SkillState, string> = { mastered: "✓", developing: "◐", unknown: "○" };
const areaName = (area: string) => {
  const s = area.replace(/-/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
};
const isMobile = () => typeof window !== "undefined" && window.matchMedia("(max-width: 860px)").matches;
const sameStep = (a: Step, b: Step) => a.kind === b.kind && a.title === b.title && a.capabilityId === b.capabilityId;

export default function Home() {
  const id = param(useParams().id);
  const base = `/learn/${encodeURIComponent(id)}`;
  const [profile, setProfile] = useState<SkillProfile | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [profileTry, setProfileTry] = useState(0);
  const [plan, setPlan] = useState<NextActivities | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [planTry, setPlanTry] = useState(0);
  // undefined = loading or not needed yet; null = no unit material; "error" = request failed.
  const [unit, setUnit] = useState<UnitInfo | null | "error" | undefined>(undefined);
  const [unitTry, setUnitTry] = useState(0);

  useEffect(() => {
    setError(null);
    api.profile(id).then(setProfile).catch((e) => setError(e));
  }, [id, profileTry]);
  useEffect(() => {
    setPlanError(null);
    api.next(id).then(setPlan).catch((e) => setPlanError(e.message));
  }, [id, planTry]);
  const top = plan?.steps[0];
  // Unit details are primary only for a lesson; the profile already says whether the skill
  // has unit material at all (coverage is null without it), so no request is wasted.
  const lessonCap = top?.kind === "learn" ? top.capabilityId : null;
  const hasUnit = !!(lessonCap && profile?.skills.find((s) => s.capabilityId === lessonCap)?.coverage);
  useEffect(() => {
    if (!lessonCap || !hasUnit) { setUnit(null); return; }
    setUnit(undefined);
    api.unit(id, lessonCap).then(setUnit).catch((e) => setUnit(e instanceof ApiError && e.status === 404 ? null : "error"));
  }, [id, lessonCap, hasUnit, unitTry]);

  if (error) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <section className="card" aria-labelledby="nf-h" style={{ maxWidth: 560 }}>
          <h1 id="nf-h" style={{ fontSize: 24 }}>We couldn&apos;t find this learner</h1>
          <p className="muted">There&apos;s no learner called &ldquo;{id}&rdquo;. They may have been removed, or the link may be mistyped.</p>
          <Link className="btn" href="/">Back to start</Link>
        </section>
      );
    }
    return (
      <section className="card" style={{ maxWidth: 560 }}>
        <ErrorBox error={`Couldn't load your journey. ${error.message}`} />
        <button className="btn" onClick={() => setProfileTry((n) => n + 1)}>Try again</button>
      </section>
    );
  }
  if (!profile) return <Loading stages={["Loading your journey…"]} />;

  const { learner } = profile;
  const currentCap = top && top.kind !== "nothing" ? top.capabilityId : null;
  const alternatives = plan ? plan.steps.slice(1) : [];
  // `position`: a first sentence the counts already show, then — for a learner with
  // evidence on a goal — the backend's milestone line(s).
  const milestone = profile.position.split("\n").slice(1).map((l) => l.trim()).filter(Boolean);
  const progress = <ProgressPanel milestone={milestone} noEvidence={learner.counts.mastered + learner.counts.developing === 0} base={base} />;

  return (
    <div className="journey-home">
      <header className="band" aria-labelledby="band-h">
        <p className="eyebrow">{learner.course.name} · {learner.name}</p>
        <h1 id="band-h">{learner.goal ?? "Your learning journey"}</h1>
        {/* The one set of skill counts on this page. */}
        <ul className="band-counts" aria-label="Skills">
          {(["mastered", "developing", "unknown"] as const).map((st) => (
            <li key={st} className={st}>
              <span aria-hidden="true">{STATE_ICON[st]}</span>
              <strong>{learner.counts[st]}</strong> {st === "unknown" ? "not verified yet" : st}
            </li>
          ))}
        </ul>
        {/* One segment per skill, in course order; the counts above say the same in words. */}
        <ol className="route" aria-hidden="true">
          {profile.skills.map((s) => (
            <li key={s.capabilityId} className={`${s.state}${s.capabilityId === currentCap ? " now" : ""}`} title={s.name} />
          ))}
        </ol>
      </header>

      <div className="journey-grid">
        <div className="journey-main">
          <NowCard learnerId={id} step={top} plan={plan} planError={planError} onRetry={() => setPlanTry((n) => n + 1)}
            unit={unit} onUnitRetry={() => setUnitTry((n) => n + 1)}
            skill={profile.skills.find((s) => s.capabilityId === currentCap)} />
          {progress && <div className="mobile-only">{progress}</div>}
          {/* Re-keyed when the plan arrives, so the phone's collapsed groups follow the current skill. */}
          <Journey key={currentCap ?? "no-current"} learnerId={id} skills={profile.skills} currentCap={currentCap}
            alternatives={alternatives} />
        </div>
        <aside className="journey-aside" aria-label="Your progress">
          {progress && <div className="desktop-only">{progress}</div>}
          <EvidencePanel profile={profile} base={base} />
          {alternatives.length > 0 && (
            <section className="panel" id="alternatives" aria-labelledby="alt-h">
              <h2 id="alt-h">Or try instead</h2>
              {alternatives.map((s, i) => <StepCard key={i} learnerId={id} step={s} />)}
            </section>
          )}
          {plan && plan.heldBack.length > 0 && (
            <section className="panel" aria-labelledby="held-h">
              <h2 id="held-h">Held back for now</h2>
              <ul className="list">
                {/* The reason names what is held back (e.g. a capstone); `name` is the skill
                    the plan files it under, so it is context, not the heading. */}
                {plan.heldBack.map((h, i) => (
                  <li key={i}>{h.reason.charAt(0).toUpperCase() + h.reason.slice(1)}
                    <div className="small muted">Related skill: {h.name}</div></li>
                ))}
              </ul>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}

function NowCard({ learnerId, step, plan, planError, onRetry, unit, onUnitRetry, skill }: {
  learnerId: string; step: Step | undefined; plan: NextActivities | null; planError: string | null;
  onRetry: () => void; unit: UnitInfo | null | "error" | undefined; onUnitRetry: () => void; skill: Skill | undefined;
}) {
  if (planError) {
    return (
      <section className="card now-card" aria-labelledby="now-h">
        <p className="eyebrow" id="now-h">Current activity</p>
        <ErrorBox error={`Couldn't load your plan. ${planError}`} />
        <button className="btn" onClick={onRetry}>Try again</button>
      </section>
    );
  }
  if (!plan) return <section className="card now-card"><Loading stages={["Choosing your next step…"]} /></section>;
  if (!step) {
    return (
      <section className="card now-card" aria-labelledby="now-h">
        <p className="eyebrow" id="now-h">Current activity</p>
        <p className="muted" style={{ margin: 0 }}>Nothing to do right now.</p>
      </section>
    );
  }
  const href = stepHref(learnerId, step);
  const isLesson = step.kind === "learn";
  return (
    <section className="card now-card" id="current" aria-labelledby="now-h">
      <div className="meta">
        <span className="now-tag">Now</span>
        <KindBadge kind={step.kind} />
        {step.capabilityName && <span>{step.capabilityName}</span>}
        {step.minutes > 0 && <span>about {step.minutes} min</span>}
      </div>
      <h2 id="now-h">{step.title}</h2>
      <div className="why-chosen">
        <p className="eyebrow">Why this was chosen</p>
        <p>{step.reason}</p>
      </div>
      <div className="row now-action">
        {href ? <Link className="btn" href={href}>Start →</Link> : (
          <Link className="btn" href={`/learn/${encodeURIComponent(learnerId)}/profile`}>
            {step.kind === "mission" ? "Mission coming soon — see your skill profile →" : "See your skill profile →"}
          </Link>
        )}
      </div>
      {isLesson && unit === undefined && <p className="small muted unit-note">Loading this unit&apos;s details…</p>}
      {isLesson && unit === "error" && (
        <p className="small muted unit-note">
          Unit details couldn&apos;t be loaded. <button className="link-btn" onClick={onUnitRetry}>Try again</button>
        </p>
      )}
      {isLesson && unit && unit !== "error" && <UnitBlock unit={unit} />}
      {/* Not a lesson: the activity stands on its own; lesson coverage is optional context. */}
      {!isLesson && skill?.coverage && skill.coverage.total > 0 && (
        <p className="small muted unit-note">
          Lesson coverage for {skill.name}: {skill.coverage.covered} of {skill.coverage.total} ideas covered — separate from this {step.kind === "diagnose" ? "check" : "activity"}.
        </p>
      )}
    </section>
  );
}

/** The unit behind the current lesson: this part's ideas, where it sits among the parts,
 *  and how much of the material has been covered — coverage, which is not mastery. */
function UnitBlock({ unit }: { unit: UnitInfo }) {
  const inPart = unit.part > 0 ? unit.concepts.filter((c) => c.part === unit.part) : [];
  const partDone = (p: number) => unit.concepts.filter((c) => c.part === p).every((c) => c.status !== null);
  return (
    <div className="unit-block">
      {inPart.length > 0 && (
        <div>
          <p className="eyebrow">In part {unit.part}</p>
          <ul className="concept-list">
            {inPart.map((c) => (
              <li key={c.id} className={c.status ?? "todo"}>
                <span className="mark" aria-hidden="true">{c.status === "met" ? "✓" : c.status === "partial" ? "△" : c.status === "unmet" ? "!" : "○"}</span>
                <span>{c.title}<span className="visually-hidden"> — {c.status ? CONCEPT[c.status] : "Not covered yet"}</span></span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div>
        <p className="eyebrow">Unit coverage</p>
        <div className="seg" role="img" aria-label={`${unit.covered} of ${unit.total} ideas covered`}>
          {unit.concepts.map((c) => <i key={c.id} className={c.status ? "on" : ""} />)}
        </div>
        <p className="small muted" style={{ margin: "6px 0 12px" }}>
          Lessons have covered {unit.covered} of {unit.total} ideas; you&apos;ve shown {unit.demonstrated}.
          Covering a unit isn&apos;t mastering it.
        </p>
        <ol className="parts" aria-label="Parts of this unit">
          {Array.from({ length: unit.parts }, (_, i) => i + 1).map((p) => {
            const now = p === unit.part, done = !now && partDone(p);
            return (
              <li key={p} className={now ? "now" : done ? "done" : ""} aria-current={now ? "step" : undefined}>
                Part {p}
                <span className="part-state">{now ? "Next" : done ? "Covered" : "Not started"}</span>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}

/** The milestone (when the backend has one) and, for a learner with no evidence, why the
 *  counts are all "not verified yet". The counts themselves live in the header band. */
function ProgressPanel({ milestone, noEvidence, base }: { milestone: string[]; noEvidence: boolean; base: string }) {
  if (!milestone.length && !noEvidence) return null;
  return (
    <section className="panel">
      <div className="spread" style={{ marginBottom: 10 }}>
        <h2 style={{ margin: 0 }}>{milestone.length ? "Milestone" : "Getting started"}</h2>
        <Link href={`${base}/profile`} className="small">Skill profile →</Link>
      </div>
      {milestone.map((m) => <p key={m} className="small" style={{ margin: "0 0 4px" }}>{m}</p>)}
      {noEvidence && (
        <p className="small muted" style={{ margin: 0 }}>
          No skill has evidence yet. &ldquo;Not verified yet&rdquo; isn&apos;t a weakness — there&apos;s simply nothing to go on.
        </p>
      )}
    </section>
  );
}

function EvidencePanel({ profile, base }: { profile: SkillProfile; base: string }) {
  // One attempt can count for several skills: show it once, naming each skill it touched.
  const recent = new Map<string, { title: string; kind: string; createdAt: string; met: number; total: number; skills: string[] }>();
  for (const s of profile.skills) {
    for (const e of s.evidence) {
      const key = `${e.title}|${e.createdAt}`;
      const row = recent.get(key);
      if (row) row.skills.push(s.name);
      else recent.set(key, { title: e.title, kind: e.kind, createdAt: e.createdAt, met: e.met, total: e.total, skills: [s.name] });
    }
  }
  const latest = [...recent.values()].sort((a, b) => b.createdAt.localeCompare(a.createdAt)).slice(0, 4);
  return (
    <section className="panel" aria-labelledby="evidence-h">
      <div className="spread" style={{ marginBottom: 6 }}>
        <h2 id="evidence-h" style={{ margin: 0 }}>Recent evidence</h2>
        <Link href={`${base}/history`} className="small">History →</Link>
      </div>
      {latest.length ? (
        <ul className="list evidence-rows">
          {latest.map((e) => (
            <li key={`${e.title}|${e.createdAt}`}>
              <strong>{e.kind === "lesson" ? EVIDENCE_KIND.lesson : e.title}</strong>
              <div className="meta">
                <span>{EVIDENCE_KIND[e.kind] ?? e.kind}</span>
                <span>{e.skills.join(", ")}</span>
                <span>{e.met} of {e.total} {e.kind === "lesson" ? "concepts shown" : "points met"}</span>
                <span>{new Date(e.createdAt).toLocaleDateString()}</span>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="small muted" style={{ margin: 0 }}>No answers yet. Your current activity will start your evidence.</p>
      )}
    </section>
  );
}

/** Every skill in the course's own order, grouped by area. On a phone, only the area with
 *  the current skill starts open; each closed area still says what it holds. */
function Journey({ learnerId, skills, currentCap, alternatives }: {
  learnerId: string; skills: Skill[]; currentCap: string | null; alternatives: Step[];
}) {
  const groups: { area: string; skills: Skill[] }[] = [];
  for (const s of skills) {
    const g = groups.find((x) => x.area === s.area);
    if (g) g.skills.push(s); else groups.push({ area: s.area, skills: [s] });
  }
  const [open, setOpen] = useState<Record<string, boolean>>(() => {
    const mobile = isMobile();
    const current = groups.findIndex((g) => g.skills.some((s) => s.capabilityId === currentCap));
    return Object.fromEntries(groups.map((g, i) => [g.area, !mobile || i === (current >= 0 ? current : 0)]));
  });
  return (
    <section className="journey" aria-labelledby="journey-h">
      <h2 id="journey-h">Your journey</h2>
      {groups.map((g) => {
        const n = (st: SkillState) => g.skills.filter((s) => s.state === st).length;
        const summary = [n("mastered") && `${n("mastered")} mastered`, n("developing") && `${n("developing")} developing`,
          n("unknown") && `${n("unknown")} not verified yet`].filter(Boolean).join(" · ");
        const isOpen = open[g.area] ?? true;
        return (
          <details key={g.area} className="stage" open={isOpen}
            onToggle={(e) => { const o = (e.currentTarget as HTMLDetailsElement).open; setOpen((m) => ({ ...m, [g.area]: o })); }}>
            <summary>
              <span className="stage-name">{areaName(g.area)}</span>
              <span className="stage-meta">{g.skills.length} skill{g.skills.length === 1 ? "" : "s"} · {summary}</span>
              <span className="stage-toggle">{isOpen ? "Hide skills" : "Show skills"}</span>
            </summary>
            <ol className="stops">
              {g.skills.map((s) => (
                <Stop key={s.capabilityId} learnerId={learnerId} skill={s} now={s.capabilityId === currentCap}
                  suggested={!!s.nextStep && alternatives.some((a) => sameStep(a, s.nextStep!))} />
              ))}
            </ol>
          </details>
        );
      })}
    </section>
  );
}

const NODE: Record<SkillState, string> = { mastered: "✓", developing: "◐", unknown: "" };

function Stop({ learnerId, skill: s, now, suggested }: { learnerId: string; skill: Skill; now: boolean; suggested: boolean }) {
  const latest = s.evidence[0];
  let detail: string | null = null;
  if (s.state === "developing" && s.uncertain[0]) detail = `Still to develop: “${s.uncertain[0]}”`;
  else if (latest) {
    detail = `Latest evidence: ${latest.kind === "lesson" ? "lesson checks" : latest.title} — ${latest.met} of ${latest.total} ${latest.kind === "lesson" ? "concepts shown" : "points met"}`;
  }
  const href = !now && s.nextStep ? stepHref(learnerId, s.nextStep) : null;
  return (
    <li className={`stop ${s.state}${now ? " now" : ""}`}>
      <span className={`node ${now ? "now" : s.state}`} aria-hidden="true">{now ? "▶" : NODE[s.state]}</span>
      <div className="stop-body">
        <div className="stop-head">
          <span className="stop-name">{s.name}</span>
          {now ? <a className="now-tag" href="#current">Now<span className="visually-hidden"> — current activity</span></a> : <StateLabel state={s.state} />}
        </div>
        {now && <StateLabel state={s.state} />}
        {detail && <p>{detail}</p>}
        {s.coverage && s.coverage.covered > 0 && (
          <p>Lessons: covered {s.coverage.covered} of {s.coverage.total} ideas · shown {s.coverage.demonstrated}</p>
        )}
        {/* Each real action appears once: an alternative from the plan is in "Or try
            instead" with its reason; the rest link from here. */}
        {!now && suggested && <a className="stop-link" href="#alternatives">Suggested next — see &ldquo;Or try instead&rdquo;</a>}
        {!now && !suggested && href && <Link className="stop-link" href={href}>{s.nextStep!.title} →</Link>}
        {!now && !s.nextStep && s.state !== "mastered" && <p className="stop-none">No activity for this skill in your plan yet.</p>}
      </div>
    </li>
  );
}
