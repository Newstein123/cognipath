"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, param, stepHref, type NextActivities, type SkillProfile, type Step, type UnitInfo } from "@/lib/api";
import { ErrorBox, KindBadge, Loading, PageHead, StateLabel, StepCard } from "@/components/ui";

/** Home: who you are and where you're heading, how far you've got, and the one thing to do
 *  next — with an alternative if you'd rather. The full skill picture lives on the Skill
 *  profile, past answers in History. Nothing here is generated, so Home spends no AI quota;
 *  the tutor (opened from the header) asks only when the learner sends a question. */

const CONCEPT: Record<string, string> = {
  met: "Shown", partial: "Shown after a second explanation", unmet: "Covered, not shown yet",
};

export default function Home() {
  const id = param(useParams().id);
  const base = `/learn/${encodeURIComponent(id)}`;
  const [profile, setProfile] = useState<SkillProfile | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [profileTry, setProfileTry] = useState(0);
  const [plan, setPlan] = useState<NextActivities | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [planTry, setPlanTry] = useState(0);

  useEffect(() => {
    setError(null);
    api.profile(id).then(setProfile).catch((e) => setError(e));
  }, [id, profileTry]);
  useEffect(() => {
    setPlanError(null);
    api.next(id).then(setPlan).catch((e) => setPlanError(e.message));
  }, [id, planTry]);

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
        <ErrorBox error={`Couldn't load your home page. ${error.message}`} />
        <button className="btn" onClick={() => setProfileTry((n) => n + 1)}>Try again</button>
      </section>
    );
  }
  if (!profile) return <Loading stages={["Loading…"]} />;

  const { learner } = profile;
  const top = plan?.steps[0];
  const alternatives = plan ? plan.steps.slice(1) : [];
  // The profile already says whether the lesson's skill has unit material (coverage is null
  // without it), so the optional details are offered only when there is something to show.
  const hasUnit = !!(top?.kind === "learn" && top.capabilityId
    && profile.skills.find((s) => s.capabilityId === top.capabilityId)?.coverage);

  return (
    <div className="home">
      <PageHead eyebrow={learner.course.name} title={`Hi ${learner.name}`}>
        {learner.goal ? <>Working toward <strong>{learner.goal}</strong></> : null}
      </PageHead>

      <section className="summary" aria-labelledby="summary-h">
        <h2 id="summary-h" className="visually-hidden">Your skills</h2>
        <ul className="summary-counts">
          {(["mastered", "developing", "unknown"] as const).map((st) => (
            <li key={st} aria-describedby={st === "unknown" && learner.counts.unknown > 0 ? "unknown-note" : undefined}>
              <strong>{learner.counts[st]}</strong> <StateLabel state={st} />
            </li>
          ))}
        </ul>
        <Link href={`${base}/profile`} className="summary-link">View skill profile →</Link>
        {learner.counts.unknown > 0 && (
          <p className="summary-note" id="unknown-note">
            <span className="state-text unknown" aria-hidden="true">○</span> These skills haven&apos;t been assessed yet.
          </p>
        )}
      </section>

      <NextCard learnerId={id} step={top} plan={plan} planError={planError} hasUnit={hasUnit}
        onRetry={() => setPlanTry((n) => n + 1)} />

      {alternatives.length > 0 && (
        <section className="alternatives" aria-labelledby="alt-h">
          <h2 id="alt-h">Or try instead</h2>
          <StepCard learnerId={id} step={alternatives[0]} />
          {alternatives.length > 1 && <MoreOptions learnerId={id} steps={alternatives.slice(1)} />}
        </section>
      )}
    </div>
  );
}

function NextCard({ learnerId, step, plan, planError, hasUnit, onRetry }: {
  learnerId: string; step: Step | undefined; plan: NextActivities | null; planError: string | null;
  hasUnit: boolean; onRetry: () => void;
}) {
  if (planError) {
    return (
      <section className="card now-card" aria-labelledby="now-h">
        <p className="eyebrow" id="now-h">Your next activity</p>
        <ErrorBox error={`Couldn't load your next activity. ${planError}`} />
        <button className="btn" onClick={onRetry}>Try again</button>
      </section>
    );
  }
  if (!plan) return <section className="card now-card"><Loading stages={["Choosing your next activity…"]} /></section>;
  if (!step) {
    return (
      <section className="card now-card" aria-labelledby="now-h">
        <p className="eyebrow" id="now-h">Your next activity</p>
        <p className="muted" style={{ margin: 0 }}>Nothing to do right now.</p>
      </section>
    );
  }
  const href = stepHref(learnerId, step);
  return (
    <section className="card now-card" aria-labelledby="now-h">
      <p className="eyebrow">Your next activity</p>
      <div className="meta">
        <KindBadge kind={step.kind} />
        {step.capabilityName && <span>{step.capabilityName}</span>}
        {step.minutes > 0 && <span>about {step.minutes} min</span>}
      </div>
      <h2 id="now-h">{step.title}</h2>
      <Reason text={step.reason} />
      <div className="row now-action">
        {href ? <Link className="btn" href={href}>Start →</Link> : (
          <Link className="btn" href={`/learn/${encodeURIComponent(learnerId)}/profile`}>
            {step.kind === "mission" ? "Mission coming soon — see your skill profile →" : "See your skill profile →"}
          </Link>
        )}
      </div>
      {hasUnit && step.capabilityId && <LessonDetails learnerId={learnerId} capabilityId={step.capabilityId} />}
    </section>
  );
}

/** The rest of the plan, folded away. The summary says what it does next; its expanded state
 *  is the native <details> one, which browsers expose to assistive tech themselves. */
function MoreOptions({ learnerId, steps }: { learnerId: string; steps: Step[] }) {
  const [open, setOpen] = useState(false);
  return (
    <details className="more-options" onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}>
      <summary>{open ? "Hide other options" : `Show other options (${steps.length})`}</summary>
      {steps.map((s, i) => <StepCard key={i} learnerId={learnerId} step={s} />)}
    </details>
  );
}

/** The plan's reason, kept short so Start stays in view; long ones can be expanded. The
 *  whole text is always in the page, so assistive tech reads all of it either way. */
function Reason({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  // Offer the toggle only when three lines really cut the text off at this width.
  const [cut, setCut] = useState(false);
  const ref = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    const measure = () => { const el = ref.current; if (el && !open) setCut(el.scrollHeight > el.clientHeight + 1); };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [text, open]);
  return (
    <div className="why-chosen">
      <p className="eyebrow">Why this was chosen</p>
      <p id="reason-text" ref={ref} className={open ? undefined : "clamped"}>{text}</p>
      {(cut || open) && (
        <button type="button" className="link-btn small" aria-expanded={open} aria-controls="reason-text"
          onClick={() => setOpen((o) => !o)}>
          {open ? "Show less" : "Show full reason"}
        </button>
      )}
    </div>
  );
}

/** Optional: this lesson's parts, concepts and coverage. Loaded only when opened. */
function LessonDetails({ learnerId, capabilityId }: { learnerId: string; capabilityId: string }) {
  // undefined = not requested yet; null = no unit material; "error" = the request failed.
  const [unit, setUnit] = useState<UnitInfo | null | "error" | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const load = () => {
    setLoading(true);
    api.unit(learnerId, capabilityId).then(setUnit)
      .catch((e) => setUnit(e instanceof ApiError && e.status === 404 ? null : "error"))
      .finally(() => setLoading(false));
  };
  return (
    <details className="lesson-details" onToggle={(e) => { if ((e.currentTarget as HTMLDetailsElement).open && unit === undefined && !loading) load(); }}>
      <summary>Lesson details — parts and coverage</summary>
      {loading && <p className="small muted">Loading this unit&apos;s details…</p>}
      {unit === null && <p className="small muted">This lesson has no unit details to show.</p>}
      {unit === "error" && !loading && (
        <p className="small muted">Unit details couldn&apos;t be loaded. <button type="button" className="link-btn" onClick={load}>Try again</button></p>
      )}
      {unit && unit !== "error" && <UnitBlock unit={unit} />}
    </details>
  );
}

/** This part's ideas, where it sits among the parts, and coverage — which is not mastery. */
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
