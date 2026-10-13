"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, param, type NextActivities, type SkillProfile } from "@/lib/api";
import { ErrorBox, Loading, StepCard } from "@/components/ui";

export default function Home() {
  const id = param(useParams().id);
  const [profile, setProfile] = useState<SkillProfile | null>(null);
  const [next, setNext] = useState<NextActivities | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.profile(id), api.next(id)])
      .then(([p, n]) => { setProfile(p); setNext(n); })
      .catch((e) => setError(e.message));
  }, [id]);

  if (error) return <ErrorBox error={error} />;
  if (!profile || !next) return <Loading stages={["Loading…"]} />;

  const { learner } = profile;
  const [top, ...others] = next.steps;
  const verified = learner.counts.mastered + learner.counts.developing;

  return (
    <>
      <h1>Hi {learner.name}</h1>
      <p className="muted">
        Working toward <strong>{learner.goal ?? "no goal yet"}</strong>
      </p>

      <div className="card">
        <div className="spread">
          <div>
            <strong>{learner.counts.mastered}</strong> mastered ·{" "}
            <strong>{learner.counts.developing}</strong> developing ·{" "}
            <strong>{learner.counts.unknown}</strong> not verified yet
          </div>
          <Link href={`/learn/${encodeURIComponent(id)}/profile`}>See skill profile →</Link>
        </div>
        <div className="progress"><span style={{ width: `${(verified / learner.counts.total) * 100}%` }} /></div>
        <p className="small muted" style={{ whiteSpace: "pre-line", margin: 0 }}>{profile.position}</p>
      </div>

      <h2>Recommended for you</h2>
      {top ? <StepCard learnerId={id} step={top} primary /> : <p className="muted">Nothing to do right now.</p>}

      {others.length > 0 && (
        <>
          <h3 className="muted" style={{ marginTop: 22 }}>Other possible next steps</h3>
          {others.map((s, i) => <StepCard key={i} learnerId={id} step={s} />)}
        </>
      )}

      {next.heldBack.length > 0 && (
        <details className="card">
          <summary><strong>Held back for now</strong> <span className="small muted">({next.heldBack.length}) — and why</span></summary>
          <ul className="list" style={{ marginTop: 8 }}>
            {next.heldBack.map((h, i) => (
              <li key={i}><strong>{h.name}</strong> <span className="small muted">— {h.reason}</span></li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}
