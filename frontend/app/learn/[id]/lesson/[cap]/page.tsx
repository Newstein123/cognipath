"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { activityHref, api, param, type AttemptResult, type Lesson, type Step, type UnitInfo } from "@/lib/api";
import { GuidedLesson, LessonOutcome } from "@/components/GuidedLesson";
import { UnitProgress } from "@/components/UnitProgress";
import { chatKey, setChatExtras } from "@/lib/tutorChat";
import { ErrorBox, Loading, Markdown, PageHead, Sources, StepCard } from "@/components/ui";

export default function LessonPage() {
  return <Suspense><LessonView /></Suspense>;
}

/** Guided lesson (ask → teach only what's needed → check → explain differently), then a
 *  written challenge in a new situation. Falls back to a plain explanation when the
 *  material can't support a guided lesson. */
function LessonView() {
  const params = useParams();
  const id = param(params.id);
  const cap = param(params.cap);
  const search = useSearchParams();
  const retryParam = search.get("retry");
  const full = search.get("full") === "1";
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [practice, setPractice] = useState<Step | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [finished, setFinished] = useState(false);
  const [outcome, setOutcome] = useState<AttemptResult | null>(null);
  // Coverage after finishing a part (decides "continue" vs the challenge).
  const [unitAfter, setUnitAfter] = useState<UnitInfo | null>(null);
  const [partReq, setPartReq] = useState<number | null>(null);
  // Bumped by "Try again" to re-request the same lesson after a failure.
  const [attempt, setAttempt] = useState(0);
  // The skill's name from the profile, so the title is readable before (or without) a lesson.
  const [skillName, setSkillName] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    api.profile(id).then((p) => setSkillName(p.skills.find((s) => s.capabilityId === cap)?.name ?? null))
      .catch(() => {});
  }, [id, cap]);

  useEffect(() => {
    // A superseded request (StrictMode's first mount, or a part change) must not land.
    let current = true;
    setLesson(null); setError(null); setFinished(false); setOutcome(null); setUnitAfter(null);
    api.lesson(id, cap, { fromActivityId: retryParam, full, part: partReq })
      .then((l) => { if (current) setLesson(l); })
      .catch((e) => { if (current) setError(e.message); });
    api.next(id, 6).then((n) => {
      const doable = n.steps.filter((s) => s.activityId && s.capabilityId === cap);
      if (current) setPractice(doable[0] ?? null);
    }).catch(() => {});
    return () => { current = false; };
  }, [id, cap, retryParam, full, partReq, attempt]);

  const retry = retryParam ?? lesson?.retryActivityId ?? null;
  const name = lesson?.name ?? skillName ?? "this skill";
  const guided = !!lesson?.sections?.length;
  const unit = unitAfter ?? lesson?.unit ?? null;
  // The challenge proves the WHOLE unit, so it waits until every concept has been taught.
  const unitDone = !unit || unit.covered >= unit.total;
  const nextPart = unit && !unitDone
    ? Math.min(...unit.concepts.filter((c) => !c.status).map((c) => c.part)) : null;
  const showChallenge = lesson && (!guided || finished) && unitDone;

  async function newChallenge() {
    setGenerating(true);
    setError(null);
    try {
      const a = await api.challenge(id, cap, retry, lesson?.focused ? lesson.missed : []);
      router.push(activityHref(id, a.id));
    } catch (e) {
      setError((e as Error).message);
      setGenerating(false);
    }
  }

  // The header's tutor (opened from the layout) is scoped to this topic; this page adds its
  // placeholder and, when there is no guided lesson, its one-click questions.
  useEffect(() => {
    if (!lesson) return;
    const key = chatKey(id, cap);
    setChatExtras(key, {
      placeholder: `Ask a specific question about ${name}…`,
      presets: guided ? [] : [
        { label: "Explain it more simply", question: `Explain the most important idea of ${name} in plain words for a beginner.` },
        { label: "Show me another example", question: `Give a concrete example from the material that shows ${name} in practice.` },
        { label: "Common mistakes", question: `What mistakes do people commonly make with ${name}, and how do you avoid them?` },
      ],
    });
    return () => setChatExtras(key, null);
  }, [id, cap, lesson, guided, name]);

  return (
    <>
      <PageHead eyebrow="Lesson" title={lesson?.name ?? skillName ?? "Lesson"} />
      {unit && lesson?.unit?.part ? <UnitProgress unit={unit} current={finished ? undefined : lesson.unit.part} /> : null}
      {lesson?.pitch && (
        <p className="small" style={{ marginTop: -4 }}>
          <span className="badge kind" title="Cognith adapts how it teaches to what your answers have shown">
            Pitched for you: {lesson.pitch}
          </span>
        </p>
      )}
      <ErrorBox error={error} />
      {error && !lesson && (
        <div className="row" style={{ marginTop: 8 }}>
          <button className="btn" onClick={() => setAttempt((n) => n + 1)}>Try again</button>
        </div>
      )}

      {lesson && lesson.missed.length > 0 && !finished && (
        <div className="card primary">
          <h3>{lesson.focused ? "Focused lesson — only what you missed" : "What you missed last time"}</h3>
          {lesson.focused && (
            <p className="small muted" style={{ marginTop: 0 }}>
              You&apos;ve already shown the rest of {lesson.name}, so we&apos;ll skip it and work on:
            </p>
          )}
          <ul style={{ paddingLeft: 20, marginBottom: 0 }}>
            {lesson.missed.map((m) => <li key={m}>{m}</li>)}
          </ul>
          {lesson.focused && (
            <p className="small" style={{ marginBottom: 0 }}>
              <a href={`?full=1${retryParam ? `&retry=${encodeURIComponent(retryParam)}` : ""}`}>
                Prefer the whole {lesson.name} lesson from the start?
              </a>
            </p>
          )}
        </div>
      )}

      {!lesson && !error && (
        <div className="card">
          <Loading stages={["Writing your lesson from the course material…"]} />
        </div>
      )}

      {lesson && guided && !finished && (
        <div className="reading">
        <GuidedLesson learnerId={id} capabilityId={cap} hook={lesson.hook}
          sections={lesson.sections!} teachFirst={lesson.teachFirst}
          onConceptDone={() => api.unit(id, cap).then(setUnitAfter).catch(() => {})}
          onComplete={(r) => {
            setOutcome(r); setFinished(true); window.scrollTo(0, 0);
            api.unit(id, cap).then(setUnitAfter).catch(() => {});
          }} />
        </div>
      )}
      {finished && outcome && <LessonOutcome result={outcome} />}
      {finished && unit && !unitDone && nextPart && (
        <div className="card highlight">
          <h2>Part done — covered {unit.covered} of {unit.total} ideas, demonstrated {unit.demonstrated}</h2>
          <p className="muted">
            {unit.parts - nextPart === 0
              ? <>This is the last part: <strong>the unit challenge unlocks when you finish it</strong>.</>
              : <>The unit challenge unlocks after Part {unit.parts} — {unit.parts - nextPart + 1} parts
                  ({unit.total - unit.covered} ideas) to go. It tests the whole unit in a new situation,
                  so it waits until you&apos;ve been taught all of it.</>}
          </p>
          <button className="btn" onClick={() => setPartReq(nextPart)}>
            Continue: Part {nextPart} of {unit.parts} →
          </button>
        </div>
      )}

      {lesson && !guided && (
        <div className="card reading">
          <h2>Explanation</h2>
          {lesson.answered ? <Markdown text={lesson.explanation} /> : (
            <div className="notice">
              {lesson.explanation}
              <div className="small muted" style={{ marginTop: 6 }}>
                Cognith only teaches from trusted course material, so it won&apos;t improvise here.
              </div>
            </div>
          )}
          <Sources sources={lesson.sources} />
        </div>
      )}

      {showChallenge && (
        <div className="card highlight">
          <h2>Challenge</h2>
          <p>
            A <strong>new</strong> question written from the same course material — a situation you
            haven&apos;t seen. Work it on paper, then type your answer. Stuck? Ask for a hint.
            This is what proves the skill.
          </p>
          <ErrorBox error={generating ? null : error} />
          {generating ? (
            <Loading stages={["Picking the course sections you just learned…", "Writing a new question…", "Checking every mark is backed by the material…"]} />
          ) : (
            <div className="row">
              <button className="btn" onClick={newChallenge}>Give me a challenge →</button>
              {retry && <Link className="btn secondary" href={activityHref(id, retry)}>Retry the original question</Link>}
            </div>
          )}
        </div>
      )}

      {showChallenge && practice && practice.activityId !== retry && (
        <>
          <h3 className="muted">Or practise with a prepared exercise</h3>
          <StepCard learnerId={id} step={practice} />
        </>
      )}
    </>
  );
}
