"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, param, pct, type Skill, type SkillProfile } from "@/lib/api";
import { ErrorBox, Loading, MasteryBar, StateBadge } from "@/components/ui";

const ORDER = { mastered: 0, developing: 1, unknown: 2 } as const;

export default function ProfilePage() {
  const id = param(useParams().id);
  const [profile, setProfile] = useState<SkillProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.profile(id).then(setProfile).catch((e) => setError(e.message));
  }, [id]);

  if (error) return <ErrorBox error={error} />;
  if (!profile) return <Loading stages={["Loading…"]} />;

  const areas = new Map<string, Skill[]>();
  for (const s of profile.skills) areas.set(s.area, [...(areas.get(s.area) ?? []), s]);

  return (
    <>
      <h1>Your skill profile</h1>
      <p className="muted">
        Based on what you demonstrated — not a generic course sequence. &ldquo;Not verified
        yet&rdquo; is not a weakness; it means we have no evidence either way.
      </p>
      <p className="small muted">
        Bar = evidence. Tick mark = what you rated yourself at the start.
      </p>

      {[...areas.entries()].map(([area, skills]) => (
        <div className="card" key={area}>
          <h2 style={{ textTransform: "capitalize" }}>{area.replace(/-/g, " ")}</h2>
          <ul className="list">
            {[...skills].sort((a, b) => ORDER[a.state] - ORDER[b.state]).map((s) => (
              <li key={s.capabilityId}>
                <div className="spread">
                  <strong>{s.name}</strong>
                  <span className="row" style={{ gap: 8 }}>
                    <span className="small muted">{pct(s.mastery)}</span>
                    <StateBadge state={s.state} />
                  </span>
                </div>
                <div style={{ margin: "8px 0" }}><MasteryBar skill={s} /></div>
                <div className="small muted">{s.explanation}</div>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </>
  );
}
