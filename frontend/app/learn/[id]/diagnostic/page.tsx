"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, param, type Diagnostic, type NextActivities } from "@/lib/api";
import { ActivityRunner } from "@/components/ActivityRunner";
import { ErrorBox, Loading, StepCard } from "@/components/ui";

export default function DiagnosticPage() {
  const id = param(useParams().id);
  // Fetched once: the diagnostic is re-planned after every answer server-side, so
  // re-fetching mid-way would reshuffle the questions under the learner.
  const [diag, setDiag] = useState<Diagnostic | null>(null);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<NextActivities | null>(null);

  useEffect(() => {
    api.diagnostic(id).then(setDiag).catch((e) => setError(e.message));
  }, [id]);

  const finished = diag != null && diag.activities.length > 0 && index >= diag.activities.length;
  useEffect(() => {
    if (finished) api.next(id).then(setPlan).catch((e) => setError(e.message));
  }, [finished, id]);

  if (error) return <ErrorBox error={error} />;
  if (!diag) return <Loading stages={["Choosing what to check…"]} />;

  if (!diag.activities.length) {
    return (
      <div className="card">
        <h2>Nothing to check right now</h2>
        <p className="muted">Everything worth verifying already has evidence.</p>
        <Link className="btn" href={`/learn/${encodeURIComponent(id)}`}>See what&apos;s next →</Link>
      </div>
    );
  }

  const total = diag.activities.length;
  const done = index >= total;
  const activity = diag.activities[Math.min(index, total - 1)];
  const target = diag.targets[Math.min(index, total - 1)];

  return (
    <>
      <div className="spread">
        <h1>Quick diagnosis</h1>
        <span className="muted small">{Math.min(index + 1, total)} of {total} · about {diag.minutes} min</span>
      </div>
      <div className="progress"><span style={{ width: `${(index / total) * 100}%` }} /></div>

      {index === 0 && (
        <div className="card">
          <h3>Why these questions</h3>
          <p className="small muted">
            We don&apos;t give everyone the same exam. These were picked because they are the
            parts of your profile we are taking most on trust.
          </p>
          <ul className="small" style={{ paddingLeft: 20, margin: 0 }}>
            {diag.targets.map((t) => (
              <li key={t.capabilityId}><strong>{t.name}</strong> — {t.notes.join("; ") || "worth checking"}</li>
            ))}
          </ul>
        </div>
      )}

      {done ? (
        <>
          <div className="card">
            <h2>Diagnosis complete — now the learning starts</h2>
            <p>
              Your profile now reflects what you showed, not just what you told us. Instead of a
              full course, Cognith will teach you only the gaps it found, in this order:
            </p>
            <Link href={`/learn/${encodeURIComponent(id)}/profile`} className="small">See your full skill profile →</Link>
          </div>
          {!plan ? <Loading stages={["Planning your first lesson…"]} /> : (
            <>
              {plan.steps.map((s, i) => (
                <StepCard key={i} learnerId={id} step={s} primary={i === 0} />
              ))}
            </>
          )}
        </>
      ) : (
        <>
          {target && <p className="small muted">Checking <strong>{target.name}</strong></p>}
          <ActivityRunner
            key={activity.id}
            learnerId={id}
            activity={activity}
            showNext={false}
            showTeach={false}
            doneLabel={index + 1 < total ? "Next question" : "Finish diagnosis"}
            onDone={() => setIndex((i) => i + 1)}
          />
        </>
      )}
    </>
  );
}
