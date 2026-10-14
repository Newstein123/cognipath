"use client";

import { Markdown } from "./ui";

import { partLabel, type Part } from "@/lib/parts";

export { joinAnswers, splitParts } from "@/lib/parts";

/** One answer box per part; answers join as "(a) …\n\n(b) …" for marking. */
export function MultiPartAnswer({ intro, parts, answers, onChange, disabled }: {
  intro: string; parts: Part[]; answers: string[];
  onChange: (answers: string[]) => void; disabled: boolean;
}) {
  return (
    <div className="multipart">
      {intro && <div className="prompt md" style={{ whiteSpace: "normal" }}><Markdown text={intro} /></div>}
      {parts.map((p, k) => (
        <div className="part" key={p.label}>
          <div className="part-q">
            <span className="part-label">{partLabel(p)}</span>
            <div style={{ minWidth: 0 }}>
              <Markdown text={p.text} />
              {p.subs.length > 0 && (
                <ol className="subs">
                  {p.subs.map((s) => (
                    <li key={s.label}><span className="sub-label">({s.label})</span> <Markdown text={s.text} /></li>
                  ))}
                </ol>
              )}
            </div>
          </div>
          <textarea value={answers[k] ?? ""} disabled={disabled} style={{ minHeight: p.subs.length ? 110 : 70 }}
            placeholder={p.subs.length ? `Answer each of ${p.subs.map((s) => `(${s.label})`).join(", ")} with a one-line reason` : "Your answer, with working"}
            onChange={(e) => onChange(parts.map((_, j) => (j === k ? e.target.value : answers[j] ?? "")))} />
        </div>
      ))}
    </div>
  );
}
