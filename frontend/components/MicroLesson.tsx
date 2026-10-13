"use client";

import { useState } from "react";
import type { LessonCard } from "@/lib/api";
import { Markdown } from "./ui";

const LETTERS = ["A", "B", "C", "D"];

/** One card at a time: idea → worked example → quick check with instant feedback.
 *  Quick checks are practice only; nothing here changes the skill profile. */
export function MicroLesson({ hook, cards, onFinish }: {
  hook: string | null;
  cards: LessonCard[];
  onFinish: (correct: number) => void;
}) {
  const [index, setIndex] = useState(0);
  const [picked, setPicked] = useState<(number | null)[]>(() => cards.map(() => null));
  const [showExample, setShowExample] = useState(false);
  const card = cards[index];
  const choice = picked[index];
  const answered = choice !== null;
  const right = answered && choice === card.check.answerIndex;
  const correct = picked.filter((p, i) => p === cards[i].check.answerIndex).length;

  function pick(i: number) {
    if (answered) return;
    setPicked((cur) => cur.map((p, j) => (j === index ? i : p)));
  }

  function next() {
    if (index + 1 < cards.length) {
      setIndex(index + 1);
      setShowExample(false);
    } else {
      onFinish(correct);
    }
  }

  return (
    <div className="card micro">
      {index === 0 && hook && <p className="hook">{hook}</p>}

      <div className="dots" aria-label={`Card ${index + 1} of ${cards.length}`}>
        {cards.map((_, i) => (
          <span key={i} className={
            i === index ? "dot now"
              : picked[i] === null ? "dot"
              : picked[i] === cards[i].check.answerIndex ? "dot ok" : "dot miss"} />
        ))}
        <span className="small muted">{index + 1} / {cards.length}</span>
      </div>

      <h2 style={{ marginTop: 10 }}>{card.title}</h2>
      <div className="idea"><Markdown text={card.idea} /></div>

      <button className="chip" onClick={() => setShowExample((v) => !v)}>
        {showExample ? "Hide the example" : "Show a worked example"}
      </button>
      {showExample && <div className="example"><Markdown text={card.example} /></div>}

      <div className="check">
        <div className="small muted" style={{ fontWeight: 600 }}>QUICK CHECK</div>
        <div style={{ margin: "6px 0 10px" }}><Markdown text={card.check.question} /></div>
        <div className="options">
          {card.check.options.map((o, i) => {
            const state = !answered ? "" : i === card.check.answerIndex ? "correct"
              : i === choice ? "wrong" : "dim";
            return (
              <button key={i} className={`option ${state}`} onClick={() => pick(i)} disabled={answered}>
                <span className="letter">{LETTERS[i]}</span>
                <span className="md-inline"><Markdown text={o} /></span>
              </button>
            );
          })}
        </div>
        {answered && (
          <div className={right ? "verdict ok" : "verdict miss"}>
            <strong>{right ? "Correct! " : "Not quite. "}</strong>
            <Markdown text={card.check.explanation} />
          </div>
        )}
      </div>

      <div className="spread" style={{ marginTop: 14 }}>
        <span className="small muted">From: {card.sources.join("; ") || "course material"}</span>
        <div className="row">
          {index > 0 && (
            <button className="btn secondary" onClick={() => { setIndex(index - 1); setShowExample(false); }}>← Back</button>
          )}
          <button className="btn" disabled={!answered} onClick={next}>
            {index + 1 < cards.length ? "Next card →" : "Finish lesson →"}
          </button>
        </div>
      </div>
    </div>
  );
}
