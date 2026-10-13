"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { param } from "@/lib/api";

export default function LearnerLayout({ children }: { children: React.ReactNode }) {
  const id = param(useParams().id);
  const path = usePathname();
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
          Learner: <strong>{id}</strong>
          <br /><Link href="/">Switch learner</Link>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
