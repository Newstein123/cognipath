"use client";

import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";
import { getInlineMath } from "@/lib/settings";
import { pct, stepHref, type Skill, type SkillState, type Source, type Step, type Verdict } from "@/lib/api";

const STATE_LABEL: Record<SkillState, string> = {
  mastered: "Mastered",
  developing: "Developing",
  unknown: "Not verified yet",
};

const KIND_LABEL: Record<string, string> = {
  diagnose: "Check",
  learn: "Lesson",
  practise: "Practice",
  apply: "Challenge",
  mission: "Mission",
  onboard: "Start",
  nothing: "Done",
};

// Status is never colour alone: each badge carries an icon and words.
const STATE_ICON: Record<SkillState, string> = { mastered: "✓", developing: "◐", unknown: "○" };

export function StateBadge({ state }: { state: SkillState }) {
  return <span className={`badge ${state}`}><span aria-hidden="true">{STATE_ICON[state]}</span>{STATE_LABEL[state]}</span>;
}

const VERDICT: Record<Verdict, [string, string]> = {
  met: ["✓", "Met"], partial: ["△", "Partly met"], unmet: ["✗", "Not met"],
};

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const [icon, label] = VERDICT[verdict];
  return <span className={`badge ${verdict}`}><span aria-hidden="true">{icon}</span>{label}</span>;
}

/** The same header on every page: an optional eyebrow, the title, an optional lede. */
export function PageHead({ eyebrow, title, children }: { eyebrow?: string; title: string; children?: React.ReactNode }) {
  return (
    <header className="page-head">
      {eyebrow && <p className="eyebrow">{eyebrow}</p>}
      <h1>{title}</h1>
      {children && <p className="lede">{children}</p>}
    </header>
  );
}

export function KindBadge({ kind }: { kind: string }) {
  return <span className="badge kind">{KIND_LABEL[kind] ?? kind}</span>;
}

// Gemini writes formulas as $…$ / $$…$$ LaTeX. Inline $…$ is per course (lib/settings.ts)
// because prose with prices ("$500 … $2,000/month") would otherwise be read as a formula.
const math = () => [remarkMath, { singleDollarTextMath: getInlineMath() }] as const;

/** \( … \) and \[ … \] are LaTeX delimiters Gemini sometimes uses; remark-math wants $. */
const toDollars = (t: string) =>
  t.replace(/\\\[([\s\S]+?)\\\]/g, (_, m) => `$$${m}$$`).replace(/\\\(([\s\S]+?)\\\)/g, (_, m) => `$${m}$`);

export function Markdown({ text }: { text: string }) {
  text = toDollars(text);
  return (
    <div className="md">
      <ReactMarkdown remarkPlugins={[remarkGfm, math() as never]} rehypePlugins={[rehypeKatex]}>{text}</ReactMarkdown>
    </div>
  );
}

export function ErrorBox({ error }: { error: string | null }) {
  return error ? <div className="error" role="alert">{error}</div> : null;
}

/** Gemini calls take 5–15 s. The wait shows what was asked and how long it has taken —
 *  not a sequence of stages, since the backend reports no progress. Only the first of
 *  `stages` is shown. */
export function Loading({ stages }: { stages: string[] }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSeconds((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="loading">
      <span className="spinner" />{stages[0]}
      {seconds >= 3 && <span className="muted small" style={{ marginLeft: 8 }}>{seconds} s</span>}
    </div>
  );
}

export function MasteryBar({ skill }: { skill: Pick<Skill, "mastery" | "selfRated"> }) {
  return (
    <div className="bar" title={`Evidence ${pct(skill.mastery)} · starting estimate ${pct(skill.selfRated)}`}>
      <span style={{ width: `${(skill.mastery ?? 0) * 100}%` }} />
      {skill.selfRated != null && (
        <i className="claim" style={{ left: `calc(${skill.selfRated * 100}% - 1px)` }} />
      )}
    </div>
  );
}

/** A recommended step from the plan: its real title, the plan's own reason, one action.
 *  `primary` is the prominent "next step" card; `label` names it (e.g. "Your next step"). */
export function StepCard({ learnerId, step, primary, label }: {
  learnerId: string; step: Step; primary?: boolean; label?: string;
}) {
  const href = stepHref(learnerId, step);
  const Title = primary ? "h2" : "h3";
  return (
    <div className={primary ? "card next" : "card step"}>
      {label && <p className="eyebrow">{label}</p>}
      <div className="meta">
        <KindBadge kind={step.kind} />
        {step.capabilityName && <span>{step.capabilityName}</span>}
        {step.minutes > 0 && <span>about {step.minutes} min</span>}
      </div>
      <Title style={primary ? undefined : { margin: "8px 0 0" }}>{step.title}</Title>
      <p className={primary ? "why" : "reason"}>
        <strong>Why this: </strong>{step.reason}
      </p>
      {href ? (
        <Link className={primary ? "btn" : "btn secondary sm"} href={href}>
          {primary ? "Start" : "Open"} →
        </Link>
      ) : (
        // Never a dead end: anything that can't start here goes back to the plan.
        <Link className={primary ? "btn" : "btn secondary sm"} href={`/learn/${encodeURIComponent(learnerId)}`}>
          {step.kind === "mission" ? "Mission coming soon — back to my plan →" : "Back to my plan →"}
        </Link>
      )}
    </div>
  );
}

export function Sources({ sources }: { sources: Source[] }) {
  const shown = sources.some((s) => s.cited) ? sources.filter((s) => s.cited) : sources;
  if (!shown.length) return null;
  return (
    <div>
      <h3>Sources from the course material</h3>
      <ul className="list">
        {shown.map((s) => (
          <li key={s.chunkId}>
            <details>
              <summary><strong>{s.citation}</strong></summary>
              <div className="excerpt">{s.excerpt}</div>
            </details>
            {s.reference && <div className="small muted">Based on: {s.reference}</div>}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** A skill state as plain text with its icon — for tight spaces where a pill would wrap. */
export function StateLabel({ state }: { state: SkillState }) {
  return <span className={`state-text ${state}`}><span aria-hidden="true">{STATE_ICON[state]}</span>{STATE_LABEL[state]}</span>;
}

/** Worked examples often put literal lines — an HTTP request, the steps of a calculation —
 *  on consecutive lines with no Markdown, which Markdown would join into one line. Keep
 *  those breaks; leave real Markdown (lists, headings, quotes, tables, paragraphs, code
 *  fences and display maths) exactly as written. */
export function keepLineBreaks(text: string): string {
  const block = /^\s*([-*+]\s|\d+[.)]\s|#{1,6}\s|>|\|)/;
  const lines = text.split("\n");
  let verbatim = false;  // inside ``` / ~~~ fences or $$ / \[ maths
  return lines.map((line, i) => {
    const t = line.trim();
    const toggles = /^(```|~~~)/.test(t) || ((t.match(/\$\$/g)?.length ?? 0) % 2 === 1) || t === "\\[" || t === "\\]";
    if (toggles) { verbatim = !verbatim; return line; }
    const next = lines[i + 1];
    if (verbatim || !t || next === undefined || !next.trim() || block.test(line) || block.test(next)
        || /^(```|~~~|\$\$)/.test(next.trim())) return line;
    return line.replace(/\s*$/, "") + "  ";  // Markdown hard break
  }).join("\n");
}

// --- theme ---------------------------------------------------------------------------------
type ThemeChoice = "light" | "dark" | "system";
declare global { interface Window { __cognithApplyTheme?: (animate: boolean) => void } }

const onThemeChange = (cb: () => void) => {
  window.addEventListener("cognith-theme", cb);
  return () => window.removeEventListener("cognith-theme", cb);
};
const currentChoice = (): ThemeChoice => {
  const c = document.documentElement.dataset.themeChoice;
  return c === "light" || c === "dark" ? c : "system";
};

/** Light / Dark / System, as native radio buttons. The choice is saved in this browser;
 *  "System" clears it and follows the device. app/layout.tsx applies it before paint. */
export function ThemeSwitch({ tone }: { tone: "on-dark" | "on-page" }) {
  // The server can't know the saved choice: render "System" there, the real one after.
  const choice = useSyncExternalStore(onThemeChange, currentChoice, () => "system" as ThemeChoice);
  function choose(next: ThemeChoice) {
    try {
      if (next === "system") localStorage.removeItem("cognith-theme");
      else localStorage.setItem("cognith-theme", next);
    } catch { /* storage blocked: still applies for this page */ }
    if (window.__cognithApplyTheme) window.__cognithApplyTheme(true);
    else document.documentElement.dataset.themeChoice = next;
  }
  return (
    <fieldset className={`theme-switch ${tone}`}>
      <legend>Theme</legend>
      <div className={`segmented ${tone}`}>
        {(["light", "dark", "system"] as const).map((c) => (
          <label key={c}>
            <input type="radio" name={`theme-${tone}`} value={c} checked={choice === c} onChange={() => choose(c)} />
            <span>{c === "light" ? "Light" : c === "dark" ? "Dark" : "System"}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
