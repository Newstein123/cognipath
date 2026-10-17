import { useSyncExternalStore } from "react";
import { api, type TutorAnswer } from "./api";

/** Tutor conversations, kept in memory for this browser tab so the draft and the messages
 *  survive closing the panel and moving between a learner's pages. One conversation per
 *  learner and scope (all of the course, or one capability inside its lesson): a learner
 *  belongs to exactly one course, so another learner's messages are never shown. Nothing is
 *  saved, and a reload starts afresh.
 *
 *  The tutor endpoint takes one question at a time and gets no earlier messages, so each
 *  question is answered on its own — the chat says so rather than imply it remembers. */

export type ChatMessage =
  | { id: number; role: "learner"; text: string; label?: string; status: "pending" | "sent" | "failed"; error?: string }
  | { id: number; role: "tutor"; answer: TutorAnswer };

export interface Chat { messages: ChatMessage[]; draft: string; busy: boolean }

const EMPTY: Chat = { messages: [], draft: "", busy: false };
const chats = new Map<string, Chat>();
const listeners = new Map<string, Set<() => void>>();
let nextId = 1;

export function chatKey(learnerId: string, capabilityId?: string): string {
  return JSON.stringify([learnerId, capabilityId ?? null]);
}

const read = (key: string) => chats.get(key) ?? EMPTY;

function write(key: string, update: (c: Chat) => Chat) {
  chats.set(key, update(read(key)));
  listeners.get(key)?.forEach((l) => l());
}

function subscribe(key: string, listener: () => void) {
  const set = listeners.get(key) ?? new Set();
  set.add(listener);
  listeners.set(key, set);
  return () => { set.delete(listener); };
}

export function useChat(key: string): Chat {
  return useSyncExternalStore((l) => subscribe(key, l), () => read(key), () => EMPTY);
}

export function setDraft(key: string, draft: string) {
  write(key, (c) => ({ ...c, draft }));
}

/** Ask one question. Ignored while an answer is pending, so a double press or a second
 *  Enter can't send twice. `retry` re-sends a failed message, moving it to the end. */
export async function ask(key: string, learnerId: string, capabilityId: string | undefined,
                          text: string, opts: { label?: string; retry?: number } = {}) {
  text = text.trim();
  if (!text || read(key).busy) return;
  const id = opts.retry ?? nextId++;
  const typed = opts.retry === undefined && opts.label === undefined;
  write(key, (c) => {
    const old = c.messages.find((m) => m.id === id);
    const label = old?.role === "learner" ? old.label : opts.label;
    return {
      busy: true,
      draft: typed ? "" : c.draft,
      messages: [...c.messages.filter((m) => m.id !== id), { id, role: "learner", text, label, status: "pending" }],
    };
  });
  try {
    const answer = await api.tutor(learnerId, text, capabilityId);
    write(key, (c) => ({
      ...c, busy: false,
      messages: [...c.messages.map((m) => (m.id === id && m.role === "learner" ? { ...m, status: "sent" as const } : m)),
                 { id: nextId++, role: "tutor", answer }],
    }));
  } catch (e) {
    write(key, (c) => ({
      ...c, busy: false,
      messages: c.messages.map((m) => (m.id === id && m.role === "learner"
        ? { ...m, status: "failed" as const, error: (e as Error).message } : m)),
    }));
  }
}
