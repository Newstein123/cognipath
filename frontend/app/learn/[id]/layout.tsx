"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, param, type Course } from "@/lib/api";
import { setInlineMath } from "@/lib/settings";
import { ThemeSwitch } from "@/components/ui";
import { SIDE_BY_SIDE, TutorModal, TutorRail, TutorToggle, useMedia } from "@/components/TutorPanel";

// 24×24 outline icons, drawn in currentColor so they follow the link's state.
const ICON: Record<string, React.ReactNode> = {
  home: <path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z" />,
  diagnosis: <><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M9 4h6v3H9zM9 12l2 2 4-4" /></>,
  profile: <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />,
  tutor: <path d="M4 5h16v11H9l-5 4z" />,
  history: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
};

function Icon({ name }: { name: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICON[name]}</svg>
  );
}

export default function LearnerLayout({ children }: { children: React.ReactNode }) {
  const params = useParams();
  const id = param(params.id);
  const path = usePathname();
  // The learner's course decides display settings (inline maths); render once known.
  const [course, setCourse] = useState<Course | null>(null);
  const [learnerName, setLearnerName] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const sidebar = useRef<HTMLElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  // The tutor: closed until asked for. Beside the page on wide screens, a dialog otherwise.
  const [tutorOpen, setTutorOpen] = useState(false);
  const tutorButton = useRef<HTMLButtonElement>(null);
  const wide = useMedia(SIDE_BY_SIDE);
  // In a lesson the tutor answers from that topic's material only: its own conversation,
  // never the course-wide one. The topic comes from the route, so it is right from the start.
  const lessonCap = path.startsWith(`/learn/${encodeURIComponent(id)}/lesson/`) && params.cap ? param(params.cap) : undefined;
  // Another learner or topic, or a change between the side-by-side and dialog forms, starts closed.
  useEffect(() => { setTutorOpen(false); }, [id, wide, lessonCap]);
  // Focus goes back to the toggle without scrolling to it: closing must leave a learner
  // where they were reading, e.g. far down a lesson.
  const closeTutor = () => { setTutorOpen(false); tutorButton.current?.focus({ preventScroll: true }); };
  useEffect(() => {
    api.profile(id).then((p) => {
      setInlineMath(p.learner.course.inlineMath); setCourse(p.learner.course); setLearnerName(p.learner.name);
    }).catch(() => setCourse({ id: "", name: "", subject: "", description: "", inlineMath: false }));
  }, [id]);
  // Choosing a page closes the mobile menu; the new page then starts at the top.
  const navigated = useRef(false);
  const lastPath = useRef(path);
  useEffect(() => {
    if (path === lastPath.current) return;
    lastPath.current = path;
    navigated.current = true;
    setMenuOpen(false);
  }, [path]);
  // Widening to the desktop layout (where the menu is the sidebar) resets it.
  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 861px)");
    const onChange = () => { if (desktop.matches) setMenuOpen(false); };
    desktop.addEventListener("change", onChange);
    return () => desktop.removeEventListener("change", onChange);
  }, []);
  // The open menu is modal: the page behind is inert (main has `inert`) and covered by a
  // backdrop that only closes the menu, focus cycles inside the panel, Escape closes and
  // returns focus to the button, and the page cannot scroll — it is held where it was and
  // restored on close (a page chosen from the menu starts at the top instead).
  useEffect(() => {
    const bar = sidebar.current;
    if (!menuOpen || !bar) return;
    navigated.current = false;  // only a navigation while this menu is open counts
    const body = document.body;
    const before = { position: body.style.position, top: body.style.top, left: body.style.left, right: body.style.right };
    const start = window.scrollY;
    // If the top bar is partly scrolled away, bring all of it — and its close button — into view.
    const held = Math.max(0, start + Math.min(0, bar.getBoundingClientRect().top));
    Object.assign(body.style, { position: "fixed", top: `-${held}px`, left: "0", right: "0" });
    bar.style.setProperty("--menu-top", `${bar.getBoundingClientRect().bottom}px`);

    const focusable = () => [...bar.querySelectorAll<HTMLElement>("a[href], button:not([disabled]), input:not([disabled])")]
      .filter((el) => !(el instanceof HTMLInputElement && el.type === "radio" && !el.checked) && el.getClientRects().length > 0);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setMenuOpen(false); menuButton.current?.focus(); return; }
      if (e.key !== "Tab") return;
      const items = focusable();
      if (!items.length) return;
      const [first, last] = [items[0], items[items.length - 1]];
      const inside = bar.contains(document.activeElement);
      if (e.shiftKey && (document.activeElement === first || !inside)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && (document.activeElement === last || !inside)) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      Object.assign(body.style, before);
      window.scrollTo(0, navigated.current ? 0 : start);
      navigated.current = false;
    };
  }, [menuOpen]);
  const base = `/learn/${encodeURIComponent(id)}`;
  const nav = [
    { href: base, label: "Home", icon: "home" },
    { href: `${base}/diagnostic`, label: "Diagnosis", icon: "diagnosis" },
    { href: `${base}/profile`, label: "Skill profile", icon: "profile" },
    { href: `${base}/tutor`, label: "Ask the tutor", icon: "tutor" },
    { href: `${base}/history`, label: "History", icon: "history" },
  ];
  const isActive = (href: string) =>
    href === base ? path === base : path.startsWith(href);
  // Offered on Home, the skill profile, history and lessons (scoped to the lesson's topic).
  // Not on the tutor page (it is the chat) or during a diagnosis or challenge (an attempt is
  // answered without the tutor beside it).
  const tutorHere = !!course && (!!lessonCap || [base, `${base}/profile`, `${base}/history`].includes(path));
  const rail = tutorHere && wide;

  return (
    <div className={rail ? (tutorOpen ? "shell has-tutor tutor-open" : "shell has-tutor") : "shell"}>
      {/* Mobile only (CSS): catches the first outside tap so it closes the menu and nothing else. */}
      <div className={menuOpen ? "backdrop open" : "backdrop"} aria-hidden="true" onClick={() => setMenuOpen(false)} />
      <aside ref={sidebar} className={menuOpen ? "sidebar open" : "sidebar"}
        {...(menuOpen ? { role: "dialog", "aria-modal": true, "aria-label": "Menu" } : {})}>
        <Link href="/" className="brand"><span className="brand-mark" aria-hidden="true" /> Cognith</Link>
        <button ref={menuButton} type="button" className="menu-btn" aria-expanded={menuOpen} aria-controls="learner-menu"
          onClick={() => setMenuOpen((o) => !o)}>
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" aria-hidden="true">
            {menuOpen ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
          </svg>
          {menuOpen ? "Close menu" : "Menu"}
        </button>
        <div className="drawer" id="learner-menu">
          <nav className="nav" aria-label="Learner">
            {nav.map((n) => {
              const active = isActive(n.href);
              return (
                <Link key={n.href} href={n.href} className={active ? "active" : ""}
                  aria-current={active ? "page" : undefined}>
                  <Icon name={n.icon} />{n.label}
                </Link>
              );
            })}
          </nav>
          <div className="who">
            {course?.name && <div>Course<br /><strong>{course.name}</strong></div>}
            {learnerName && <div>Learner<br /><strong>{learnerName}</strong></div>}
            <div><Link href="/">Switch learner</Link></div>
            <div style={{ marginTop: 14 }}><ThemeSwitch tone="on-dark" /></div>
          </div>
        </div>
      </aside>
      {/* Home's content is centred, up to about 1100px (globals.css). */}
      <main className={path === base ? "main wide" : "main"} id="main" inert={menuOpen}>
        {tutorHere && (
          <div className="learner-bar">
            <TutorToggle open={tutorOpen} onToggle={() => setTutorOpen((o) => !o)} buttonRef={tutorButton} />
          </div>
        )}
        {course ? children : null}
      </main>
      {rail && <TutorRail learnerId={id} capabilityId={lessonCap} open={tutorOpen} onClose={closeTutor} />}
      {tutorHere && !wide && <TutorModal learnerId={id} capabilityId={lessonCap} open={tutorOpen} onClose={closeTutor} />}
    </div>
  );
}
