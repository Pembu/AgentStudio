import { duration, STATUS_LABEL, tokens } from "./format.js";

const ICON = { waiting: "○", running: "", done: "✓", failed: "✕", skipped: "–", cancelled: "■" };

// Column = how many hops from the first agent, so parallel agents share a column.
function columns(agents) {
  const depth = {};
  for (const a of agents) {
    depth[a.role] = a.depends_on.length ? Math.max(...a.depends_on.map((d) => depth[d])) + 1 : 0;
  }
  const cols = [];
  for (const a of agents) (cols[depth[a.role]] ??= []).push(a);
  return cols;
}

function statusLine(agent) {
  if (agent.status === "running") return agent.activity.at(-1)?.text ?? "Starting…";
  if (agent.status === "failed" || agent.status === "skipped") return agent.error;
  if (agent.status === "done") return agent.handoff.split("\n").find((l) => l.trim()) ?? "Finished";
  if (agent.status === "waiting") return agent.depends_on.length ? "Waiting for handoff…" : "Starting…";
  return STATUS_LABEL[agent.status];
}

function Connector({ from, to }) {
  const passed = from.every((a) => a.status === "done");
  const flowing = passed && to.some((a) => a.status === "running");
  return (
    <div className={`connector ${passed ? "passed" : ""} ${flowing ? "flowing" : ""}`} aria-hidden>
      <span className="c-line" />
      <span className="c-label">handoff</span>
    </div>
  );
}

export default function Pipeline({ agents, selected, onSelect }) {
  const cols = columns(agents);
  return (
    <section className="card">
      <h2>Agent pipeline</h2>
      <div className="pipeline">
        {cols.map((col, i) => (
          <div key={i} className="p-col-wrap">
            {i > 0 && <Connector from={cols[i - 1]} to={col} />}
            <div className="p-col">
              {col.map((a) => (
                <button
                  key={a.role}
                  className={`agent-card s-${a.status} ${a.role === selected ? "selected" : ""}`}
                  onClick={() => onSelect(a.role)}
                  aria-pressed={a.role === selected}
                >
                  <div className="ac-head">
                    <span className="ac-icon">{a.status === "running" ? <span className="spinner" /> : ICON[a.status]}</span>
                    <span className="ac-title">{a.title}</span>
                    <span className="ac-status">{STATUS_LABEL[a.status]}</span>
                  </div>
                  <div className="ac-summary">{a.summary}</div>
                  <div className="ac-now" title={statusLine(a)}>{statusLine(a)}</div>
                  <div className="ac-foot">
                    <span>{tokens(a.usage.total)} tokens</span>
                    {a.started_at && <span>{duration(a.started_at, a.ended_at)}</span>}
                    {a.model && <span>{a.model}</span>}
                  </div>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
