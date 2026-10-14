"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { activityHref, api, param, type AttemptResult, type Lesson, type Step } from "@/lib/api";
import { GuidedLesson, LessonOutcome } from "@/components/GuidedLesson";
import { TutorBox } from "@/components/TutorBox";
import { ErrorBox, Loading, Markdown, Sources, StepCard } from "@/components/ui";

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
  const router = useRouter();

  useEffect(() => {
    api.lesson(id, cap, { fromActivityId: retryParam, full }).then(setLesson).catch((e) => setError(e.message));
    api.next(id, 6).then((n) => {
      const doable = n.steps.filter((s) => s.activityId && s.capabilityId === cap);
      setPractice(doable[0] ?? null);
    }).catch(() => {});
  }, [id, cap, retryParam, full]);

  const retry = retryParam ?? lesson?.retryActivityId ?? null;
  const name = lesson?.name ?? cap;
  const guided = !!lesson?.sections?.length;
  const showChallenge = lesson && (!guided || finished);

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

  const presets = [
    { label: "Explain it more simply", question: `Explain the most important idea of ${name} in plain words for a beginner.` },
    { label: "Show me another example", question: `Give a concrete example from the material that shows ${name} in practice.` },
    { label: "Common mistakes", question: `What mistakes do people commonly make with ${name}, and how do you avoid them?` },
  ];

  return (
    <>
      <p className="small muted" style={{ marginBottom: 4 }}>Lesson</p>
      <h1>{name}</h1>
      <ErrorBox error={error} />

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
          <Loading stages={[
            "Finding the parts of the course material you need…",
            "Planning what to ask you first…",
            "Preparing examples and diagrams…",
          ]} />
        </div>
      )}

      {lesson && guided && !finished && (
        <GuidedLesson learnerId={id} capabilityId={cap} hook={lesson.hook}
          sections={lesson.sections!}
          onComplete={(r) => { setOutcome(r); setFinished(true); window.scrollTo(0, 0); }} />
      )}
      {finished && outcome && <LessonOutcome result={outcome} />}

      {lesson && !guided && (
        <div className="card">
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

      {lesson && (
        <TutorBox learnerId={id} capabilityId={cap} presets={presets}
          title="Ask the tutor" placeholder={`Ask anything about ${name}…`} />
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
