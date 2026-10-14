"use client";

import { useState } from "react";
import { api, type TutorAnswer } from "@/lib/api";
import { ErrorBox, Loading, Markdown, Sources } from "./ui";

/** Free questions, answered only from the curated course material. */
export function TutorBox({
  learnerId, capabilityId, presets = [], placeholder, title = "Ask the tutor",
}: {
  learnerId: string;
  /** Keeps answers inside one capability's material, e.g. during its lesson. */
  capabilityId?: string;
  /** One-click follow-ups, e.g. "Show me an example". */
  presets?: { label: string; question: string }[];
  placeholder?: string;
  title?: string;
}) {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<(TutorAnswer & { label?: string })[]>([]);

  async function ask(q: string, label?: string) {
    q = q.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);
    try {
      const a = await api.tutor(learnerId, q, capabilityId);
      setAnswers((cur) => [{ ...a, label }, ...cur]);
      if (!label) setQuestion("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>{title}</h2>
      <p className="small muted">
        Answers come from your course material, with sources. If your material doesn&apos;t cover a
        course question, you get a clearly labelled general explanation; questions outside the course are declined.
      </p>
      {presets.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          {presets.map((p) => (
            <button key={p.label} className="chip" disabled={busy} onClick={() => ask(p.question, p.label)}>
              {p.label}
            </button>
          ))}
        </div>
      )}
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <input type="text" value={question} disabled={busy}
          placeholder={placeholder ?? "e.g. Why does adding an index make a query faster?"}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") ask(question); }} />
        <button className="btn" disabled={busy || !question.trim()} onClick={() => ask(question)}>Ask</button>
      </div>
      <ErrorBox error={error} />
      {busy && <Loading stages={["Searching the course material…", "Checking it covers your question…", "Writing a grounded answer…"]} />}
      {answers.map((a, i) => (
        <div key={i} style={{ borderTop: "1px solid var(--border)", marginTop: 16, paddingTop: 14 }}>
          <p><strong>{a.label ?? `Q: ${a.question}`}</strong></p>
          {a.kind === "general" ? (
            <div className="general-answer">
              <div className="general-label">⚠ Not in your course material — general explanation</div>
              <Markdown text={a.answer} />
              <div className="small muted">Check your lecture notes: your lecturer may present this differently.</div>
            </div>
          ) : a.answered ? <Markdown text={a.answer} /> : <div className="notice">{a.answer}</div>}
          {a.answered && a.kind === "course" && <Sources sources={a.sources} />}
        </div>
      ))}
    </div>
  );
}
