"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, lessonHref, pct, type Activity, type AttemptResult } from "@/lib/api";
import { GuidedHelp } from "./GuidedHelp";
import { joinAnswers, MultiPartAnswer, splitParts } from "./MultiPart";
import { ErrorBox, Loading, Markdown, StateBadge, StepCard } from "./ui";

const MARK = { met: "✓", partial: "△", unmet: "✗" } as const;

/** An unsent answer survives a failed submit and a page refresh (this tab only). */
type Draft = { response: string; parts: string[] };
const draftKey = (learnerId: string, activityId: string) => `cognith-draft:${learnerId}:${activityId}`;
function readDraft(key: string): Draft | null {
  try { return JSON.parse(sessionStorage.getItem(key) ?? "null"); } catch { return null; }
}
function writeDraft(key: string, draft: Draft | null) {
  try {
    if (draft && (draft.response.trim() || draft.parts.some((a) => a?.trim()))) sessionStorage.setItem(key, JSON.stringify(draft));
    else sessionStorage.removeItem(key);
  } catch { /* storage unavailable: the answer still lives in this page */ }
}

/** Prompt + rubric + answer box. On submit, shows the judged result in place. */
export function ActivityRunner({
  learnerId, activity, onDone, doneLabel, showNext = true, showTeach = true,
}: {
  learnerId: string;
  activity: Activity;
  /** Called after a successful assessment — e.g. to move to the next diagnostic question. */
  onDone?: (result: AttemptResult) => void;
  doneLabel?: string;
  showNext?: boolean;
  /** Off during the diagnosis: leaving mid-way would lose the learner's place. */
  showTeach?: boolean;
}) {
  const key = draftKey(learnerId, activity.id);
  const [response, setResponse] = useState(() => readDraft(key)?.response ?? "");
  // Multi-part questions — "(a) … (b) …" — get one answer box per part.
  const split = useMemo(() => splitParts(activity.prompt), [activity.prompt]);
  const [partAnswers, setPartAnswers] = useState<string[]>(() => readDraft(key)?.parts ?? []);
  const answerText = split ? joinAnswers(split.parts, partAnswers) : response;
  const hasAnswer = split ? partAnswers.some((a) => a?.trim()) : !!response.trim();
  const blank = split ? split.parts.filter((_, k) => !partAnswers[k]?.trim()).map((p) => p.label) : [];
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AttemptResult | null>(null);
  // Guided-help requests so far; sent with the answer, which then counts as assisted.
  const [helpUsed, setHelpUsed] = useState(0);
  useEffect(() => { if (!result) writeDraft(key, { response, parts: partAnswers }); }, [key, response, partAnswers, result]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.attempt(learnerId, activity.id, answerText, helpUsed));
      writeDraft(key, null);
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
        {!split && (
          <div className="prompt md" style={{ marginTop: 14, whiteSpace: "normal" }}><Markdown text={activity.prompt} /></div>
        )}

        {/* Criteria often state the expected answer, so they are revealed only in the
            feedback, each with its verdict. */}
        <p className="small muted" style={{ marginTop: 14 }}>
          Marked on {activity.criteria.length} points, shown with your feedback after you submit.
          Show your working: method counts, not just the final answer.
        </p>

        {!result && (
          <>
            {split ? (
              <MultiPartAnswer intro={split.intro} parts={split.parts} answers={partAnswers}
                onChange={setPartAnswers} disabled={busy} />
            ) : (
              <>
                <label htmlFor="answer">Your answer</label>
                <textarea
                  id="answer" value={response} disabled={busy}
                  placeholder="Explain your reasoning. There is no word limit — what matters is the thinking."
                  onChange={(e) => setResponse(e.target.value)}
                />
              </>
            )}
            <ErrorBox error={error} />
            {busy ? (
              <Loading stages={["Marking your answer against each point…"]} />
            ) : (
              <div className="row" style={{ marginTop: 12 }}>
                <button className="btn" disabled={!hasAnswer} onClick={submit}>{error ? "Try again" : "Submit answer"}</button>
                {split && hasAnswer && blank.length > 0 && (
                  <span className="small muted">Not answered yet: {blank.map((b) => `(${b})`).join(", ")}</span>
                )}
                {helpUsed > 0 && <span className="small muted">Submitted with help — counts as assisted.</span>}
              </div>
            )}
          </>
        )}
      </div>

      {/* No help during the diagnosis: it measures where the learner starts. */}
      {!result && activity.type !== "diagnostic" && (
        <GuidedHelp learnerId={learnerId} activityId={activity.id} onUse={setHelpUsed} />
      )}

      {result && (
        <AttemptResultView
          learnerId={learnerId} activityId={activity.id} result={result} showNext={showNext} showTeach={showTeach}
          onRetry={() => { setResult(null); }}
          onDone={onDone ? () => onDone(result) : undefined} doneLabel={doneLabel}
        />
      )}
    </div>
  );
}

export function AttemptResultView({
  learnerId, activityId, result, onRetry, onDone, doneLabel, showNext, showTeach,
}: {
  learnerId: string; activityId: string; result: AttemptResult; onRetry: () => void;
  onDone?: () => void; doneLabel?: string; showNext: boolean; showTeach: boolean;
}) {
  const met = result.criteria.filter((c) => c.verdict === "met").length;
  const improved = result.changes.filter(
    (c) => c.masteryBefore != null && c.masteryAfter > c.masteryBefore + 0.005);
  return (
    <>
      {improved.length > 0 && (
        <div className="card highlight">
          <h2 style={{ marginBottom: 4 }}>You improved</h2>
          {improved.map((c) => (
            <div key={c.capabilityId}>
              <strong>{c.name}</strong>: {pct(c.masteryBefore)} → <strong>{pct(c.masteryAfter)}</strong>
              {c.stateAfter !== c.stateBefore && <> · now <StateBadge state={c.stateAfter} /></>}
            </div>
          ))}
        </div>
      )}
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
                <div className="md-inline" style={{ minWidth: 0 }}>
                  <Markdown text={c.criterion} />
                  <div className="small muted"><Markdown text={c.justification} /></div>
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

      {showTeach && result.teach && (
        <div className="card primary">
          <h2>Learn what you missed</h2>
          <p className="muted small">Before moving on, here&apos;s the part of {result.teach.name} this answer didn&apos;t cover:</p>
          <ul style={{ paddingLeft: 20 }}>
            {result.teach.missed.slice(0, 3).map((m) => <li key={m}>{m}</li>)}
          </ul>
          <Link className="btn"
            href={lessonHref(learnerId, result.teach.capabilityId, activityId)}>
            Teach me {result.teach.name} →
          </Link>
          <p className="small muted" style={{ marginTop: 8, marginBottom: 0 }}>
            You&apos;ll get a short lesson from the course material, then try this question again.
          </p>
        </div>
      )}

      {showNext && result.next.steps[0] && (
        <>
          <h2>What&apos;s next</h2>
          <StepCard learnerId={learnerId} step={result.next.steps[0]} primary />
        </>
      )}
      {showNext && (
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <Link className="btn secondary" href={`/learn/${encodeURIComponent(learnerId)}`}>
            See my full plan →
          </Link>
        </div>
      )}
    </>
  );
}
