// Splitting exam-style prompts into parts. Pure functions, no React, so they can be
// tested on every question in every course (see scripts/check-parts.mjs).

export interface SubPart { label: string; text: string }
export interface Part { label: string; text: string; subs: SubPart[] }

// A label only counts when it stands on its own — at the start or after whitespace or
// a colon. "f(c)", "x(i)" and "P(a)" are notation, not parts.
const PART = /(?<=^|[\s:])\(([a-h])\)(?=\s)/g;
const SUB = /(?<=^|[\s:])\(((?:i|ii|iii|iv|v|vi|vii|viii|ix|x))\)(?=\s)/g;
const NUMBERED = /(?:^|\n)\s*(\d)[.)]\s+/g;

const SEQ: string[][] = [
  ["a", "b", "c", "d", "e", "f", "g", "h"],
  ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"],
  ["1", "2", "3", "4", "5", "6", "7", "8", "9"],
];

function splitOn(re: RegExp, text: string): { head: string; items: SubPart[] } {
  // Only labels in sequence count: "(d) … check it against (a)" refers back.
  const all = [...text.matchAll(re)];
  const seq = SEQ.find((sq) => all.some((m) => m[1] === sq[0])) ?? [];
  const marks: RegExpMatchArray[] = [];
  for (const m of all) if (m[1] === seq[marks.length]) marks.push(m);
  if (marks.length < 2) return { head: text, items: [] };
  const items = marks.map((m, k) => ({
    label: m[1],
    text: text.slice(m.index! + m[0].length, k + 1 < marks.length ? marks[k + 1].index : undefined).trim(),
  }));
  return { head: text.slice(0, marks[0].index).trim(), items };
}

/** "(a) … (b) …" or "1. … 2. …" → parts; "(i) … (ii) …" inside a part → sub-items.
 *  Null when the prompt has fewer than two parts. */
export function splitParts(prompt: string): { intro: string; parts: Part[] } | null {
  let { head, items } = splitOn(PART, prompt);
  let outro = "";
  if (!items.length) {
    ({ head, items } = splitOn(NUMBERED, prompt));
    if (items.length >= 2) {
      // Text after a numbered list belongs to the question, not to its last item.
      const last = items[items.length - 1];
      const nl = last.text.indexOf("\n");
      if (nl > 0) { outro = last.text.slice(nl).trim(); last.text = last.text.slice(0, nl).trim(); }
      // Short numbered lines are parts only when the question asks about each one
      // ("For each action…"); otherwise they are data, e.g. an argument's premises.
      if (items.some((it) => it.text.length < 25) && !/\bfor each\b|\beach (one|of)\b/i.test(outro)) return null;
    }
  }
  if (items.length < 2) return null;
  const parts: Part[] = items.map((it) => {
    const sub = splitOn(SUB, it.text);
    return { label: it.label, text: sub.items.length ? sub.head : it.text, subs: sub.items };
  });
  // The instruction after the list leads; anything further it asks gets its own box.
  const sentences = outro.split(/(?<=[.?])\s+/);
  const isExtra = (q: string) => !/\bfor each\b|\beach (one|of)\b/i.test(q)
    && (q.includes("?") || /^then\b/i.test(q));
  const extra = sentences.filter(isExtra).join(" ");
  const lead = sentences.filter((q) => !isExtra(q)).join(" ");
  if (extra) parts.push({ label: "+", text: extra, subs: [] });
  return { intro: [head, lead].filter(Boolean).join("\n\n"), parts };
}

export const partLabel = (p: { label: string }) =>
  p.label === "+" ? "Also" : /^\d$/.test(p.label) ? `${p.label})` : `(${p.label})`;

export function joinAnswers(parts: Part[], answers: string[]): string {
  return parts.map((p, k) => `${partLabel(p)} ${(answers[k] ?? "").trim() || "(no answer)"}`).join("\n\n");
}
