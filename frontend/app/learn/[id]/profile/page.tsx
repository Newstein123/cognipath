"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, param, pct, stepHref, type Skill, type SkillProfile } from "@/lib/api";
import { ErrorBox, Loading, MasteryBar, StateBadge, StepCard } from "@/components/ui";

const ORDER = { mastered: 0, developing: 1, unknown: 2 } as const;
const KIND: Record<string, string> = {
  lesson: "Lesson tasks", practice: "Practice question", challenge: "Challenge", diagnosis: "Diagnosis",
};

/** A profile that explains: what's been shown, what's uncertain, and what to do next. */
export default function ProfilePage() {
  const id = param(useParams().id);
  const [profile, setProfile] = useState<SkillProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.profile(id).then(setProfile).catch((e) => setError(e.message));
  }, [id]);

  if (error) return <ErrorBox error={error} />;
  if (!profile) return <Loading stages={["Loading your evidence…"]} />;

  const areas = new Map<string, Skill[]>();
  for (const s of profile.skills) areas.set(s.area, [...(areas.get(s.area) ?? []), s]);
  const shown = profile.skills.filter((s) => s.evidence.length > 0);
  const c = profile.learner.counts;

  return (
    <>
      <h1>Your skill profile</h1>
      <p className="muted">
        Built from what you&apos;ve <strong>shown</strong>, not what you&apos;ve read. You have evidence on{" "}
        {shown.length} of {profile.skills.length} skills: {c.mastered} mastered, {c.developing} developing.
        &ldquo;Not verified yet&rdquo; isn&apos;t a weakness — there&apos;s simply no evidence either way.
      </p>

      {profile.nextStep && (
        <>
          <h2>What to do next</h2>
          <StepCard learnerId={id} step={profile.nextStep} primary />
        </>
      )}

      {[...areas.entries()].map(([area, skills]) => (
        <div className="card" key={area}>
          <h2 style={{ textTransform: "capitalize" }}>{area.replace(/-/g, " ")}</h2>
          <ul className="list">
            {[...skills].sort((a, b) => ORDER[a.state] - ORDER[b.state]).map((s) => (
              <li key={s.capabilityId}>
                <div className="spread">
                  <strong>{s.name}</strong>
                  <span className="row" style={{ gap: 8 }}>
                    {s.coverage && (
                      <span className="small muted">
                        {s.coverage.covered
                          ? `covered ${s.coverage.covered}/${s.coverage.total} · shown ${s.coverage.demonstrated}`
                          : `${s.coverage.total} ideas`}
                      </span>
                    )}
                    <span className="small muted">{pct(s.mastery)}</span>
                    <StateBadge state={s.state} />
                  </span>
                </div>
                <div style={{ margin: "8px 0" }}><MasteryBar skill={s} /></div>
                <div className="small muted">{s.explanation}</div>

                {(s.evidence.length > 0 || s.uncertain.length > 0 || s.nextStep) && (
                  <details style={{ marginTop: 8 }}>
                    <summary className="small">Evidence and next step</summary>
                    <div className="grid2" style={{ marginTop: 8 }}>
                      <div>
                        <div className="example-label">WHAT YOU&apos;VE SHOWN</div>
                        {s.evidence.length === 0 ? <p className="small muted">Nothing yet.</p> : (
                          <ul className="small" style={{ paddingLeft: 18, margin: 0 }}>
                            {s.evidence.map((e, k) => (
                              <li key={k}>
                                <strong>{KIND[e.kind] ?? e.kind}</strong>{e.kind !== "lesson" && <> — {e.title}</>}:{" "}
                                {e.met} of {e.total} {e.kind === "lesson" ? "concepts shown" : "points met"}
                                {!!e.partial && <>, {e.partial} partly</>}
                                {e.assisted && <span className="muted"> (with help)</span>}
                                <span className="muted"> · {new Date(e.createdAt).toLocaleDateString()}</span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                      <div>
                        <div className="example-label">STILL UNCERTAIN</div>
                        {s.uncertain.length === 0 ? (
                          <p className="small muted">
                            {s.evidence.length ? "Nothing your latest attempt missed." : "Not assessed yet."}
                          </p>
                        ) : (
                          <ul className="small" style={{ paddingLeft: 18, margin: 0 }}>
                            {s.uncertain.map((u) => <li key={u}>{u}</li>)}
                          </ul>
                        )}
                      </div>
                    </div>
                    {s.nextStep && (
                      <div className="row" style={{ marginTop: 10 }}>
                        <span className="small"><strong>Next:</strong> {s.nextStep.title}</span>
                        {stepHref(id, s.nextStep) && (
                          <Link className="btn secondary" href={stepHref(id, s.nextStep)!}>Start →</Link>
                        )}
                      </div>
                    )}
                  </details>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </>
  );
}
