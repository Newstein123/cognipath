"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { activityHref, api, param, type Lesson, type Step } from "@/lib/api";
import { TutorBox } from "@/components/TutorBox";
import { ErrorBox, Loading, Markdown, Sources, StepCard } from "@/components/ui";

export default function LessonPage() {
  return <Suspense><LessonView /></Suspense>;
}

function LessonView() {
  const params = useParams();
  const id = param(params.id);
  const cap = param(params.cap);
  const retryParam = useSearchParams().get("retry");
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [practice, setPractice] = useState<Step | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const router = useRouter();

  useEffect(() => {
    api.lesson(id, cap).then(setLesson).catch((e) => setError(e.message));
    api.next(id, 6).then((n) => {
      const doable = n.steps.filter((s) => s.activityId && s.capabilityId === cap);
      setPractice(doable[0] ?? null);
    }).catch(() => {});
  }, [id, cap]);

  // The question the learner just got wrong comes first; the engine's record second.
  const retry = retryParam ?? lesson?.retryActivityId ?? null;
  const name = lesson?.name ?? cap;

  async function newChallenge() {
    setGenerating(true);
    setError(null);
    try {
      const a = await api.challenge(id, cap, retry);
      router.push(activityHref(id, a.id));
    } catch (e) {
      setError((e as Error).message);
      setGenerating(false);
    }
  }
  const presets = [
    { label: "Explain it more simply", question: `Explain the most important idea of ${name} in plain words for a beginner.` },
    { label: "Show me an example", question: `Give a concrete example from the material that shows ${name} in practice.` },
    { label: "Common mistakes", question: `What mistakes do people commonly make with ${name}, and how do you avoid them?` },
  ];

  return (
    <>
      <p className="small muted" style={{ marginBottom: 4 }}>Lesson</p>
      <h1>{name}</h1>
      <ErrorBox error={error} />

      {lesson && lesson.missed.length > 0 && (
        <div className="card primary">
          <h3>{lesson.targeted ? "What this lesson fixes" : "What you missed"}</h3>
          <p className="small muted">From your last answer, you didn&apos;t yet show that you:</p>
          <ul style={{ paddingLeft: 20, marginBottom: 0 }}>
            {lesson.missed.map((m) => <li key={m}>{m}</li>)}
          </ul>
          {!lesson.targeted && (
            <p className="small muted" style={{ marginTop: 8, marginBottom: 0 }}>
              The course material doesn&apos;t cover your exact scenario, so this lesson teaches the
              underlying ideas. Keep these points in mind as you read.
            </p>
          )}
        </div>
      )}

      {!lesson && !error && (
        <div className="card">
          <Loading stages={[
            "Finding the parts of the course material you need…",
            "Checking the sources cover what you missed…",
            "Writing your lesson…",
          ]} />
        </div>
      )}

      {lesson && (
        <div className="card">
          <h2>Explanation</h2>
          {lesson.prerequisitesFirst.length > 0 && (
            <div className="notice small">
              This builds on {lesson.prerequisitesFirst.join(", ")}, which you haven&apos;t demonstrated yet.
            </div>
          )}
          {lesson.answered ? (
            <Markdown text={lesson.explanation} />
          ) : (
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

      {lesson && (
        <TutorBox
          learnerId={id} capabilityId={cap} presets={presets}
          title="Still unclear?" placeholder={`Ask anything about ${name}…`}
        />
      )}

      {lesson && (
        <div className="card highlight">
          <h2>Check your understanding</h2>
          <p>
            Cognith will write a <strong>new</strong> challenge from the same course material — a
            different situation, so it tests understanding rather than memory. Your skill
            profile updates from your answer.
          </p>
          <ErrorBox error={generating ? null : error} />
          {generating ? (
            <Loading stages={["Picking the course sections you just read…", "Writing a new situation…", "Checking every criterion is backed by the material…"]} />
          ) : (
            <div className="row">
              <button className="btn" onClick={newChallenge}>Give me a new challenge →</button>
              {retry && (
                <Link className="btn secondary" href={activityHref(id, retry)}>Retry the original question</Link>
              )}
            </div>
          )}
        </div>
      )}

      {lesson && practice && practice.activityId !== retry && (
        <>
          <h3 className="muted">Or practise with a prepared exercise</h3>
          <StepCard learnerId={id} step={practice} />
        </>
      )}
    </>
  );
}
