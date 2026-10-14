"use client";

import { useState } from "react";
import { api, type AttemptResult, type LessonSection, type QuizQuestion, type Verdict } from "@/lib/api";
import { Diagram } from "./Diagram";
import { Loading, Markdown, StateBadge } from "./ui";

const LETTERS = ["A", "B", "C", "D", "E"];
const NOT_SURE = "I'm not sure yet";
const TASK_LABEL: Record<string, string> = {
  explain: "YOUR TURN — EXPLAIN IT",
  predict: "YOUR TURN — PREDICT WHAT HAPPENS",
  debug: "YOUR TURN — FIND THE PROBLEM",
  choose: "YOUR TURN — CHOOSE AND JUSTIFY",
};

type Phase =
  | "probe"        // does the learner already know it? (multiple choice, fast)
  | "confirm"      // they did — a different quick question to be sure
  | "teach"        // explanation, diagram, worked example, then the applied task
  | "judging"
  | "reexplaining" // explain again, aimed at what the answer missed
  | "recheck"
  | "done";

/** What the learner showed for one concept. "Covered" = taught; "demonstrated" = shown. */
interface Outcome { conceptId?: string | null; title: string; verdict: Verdict; note: string }

const NOTE = {
  knew: "demonstrated — you already knew it",
  learned: "demonstrated after the lesson",
  second: "demonstrated after a second explanation",
  unclear: "covered — not demonstrated yet",
} as const;

type Judged = {
  outcome: Verdict; missed: string[]; modelAnswer: string;
  criteria: { criterion: string; verdict: Verdict; justification: string }[];
};

/** Teach → apply in your own words → feedback on the actual answer → explain the missed
 *  part differently. Each concept's outcome is saved the moment it is decided, so the
 *  coverage on screen and in the profile always agree. Outcomes are light evidence. */
export function GuidedLesson({ learnerId, capabilityId, hook, sections, teachFirst, onComplete, onConceptDone }: {
  learnerId: string; capabilityId: string; hook: string | null;
  sections: LessonSection[];
  teachFirst: boolean;
  onComplete: (result: AttemptResult | null) => void;
  /** Called after each concept is saved, so the page can refresh coverage. */
  onConceptDone?: () => void;
}) {
  const start: Phase = teachFirst ? "teach" : "probe";
  const [i, setI] = useState(0);
  const [phase, setPhase] = useState<Phase>(start);
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);
  const [log, setLog] = useState<string[]>([]);
  const [answer, setAnswer] = useState("");
  const [judged, setJudged] = useState<Judged | null>(null);
  const [re, setRe] = useState<{ explanation: string; check: QuizQuestion | null } | null>(null);
  const [last, setLast] = useState<AttemptResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [extras, setExtras] = useState<{ label: string; text: string; sources: string[] }[]>([]);
  const [extraBusy, setExtraBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const sec = sections[i];
  const task = sec.task;

  const say = (line: string) => setLog((l) => [...l, line]);

  async function finishConcept(verdict: Verdict, note: keyof typeof NOTE) {
    const o = { conceptId: sec.conceptId, title: sec.title, verdict, note: NOTE[note] };
    setOutcomes((cur) => [...cur, o]);
    setPhase("done");
    setSaving(true);
    try {
      // Saved now, not at the end of the part: coverage must match what the screen says.
      setLast(await api.lessonResult(learnerId, { capabilityId, concepts: [o] }));
      onConceptDone?.();
    } catch { /* the outcome stays on screen; the profile catches up on the next save */ }
    finally { setSaving(false); }
  }

  async function more(kind: "simpler" | "example" | "mistakes", label: string) {
    setExtraBusy(label);
    try {
      const r = await api.followup(learnerId, { capabilityId, concept: sec.title, explanation: sec.explanation, kind });
      setExtras((x) => [...x, { label, text: r.text, sources: r.sources }]);
    } catch (e) {
      setExtras((x) => [...x, { label, text: (e as Error).message, sources: [] }]);
    } finally { setExtraBusy(null); }
  }

  function onProbe(choice: number, notSure: boolean) {
    if (!notSure && choice === sec.probe.answerIndex) {
      say("You already have the idea. One more, in a different situation, to be sure:");
      setPhase("confirm");
    } else {
      say(notSure ? "That's fine — let's learn it together." : "Good guess, but not quite. Let's look at how it works.");
      setPhase("teach");
    }
  }

  function onConfirm(choice: number) {
    if (choice === sec.check.answerIndex) {
      say("Confirmed — you know this. Skipping ahead.");
      finishConcept("met", "knew");
    } else {
      say("Not quite — let's go through it properly.");
      setPhase("teach");
    }
  }

  async function submitTask() {
    if (!task) return;
    setPhase("judging"); setErr(null);
    try {
      const j = await api.judge(learnerId, { capabilityId, concept: sec.title, task, answer });
      setJudged(j);
      if (j.outcome === "met") {
        say("That's it — you applied it correctly.");
        finishConcept("met", "learned");
        return;
      }
      say(j.outcome === "partial"
        ? "Part of that is right. Let me explain just the part you missed."
        : "Not yet — let me explain it a different way, aimed at your answer.");
      setPhase("reexplaining");
      const r = await api.reexplain(learnerId, {
        capabilityId, concept: sec.title, explanation: sec.explanation,
        question: task.prompt, chosen: answer,
        correct: `A correct answer needed to: ${j.missed.join("; ")}`,
      });
      setRe({ explanation: r.explanation, check: r.check });
      if (r.check) setPhase("recheck"); else finishConcept("unmet", "unclear");
    } catch (e) {
      setErr((e as Error).message); setPhase("teach");
    }
  }

  function onRecheck(choice: number) {
    if (!re?.check) return;
    if (choice === re.check.answerIndex) { say("That's it — it clicked the second time."); finishConcept("partial", "second"); }
    else {
      say("Still tricky — that's saved as not shown yet. Cognith will bring it back for review before the unit challenge; the tutor below can help right now.");
      finishConcept("unmet", "unclear");
    }
  }

  function next() {
    if (i + 1 < sections.length) {
      setI(i + 1); setPhase(start); setLog([]); setRe(null); setExtras([]); setAnswer(""); setJudged(null);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      onComplete(last);
    }
  }

  const knewIt = phase === "done" && outcomes[outcomes.length - 1]?.note === NOTE.knew;
  const showTeach = !["probe", "confirm"].includes(phase) && !knewIt;
  const answering = phase === "teach";

  return (
    <div>
      {i === 0 && hook && <p className="hook" style={{ fontSize: 16 }}>{hook}</p>}

      {outcomes.slice(0, phase === "done" ? -1 : undefined).map((o) => (
        <div key={o.title} className="concept-done">
          <span className={`badge ${o.verdict}`}>{o.verdict === "met" ? "✓" : o.verdict === "partial" ? "△" : "…"}</span>
          <strong>{o.title}</strong> <span className="small muted">— {o.note}</span>
        </div>
      ))}

      <div className="card" key={i}>
        <div className="spread">
          <h2 style={{ margin: 0 }}>{sec.title}</h2>
          <span className="small muted">Concept {i + 1} of {sections.length}</span>
        </div>

        {!teachFirst && (
          <Choice label="FIRST, WHAT DO YOU THINK?" q={sec.probe} allowNotSure
            locked={phase !== "probe"} onAnswer={onProbe} />
        )}
        {!teachFirst && log[0] && <Tutor text={log[0]} />}
        {!teachFirst && log[0]?.startsWith("You already") && (
          <Choice label="TO BE SURE" q={sec.check} locked={phase !== "confirm"} onAnswer={(c) => onConfirm(c)} />
        )}
        {knewIt && log[1] && <Tutor text={log[1]} />}

        {showTeach && (
          <div className="teach">
            <Markdown text={sec.explanation} />
            <Diagram d={sec.diagram} />
            <div className="example">
              <div className="example-label">WORKED EXAMPLE</div>
              <Markdown text={sec.example} />
            </div>
            {extras.map((x, k) => (
              <div key={k} className="teach again" style={{ marginTop: 10 }}>
                <div className="example-label">{x.label.toUpperCase()}</div>
                <Markdown text={x.text} />
                {x.sources.length > 0 && <div className="small muted">From: {x.sources.join("; ")}</div>}
              </div>
            ))}
            <div className="row" style={{ gap: 6, marginTop: 10 }}>
              {([["simpler", "Explain it more simply"], ["example", "Show me another example"],
                 ["mistakes", "Common mistakes"]] as const).map(([kind, label]) => (
                <button key={kind} className="chip" disabled={!!extraBusy} onClick={() => more(kind, label)}>{label}</button>
              ))}
            </div>
            {extraBusy && <Loading stages={[`${extraBusy}…`]} />}
          </div>
        )}

        {/* the real check: apply the idea in your own words */}
        {showTeach && task && (
          <div className="check">
            <div className="small muted" style={{ fontWeight: 700, letterSpacing: ".04em" }}>
              {TASK_LABEL[task.kind] ?? "YOUR TURN"}
            </div>
            <div style={{ margin: "6px 0 10px" }}><Markdown text={task.prompt} /></div>
            {answering ? (
              <>
                <textarea value={answer} onChange={(e) => setAnswer(e.target.value)} style={{ minHeight: 80 }}
                  placeholder="A few sentences in your own words. Reasoning counts more than wording." />
                {err && <div className="error">{err}</div>}
                <div className="row" style={{ marginTop: 8 }}>
                  <button className="btn" disabled={!answer.trim()} onClick={submitTask}>Check my answer →</button>
                  <span className="small muted">Marked on {task.criteria.length} point{task.criteria.length > 1 ? "s" : ""}</span>
                </div>
              </>
            ) : (
              <div className="prompt small">{answer}</div>
            )}
            {phase === "judging" && <Loading stages={["Reading your answer…", "Checking each point…"]} />}
            {judged && (
              <div style={{ marginTop: 10 }}>
                {judged.criteria.map((c) => (
                  <div key={c.criterion} className="row" style={{ alignItems: "flex-start", flexWrap: "nowrap", margin: "6px 0" }}>
                    <span className={`badge ${c.verdict}`}>{c.verdict === "met" ? "✓" : c.verdict === "partial" ? "△" : "✗"}</span>
                    <div className="md-inline" style={{ minWidth: 0 }}><Markdown text={c.criterion} />
                      <div className="small muted"><Markdown text={c.justification} /></div></div>
                  </div>
                ))}
                <details style={{ marginTop: 6 }}>
                  <summary className="small">A model answer</summary>
                  <div className="small"><Markdown text={judged.modelAnswer} /></div>
                </details>
              </div>
            )}
          </div>
        )}
        {showTeach && log[teachFirst ? 0 : 1] && <Tutor text={log[teachFirst ? 0 : 1]} />}

        {phase === "reexplaining" && <Loading stages={["Working out what your answer missed…", "Explaining just that part…"]} />}
        {re && (
          <div className="teach again">
            <div className="example-label">THE PART YOU MISSED</div>
            <Markdown text={re.explanation} />
          </div>
        )}
        {re?.check && <Choice label="ONE MORE TRY" q={re.check} locked={phase !== "recheck"} onAnswer={onRecheck} />}
        {showTeach && log[teachFirst ? 1 : 2] && <Tutor text={log[teachFirst ? 1 : 2]} />}

        {phase === "done" && (
          <div className="row" style={{ marginTop: 14, justifyContent: "flex-end" }}>
            {saving ? <Loading stages={["Saving to your profile…"]} /> : (
              <button className="btn" onClick={next}>
                {i + 1 < sections.length ? `Next concept: ${sections[i + 1].title} →` : "Finish this part →"}
              </button>
            )}
          </div>
        )}
      </div>
      <p className="small muted">From: {sec.sources.join("; ") || "course material"}</p>
    </div>
  );
}

function Tutor({ text }: { text: string }) {
  return <div className="tutor-line"><span className="tutor-avatar">C</span><span>{text}</span></div>;
}

function Choice({ label, q, locked, onAnswer, allowNotSure }: {
  label: string; q: QuizQuestion; locked: boolean;
  onAnswer: (choice: number, notSure: boolean) => void; allowNotSure?: boolean;
}) {
  const [picked, setPicked] = useState<number | null>(null);
  const options = allowNotSure ? [...q.options, NOT_SURE] : q.options;
  const answered = picked !== null;
  const notSure = allowNotSure && picked === q.options.length;
  return (
    <div className="check">
      <div className="small muted" style={{ fontWeight: 700, letterSpacing: ".04em" }}>{label}</div>
      <div style={{ margin: "6px 0 10px" }}><Markdown text={q.question} /></div>
      <div className="options">
        {options.map((o, k) => {
          const isNotSure = allowNotSure && k === q.options.length;
          const state = !answered ? "" : k === q.answerIndex && !notSure ? "correct"
            : k === picked ? (isNotSure ? "dim" : "wrong") : "dim";
          return (
            <button key={k} className={`option ${state}`} disabled={answered || locked}
              onClick={() => { setPicked(k); onAnswer(k, !!isNotSure); }}>
              <span className="letter">{isNotSure ? "?" : LETTERS[k]}</span>
              <span className="md-inline"><Markdown text={o} /></span>
            </button>
          );
        })}
      </div>
      {answered && !notSure && (
        <div className={picked === q.answerIndex ? "verdict ok" : "verdict miss"}><Markdown text={q.explanation} /></div>
      )}
    </div>
  );
}

export function LessonOutcome({ result }: { result: AttemptResult }) {
  return (
    <div className="card highlight">
      <h2>Part complete</h2>
      {result.changes.map((c) => (
        <p key={c.capabilityId} style={{ margin: "4px 0" }}>
          <strong>{c.name}</strong>: <StateBadge state={c.stateBefore} /> → <StateBadge state={c.stateAfter} />
        </p>
      ))}
      <p className="small muted" style={{ marginBottom: 0 }}>
        In-lesson tasks show progress, but a skill is only mastered after the unit challenge.
      </p>
    </div>
  );
}
