async function request(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    // FastAPI validation errors arrive as a list; show their messages, not the raw JSON.
    const detail = Array.isArray(body.detail)
      ? body.detail.map((d) => d.msg.replace(/^Value error, /, "")).join(". ")
      : body.detail;
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return body;
}

export const getCatalog = () => request("/api/catalog");
export const listRuns = () => request("/api/runs");
export const getRun = (id) => request(`/api/runs/${id}`);
export const startRun = (spec) => request("/api/runs", { method: "POST", body: JSON.stringify(spec) });
export const cancelRun = (id) => request(`/api/runs/${id}/cancel`, { method: "POST" });

const FINISHED = ["done", "failed", "cancelled", "interrupted"];
export const isFinished = (status) => FINISHED.includes(status);

/** Subscribe to live snapshots of a run. Returns an unsubscribe function. */
export function watchRun(id, onSnapshot, onError) {
  const source = new EventSource(`/api/runs/${id}/stream`);
  source.onmessage = (e) => {
    const run = JSON.parse(e.data);
    onSnapshot(run);
    // The server ends the stream when the run finishes; close so the browser doesn't reconnect.
    if (isFinished(run.status)) source.close();
  };
  source.onerror = () => {
    if (source.readyState === EventSource.CLOSED) onError?.();
  };
  return () => source.close();
}
