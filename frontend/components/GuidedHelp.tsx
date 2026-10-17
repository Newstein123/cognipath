"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Loading, Markdown } from "./ui";

const LEVELS = [
  { level: 1, label: "Give me a nudge", hint: "a guiding question" },
  { level: 2, label: "Show the key idea", hint: "the rule you need" },
  { level: 3, label: "Show a similar example", hint: "worked, on different values" },
];

interface Turn { role: "student" | "tutor"; text: string; sources?: string[] }

/** A tutor beside the challenge: helps the learner think, never gives the answer.
 *  Every request is counted and sent with the answer, which then counts as assisted. */
export function GuidedHelp({ learnerId, activityId, onUse }: {
  learnerId: string; activityId: string; onUse: (count: number) => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [used, setUsed] = useState(0);
  const [nextLevel, setNextLevel] = useState(1);

  async function ask(level: number | null, text: string) {
    setBusy(true);
    const history = turns.map(({ role, text }) => ({ role, text }));
    const shown = level ? LEVELS[level - 1].label : text;
    setTurns((t) => [...t, { role: "student", text: shown }]);
    try {
      const r = await api.help(learnerId, { activityId, level: level ?? undefined, message: text, history });
      setTurns((t) => [...t, { role: "tutor", text: r.reply, sources: r.sources }]);
    } catch (e) {
      setTurns((t) => [...t, { role: "tutor", text: (e as Error).message }]);
    } finally {
      setBusy(false);
      setUsed((u) => { onUse(u + 1); return u + 1; });
      if (level) setNextLevel((n) => Math.max(n, Math.min(level + 1, 3)));
      setMessage("");
    }
  }

  return (
    <div className="card help">
      <div className="spread">
        <h3 style={{ margin: 0 }}>Stuck? Get guided help</h3>
        {used > 0 && <span className="badge developing">Help used: {used} · counts as assisted</span>}
      </div>
      <p className="small muted" style={{ margin: "6px 0 10px" }}>
        The tutor helps you think — it won&apos;t give you the answer. Start with the smallest help you need.
      </p>
      <div className="row" style={{ gap: 6 }}>
        {LEVELS.map((l) => (
          <button key={l.level} className="chip" disabled={busy || l.level > nextLevel}
            title={l.level > nextLevel ? "Try the smaller help first" : l.hint}
            onClick={() => ask(l.level, "")}>
            {l.level}. {l.label}
          </button>
        ))}
      </div>
      {nextLevel < 3 && <p className="why-disabled" style={{ margin: "0 0 4px" }}>Hints open one at a time — try the smaller one first.</p>}

      {turns.map((t, i) => (
        t.role === "tutor" ? (
          <div key={i} className="tutor-line" style={{ alignItems: "flex-start" }}>
            <span className="tutor-avatar">C</span>
            <div style={{ minWidth: 0 }}>
              <Markdown text={t.text} />
              {t.sources && t.sources.length > 0 && <div className="small muted">From: {t.sources.join("; ")}</div>}
            </div>
          </div>
        ) : (
          <div key={i} className="student-line">{t.text}</div>
        )
      ))}
      {busy && <Loading stages={["Thinking about how to guide you…"]} />}

      <div className="row" style={{ flexWrap: "nowrap", marginTop: 10 }}>
        <input type="text" value={message} disabled={busy}
          placeholder="Ask about this question, e.g. “How do I start the inductive step?”"
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && message.trim()) ask(null, message.trim()); }} />
        <button className="btn secondary" disabled={busy || !message.trim()} onClick={() => ask(null, message.trim())}>Ask</button>
      </div>
    </div>
  );
}
