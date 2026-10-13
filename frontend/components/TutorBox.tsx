"use client";

import { useState } from "react";
import { api, type TutorAnswer } from "@/lib/api";
import { ErrorBox, Loading, Markdown, Sources } from "./ui";

/** Free questions, answered only from the curated course material. */
export function TutorBox({ learnerId, placeholder }: { learnerId: string; placeholder?: string }) {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<TutorAnswer[]>([]);

  async function ask() {
    const q = question.trim();
    if (!q) return;
    setBusy(true);
    setError(null);
    try {
      const a = await api.tutor(learnerId, q);
      setAnswers((cur) => [a, ...cur]);
      setQuestion("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>Ask the tutor</h2>
      <p className="small muted">Answers come only from the course material, with sources. If it isn&apos;t covered, the tutor says so.</p>
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <input type="text" value={question} disabled={busy}
          placeholder={placeholder ?? "e.g. Why does adding an index make a query faster?"}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") ask(); }} />
        <button className="btn" disabled={busy || !question.trim()} onClick={ask}>Ask</button>
      </div>
      <ErrorBox error={error} />
      {busy && <Loading stages={["Searching the course material…", "Checking it covers your question…", "Writing a grounded answer…"]} />}
      {answers.map((a, i) => (
        <div key={i} style={{ borderTop: "1px solid var(--border)", marginTop: 16, paddingTop: 14 }}>
          <p><strong>Q: {a.question}</strong></p>
          {a.answered ? <Markdown text={a.answer} /> : <div className="notice">{a.answer}</div>}
          {a.answered && <Sources sources={a.sources} />}
        </div>
      ))}
    </div>
  );
}
