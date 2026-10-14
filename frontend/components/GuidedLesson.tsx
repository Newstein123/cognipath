"use client";

import { useState } from "react";
import { api, type AttemptResult, type LessonSection, type QuizQuestion, type Verdict } from "@/lib/api";
import { Diagram } from "./Diagram";
import { Loading, Markdown, StateBadge } from "./ui";

const LETTERS = ["A", "B", "C", "D", "E"];
const NOT_SURE = "I'm not sure yet";

type Phase =
  | "probe"        // does the learner already know it?
  | "confirm"      // they did — a different question to be sure
  | "teach"        // explanation, diagram, worked example
  | "check"        // apply it in a new situation
  | "reexplaining" // fetching a different explanation
  | "recheck"      // after the different explanation
  | "done";

interface Outcome { conceptId?: string | null; title: string; verdict: Verdict; note: string }

/** A concept at a time, the way a tutor would: ask first, teach only what's needed,
 *  check straight away, explain differently when an answer reveals a misconception.
 *  Outcomes are posted as light evidence at the end (they can't claim mastery). */
export function GuidedLesson({ learnerId, capabilityId, hook, sections, teachFirst, onComplete }: {
  learnerId: string; capabilityId: string; hook: string | null;
  sections: LessonSection[];
  /** Beginners: no probe — explain, then check. */
  teachFirst: boolean;
  onComplete: (result: AttemptResult | null) => void;
}) {
  const [i, setI] = useState(0);
  const start: Phase = teachFirst ? "teach" : "probe";
  const [phase, setPhase] = useState<Phase>(start);
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);
  const [log, setLog] = useState<string[]>([]);       // short tutor lines for this concept
  const [re, setRe] = useState<{ explanation: string; check: QuizQuestion | null } | null>(null);
  const [saving, setSaving] = useState(false);
  // "Explain more simply" etc. — re-teaching THIS concept, not a topic-wide Q&A.
  const [extras, setExtras] = useState<{ label: string; text: string; sources: string[] }[]>([]);
  const [extraBusy, setExtraBusy] = useState<string | null>(null);

  async function more(kind: "simpler" | "example" | "mistakes", label: string) {
    setExtraBusy(label);
    try {
      const r = await api.followup(learnerId, { capabilityId, concept: sec.title, explanation: sec.explanation, kind });
      setExtras((x) => [...x, { label, text: r.text, sources: r.sources }]);
    } catch (e) {
      setExtras((x) => [...x, { label, text: (e as Error).message, sources: [] }]);
    } finally {
      setExtraBusy(null);
    }
  }
  const sec = sections[i];

  function say(line: string) { setLog((l) => [...l, line]); }

  function finishConcept(verdict: Verdict, note: string) {
    setOutcomes((o) => [...o, { conceptId: sec.conceptId, title: sec.title, verdict, note }]);
    setPhase("done");
  }

  async function explainDifferently(q: QuizQuestion, chosen: number) {
    setPhase("reexplaining");
    try {
      const r = await api.reexplain(learnerId, {
        capabilityId, concept: sec.title, explanation: sec.explanation,
        question: q.question, chosen: q.options[chosen], correct: q.options[q.answerIndex],
      });
      setRe({ explanation: r.explanation, check: r.check });
      setPhase(r.check ? "recheck" : "done");
      if (!r.check) setOutcomes((o) => [...o, { conceptId: sec.conceptId, title: sec.title, verdict: "unmet", note: "still unclear" }]);
    } catch {
      setRe({ explanation: "I couldn't load a different explanation. Read the example again, or ask the tutor below.", check: null });
      setOutcomes((o) => [...o, { conceptId: sec.conceptId, title: sec.title, verdict: "unmet", note: "still unclear" }]);
      setPhase("done");
    }
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

  function onCheck(choice: number) {
    if (choice === sec.check.answerIndex) {
      if (phase === "confirm") { say("Confirmed — you know this. Skipping the explanation."); finishConcept("met", "knew it already"); }
      else { say("Exactly. You've got it."); finishConcept("met", "learned it"); }
    } else {
      say("Not quite — let me explain it a different way, aimed at that answer.");
      explainDifferently(sec.check, choice);
    }
  }

  function onRecheck(choice: number) {
    if (!re?.check) return;
    if (choice === re.check.answerIndex) { say("That's it. It clicked the second time."); finishConcept("partial", "after a second explanation"); }
    else { say("Still tricky — we'll come back to this one. The tutor below can help."); finishConcept("unmet", "still unclear"); }
  }

  async function next() {
    if (i + 1 < sections.length) {
      setI(i + 1); setPhase(start); setLog([]); setRe(null); setExtras([]);
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    setSaving(true);
    try {
      onComplete(await api.lessonResult(learnerId, { capabilityId, concepts: outcomes }));
    } catch {
      onComplete(null);
    }
  }

  const showTeach = ["teach", "check", "reexplaining", "recheck"].includes(phase)
    || (phase === "done" && outcomes[outcomes.length - 1]?.note !== "knew it already");

  return (
    <div>
      {i === 0 && hook && <p className="hook" style={{ fontSize: 16 }}>{hook}</p>}

      {/* finished concepts, one line each */}
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

        {/* 1. ask first — unless the learner is new to this, then explain first */}
        {!teachFirst && (
          <Question label="FIRST, WHAT DO YOU THINK?" q={sec.probe} allowNotSure
            locked={phase !== "probe"} onAnswer={onProbe} />
        )}
        {!teachFirst && log[0] && <Tutor text={log[0]} />}

        {/* 2. teach — only if needed */}
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
                <button key={kind} className="chip" disabled={!!extraBusy}
                  onClick={() => more(kind, label)}>{label}</button>
              ))}
            </div>
            {extraBusy && <Loading stages={[`${extraBusy}…`]} />}
          </div>
        )}

        {/* 3. check — or confirm, for someone who already knew it */}
        {(phase === "confirm" || (showTeach && phase !== "teach")) && (
          <Question label={phase === "confirm" || log[0]?.startsWith("You already") ? "TO BE SURE" : "NOW TRY THIS"}
            q={sec.check} locked={phase !== "check" && phase !== "confirm"}
            onAnswer={(c) => onCheck(c)} />
        )}
        {phase === "teach" && (
          <button className="btn" style={{ marginTop: 10 }} onClick={() => setPhase("check")}>I&apos;ve read it — check me →</button>
        )}
        {(teachFirst ? log[0] : log[1]) && <Tutor text={(teachFirst ? log[0] : log[1])!} />}

        {/* 4. explain differently, then a new check */}
        {phase === "reexplaining" && <Loading stages={["Working out what that answer misunderstood…", "Explaining it another way…"]} />}
        {re && (
          <div className="teach again">
            <div className="example-label">ANOTHER WAY TO SEE IT</div>
            <Markdown text={re.explanation} />
          </div>
        )}
        {re?.check && (
          <Question label="ONE MORE TRY" q={re.check} locked={phase !== "recheck"} onAnswer={onRecheck} />
        )}
        {(teachFirst ? log[1] : log[2]) && <Tutor text={(teachFirst ? log[1] : log[2])!} />}

        {phase === "done" && (
          <div className="row" style={{ marginTop: 14, justifyContent: "flex-end" }}>
            {saving ? <Loading stages={["Updating your skill profile…"]} /> : (
              <button className="btn" onClick={next}>
                {i + 1 < sections.length ? `Next concept: ${sections[i + 1].title} →` : "Finish the lesson →"}
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

function Question({ label, q, locked, onAnswer, allowNotSure }: {
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
        <div className={picked === q.answerIndex ? "verdict ok" : "verdict miss"}>
          <Markdown text={q.explanation} />
        </div>
      )}
    </div>
  );
}

export function LessonOutcome({ result }: { result: AttemptResult }) {
  return (
    <div className="card highlight">
      <h2>Lesson complete</h2>
      {result.changes.map((c) => (
        <p key={c.capabilityId} style={{ margin: "4px 0" }}>
          <strong>{c.name}</strong>: <StateBadge state={c.stateBefore} /> → <StateBadge state={c.stateAfter} />
        </p>
      ))}
      <p className="small muted" style={{ marginBottom: 0 }}>
        Quick checks show progress but can&apos;t prove mastery on their own — the challenge below does that.
      </p>
    </div>
  );
}
