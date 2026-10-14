"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, param, type Course } from "@/lib/api";
import { setInlineMath } from "@/lib/settings";

export default function LearnerLayout({ children }: { children: React.ReactNode }) {
  const id = param(useParams().id);
  const path = usePathname();
  // The learner's course decides display settings (inline maths); render once known.
  const [course, setCourse] = useState<Course | null>(null);
  useEffect(() => {
    api.profile(id).then((p) => { setInlineMath(p.learner.course.inlineMath); setCourse(p.learner.course); })
      .catch(() => setCourse({ id: "", name: "", subject: "", description: "", inlineMath: false }));
  }, [id]);
  const base = `/learn/${encodeURIComponent(id)}`;
  const nav = [
    { href: base, label: "Home" },
    { href: `${base}/diagnostic`, label: "Diagnosis" },
    { href: `${base}/profile`, label: "Skill profile" },
    { href: `${base}/tutor`, label: "Ask the tutor" },
    { href: `${base}/history`, label: "History" },
  ];
  const isActive = (href: string) =>
    href === base ? path === base : path.startsWith(href);

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/" className="brand"><span className="brand-mark" /> Cognith</Link>
        <nav className="nav">
          {nav.map((n) => (
            <Link key={n.href} href={n.href} className={isActive(n.href) ? "active" : ""}>{n.label}</Link>
          ))}
        </nav>
        <div className="who">
          {course?.name && <>Course: <strong>{course.name}</strong><br /></>}
          Learner: <strong>{id}</strong>
          <br /><Link href="/">Switch learner</Link>
        </div>
      </aside>
      <main className="main">{course ? children : null}</main>
    </div>
  );
}
