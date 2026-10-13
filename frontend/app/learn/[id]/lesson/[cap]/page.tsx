"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, param, type Lesson, type Step } from "@/lib/api";
import { TutorBox } from "@/components/TutorBox";
import { ErrorBox, Loading, Markdown, Sources, StepCard } from "@/components/ui";

export default function LessonPage() {
  const params = useParams();
  const id = param(params.id);
  const cap = param(params.cap);
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [practice, setPractice] = useState<Step | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.lesson(id, cap).then(setLesson).catch((e) => setError(e.message));
    // The step to take after reading: practice for this capability if the plan has one.
    api.next(id, 6).then((n) => {
      const doable = n.steps.filter((s) => s.activityId);
      setPractice(doable.find((s) => s.capabilityId === cap) ?? doable[0] ?? null);
    }).catch(() => {});
  }, [id, cap]);

  return (
    <>
      <p className="small muted" style={{ marginBottom: 4 }}>Learn with AI</p>
      <ErrorBox error={error} />
      {!lesson && !error && (
        <Loading stages={["Finding the parts of the course material you need…", "Checking the sources cover it…", "Writing your explanation…"]} />
      )}
      {lesson && (
        <div className="card">
          <h1>{lesson.name}</h1>
          <p className="muted small">{lesson.question}</p>
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

      {lesson && practice && (
        <>
          <h2>Put it into practice</h2>
          <StepCard learnerId={id} step={practice} primary />
        </>
      )}

      <TutorBox learnerId={id} placeholder={lesson ? `Ask anything about ${lesson.name}…` : undefined} />
    </>
  );
}
