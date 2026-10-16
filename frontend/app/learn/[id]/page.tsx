"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, param, type NextActivities, type SkillProfile, type SkillState } from "@/lib/api";
import { ErrorBox, Loading, PageHead, StateBadge, StateLabel, StepCard } from "@/components/ui";

const KIND: Record<string, string> = {
  lesson: "Lesson checks", practice: "Practice", challenge: "Challenge", diagnosis: "Diagnosis",
};
const ORDER: Record<SkillState, number> = { developing: 0, mastered: 1, unknown: 2 };

export default function Home() {
  const id = param(useParams().id);
  const base = `/learn/${encodeURIComponent(id)}`;
  const [profile, setProfile] = useState<SkillProfile | null>(null);
  const [next, setNext] = useState<NextActivities | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.profile(id), api.next(id)])
      .then(([p, n]) => { setProfile(p); setNext(n); })
      .catch((e) => setError(e.message));
  }, [id]);

  if (error) return <ErrorBox error={error} />;
  if (!profile || !next) return <Loading stages={["Loading your plan…"]} />;

  const { learner } = profile;
  const [top, ...others] = next.steps;
  const assessed = [...profile.skills.filter((s) => s.state !== "unknown")]
    .sort((a, b) => ORDER[a.state] - ORDER[b.state]);
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
    <>
      <PageHead eyebrow={learner.course.name} title={`Hi ${learner.name}`}>
        Working toward <strong>{learner.goal ?? "no goal yet"}</strong>
      </PageHead>

      {top ? <StepCard learnerId={id} step={top} primary label="Your next step" />
        : <div className="card"><p className="muted" style={{ margin: 0 }}>Nothing to do right now.</p></div>}

      {others.length > 0 && (
        <>
          <div className="section-title"><h2>Other possible next steps</h2></div>
          {others.map((s, i) => <StepCard key={i} learnerId={id} step={s} />)}
        </>
      )}

      <div className="grid2" style={{ marginTop: 28 }}>
        <section className="card" aria-labelledby="status-h">
          <div className="spread" style={{ marginBottom: 6 }}>
            <h2 id="status-h" style={{ margin: 0 }}>Skill status</h2>
            <Link href={`${base}/profile`} className="small">Skill profile →</Link>
          </div>
          <div className="counts">
            <div className="count"><strong>{learner.counts.mastered}</strong><StateLabel state="mastered" /></div>
            <div className="count"><strong>{learner.counts.developing}</strong><StateLabel state="developing" /></div>
            <div className="count"><strong>{learner.counts.unknown}</strong><StateLabel state="unknown" /></div>
          </div>
          {assessed.length ? (
            <ul className="list skill-rows">
              {assessed.slice(0, 6).map((s) => (
                <li key={s.capabilityId}><span className="name">{s.name}</span><StateBadge state={s.state} /></li>
              ))}
            </ul>
          ) : (
            <p className="small muted" style={{ margin: 0 }}>
              No skill has evidence yet. &ldquo;Not verified yet&rdquo; isn&apos;t a weakness — there&apos;s simply nothing to go on.
            </p>
          )}
        </section>

        <section className="card" aria-labelledby="evidence-h">
          <div className="spread" style={{ marginBottom: 6 }}>
            <h2 id="evidence-h" style={{ margin: 0 }}>Recent evidence</h2>
            <Link href={`${base}/history`} className="small">History →</Link>
          </div>
          {latest.length ? (
            <ul className="list evidence-rows">
              {latest.map((e) => (
                <li key={`${e.title}|${e.createdAt}`}>
                  <strong>{e.kind === "lesson" ? KIND.lesson : e.title}</strong>
                  <div className="meta">
                    <span>{e.skills.join(", ")}</span>
                    <span>{e.met} of {e.total} {e.kind === "lesson" ? "concepts shown" : "points met"}</span>
                    <span>{new Date(e.createdAt).toLocaleDateString()}</span>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="small muted" style={{ margin: 0 }}>No answers yet. Your next step will start your evidence.</p>
          )}
        </section>
      </div>

      {next.heldBack.length > 0 && (
        <details className="card quiet">
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
