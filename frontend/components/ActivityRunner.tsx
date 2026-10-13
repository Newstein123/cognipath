"use client";

import { useState } from "react";
import { api, pct, type Activity, type AttemptResult } from "@/lib/api";
import { ErrorBox, Loading, StateBadge, StepCard } from "./ui";

const MARK = { met: "✓", partial: "△", unmet: "✗" } as const;

/** Prompt + rubric + answer box. On submit, shows the judged result in place. */
export function ActivityRunner({
  learnerId, activity, onDone, doneLabel, showNext = true,
}: {
  learnerId: string;
  activity: Activity;
  /** Called after a successful assessment — e.g. to move to the next diagnostic question. */
  onDone?: (result: AttemptResult) => void;
  doneLabel?: string;
  showNext?: boolean;
}) {
  const [response, setResponse] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AttemptResult | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.attempt(learnerId, activity.id, response));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="card">
        <div className="spread">
          <h2 style={{ margin: 0 }}>{activity.title}</h2>
          <span className="muted small">{activity.level} · about {activity.minutes} min</span>
        </div>
        <div className="prompt" style={{ marginTop: 14 }}>{activity.prompt}</div>

        <h3 style={{ marginTop: 18 }}>Assessment criteria</h3>
        <ul className="small" style={{ paddingLeft: 20, marginTop: 0 }}>
          {activity.criteria.map((c) => <li key={c.id}>{c.criterion}</li>)}
        </ul>

        {!result && (
          <>
            <label htmlFor="answer">Your answer</label>
            <textarea
              id="answer" value={response} disabled={busy}
              placeholder="Explain your reasoning. There is no word limit — what matters is the thinking."
              onChange={(e) => setResponse(e.target.value)}
            />
            <ErrorBox error={error} />
            {busy ? (
              <Loading stages={["Reading your answer…", "Judging each criterion…", "Updating your skill profile…"]} />
            ) : (
              <div className="row" style={{ marginTop: 12 }}>
                <button className="btn" disabled={!response.trim()} onClick={submit}>Submit answer</button>
              </div>
            )}
          </>
        )}
      </div>

      {result && (
        <AttemptResultView
          learnerId={learnerId} result={result} showNext={showNext}
          onRetry={() => { setResult(null); }}
          onDone={onDone ? () => onDone(result) : undefined} doneLabel={doneLabel}
        />
      )}
    </div>
  );
}

export function AttemptResultView({
  learnerId, result, onRetry, onDone, doneLabel, showNext,
}: {
  learnerId: string; result: AttemptResult; onRetry: () => void;
  onDone?: () => void; doneLabel?: string; showNext: boolean;
}) {
  const met = result.criteria.filter((c) => c.verdict === "met").length;
  return (
    <>
      <div className="card">
        <div className="spread">
          <h2 style={{ margin: 0 }}>Feedback</h2>
          <span className="muted small">
            Attempt {result.attempt} · {met} of {result.criteria.length} criteria met
          </span>
        </div>
        <ul className="list" style={{ marginTop: 10 }}>
          {result.criteria.map((c) => (
            <li key={c.id}>
              <div className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap" }}>
                <span className={`badge ${c.verdict}`}>{MARK[c.verdict]}</span>
                <div>
                  <div>{c.criterion}</div>
                  <div className="small muted">{c.justification}</div>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <div className="card">
        <h2>How your skills changed</h2>
        <ul className="list">
          {result.changes.map((c) => (
            <li key={c.capabilityId} className="spread">
              <strong>{c.name}</strong>
              <span className="row" style={{ gap: 8 }}>
                <StateBadge state={c.stateBefore} />
                <span className="muted small">{pct(c.masteryBefore)}</span>
                →
                <StateBadge state={c.stateAfter} />
                <span className="small"><strong>{pct(c.masteryAfter)}</strong></span>
              </span>
            </li>
          ))}
        </ul>
        <h3 style={{ marginTop: 14 }}>Why</h3>
        {result.explanation.split("\n\n").map((p, i) => <p key={i}>{p}</p>)}
        <div className="row" style={{ marginTop: 8 }}>
          {onDone && <button className="btn" onClick={onDone}>{doneLabel ?? "Continue"} →</button>}
          <button className="btn secondary" onClick={onRetry}>Try again</button>
        </div>
      </div>

      {showNext && result.next.steps[0] && (
        <>
          <h2>What&apos;s next</h2>
          <StepCard learnerId={learnerId} step={result.next.steps[0]} primary />
        </>
      )}
    </>
  );
}
