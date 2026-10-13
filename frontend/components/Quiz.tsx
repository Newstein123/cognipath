"use client";

import { useState } from "react";
import type { QuizQuestion } from "@/lib/api";
import { Markdown } from "./ui";

const LETTERS = ["A", "B", "C", "D"];

/** One question at a time, instant feedback, score at the end. Practice only —
 *  nothing here changes the skill profile. */
export function Quiz({ questions, onFinish }: {
  questions: QuizQuestion[];
  onFinish: (correct: number) => void;
}) {
  const [index, setIndex] = useState(0);
  const [picked, setPicked] = useState<(number | null)[]>(() => questions.map(() => null));
  const q = questions[index];
  const choice = picked[index];
  const answered = choice !== null;
  const right = answered && choice === q.answerIndex;
  const correct = picked.filter((p, i) => p === questions[i].answerIndex).length;

  return (
    <div className="card">
      <div className="spread">
        <h2 style={{ margin: 0 }}>Quiz</h2>
        <div className="dots">
          {questions.map((_, i) => (
            <span key={i} className={i === index ? "dot now" : picked[i] === null ? "dot"
              : picked[i] === questions[i].answerIndex ? "dot ok" : "dot miss"} />
          ))}
          <span className="small muted">{index + 1} / {questions.length}</span>
        </div>
      </div>
      <div style={{ margin: "14px 0 10px", fontSize: 16 }}><Markdown text={q.question} /></div>
      <div className="options">
        {q.options.map((o, i) => {
          const state = !answered ? "" : i === q.answerIndex ? "correct" : i === choice ? "wrong" : "dim";
          return (
            <button key={i} className={`option ${state}`} disabled={answered}
              onClick={() => setPicked((cur) => cur.map((p, j) => (j === index ? i : p)))}>
              <span className="letter">{LETTERS[i]}</span>
              <span className="md-inline"><Markdown text={o} /></span>
            </button>
          );
        })}
      </div>
      {answered && (
        <div className={right ? "verdict ok" : "verdict miss"}>
          <strong>{right ? "Correct! " : "Not quite. "}</strong>
          <Markdown text={q.explanation} />
        </div>
      )}
      <div className="row" style={{ marginTop: 14, justifyContent: "flex-end" }}>
        <button className="btn" disabled={!answered}
          onClick={() => (index + 1 < questions.length ? setIndex(index + 1) : onFinish(correct))}>
          {index + 1 < questions.length ? "Next question →" : "See my score →"}
        </button>
      </div>
    </div>
  );
}
