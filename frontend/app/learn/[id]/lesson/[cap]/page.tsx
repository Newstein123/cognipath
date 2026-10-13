"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { activityHref, api, param, type Lesson, type Step } from "@/lib/api";
import { Diagram } from "@/components/Diagram";
import { Quiz } from "@/components/Quiz";
import { TutorBox } from "@/components/TutorBox";
import { ErrorBox, Loading, Markdown, Sources, StepCard } from "@/components/ui";

export default function LessonPage() {
  return <Suspense><LessonView /></Suspense>;
}

/** A lesson in three parts: 1 Learn (sections with examples and diagrams), 2 Quiz
 *  (practice, instant feedback), 3 Challenge (the written answer that counts). */
function LessonView() {
  const params = useParams();
  const id = param(params.id);
  const cap = param(params.cap);
  const retryParam = useSearchParams().get("retry");
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [practice, setPractice] = useState<Step | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [stage, setStage] = useState<"learn" | "quiz" | "done">("learn");
  const [score, setScore] = useState<number | null>(null);
  const router = useRouter();

  useEffect(() => {
    api.lesson(id, cap).then(setLesson).catch((e) => setError(e.message));
    api.next(id, 6).then((n) => {
      const doable = n.steps.filter((s) => s.activityId && s.capabilityId === cap);
      setPractice(doable[0] ?? null);
    }).catch(() => {});
  }, [id, cap]);

  const retry = retryParam ?? lesson?.retryActivityId ?? null;
  const name = lesson?.name ?? cap;
  const structured = !!lesson?.sections?.length;
  const hasQuiz = !!lesson?.quiz?.length;
  const showChallenge = lesson && (!structured || !hasQuiz || stage === "done");

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
    { label: "Show me another example", question: `Give a concrete example from the material that shows ${name} in practice.` },
    { label: "Common mistakes", question: `What mistakes do people commonly make with ${name}, and how do you avoid them?` },
  ];

  const steps = [
    { key: "learn", label: "1 · Learn" },
    { key: "quiz", label: "2 · Quiz" },
    { key: "done", label: "3 · Challenge" },
  ] as const;

  return (
    <>
      <p className="small muted" style={{ marginBottom: 4 }}>Lesson</p>
      <h1>{name}</h1>
      {structured && hasQuiz && (
        <div className="row" style={{ gap: 6, marginBottom: 14 }}>
          {steps.map((s) => (
            <span key={s.key} className={`badge ${stage === s.key ? "kind" : "unknown"}`}>{s.label}</span>
          ))}
        </div>
      )}
      <ErrorBox error={error} />

      {lesson && lesson.missed.length > 0 && stage === "learn" && (
        <div className="card primary">
          <h3>{lesson.targeted ? "What this lesson fixes" : "What you missed"}</h3>
          <p className="small muted">From your last answer, you didn&apos;t yet show that you:</p>
          <ul style={{ paddingLeft: 20, marginBottom: 0 }}>
            {lesson.missed.map((m) => <li key={m}>{m}</li>)}
          </ul>
        </div>
      )}

      {!lesson && !error && (
        <div className="card">
          <Loading stages={[
            "Finding the parts of the course material you need…",
            "Planning the lesson and its examples…",
            "Drawing the diagrams…",
            "Writing your quiz…",
          ]} />
        </div>
      )}

      {/* ---- 1 · Learn ---------------------------------------------------------- */}
      {lesson && structured && stage === "learn" && (
        <>
          {lesson.hook && <p className="hook" style={{ fontSize: 16 }}>{lesson.hook}</p>}
          {lesson.prerequisitesFirst.length > 0 && (
            <div className="notice small">
              This builds on {lesson.prerequisitesFirst.join(", ")}, which you haven&apos;t covered yet.
            </div>
          )}
          {lesson.sections!.map((sec, i) => (
            <section className="card" key={i}>
              <h2><span className="section-n">{i + 1}</span>{sec.title}</h2>
              <Markdown text={sec.explanation} />
              <Diagram d={sec.diagram} />
              <div className="example">
                <div className="example-label">WORKED EXAMPLE</div>
                <Markdown text={sec.example} />
              </div>
              {sec.sources.length > 0 && (
                <p className="small muted" style={{ margin: "8px 0 0" }}>From: {sec.sources.join("; ")}</p>
              )}
            </section>
          ))}
          <TutorBox learnerId={id} capabilityId={cap} presets={presets}
            title="Still unclear?" placeholder={`Ask anything about ${name}…`} />
          {hasQuiz && (
            <div className="card highlight">
              <h2>Ready? Test yourself</h2>
              <p className="muted">{lesson.quiz!.length} quick questions with instant feedback. Practice only — they don&apos;t change your profile.</p>
              <button className="btn" onClick={() => { setStage("quiz"); window.scrollTo(0, 0); }}>Start the quiz →</button>
            </div>
          )}
        </>
      )}

      {/* ---- 2 · Quiz ----------------------------------------------------------- */}
      {lesson && structured && stage === "quiz" && (
        <>
          <Quiz questions={lesson.quiz!} onFinish={(c) => { setScore(c); setStage("done"); window.scrollTo(0, 0); }} />
          <button className="btn secondary" onClick={() => setStage("learn")}>← Back to the lesson</button>
        </>
      )}

      {lesson && structured && stage === "done" && score !== null && (
        <div className={score === lesson.quiz!.length ? "card highlight" : "card"}>
          <h2>Quiz: {score} of {lesson.quiz!.length} right</h2>
          <p className="muted" style={{ marginBottom: 8 }}>
            {score === lesson.quiz!.length
              ? "Great. Now prove it on a question you haven't seen — that's what counts."
              : "Worth a second look at the lesson before the challenge."}
          </p>
          <div className="row">
            <button className="btn secondary" onClick={() => setStage("learn")}>Review the lesson</button>
            <button className="btn secondary" onClick={() => setStage("quiz")}>Retake the quiz</button>
          </div>
        </div>
      )}

      {/* ---- fallback: plain explanation ---------------------------------------- */}
      {lesson && !structured && (
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
      {lesson && !structured && (
        <TutorBox learnerId={id} capabilityId={cap} presets={presets}
          title="Still unclear?" placeholder={`Ask anything about ${name}…`} />
      )}

      {/* ---- 3 · Challenge ------------------------------------------------------ */}
      {showChallenge && (
        <div className="card highlight">
          <h2>Challenge</h2>
          <p>
            A <strong>new</strong> question written from the same course material — a situation you
            haven&apos;t seen. Work it on paper, then type your answer. This one updates your skill profile.
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
