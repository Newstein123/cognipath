"use client";

import type { Diagram as D } from "@/lib/api";

/** Draws a lesson diagram from data. The model chooses the type and fills the fields;
 *  drawing here keeps every diagram clean and consistent with what it claims. */
export function Diagram({ d }: { d: D }) {
  if (d.type === "none") return null;
  return (
    <figure className="diagram">
      {d.type === "venn" && <Venn d={d} />}
      {d.type === "mapping" && <Mapping d={d} />}
      {d.type === "table" && <Table d={d} />}
      {d.type === "flow" && <Flow d={d} />}
      {d.caption && <figcaption className="small muted">{d.caption}</figcaption>}
    </figure>
  );
}

const SHADE_LABEL: Record<string, (a: string, b: string) => string> = {
  union: (a, b) => `${a} ∪ ${b}`,
  intersection: (a, b) => `${a} ∩ ${b}`,
  first_minus_second: (a, b) => `${a} − ${b}`,
  second_minus_first: (a, b) => `${b} − ${a}`,
  complement_first: (a) => `${a}′`,
};

/** Two-set Venn diagram; the shaded region is the operation being taught. */
function Venn({ d }: { d: D }) {
  const [a, b] = d.sets;
  const W = 360, H = 230, r = 82, A = { x: 140, y: 118 }, B = { x: 220, y: 118 };
  const circle = (c: { x: number; y: number }, extra: Record<string, string> = {}) =>
    <circle cx={c.x} cy={c.y} r={r} {...extra} />;
  const shade = d.shade;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="svg" role="img"
      aria-label={`Venn diagram of ${a} and ${b}${shade !== "none" ? `, shading ${SHADE_LABEL[shade]?.(a, b)}` : ""}`}>
      <defs>
        <clipPath id="clipA">{circle(A)}</clipPath>
        <clipPath id="clipB">{circle(B)}</clipPath>
        <mask id="notB"><rect width={W} height={H} fill="white" />{circle(B, { fill: "black" })}</mask>
        <mask id="notA"><rect width={W} height={H} fill="white" />{circle(A, { fill: "black" })}</mask>
      </defs>
      <rect x="4" y="4" width={W - 8} height={H - 8} rx="10" className="universe" />
      {/* shaded region */}
      {shade === "union" && <>{circle(A, { className: "shade" })}{circle(B, { className: "shade" })}</>}
      {shade === "intersection" && <g clipPath="url(#clipA)">{circle(B, { className: "shade" })}</g>}
      {shade === "first_minus_second" && <g mask="url(#notB)">{circle(A, { className: "shade" })}</g>}
      {shade === "second_minus_first" && <g mask="url(#notA)">{circle(B, { className: "shade" })}</g>}
      {shade === "complement_first" && <g mask="url(#notA)"><rect x="4" y="4" width={W - 8} height={H - 8} rx="10" className="shade" /></g>}
      {circle(A, { className: "set-line" })}
      {circle(B, { className: "set-line" })}
      <text x="16" y="24" className="label">U</text>
      <text x={A.x - r + 4} y={A.y - r + 14} className="label">{a}</text>
      <text x={B.x + r - 16} y={B.y - r + 14} className="label">{b}</text>
      <text x={A.x - 38} y={A.y + 5} className="elems" textAnchor="middle">{d.onlyFirst.join(", ")}</text>
      <text x={(A.x + B.x) / 2} y={A.y + 5} className="elems" textAnchor="middle">{d.both.join(", ")}</text>
      <text x={B.x + 38} y={B.y + 5} className="elems" textAnchor="middle">{d.onlySecond.join(", ")}</text>
      {d.outside.length > 0 && <text x="16" y={H - 14} className="elems">{d.outside.join(", ")}</text>}
      {shade !== "none" && SHADE_LABEL[shade] && (
        <text x={W - 16} y="24" className="label" textAnchor="end">shaded: {SHADE_LABEL[shade](a, b)}</text>
      )}
    </svg>
  );
}

function Mapping({ d }: { d: D }) {
  const rows = Math.max(d.domain.length, d.codomain.length);
  const H = 50 + rows * 34, W = 360, lx = 80, rx = 280;
  const y = (i: number, n: number) => 40 + (i + 0.5) * ((H - 60) / n);
  const pos = (list: string[], v: string) => list.indexOf(v);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="svg" role="img" aria-label="Arrow diagram">
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" className="arrowhead" />
        </marker>
      </defs>
      <text x={lx} y="20" className="label" textAnchor="middle">{d.fromLabel || "Domain"}</text>
      <text x={rx} y="20" className="label" textAnchor="middle">{d.toLabel || "Codomain"}</text>
      <ellipse cx={lx} cy={H / 2 + 10} rx="46" ry={(H - 50) / 2} className="set s0" />
      <ellipse cx={rx} cy={H / 2 + 10} rx="46" ry={(H - 50) / 2} className="set s1" />
      {d.arrows.map(([f, t], i) => (
        <line key={i} x1={lx + 18} y1={y(pos(d.domain, f), d.domain.length)}
          x2={rx - 22} y2={y(pos(d.codomain, t), d.codomain.length)} className="edge" markerEnd="url(#arrow)" />
      ))}
      {d.domain.map((v, i) => <text key={v} x={lx} y={y(i, d.domain.length) + 4} className="elems" textAnchor="middle">{v}</text>)}
      {d.codomain.map((v, i) => <text key={v} x={rx} y={y(i, d.codomain.length) + 4} className="elems" textAnchor="middle">{v}</text>)}
    </svg>
  );
}

function Table({ d }: { d: D }) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="dtable">
        <thead><tr>{d.headers.map((h, i) => <th key={i}>{h}</th>)}</tr></thead>
        <tbody>
          {d.rows.map((r, i) => (
            <tr key={i}>{r.map((c, j) => <td key={j} className={c === "T" ? "t" : c === "F" ? "f" : ""}>{c}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Flow({ d }: { d: D }) {
  return (
    <ol className="flow">
      {d.steps.map((s, i) => (
        <li key={i}><span className="n">{i + 1}</span><span>{s}</span></li>
      ))}
    </ol>
  );
}
