"use client";

import { useState } from "react";
import { api, pct, type AttemptResult, type LessonSection, type QuizQuestion, type Verdict } from "@/lib/api";
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
  | "stuck"        // several explanations in: learner chooses another try or moving on
  | "done";

/** Re-explanations before the learner is offered "move on". Not a cap: they can keep going. */
const ROUNDS_BEFORE_ASKING = 3;

/** What the learner showed for one concept. "Covered" = taught; "demonstrated" = shown. */
interface Outcome { conceptId?: string | null; title: string; verdict: Verdict; note: string }

const NOTE = {
  knew: "demonstrated — you already knew it",
  learned: "demonstrated after the lesson",
  second: "demonstrated after a second explanation",
  persisted: "demonstrated after a few explanations",
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
  /** Each re-explanation and its question, plus the learner's line after answering it. */
  const [rounds, setRounds] = useState<{ explanation: string; check: QuizQuestion; reply?: string }[]>([]);
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
      await explainAgain(task.prompt, answer, `A correct answer needed to: ${j.missed.join("; ")}`, []);
    } catch (e) {
      setErr((e as Error).message); setPhase("teach");
    }
  }

  /** Explain again from a new angle (told what was already tried) with a new question. */
  async function explainAgain(question: string, chosen: string, correct: string, previous: string[]) {
    setPhase("reexplaining");
    try {
      const r = await api.reexplain(learnerId, {
        capabilityId, concept: sec.title, explanation: sec.explanation, question, chosen, correct, previous,
      });
      if (!r.check) { finishConcept("unmet", "unclear"); return; }
      setRounds((cur) => [...cur, { explanation: r.explanation, check: r.check! }]);
      setPhase("recheck");
    } catch (e) {
      setErr((e as Error).message); setPhase(previous.length ? "stuck" : "teach");
    }
  }

  function reply(line: string) {
    setRounds((cur) => cur.map((r, k) => (k === cur.length - 1 ? { ...r, reply: line } : r)));
  }

  function onRecheck(choice: number) {
    const cur = rounds[rounds.length - 1];
    if (!cur) return;
    if (choice === cur.check.answerIndex) {
      reply(rounds.length === 1 ? "That's it — it clicked the second time." : "That's it — you've got it now.");
      finishConcept("partial", rounds.length === 1 ? "second" : "persisted");
    } else if (rounds.length < ROUNDS_BEFORE_ASKING) {
      reply("Not yet — let's try it another way, in smaller steps.");
      tryAnotherWay(choice);
    } else {
      reply("Still tricky. You can keep going, or move on and come back to it — Cognith will bring it back before the unit challenge.");
      setPhase("stuck");
    }
  }

  function tryAnotherWay(choice?: number) {
    const cur = rounds[rounds.length - 1];
    const picked = choice ?? -1;
    explainAgain(cur.check.question,
      picked >= 0 ? cur.check.options[picked] : "(still unsure)",
      `${cur.check.options[cur.check.answerIndex]}. ${cur.check.explanation}`,
      rounds.map((r) => r.explanation));
  }

  function next() {
    if (i + 1 < sections.length) {
      setI(i + 1); setPhase(start); setLog([]); setRounds([]); setExtras([]); setAnswer(""); setJudged(null);
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

        {phase === "reexplaining" && rounds.length === 0 && <Loading stages={["Working out what your answer missed…", "Explaining just that part…"]} />}
        {rounds.map((r, k) => {
          const latest = k === rounds.length - 1;
          return (
            <div key={k}>
              <div className="teach again">
                <div className="example-label">{k === 0 ? "THE PART YOU MISSED" : `ANOTHER WAY TO SEE IT (${k + 1})`}</div>
                <Markdown text={r.explanation} />
              </div>
              <Choice label={k === 0 ? "ONE MORE TRY" : "TRY THIS ONE"} q={r.check}
                locked={!(latest && phase === "recheck")} onAnswer={onRecheck} />
              {r.reply && <Tutor text={r.reply} />}
            </div>
          );
        })}
        {phase === "reexplaining" && rounds.length > 0 && <Loading stages={["Finding another way to explain it…"]} />}
        {phase === "stuck" && (
          <div className="row" style={{ marginTop: 10, justifyContent: "flex-end" }}>
            {err && <div className="error">{err}</div>}
            <button className="btn secondary" onClick={() => finishConcept("unmet", "unclear")}>
              Move on — review it later
            </button>
            <button className="btn" onClick={() => { setErr(null); tryAnotherWay(); }}>Explain it another way →</button>
          </div>
        )}

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
          <strong>{c.name}</strong>:{" "}
          {c.stateBefore !== c.stateAfter && <><StateBadge state={c.stateBefore} /> → </>}
          <StateBadge state={c.stateAfter} /> <span className="small muted">· skill level now {pct(c.masteryAfter)}</span>
        </p>
      ))}
      <p className="small muted" style={{ marginBottom: 0 }}>
        In-lesson tasks show progress, but a skill is only mastered after the unit challenge.
      </p>
    </div>
  );
}
