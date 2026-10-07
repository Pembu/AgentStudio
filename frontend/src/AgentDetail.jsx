import { useEffect, useRef, useState } from "react";
import { clock, STATUS_LABEL } from "./format.js";

const KIND_ICON = { say: "💬", tool: "🔧", error: "⚠" };

function Activity({ items }) {
  const box = useRef(null);
  const pinned = useRef(true); // stay scrolled to the bottom unless the user scrolls up

  useEffect(() => {
    if (pinned.current && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [items]);

  if (!items.length) return <p className="muted pad">No activity yet.</p>;
  return (
    <ol
      className="activity"
      ref={box}
      onScroll={(e) => {
        const el = e.currentTarget;
        pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
      }}
    >
      {items.map((a, i) => (
        <li key={i} className={`act-${a.kind}`}>
          <time>{clock(a.t)}</time>
          <span className="act-icon" aria-hidden>{KIND_ICON[a.kind]}</span>
          <span className="act-text">{a.text}</span>
        </li>
      ))}
    </ol>
  );
}

export default function AgentDetail({ agent }) {
  const [tab, setTab] = useState("activity");
  const tabs = [
    ["activity", `Live activity (${agent.activity.length})`],
    ["tasks", `Tasks (${agent.todos.length})`],
    ["context", "Context received"],
    ["handoff", "Handoff sent"],
  ];

  return (
    <section className="card detail">
      <div className="detail-head">
        <h2>{agent.title}</h2>
        <span className={`pill s-${agent.status}`}>{STATUS_LABEL[agent.status]}</span>
      </div>
      <div className="tabs" role="tablist">
        {tabs.map(([key, label]) => (
          <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? "active" : ""}
                  onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>

      {agent.error && <p className="alert">{agent.error}</p>}

      {tab === "activity" && <Activity items={agent.activity} />}

      {tab === "tasks" && (
        agent.todos.length ? (
          <ul className="todos">
            {agent.todos.map((t, i) => (
              <li key={i} className={`todo-${t.status}`}>
                <span aria-hidden>{t.status === "completed" ? "☑" : t.status === "in_progress" ? "◐" : "☐"}</span> {t.content}
              </li>
            ))}
          </ul>
        ) : <p className="muted pad">This agent hasn't written a task list yet.</p>
      )}

      {tab === "context" && (
        agent.prompt ? (
          <>
            <p className="muted pad">The exact prompt this agent started with: the project brief plus the handoffs
              from the agents before it. Its role instructions are added as a system prompt.</p>
            <pre className="prose">{agent.prompt}</pre>
          </>
        ) : <p className="muted pad">This agent hasn't started yet. Its context is assembled once the agents before it hand off.</p>
      )}

      {tab === "handoff" && (
        agent.handoff ? (
          <>
            <p className="muted pad">This agent's final message, which is passed on to the next agents.</p>
            <pre className="prose">{agent.handoff}</pre>
          </>
        ) : <p className="muted pad">Written when the agent finishes.</p>
      )}
    </section>
  );
}
