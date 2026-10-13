"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, param, pct, type EvidenceEntry } from "@/lib/api";
import { ErrorBox, Loading, StateBadge } from "@/components/ui";

const MARK = { met: "✓", partial: "△", unmet: "✗" } as const;

export default function HistoryPage() {
  const id = param(useParams().id);
  const [entries, setEntries] = useState<EvidenceEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.evidence(id).then((e) => setEntries([...e].reverse())).catch((e) => setError(e.message));
  }, [id]);

  if (error) return <ErrorBox error={error} />;
  if (!entries) return <Loading stages={["Loading…"]} />;

  return (
    <>
      <h1>Your evidence</h1>
      <p className="muted">Every answer you gave, how it was judged, and what it changed. Newest first.</p>
      {entries.length === 0 && <p className="muted">No evidence yet — take the diagnosis to start.</p>}
      {entries.map((e, i) => (
        <details className="card" key={i}>
          <summary>
            <strong>{e.activityId}</strong>{" "}
            <span className="small muted">
              attempt {e.attempt} · {new Date(e.createdAt).toLocaleString()} ·{" "}
              {e.criteria.map((c) => MARK[c.verdict]).join(" ")}
            </span>
          </summary>
          <div style={{ marginTop: 12 }}>
            <ul className="list">
              {e.changes.map((c) => (
                <li key={c.capabilityId} className="spread">
                  <strong>{c.name}</strong>
                  <span className="row" style={{ gap: 6 }}>
                    <StateBadge state={c.stateBefore} /> {pct(c.masteryBefore)} → <StateBadge state={c.stateAfter} /> {pct(c.masteryAfter)}
                  </span>
                </li>
              ))}
            </ul>
            <h3>Your answer</h3>
            <div className="prompt small">{e.response}</div>
            <h3 style={{ marginTop: 12 }}>Why it changed</h3>
            {e.explanation.split("\n\n").map((p, j) => <p key={j} className="small">{p}</p>)}
          </div>
        </details>
      ))}
    </>
  );
}
