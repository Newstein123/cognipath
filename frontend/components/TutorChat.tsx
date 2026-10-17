"use client";

import { useEffect, useId, useLayoutEffect, useRef } from "react";
import type { TutorAnswer } from "@/lib/api";
import { ask, chatKey, setDraft, useChat, useChatExtras, type ChatMessage } from "@/lib/tutorChat";
import { ErrorBox, Loading, Markdown, Sources } from "./ui";

/** The tutor as a conversation: the learner's questions and the tutor's answers as
 *  bubbles, a composer at the bottom. One component for the header's panel or dialog and the
 *  tutor page. Nothing is sent until the learner submits — opening it calls nothing. */
export function TutorChat({
  learnerId, capabilityId, presets: presetsProp, placeholder: placeholderProp, title = "Ask the tutor",
  variant, onClose, autoFocus = false,
}: {
  learnerId: string;
  /** Keeps answers inside one capability's material, e.g. during its lesson. */
  capabilityId?: string;
  /** One-click follow-ups, e.g. "Show me an example". Default: what the page set (setChatExtras). */
  presets?: { label: string; question: string }[];
  placeholder?: string;
  title?: string;
  /** panel: the header's side panel or dialog · page: the tutor page. */
  variant: "panel" | "page";
  /** Shown as a Close button (the dialog). */
  onClose?: () => void;
  /** Marks the composer as where a dialog puts focus when it opens. */
  autoFocus?: boolean;
}) {
  const key = chatKey(learnerId, capabilityId);
  const { messages, draft, busy } = useChat(key);
  const extras = useChatExtras(key);
  const presets = presetsProp ?? extras.presets ?? [];
  const placeholder = placeholderProp ?? extras.placeholder;
  const ids = useId();
  const log = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const send = (text: string, label?: string) => ask(key, learnerId, capabilityId, text, { label });

  // Grow the composer with its text, up to the CSS max-height (then it scrolls).
  useLayoutEffect(() => {
    const el = input.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight + 2}px`;
  }, [draft]);

  // Keep the newest exchange in view: the bottom after a question, the START of an answer
  // (a long answer is read from its first line).
  const last = messages[messages.length - 1];
  useEffect(() => {
    const el = log.current;
    if (!el) return;
    const node = el.querySelector<HTMLElement>("[data-last]");
    el.scrollTop = last?.role === "tutor" && node ? node.offsetTop - 8 : el.scrollHeight;
  }, [last?.id, last?.role, busy]);

  const status = busy ? "Waiting for the tutor’s answer…"
    : last?.role === "tutor" ? "The tutor answered."
    : last?.role === "learner" && last.status === "failed" ? "The question wasn’t answered. You can retry it." : "";

  return (
    <section className={`chat chat-${variant}`} aria-labelledby={`${ids}-h`}>
      <header className="chat-head">
        <div className="chat-title">
          <span className="tutor-avatar" aria-hidden="true">C</span>
          <h2 id={`${ids}-h`}>{title}</h2>
          {onClose && (
            <button type="button" className="chat-close" onClick={onClose} aria-label="Close the tutor">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2"
                strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
            </button>
          )}
        </div>
        <p className="chat-note">
          Each question is answered on its own — the tutor doesn&apos;t see earlier messages.
        </p>
      </header>

      <div className="chat-log" ref={log} tabIndex={0} role="region" aria-label="Conversation with the tutor">
        {messages.length === 0 && !busy && (
          <div className="chat-empty">
            <p>{capabilityId ? "Ask about this topic." : "Ask about anything in your course."}</p>
            <p className="small muted">
              Answers come from your course material, with sources. If the material doesn&apos;t cover a
              course question, you get a clearly labelled general explanation; questions outside the
              course are declined.
            </p>
          </div>
        )}
        <ol className="chat-messages">
          {messages.map((m) => (
            <li key={m.id} className={m.role === "learner" ? "from-learner" : "from-tutor"}
              data-last={m === last ? "" : undefined}>
              {m.role === "learner"
                ? <LearnerMessage m={m} busy={busy}
                    onRetry={() => ask(key, learnerId, capabilityId, m.text, { retry: m.id })} />
                : <TutorMessage a={m.answer} />}
            </li>
          ))}
          {busy && (
            <li className="from-tutor">
              <div className="bubble tutor pending">
                <span className="visually-hidden">Tutor: </span>
                <Loading stages={["Looking in your course material…"]} />
              </div>
            </li>
          )}
        </ol>
      </div>

      {presets.length > 0 && (
        <div className="chat-presets" role="group" aria-label="Suggested questions">
          {presets.map((p) => (
            <button key={p.label} type="button" className="chip" disabled={busy} onClick={() => send(p.question, p.label)}>
              {p.label}
            </button>
          ))}
        </div>
      )}

      <form className="chat-composer" onSubmit={(e) => { e.preventDefault(); send(draft); }}>
        <label className="visually-hidden" htmlFor={`${ids}-in`}>Your question for the tutor</label>
        <textarea id={`${ids}-in`} ref={input} rows={1} value={draft} data-autofocus={autoFocus || undefined}
          placeholder={placeholder ?? "Ask a question…"} aria-describedby={`${ids}-hint`}
          onChange={(e) => setDraft(key, e.target.value)}
          onKeyDown={(e) => {
            // Enter sends; Shift+Enter is a new line. Never while an IME is composing a word.
            if (e.key !== "Enter" || e.shiftKey || e.nativeEvent.isComposing || e.keyCode === 229) return;
            e.preventDefault();
            send(draft);
          }} />
        <button type="submit" className="btn chat-send" disabled={busy || !draft.trim()}>
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 12l16-8-6 16-2-7z" /></svg>
          Send
        </button>
        <p id={`${ids}-hint`} className="chat-hint">
          {busy ? "You can type your next question while you wait." : "Enter to send · Shift+Enter for a new line"}
        </p>
      </form>
      <div className="visually-hidden" aria-live="polite">{status}</div>
    </section>
  );
}

function LearnerMessage({ m, busy, onRetry }: {
  m: Extract<ChatMessage, { role: "learner" }>; busy: boolean; onRetry: () => void;
}) {
  return (
    <>
      <div className={`bubble learner${m.status === "failed" ? " failed" : ""}`}>
        <span className="visually-hidden">You: </span>
        {m.label ? <strong>{m.label}</strong> : <p className="bubble-text">{m.text}</p>}
      </div>
      {m.status === "failed" && (
        <div className="bubble-failure">
          <ErrorBox error={`Not answered. ${m.error ?? ""}`.trim()} />
          <button type="button" className="btn secondary sm" disabled={busy} onClick={onRetry}>Retry this question</button>
        </div>
      )}
    </>
  );
}

function TutorMessage({ a }: { a: TutorAnswer }) {
  if (a.kind === "general") {
    return (
      <div className="bubble tutor general">
        <span className="visually-hidden">Tutor: </span>
        <div className="general-label">⚠ Not in your course material — general explanation</div>
        <Markdown text={a.answer} />
        <div className="small muted">Check your lecture notes: your lecturer may present this differently.</div>
      </div>
    );
  }
  if (!a.answered) {
    return (
      <div className="bubble tutor declined">
        <span className="visually-hidden">Tutor: </span>
        {a.answer}
      </div>
    );
  }
  return (
    <div className="bubble tutor">
      <span className="visually-hidden">Tutor: </span>
      <div className="grounded-label">✓ From your course material</div>
      <Markdown text={a.answer} />
      <Sources sources={a.sources} />
    </div>
  );
}
