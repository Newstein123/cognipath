"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";
import { getInlineMath } from "@/lib/settings";
import { pct, stepHref, type Skill, type SkillState, type Source, type Step } from "@/lib/api";

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

export function StateBadge({ state }: { state: SkillState }) {
  return <span className={`badge ${state}`}>{STATE_LABEL[state]}</span>;
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

/** Gemini calls take 5–15 s, so the wait names what is happening. */
export function Loading({ stages }: { stages: string[] }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (stages.length < 2) return;
    const t = setInterval(() => setI((n) => Math.min(n + 1, stages.length - 1)), 3500);
    return () => clearInterval(t);
  }, [stages.length]);
  return <div className="loading"><span className="spinner" />{stages[i]}</div>;
}

export function MasteryBar({ skill }: { skill: Pick<Skill, "mastery" | "selfRated"> }) {
  return (
    <div className="bar" title={`Evidence ${pct(skill.mastery)} · self-rated ${pct(skill.selfRated)}`}>
      <span style={{ width: `${(skill.mastery ?? 0) * 100}%` }} />
      {skill.selfRated != null && (
        <i className="claim" style={{ left: `calc(${skill.selfRated * 100}% - 1px)` }} />
      )}
    </div>
  );
}

export function StepCard({ learnerId, step, primary }: { learnerId: string; step: Step; primary?: boolean }) {
  const href = stepHref(learnerId, step);
  return (
    <div className={primary ? "card highlight" : "card"}>
      <div className="spread">
        <h3 style={{ margin: 0 }}>{step.title}</h3>
        <KindBadge kind={step.kind} />
      </div>
      <p className="muted small" style={{ marginTop: 4 }}>
        {step.capabilityName && <>{step.capabilityName}</>}
        {step.minutes > 0 && <> · about {step.minutes} min</>}
      </p>
      <p><strong>Why this: </strong>{step.reason}</p>
      {href ? (
        <Link className={primary ? "btn" : "btn secondary"} href={href}>
          {primary ? "Start" : "Open"} →
        </Link>
      ) : (
        // Never a dead end: anything that can't start here goes back to the plan.
        <Link className={primary ? "btn" : "btn secondary"} href={`/learn/${encodeURIComponent(learnerId)}`}>
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
