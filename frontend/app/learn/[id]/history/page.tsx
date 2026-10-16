"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, param, pct, type EvidenceEntry } from "@/lib/api";
import { ErrorBox, Loading, PageHead, StateBadge } from "@/components/ui";


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
      <PageHead eyebrow="History" title="Your evidence">
        Every answer you gave, how it was judged, and what it changed. Newest first.
      </PageHead>
      {entries.length === 0 && <div className="card"><p className="muted" style={{ margin: 0 }}>No evidence yet — take the diagnosis to start.</p></div>}
      {entries.map((e, i) => (
        <details className="card" key={i}>
          <summary>
            <strong>{e.changes.map((c) => c.name).join(", ") || e.activityId}</strong>
            <div className="meta" style={{ marginTop: 4 }}>
              <span>Attempt {e.attempt}</span>
              <span>{new Date(e.createdAt).toLocaleString()}</span>
              <span>
                {e.criteria.filter((c) => c.verdict === "met").length} of {e.criteria.length} points met
                {e.criteria.some((c) => c.verdict === "partial") &&
                  `, ${e.criteria.filter((c) => c.verdict === "partial").length} partly`}
              </span>
            </div>
          </summary>
          <div style={{ marginTop: 12 }}>
            <ul className="list">
              {e.changes.map((c) => (
                <li key={c.capabilityId} className="spread" style={{ alignItems: "flex-start" }}>
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
