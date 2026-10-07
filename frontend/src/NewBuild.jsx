import { useEffect, useMemo, useState } from "react";
import { getCatalog, listRuns, startRun } from "./api.js";
import { go } from "./App.jsx";
import { STATUS_LABEL, tokens, usd } from "./format.js";

const EXAMPLES = [
  { name: "Task Board", idea: "A kanban task board with columns (To do, Doing, Done), drag cards between columns, and add, edit and delete tasks." },
  { name: "Expense Tracker", idea: "Track expenses with amount, category and date. Show monthly totals per category and a simple chart." },
  { name: "Recipe Box", idea: "Save recipes with ingredients and steps, search by ingredient, and mark favourites." },
  { name: "Library", idea: "A small library system: books, members, borrowing and returning books, and a list of overdue loans." },
];

const EMPTY = {
  name: "", idea: "",
  backend: "python-fastapi", backend_custom: "",
  frontend: "react-vite", frontend_custom: "",
  database: "sqlite", database_custom: "",
  notes: "", model: "",
};

// Group the catalog by language so the dropdown reads "Java → Spring Boot, Quarkus".
function grouped(options) {
  const groups = {};
  for (const o of options) (groups[o.language] ??= []).push(o);
  return Object.entries(groups);
}

function StackSelect({ label, layer, options, form, set, toolchains, allowNone }) {
  const value = form[layer];
  const chosen = options.find((o) => o.id === value);
  const missing = (chosen?.tools ?? []).filter((t) => toolchains[t] === false);
  return (
    <div className="field">
      <label htmlFor={layer}>{label}</label>
      <select id={layer} value={value} onChange={(e) => set(layer, e.target.value)}>
        {options[0]?.language
          ? grouped(options).map(([lang, opts]) => (
              <optgroup key={lang} label={lang}>
                {opts.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
              </optgroup>
            ))
          : options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
        <optgroup label="More">
          <option value="custom">Something else… (type it)</option>
          {allowNone && <option value="none">None — skip this part</option>}
        </optgroup>
      </select>
      {value === "custom" && (
        <input
          className="custom-input"
          placeholder={`e.g. ${layer === "backend" ? "Elixir Phoenix, Kotlin Ktor" : layer === "frontend" ? "SolidJS, Flutter Web" : "Redis, DynamoDB"}`}
          value={form[`${layer}_custom`]}
          onChange={(e) => set(`${layer}_custom`, e.target.value)}
          maxLength={200}
          autoFocus
        />
      )}
      {chosen?.tools?.length > 0 && (
        missing.length ? (
          <p className="hint warn">
            ⚠ Not installed: {missing.join(", ")}. Agents will still write the code but can't build or test it.
          </p>
        ) : (
          <p className="hint ok">✓ {chosen.tools.join(", ")} installed</p>
        )
      )}
    </div>
  );
}

export default function NewBuild() {
  const [catalog, setCatalog] = useState(null);
  const [runs, setRuns] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getCatalog().then(setCatalog).catch((e) => setError(e.message));
    listRuns().then(setRuns).catch(() => {});
  }, []);

  const set = (key, value) => setForm((f) => ({ ...f, [key]: value }));

  // The builders run at the same time, so they share one step.
  const agents = useMemo(() => {
    const builders = [];
    if (form.backend !== "none") builders.push("Backend builder");
    if (form.frontend !== "none") builders.push("Frontend builder");
    return ["Architect", builders.join(" ∥ "), "Integrator & QA"];
  }, [form.backend, form.frontend]);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const run = await startRun(form);
      go(`/run/${run.id}`);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  if (!catalog) {
    return <main className="home">{error ? <p className="alert">{error}</p> : <p className="muted">Loading…</p>}</main>;
  }

  return (
    <main className="home">
      <form className="card build-form" onSubmit={submit}>
        <h1>New build</h1>

        <div className="field">
          <label htmlFor="name">Project name</label>
          <input id="name" value={form.name} onChange={(e) => set("name", e.target.value)}
                 placeholder="Task Board" maxLength={60} required />
        </div>

        <div className="field">
          <label htmlFor="idea">What should the app do?</label>
          <textarea id="idea" rows={4} value={form.idea} onChange={(e) => set("idea", e.target.value)}
                    placeholder="Describe the features in plain English…" maxLength={4000} required />
          <div className="chips">
            {EXAMPLES.map((ex) => (
              <button type="button" key={ex.name} className="chip"
                      onClick={() => setForm((f) => ({ ...f, name: ex.name, idea: ex.idea }))}>
                {ex.name}
              </button>
            ))}
          </div>
        </div>

        <div className="grid-2">
          <StackSelect label="Backend" layer="backend" options={catalog.backends} form={form} set={set}
                       toolchains={catalog.toolchains} allowNone />
          <StackSelect label="Frontend" layer="frontend" options={catalog.frontends} form={form} set={set}
                       toolchains={catalog.toolchains} allowNone />
          <StackSelect label="Database" layer="database" options={catalog.databases} form={form} set={set}
                       toolchains={catalog.toolchains} />
          <div className="field">
            <label htmlFor="model">Claude model</label>
            <select id="model" value={form.model} onChange={(e) => set("model", e.target.value)}>
              {catalog.models.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
            </select>
          </div>
        </div>

        <div className="field">
          <label htmlFor="notes">Extra requirements <span className="muted">(optional)</span></label>
          <textarea id="notes" rows={2} value={form.notes} onChange={(e) => set("notes", e.target.value)}
                    placeholder="e.g. Use Gradle instead of Maven. Add login with email and password." maxLength={2000} />
        </div>

        <div className="pipeline-preview" aria-label="Agents that will run">
          {agents.map((a, i) => (
            <span key={a} className="pp-step">
              {i > 0 && <span className="pp-arrow">→</span>}
              <span className="pp-agent">{a}</span>
            </span>
          ))}
        </div>

        {error && <p className="alert">{error}</p>}
        <button className="btn btn-primary btn-big" disabled={busy || form.backend === "none" && form.frontend === "none"}>
          {busy ? "Starting…" : "▶ Build it"}
        </button>
      </form>

      <aside className="home-side">
        <section className="card">
          <h2>How it works</h2>
          <ol className="how">
            <li><b>One process per agent.</b> Each agent is its own <code>claude -p</code> run using your Claude Code login, working in a new folder under <code>generated/</code>.</li>
            <li><b>Architect first.</b> It writes <code>docs/PLAN.md</code> and <code>docs/API_CONTRACT.md</code>, the shared blueprint.</li>
            <li><b>Builders in parallel.</b> Backend and frontend agents both code against the contract at the same time.</li>
            <li><b>Context passing.</b> Each agent's final message is a <i>handoff</i>, pasted into the prompts of the agents after it. Files on disk are shared too.</li>
            <li><b>Integrator last.</b> It reads both handoffs, fixes mismatches, runs the builds and writes the README.</li>
            <li><b>Live tokens.</b> Every API call reports its token usage, which streams to the sidebar while agents work.</li>
          </ol>
        </section>

        <section className="card">
          <h2>Recent builds</h2>
          {runs.length === 0 ? (
            <p className="muted">No builds yet.</p>
          ) : (
            <ul className="run-list">
              {runs.map((r) => (
                <li key={r.id}>
                  <a href={`#/run/${r.id}`}>
                    <span className={`dot s-${r.status}`} />
                    <span className="rl-name">{r.name}</span>
                    <span className="rl-meta">{r.layers.backend.split(" (")[0]} · {r.layers.frontend.split(" (")[0]}</span>
                    <span className="rl-tokens">{tokens(r.total_tokens)} tok · {usd(r.cost_usd)}</span>
                    <span className="sr-only">{STATUS_LABEL[r.status]}</span>
                  </a>
                </li>
              ))}
            </ul>
          )}
        </section>
      </aside>
    </main>
  );
}
