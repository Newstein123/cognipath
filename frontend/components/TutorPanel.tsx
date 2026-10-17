"use client";

import { useEffect, useRef, useState } from "react";
import { TutorChat } from "./TutorChat";

/** Width at which the tutor fits beside the page (sidebar 248 + padding + a >= 560px
 *  column + a 360px panel). Narrower, it opens as a dialog instead. */
export const SIDE_BY_SIDE = "(min-width: 1280px)";

/** Starts false on the server and the first client render (no hydration mismatch); the
 *  real value arrives one effect later, while the tutor is still closed. */
export function useMedia(query: string): boolean {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    const m = window.matchMedia(query);
    const onChange = () => setMatches(m.matches);
    onChange();
    m.addEventListener("change", onChange);
    return () => m.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

export const TUTOR_ID = "tutor-panel";

/** The header's "Ask the tutor" button. Opening or closing the tutor sends nothing: the
 *  conversation and draft live in lib/tutorChat and survive both. */
export function TutorToggle({ open, onToggle, buttonRef }: {
  open: boolean; onToggle: () => void; buttonRef: React.RefObject<HTMLButtonElement | null>;
}) {
  return (
    <button ref={buttonRef} type="button" className="tutor-toggle" aria-expanded={open} aria-controls={TUTOR_ID}
      onClick={onToggle}>
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8"
        strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 5h16v11H9l-5 4z" /></svg>
      Ask the tutor
    </button>
  );
}

/** Wide screens: a column beside the page. It stays mounted so opening and closing can
 *  animate (the page grid widens the column, .shell.has-tutor); closed, it is hidden and
 *  inert. Focus goes to the composer on open; Escape or Close hands it back to the toggle. */
export function TutorRail({ learnerId, capabilityId, open, onClose }: {
  learnerId: string; capabilityId?: string; open: boolean; onClose: () => void;
}) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    if (open) ref.current?.querySelector<HTMLElement>("[data-autofocus]")?.focus({ preventScroll: true });
  }, [open]);
  return (
    <aside ref={ref} id={TUTOR_ID} className={open ? "tutor-rail open" : "tutor-rail"} aria-label="Tutor"
      inert={!open} onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}>
      <div className="tutor-rail-inner">
        <TutorChat variant="panel" learnerId={learnerId} capabilityId={capabilityId} autoFocus onClose={onClose} />
      </div>
    </aside>
  );
}

/** Narrower screens: the same chat in a modal dialog. */
export function TutorModal({ learnerId, capabilityId, open, onClose }: {
  learnerId: string; capabilityId?: string; open: boolean; onClose: () => void;
}) {
  return (
    <TutorDialog open={open} onClose={onClose}>
      <TutorChat variant="panel" learnerId={learnerId} capabilityId={capabilityId} autoFocus onClose={onClose} />
    </TutorDialog>
  );
}

/** A modal <dialog>: the browser makes the page behind it inert and closes it on Escape.
 *  Here: focus starts in the composer and Tab cycles inside (a native modal lets it out to
 *  the browser's own controls), the backdrop closes it, the page behind can't scroll, and
 *  its height follows the visual viewport so the composer stays above the on-screen keyboard. */
function TutorDialog({ open, onClose, children }: { open: boolean; onClose: () => void; children: React.ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) {
      d.showModal();  // focuses the first control; the composer is where typing starts
      d.querySelector<HTMLElement>("[data-autofocus]")?.focus();
    }
    if (!open && d.open) d.close();
  }, [open]);

  useEffect(() => {
    const d = ref.current;
    if (!open || !d) return;
    // Hold the page where it is (iOS ignores overflow:hidden on body), restore on close.
    const body = document.body;
    const before = { position: body.style.position, top: body.style.top, left: body.style.left, right: body.style.right };
    const y = window.scrollY;
    Object.assign(body.style, { position: "fixed", top: `-${y}px`, left: "0", right: "0" });
    const vv = window.visualViewport;
    const fit = () => {
      if (!vv) return;
      d.style.height = `${vv.height}px`;
      d.style.top = `${vv.offsetTop}px`;
    };
    fit();
    vv?.addEventListener("resize", fit);
    vv?.addEventListener("scroll", fit);
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const items = [...d.querySelectorAll<HTMLElement>("a[href], button:not([disabled]), textarea:not([disabled]), [tabindex='0'], summary")]
        .filter((el) => el.getClientRects().length > 0);
      if (!items.length) return;
      const [first, last] = [items[0], items[items.length - 1]];
      const inside = d.contains(document.activeElement);
      if (e.shiftKey && (document.activeElement === first || !inside)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && (document.activeElement === last || !inside)) { e.preventDefault(); first.focus(); }
    };
    d.addEventListener("keydown", onKey);
    return () => {
      d.removeEventListener("keydown", onKey);
      vv?.removeEventListener("resize", fit);
      vv?.removeEventListener("scroll", fit);
      // Close first: the browser then returns focus to the toggle while the page is still
      // held, and the scroll restored below is where the learner was, not the toggle.
      if (d.open) d.close();
      d.style.height = ""; d.style.top = "";
      Object.assign(body.style, before);
      window.scrollTo(0, y);
    };
  }, [open]);

  return (
    <dialog ref={ref} id={TUTOR_ID} className="tutor-dialog" aria-label="Ask the tutor"
      onCancel={(e) => { e.preventDefault(); onClose(); }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      {open && children}
    </dialog>
  );
}
