export function tokens(n) {
  if (!n) return "0";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + "M";
  if (n >= 10_000) return Math.round(n / 1000) + "k";
  if (n >= 1000) return (n / 1000).toFixed(1) + "k";
  return String(n);
}

export const exact = (n) => (n || 0).toLocaleString();

export const usd = (n) => (n ? "$" + n.toFixed(n < 1 ? 3 : 2) : "$0");

export function duration(start, end) {
  if (!start) return "";
  const s = Math.max(0, Math.round((end ?? Date.now() / 1000) - start));
  const m = Math.floor(s / 60);
  return m ? `${m}m ${String(s % 60).padStart(2, "0")}s` : `${s}s`;
}

export function clock(t) {
  return new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export const STATUS_LABEL = {
  queued: "Queued",
  waiting: "Waiting",
  running: "Running",
  done: "Done",
  failed: "Failed",
  skipped: "Skipped",
  cancelled: "Stopped",
  interrupted: "Interrupted",
};
