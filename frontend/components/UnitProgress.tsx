"use client";

import type { UnitInfo } from "@/lib/api";

/** Every concept in the unit's material, grouped by part, with this learner's coverage. */
export function UnitProgress({ unit, current }: { unit: UnitInfo; current?: number }) {
  const parts = Array.from({ length: unit.parts }, (_, i) => i + 1);
  const pct = unit.total ? Math.round((unit.covered / unit.total) * 100) : 0;
  return (
    <div className="card unit">
      <div className="spread">
        <strong>
          {current ? `Part ${current} of ${unit.parts}` : "Unit"} · covered {unit.covered} of {unit.total} ideas
        </strong>
        <span className="small muted">{pct}% of the material</span>
      </div>
      <div className="progress"><span style={{ width: `${pct}%` }} /></div>
      <details>
        <summary className="small">Everything this unit covers</summary>
        {parts.map((p) => (
          <div key={p} style={{ marginTop: 8 }}>
            <div className="small muted" style={{ fontWeight: 700 }}>
              PART {p}{p === current ? " — this lesson" : ""}
            </div>
            <ul className="unit-list">
              {unit.concepts.filter((c) => c.part === p).map((c) => (
                <li key={c.id} className={c.status ?? "todo"}>
                  <span className="mark">{c.status === "met" ? "✓" : c.status === "partial" ? "△" : c.status === "unmet" ? "!" : "○"}</span>
                  {c.title}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </details>
    </div>
  );
}
