"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, pct, stepHref, type LearnerCreated, type LearnerSummary, type NextActivities, type OnboardingOptions } from "@/lib/api";
import { ErrorBox, Loading } from "@/components/ui";

export default function Start() {
  const router = useRouter();
  const [options, setOptions] = useState<OnboardingOptions | null>(null);
  const [learners, setLearners] = useState<LearnerSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState<LearnerCreated | null>(null);
  // What the engine wants first: a diagnosis, or — for someone new to all of it — a lesson.
  const [first, setFirst] = useState<NextActivities | null>(null);
  useEffect(() => {
    if (created) api.next(created.learner.id).then(setFirst).catch(() => {});
  }, [created]);

  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [techs, setTechs] = useState<string[]>([]);
  const [level, setLevel] = useState("intermediate");
  const [knows, setKnows] = useState("");
  const [built, setBuilt] = useState("");

  useEffect(() => {
    api.options().then(setOptions).catch((e) => setError(e.message));
    api.learners().then(setLearners).catch(() => {});
  }, []);

  const toggle = (t: string) =>
    setTechs((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]));

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      setCreated(await api.createLearner({ name, goal, technologies: techs, knows, built, level }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // --- screen 2: what we understood -------------------------------------------------
  if (created) {
    const id = created.learner.id;
    return (
      <main className="center">
        <Brand />
        <div className="card">
          <div className="small muted">Your goal</div>
          <p style={{ fontSize: 17 }}>&ldquo;{created.goal.text}&rdquo;</p>
          <p>
            We read this as <strong>{created.goal.goalName}</strong>.
            {!created.goal.supported && (
              <span className="muted"> Only the backend path is fully supported in this preview.</span>
            )}
          </p>
        </div>
        <div className="card">
          <h2>Here&apos;s what we understand so far</h2>
          <div className="notice small">
            This is an initial estimate based on what you told us — not an assessment.{" "}
            {first?.stage === "starting from scratch"
              ? "You're new to this, so there's nothing to test yet — we'll start by teaching the foundations."
              : "Next, we'll check the parts that matter most for your goal."}
          </div>
          {created.initialEstimates.length ? (
            <ul className="list">
              {created.initialEstimates.map((e) => (
                <li key={e.capabilityId} className="spread">
                  <div>
                    <strong>{e.name}</strong>
                    <div className="small muted">{e.reason}</div>
                  </div>
                  <span className="small">you: {pct(e.selfRated)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Nothing to go on yet — we&apos;ll start from the basics.</p>
          )}
          {created.unrecognisedTechnologies.length > 0 && (
            <p className="small muted">Not recognised: {created.unrecognisedTechnologies.join(", ")}</p>
          )}
          {first?.stage === "starting from scratch" && first.steps[0] ? (
            <>
              <h3 style={{ marginTop: 16 }}>Your learning order</h3>
              <ol className="small" style={{ paddingLeft: 20 }}>
                {first.steps.map((s) => <li key={s.title}>{s.title}</li>)}
              </ol>
              <button className="btn block" style={{ marginTop: 12 }}
                onClick={() => router.push(stepHref(id, first.steps[0]) ?? `/learn/${encodeURIComponent(id)}`)}>
                Start my first lesson: {first.steps[0].capabilityName} →
              </button>
            </>
          ) : (
            <button className="btn block" style={{ marginTop: 12 }} disabled={!first}
              onClick={() => router.push(`/learn/${encodeURIComponent(id)}/diagnostic`)}>
              Looks good — start the quick diagnosis →
            </button>
          )}
        </div>
      </main>
    );
  }

  // --- screen 1: set your goal ------------------------------------------------------
  return (
    <main className="center">
      <Brand />
      <div className="card">
        <h1>What do you want to be able to do?</h1>
        <p className="muted">
          Tell us what you&apos;re trying to achieve. We&apos;ll find out what you already know
          and teach only what you need.
        </p>

        <label htmlFor="goal">Your goal</label>
        <textarea id="goal" value={goal} maxLength={500} style={{ minHeight: 80 }}
          placeholder={options?.examples[0] ? `${options.examples[0]}…` : "What do you want to achieve?"}
          onChange={(e) => setGoal(e.target.value)} />
        <div style={{ marginTop: 8 }}>
          {options?.examples.map((x) => (
            <button key={x} className="chip" onClick={() => setGoal(x)}>{x}</button>
          ))}
        </div>

        <label htmlFor="name">Your name</label>
        <input id="name" type="text" value={name} onChange={(e) => setName(e.target.value)} />

        <label>{options?.topicsLabel ?? "Technologies you have used"}</label>
        <div>
          {options?.technologies.map((t) => (
            <button key={t} className={`chip ${techs.includes(t) ? "on" : ""}`} onClick={() => toggle(t)}>
              {t}
            </button>
          ))}
        </div>

        <label htmlFor="level">How confident are you overall?</label>
        <select id="level" value={level} onChange={(e) => setLevel(e.target.value)}>
          {options?.levels.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
        </select>

        <details style={{ marginTop: 14 }}>
          <summary className="small">Tell us more (optional)</summary>
          <label htmlFor="knows">What do you already know?</label>
          <textarea id="knows" value={knows} style={{ minHeight: 70 }} onChange={(e) => setKnows(e.target.value)} />
          <label htmlFor="built">What have you built?</label>
          <textarea id="built" value={built} style={{ minHeight: 70 }} onChange={(e) => setBuilt(e.target.value)} />
        </details>

        <ErrorBox error={error} />
        {busy ? <Loading stages={["Building your starting map…"]} /> : (
          <button className="btn block" style={{ marginTop: 16 }}
            disabled={!goal.trim() || !name.trim()} onClick={submit}>
            Discover my learning path →
          </button>
        )}
      </div>

      {learners.length > 0 && (
        <div className="card">
          <h2>Continue as</h2>
          <ul className="list">
            {learners.map((l) => (
              <li key={l.id} className="spread">
                <div>
                  <strong>{l.name}</strong> <span className="small muted">({l.id})</span>
                  <div className="small muted">
                    {l.goal ?? "No goal"} · {l.counts.mastered} mastered, {l.counts.developing} developing
                  </div>
                </div>
                <Link className="btn secondary" href={`/learn/${encodeURIComponent(l.id)}`}>Open →</Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </main>
  );
}

function Brand() {
  return (
    <div className="brand" style={{ marginBottom: 20 }}>
      <span className="brand-mark" /> Cognith
      <span className="muted small" style={{ fontWeight: 400 }}>Learn what you need, not everything.</span>
    </div>
  );
}
