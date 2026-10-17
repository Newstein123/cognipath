"use client";

import { useEffect, useRef, useState } from "react";
import { TutorChat } from "./TutorChat";

/** Width at which Home has room for the tutor beside the learning column (sidebar 248 +
 *  padding + a ≥ 560px column + gap + a 360px panel). Narrower, the tutor is a launcher. */
const SIDE_BY_SIDE = "(min-width: 1280px)";

function useMedia(query: string): boolean {
  const [matches, setMatches] = useState(() => typeof window !== "undefined" && window.matchMedia(query).matches);
  useEffect(() => {
    const m = window.matchMedia(query);
    const onChange = () => setMatches(m.matches);
    onChange();
    m.addEventListener("change", onChange);
    return () => m.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

/** Home's tutor: a panel beside the learning column on wide screens; on smaller ones a
 *  launcher, docked along the bottom edge, that opens it as a dialog. Messages and draft live in lib/tutorChat, so
 *  they are the same in both forms and survive closing it. */
export function TutorPanel({ learnerId }: { learnerId: string }) {
  const wide = useMedia(SIDE_BY_SIDE);
  const [open, setOpen] = useState(false);
  const launcher = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (wide) setOpen(false); }, [wide]);

  if (wide) {
    return (
      <aside className="home-tutor" aria-label="Tutor">
        <TutorChat variant="panel" learnerId={learnerId} />
      </aside>
    );
  }
  return (
    <>
      <div className="tutor-dock">
        <button ref={launcher} type="button" className="tutor-launcher" aria-haspopup="dialog" aria-expanded={open}
          onClick={() => setOpen(true)}>
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8"
            strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 5h16v11H9l-5 4z" /></svg>
          Ask the tutor
        </button>
      </div>
      <TutorDialog open={open} onClose={() => { setOpen(false); launcher.current?.focus(); }}>
        <TutorChat variant="panel" learnerId={learnerId} autoFocus onClose={() => { setOpen(false); launcher.current?.focus(); }} />
      </TutorDialog>
    </>
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
      d.style.height = ""; d.style.top = "";
      Object.assign(body.style, before);
      window.scrollTo(0, y);
    };
  }, [open]);

  return (
    <dialog ref={ref} className="tutor-dialog" aria-label="Ask the tutor"
      onCancel={(e) => { e.preventDefault(); onClose(); }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      {open && children}
    </dialog>
  );
}
