import { useEffect, useState } from "react";
import { cancelRun, getRun, isFinished, watchRun } from "./api.js";
import AgentDetail from "./AgentDetail.jsx";
import { clock, duration, STATUS_LABEL } from "./format.js";
import Pipeline from "./Pipeline.jsx";
import TokenPanel from "./TokenPanel.jsx";

// Re-render every second while a build is running, so timers tick.
function useTicker(active) {
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(timer);
  }, [active]);
}

export default function RunView({ id }) {
  const [run, setRun] = useState(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    let stop = () => {};
    getRun(id)
      .then((snapshot) => {
        setRun(snapshot);
        if (!isFinished(snapshot.status)) {
          stop = watchRun(id, setRun, () => setError("Lost connection to the server. Refresh to reconnect."));
        }
      })
      .catch((e) => setError(e.message));
    return () => stop();
  }, [id]);

  const live = run && !isFinished(run.status);
  useTicker(live);

  if (error && !run) return <main className="run"><p className="alert">{error}</p></main>;
  if (!run) return <main className="run"><p className="muted">Loading…</p></main>;

  // Follow the running agent until the user picks one themselves.
  const running = run.agents.filter((a) => a.status === "running");
  const fallback = running.at(-1) ?? [...run.agents].reverse().find((a) => a.status !== "waiting") ?? run.agents[0];
  const agent = run.agents.find((a) => a.role === selected) ?? fallback;
  const finalReport = run.status === "done" ? run.agents.at(-1)?.handoff : "";

  async function stop() {
    if (confirm("Stop this build? Running agents are terminated; files written so far are kept.")) {
      setRun(await cancelRun(id));
    }
  }

  return (
    <main className="run">
      <div className="run-main">
        <section className="card run-head">
          <div className="rh-title">
            <h1>{run.spec.name}</h1>
            <span className={`pill s-${run.status}`}>{live && <span className="spinner" />}{STATUS_LABEL[run.status]}</span>
            <span className="muted">{duration(run.started_at ?? run.created_at, run.ended_at)}</span>
            {live && <button className="btn btn-danger" onClick={stop}>■ Stop</button>}
          </div>
          <p className="rh-idea">{run.spec.idea}</p>
          <div className="rh-stack">
            <span><b>Backend</b> {run.layers.backend}</span>
            <span><b>Frontend</b> {run.layers.frontend}</span>
            <span><b>Database</b> {run.layers.database}</span>
          </div>
          <div className="rh-path">
            <code>{run.project_dir}</code>
            <button className="btn btn-ghost btn-sm" onClick={() => navigator.clipboard?.writeText(run.project_dir)}>Copy path</button>
          </div>
          {error && <p className="alert">{error}</p>}
          {run.status === "failed" && <p className="alert">Build failed: {run.error}</p>}
        </section>

        <Pipeline agents={run.agents} selected={agent.role} onSelect={setSelected} />

        {finalReport && (
          <section className="card report">
            <h2>✓ Final report from the Integrator</h2>
            <pre className="prose">{finalReport}</pre>
          </section>
        )}

        <AgentDetail agent={agent} />

        <section className="card">
          <h2>Orchestration timeline</h2>
          <ul className="timeline">
            {run.log.map((e, i) => (
              <li key={i} className={`tl-${e.kind}`}>
                <time>{clock(e.t)}</time>
                <span>{e.text}</span>
              </li>
            ))}
          </ul>
          {run.handoffs.length > 0 && (
            <>
              <h3>Context passed between agents</h3>
              {run.handoffs.map((h, i) => (
                <details key={i} className="handoff">
                  <summary>
                    <b>{h.from}</b> → {h.to.join(", ")} <span className="muted">· {h.text.split(/\s+/).filter(Boolean).length} words</span>
                  </summary>
                  <pre className="prose">{h.text}</pre>
                </details>
              ))}
            </>
          )}
        </section>
      </div>

      <TokenPanel run={run} />
    </main>
  );
}
