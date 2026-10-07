import { exact, tokens, usd } from "./format.js";

const KINDS = [
  ["input", "Input", "New prompt tokens sent to the model"],
  ["cache_write", "Cache write", "Prompt tokens stored in the cache for reuse"],
  ["cache_read", "Cache read", "Prompt tokens reused from the cache (much cheaper)"],
  ["output", "Output", "Tokens the model wrote: code, messages and tool calls"],
];

export default function TokenPanel({ run }) {
  const t = run.totals;
  const max = Math.max(1, ...run.agents.map((a) => a.usage.total));

  return (
    <aside className="token-panel card" aria-label="Token usage">
      <h2>Token usage</h2>
      <div className="tp-total">
        <span className="tp-big">{tokens(t.total)}</span>
        <span className="muted">tokens · {exact(t.api_calls)} API calls</span>
      </div>

      <dl className="tp-kinds">
        {KINDS.map(([key, label, help]) => (
          <div key={key} title={help}>
            <dt><span className={`swatch k-${key}`} />{label}</dt>
            <dd>{exact(t[key])}</dd>
          </div>
        ))}
      </dl>
      <div className="stack-bar" aria-hidden>
        {KINDS.map(([key]) => (
          <span key={key} className={`k-${key}`} style={{ flexGrow: t[key] }} />
        ))}
      </div>

      <div className="tp-cost">
        <span>Cost (API list price)</span>
        <b>{usd(t.cost_usd)}</b>
      </div>

      <h3>Per agent</h3>
      <ul className="tp-agents">
        {run.agents.map((a) => {
          const u = a.usage;
          const ctxPct = u.context_window ? Math.min(100, (u.context / u.context_window) * 100) : null;
          return (
            <li key={a.role}>
              <div className="tpa-row">
                <span className={`dot s-${a.status}`} />
                <span className="tpa-name">{a.title}</span>
                <span className="tpa-num">{tokens(u.total)}</span>
              </div>
              <div className="bar"><span style={{ width: `${(u.total / max) * 100}%` }} /></div>
              <div className="tpa-meta">
                <span>out {tokens(u.output)}</span>
                <span>context {tokens(u.context)}{ctxPct !== null && ` (${ctxPct.toFixed(1)}%)`}</span>
                <span>{u.cost_usd ? usd(u.cost_usd) : a.status === "running" ? "cost at finish" : ""}</span>
              </div>
            </li>
          );
        })}
      </ul>

      <p className="tp-note">
        Counts update live with each API call. Cost appears as each agent finishes. On a Claude
        subscription you aren't billed this amount; usage counts against your plan's limits instead.
        <br /><b>Context</b> is how full the agent's memory was on its latest call.
      </p>
    </aside>
  );
}
