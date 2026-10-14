"use client";

import { Markdown } from "./ui";

export interface Part { label: string; text: string; subs: { label: string; text: string }[] }

const PART = /\(([a-h])\)\s*/g;
const SUB = /\(((?:i|ii|iii|iv|v|vi|vii|viii|ix|x))\)\s*/g;
const NUMBERED = /(?:^|\n)\s*(\d)[.)]\s+/g;

const SEQ: Record<string, string[]> = {
  letters: ["a", "b", "c", "d", "e", "f", "g", "h"],
  roman: ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"],
  digits: ["1", "2", "3", "4", "5", "6", "7", "8", "9"],
};

function splitOn(re: RegExp, text: string): { head: string; items: { label: string; text: string }[] } {
  // Only labels in sequence count: "(d) … check it against (a)" refers back, it isn't a part.
  const all = [...text.matchAll(re)];
  const seq = Object.values(SEQ).find((sq) => all.some((m) => m[1] === sq[0])) ?? [];
  const marks: RegExpMatchArray[] = [];
  for (const m of all) if (m[1] === seq[marks.length]) marks.push(m);
  if (marks.length < 2) return { head: text, items: [] };
  const items = marks.map((m, k) => ({
    label: m[1],
    text: text.slice(m.index! + m[0].length, k + 1 < marks.length ? marks[k + 1].index : undefined).trim(),
  }));
  return { head: text.slice(0, marks[0].index).trim(), items };
}

/** Split an exam-style prompt into parts: "(a) … (b) …" or "1. … 2. …". Sub-items
 *  "(i) … (ii) …" inside a part become a list. Null when the prompt has no parts. */
export function splitParts(prompt: string): { intro: string; parts: Part[] } | null {
  let { head, items } = splitOn(PART, prompt);
  if (!items.length) ({ head, items } = splitOn(NUMBERED, prompt));
  if (items.length < 2) return null;
  return {
    intro: head,
    parts: items.map((it) => {
      const sub = splitOn(SUB, it.text);
      return { label: it.label, text: sub.items.length ? sub.head : it.text, subs: sub.items };
    }),
  };
}

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
            <span className="part-label">{/^\d$/.test(p.label) ? `${p.label})` : `(${p.label})`}</span>
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

export function joinAnswers(parts: Part[], answers: string[]): string {
  return parts.map((p, k) => {
    const label = /^\d$/.test(p.label) ? `${p.label})` : `(${p.label})`;
    return `${label} ${(answers[k] ?? "").trim() || "(no answer)"}`;
  }).join("\n\n");
}
