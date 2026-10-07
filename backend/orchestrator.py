"""Runs the agent team for one build and keeps the live state the UI shows.

The pipeline is a small dependency graph:

    Architect ──┬──> Backend builder ──┬──> Integrator & QA
                └──> Frontend builder ─┘

Each agent starts as soon as every agent it depends on has finished, so the two
builders run in parallel. Its prompt contains the handoffs of those agents.
"""
import asyncio
import json
import os
import re
import secrets
import time
from pathlib import Path

import claude_runner
import prompts
import stacks

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = Path(os.environ.get("STUDIO_RUNS_DIR", ROOT / "runs"))
OUTPUT_DIR = Path(os.environ.get("STUDIO_OUTPUT_DIR", ROOT.parent / "generated")).expanduser()

PIPELINE = [
    ("architect", []),
    ("backend", ["architect"]),
    ("frontend", ["architect"]),
    ("integrator", ["backend", "frontend"]),
]

MAX_ACTIVITY = 150  # activity lines kept per agent

STARTER_GITIGNORE = """node_modules/
.venv/
venv/
__pycache__/
*.pyc
target/
build/
dist/
bin/
obj/
.next/
.angular/
*.db
.env
.DS_Store
"""


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:50] or "project"


def describe_layer(options: list[dict], choice: str, custom: str) -> str:
    if choice == "none":
        return "none (do not build this part)"
    if choice == "custom":
        return custom.strip()
    o = stacks.find(options, choice)
    return f"{o['label']} ({o['language']})" if "language" in o else o["label"]


def _now() -> float:
    return round(time.time(), 3)


class Run:
    def __init__(self, run_id: str, spec: dict, project_dir: Path):
        self.id = run_id
        self.spec = spec
        self.project_dir = project_dir
        self.status = "queued"
        self.created_at = _now()
        self.started_at = None
        self.ended_at = None
        self.error = ""
        self.log: list[dict] = []        # orchestration timeline
        self.handoffs: list[dict] = []   # context passed between agents
        self.cancel_requested = False
        self.version = 0
        self._changed = asyncio.Event()
        self._procs: set[asyncio.subprocess.Process] = set()
        self._git_lock = asyncio.Lock()  # parallel agents must not commit at the same moment

        self.layers = {
            "backend": describe_layer(stacks.BACKENDS, spec["backend"], spec.get("backend_custom", "")),
            "frontend": describe_layer(stacks.FRONTENDS, spec["frontend"], spec.get("frontend_custom", "")),
            "database": describe_layer(stacks.DATABASES, spec["database"], spec.get("database_custom", "")),
        }
        skip = {layer for layer in ("backend", "frontend") if spec[layer] == "none"}
        self.agents: dict[str, dict] = {}
        for role, deps in PIPELINE:
            if role in skip:
                continue
            self.agents[role] = {
                "role": role,
                "title": prompts.ROLES[role]["title"],
                "summary": prompts.ROLES[role]["summary"],
                "depends_on": [d for d in deps if d not in skip],
                "status": "waiting",
                "model": "",
                "prompt": "",
                "handoff": "",
                "error": "",
                "activity": [],
                "todos": [],
                "usage": claude_runner.Usage().to_dict(),
                "started_at": None,
                "ended_at": None,
            }

    # ---- change notification (for the live stream) ----

    def touch(self) -> None:
        self.version += 1
        self._changed.set()
        self._changed = asyncio.Event()  # listeners hold the old event, which is now set

    async def wait_for_change(self, timeout: float) -> None:
        try:
            await asyncio.wait_for(self._changed.wait(), timeout)
        except asyncio.TimeoutError:
            pass

    def note(self, text: str, kind: str = "info") -> None:
        self.log.append({"t": _now(), "kind": kind, "text": text})
        self.touch()

    # ---- views ----

    def totals(self) -> dict:
        keys = ("input", "output", "cache_read", "cache_write", "total", "cost_usd", "api_calls", "turns")
        return {k: sum(a["usage"][k] for a in self.agents.values()) for k in keys}

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "spec": self.spec,
            "layers": self.layers,
            "project_dir": str(self.project_dir),
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "agents": list(self.agents.values()),
            "handoffs": self.handoffs,
            "log": self.log,
            "totals": self.totals(),
            "version": self.version,
        }

    def summary(self) -> dict:
        return {
            "id": self.id,
            "name": self.spec["name"],
            "idea": self.spec["idea"],
            "layers": self.layers,
            "status": self.status,
            "created_at": self.created_at,
            "total_tokens": self.totals()["total"],
            "cost_usd": self.totals()["cost_usd"],
        }

    @property
    def finished(self) -> bool:
        return self.status in ("done", "failed", "cancelled", "interrupted")

    # ---- execution ----

    async def execute(self) -> None:
        self.status = "running"
        self.started_at = _now()
        self.note(f"Build started in {self.project_dir}")
        try:
            self.project_dir.mkdir(parents=True, exist_ok=False)
            (self.project_dir / "docs").mkdir()
            (self.project_dir / ".gitignore").write_text(STARTER_GITIGNORE)
            await self._git("init", "-q")

            brief = prompts.brief(self.spec, **self.layers)
            finished = {role: asyncio.get_running_loop().create_future() for role in self.agents}
            await asyncio.gather(*(self._agent_task(role, brief, finished) for role in self.agents))

            states = [a["status"] for a in self.agents.values()]
            if self.cancel_requested:
                self.status = "cancelled"
            elif all(s == "done" for s in states):
                self.status = "done"
            else:
                self.status = "failed"
                self.error = next((a["error"] for a in self.agents.values() if a["error"]), "An agent failed")
        except Exception as exc:  # noqa: BLE001 - surface any crash in the UI instead of losing it
            self.status = "failed"
            self.error = f"{type(exc).__name__}: {exc}"
        self.ended_at = _now()
        self.note(f"Build {self.status}", "done" if self.status == "done" else "error")
        save(self)

    async def _agent_task(self, role: str, brief: str, finished: dict) -> None:
        agent = self.agents[role]
        deps = agent["depends_on"]
        results = [await finished[d] for d in deps]
        if self.cancel_requested or not all(results):
            agent["status"] = "cancelled" if self.cancel_requested else "skipped"
            agent["error"] = "" if self.cancel_requested else "Skipped because an earlier agent failed"
            self.touch()
            finished[role].set_result(False)
            return

        handoffs = [(self.agents[d]["title"], self.agents[d]["handoff"]) for d in deps]
        agent["prompt"] = prompts.agent_prompt(role, brief, handoffs)
        agent["status"] = "running"
        agent["started_at"] = _now()
        self.note(f"{agent['title']} started" + (f" with handoffs from {', '.join(t for t, _ in handoffs)}" if handoffs else ""))

        def emit(kind: str, data: dict) -> None:
            if kind == "activity":
                agent["activity"] = (agent["activity"] + [{"t": _now(), **data}])[-MAX_ACTIVITY:]
            elif kind == "todos":
                agent["todos"] = data["todos"]
            elif kind == "init":
                agent["model"] = data["model"]
            elif kind == "usage":
                agent["usage"] = data
            self.touch()

        result = await claude_runner.run_agent(
            agent["prompt"], self.project_dir,
            system_prompt=prompts.system_prompt(role),
            model=self.spec.get("model", ""),
            emit=emit,
            on_process=self._procs.add,
        )
        agent["usage"] = result.usage.to_dict()
        agent["ended_at"] = _now()
        agent["handoff"] = result.text
        if self.cancel_requested:
            agent["status"], agent["error"] = "cancelled", "Stopped by you"
        elif result.ok:
            agent["status"] = "done"
        else:
            agent["status"], agent["error"] = "failed", result.error
        self.note(f"{agent['title']} {agent['status']}" + (f": {agent['error']}" if agent["error"] else ""),
                  "done" if result.ok else "error")

        if result.ok:
            # Builders commit only their own folder, since the other builder may still be writing.
            paths = {"backend": ["backend"], "frontend": ["frontend"]}.get(role, ["."])
            async with self._git_lock:
                await self._git("add", "-A", "--", *paths)
                await self._git("-c", "user.name=Agent Studio", "-c", "user.email=agent-studio@localhost",
                                "commit", "-q", "--allow-empty", "-m", f"{agent['title']}: {self.spec['name']}")
            receivers = [a["title"] for a in self.agents.values() if role in a["depends_on"]]
            if receivers:
                self.handoffs.append({"from": agent["title"], "to": receivers, "text": result.text, "t": _now()})
                self.note(f"Handoff: {agent['title']} → {', '.join(receivers)}", "handoff")
        finished[role].set_result(result.ok)

    async def _git(self, *args: str) -> None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", *args, cwd=self.project_dir,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await proc.wait()
        except OSError:
            pass  # git is optional

    def cancel(self) -> None:
        if self.finished:
            return
        self.cancel_requested = True
        self.note("Stop requested", "error")
        for proc in self._procs:
            if proc.returncode is None:
                proc.terminate()


# ---- storage ----

_runs: dict[str, Run] = {}
_tasks: set[asyncio.Task] = set()


def save(run: Run) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / f"{run.id}.json").write_text(json.dumps(run.snapshot(), indent=1))


def load_saved() -> None:
    """Load finished runs from disk so history survives a restart."""
    for path in sorted(RUNS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        run = Run(data["id"], data["spec"], Path(data["project_dir"]))
        run.agents = {a["role"]: a for a in data["agents"]}
        for key in ("status", "error", "created_at", "started_at", "ended_at", "handoffs", "log"):
            setattr(run, key, data[key])
        if not run.finished:
            run.status = "interrupted"
        _runs[run.id] = run


def unique_project_dir(name: str) -> Path:
    base = OUTPUT_DIR / slugify(name)
    path, n = base, 2
    taken = {r.project_dir for r in _runs.values()}
    while path.exists() or path in taken:
        path, n = Path(f"{base}-{n}"), n + 1
    return path


def start_run(spec: dict) -> Run:
    run_id = time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)
    run = Run(run_id, spec, unique_project_dir(spec["name"]))
    _runs[run.id] = run
    task = asyncio.create_task(run.execute())
    _tasks.add(task)  # keep a reference so the task is not garbage-collected
    task.add_done_callback(_tasks.discard)
    return run


def get_run(run_id: str) -> Run | None:
    return _runs.get(run_id)


def list_runs() -> list[dict]:
    return [r.summary() for r in sorted(_runs.values(), key=lambda r: r.created_at, reverse=True)]
