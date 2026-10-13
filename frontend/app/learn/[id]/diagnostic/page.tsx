"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, param, type Diagnostic } from "@/lib/api";
import { ActivityRunner } from "@/components/ActivityRunner";
import { ErrorBox, Loading } from "@/components/ui";

export default function DiagnosticPage() {
  const id = param(useParams().id);
  // Fetched once: the diagnostic is re-planned after every answer server-side, so
  // re-fetching mid-way would reshuffle the questions under the learner.
  const [diag, setDiag] = useState<Diagnostic | null>(null);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.diagnostic(id).then(setDiag).catch((e) => setError(e.message));
  }, [id]);

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
        <div className="card highlight">
          <h2>Diagnosis complete</h2>
          <p>Your skill profile now reflects what you demonstrated, not just what you told us.</p>
          <div className="row">
            <Link className="btn" href={`/learn/${encodeURIComponent(id)}`}>See your next activity →</Link>
            <Link className="btn secondary" href={`/learn/${encodeURIComponent(id)}/profile`}>Skill profile</Link>
          </div>
        </div>
      ) : (
        <>
          {target && <p className="small muted">Checking <strong>{target.name}</strong></p>}
          <ActivityRunner
            key={activity.id}
            learnerId={id}
            activity={activity}
            showNext={false}
            doneLabel={index + 1 < total ? "Next question" : "Finish diagnosis"}
            onDone={() => setIndex((i) => i + 1)}
          />
        </>
      )}
    </>
  );
}
