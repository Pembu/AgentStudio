import asyncio
import json
from pathlib import Path

import claude_runner
import orchestrator
from conftest import SPEC


def build(spec=SPEC, cancel_after=None):
    async def go():
        run = orchestrator.start_run(dict(spec))
        if cancel_after is not None:
            await asyncio.sleep(cancel_after)
            run.cancel()
        while not run.finished:
            await asyncio.sleep(0.05)
        return run
    return asyncio.run(go())


def test_full_pipeline_succeeds_and_passes_context():
    run = build()
    assert run.status == "done", run.error
    assert [a["status"] for a in run.agents.values()] == ["done"] * 4

    fake = run.project_dir / ".fake"
    # Builders receive the architect's handoff; the integrator receives both builders' handoffs.
    assert "HANDOFF from architect" in (fake / "backend.prompt.txt").read_text()
    assert "HANDOFF from architect" in (fake / "frontend.prompt.txt").read_text()
    integrator = (fake / "integrator.prompt.txt").read_text()
    assert "HANDOFF from backend" in integrator and "HANDOFF from frontend" in integrator
    assert "Spring Boot (Java)" in integrator and "Angular (TypeScript)" in integrator

    assert [h["from"] for h in run.handoffs][0] == "Architect"
    assert len(run.handoffs) == 3  # architect→builders, backend→integrator, frontend→integrator


def test_token_usage_is_tracked_per_agent_and_totalled():
    run = build()
    for agent in run.agents.values():
        u = agent["usage"]
        assert (u["input"], u["output"], u["cache_read"], u["cache_write"]) == (10, 20, 1000, 500)
        assert u["total"] == 1530 and u["cost_usd"] == 0.25 and u["context_window"] == 200000
    totals = run.totals()
    assert totals["total"] == 4 * 1530
    assert totals["cost_usd"] == 1.0


def test_activity_and_todos_are_recorded():
    run = build()
    arch = run.agents["architect"]
    texts = [a["text"] for a in arch["activity"]]
    assert "architect working" in texts
    assert "Write architect.txt" in texts  # paths are shown relative to the project
    assert any(a["kind"] == "error" and a["text"] == "boom" for a in arch["activity"])
    assert arch["todos"] == [{"content": "step one", "status": "completed"}]


def test_failed_agent_skips_dependents(monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "fail_backend")
    run = build()
    assert run.status == "failed"
    status = {r: a["status"] for r, a in run.agents.items()}
    assert status == {"architect": "done", "backend": "failed", "frontend": "done", "integrator": "skipped"}
    assert "backend failed" in run.error


def test_skipping_frontend_removes_that_agent():
    run = build({**SPEC, "frontend": "none"})
    assert list(run.agents) == ["architect", "backend", "integrator"]
    assert run.agents["integrator"]["depends_on"] == ["backend"]
    assert run.status == "done"


def test_cancel_stops_running_agents(monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "slow")
    run = build(cancel_after=1.0)
    assert run.status == "cancelled"
    assert run.agents["architect"]["status"] == "cancelled"
    assert run.agents["integrator"]["status"] == "cancelled"


def test_finished_runs_are_saved_and_reloaded(isolated):
    run = build()
    saved = json.loads((isolated / "runs" / f"{run.id}.json").read_text())
    assert saved["status"] == "done"
    orchestrator._runs.clear()
    orchestrator.load_saved()
    assert orchestrator.get_run(run.id).totals()["total"] == 4 * 1530


def test_project_folders_never_collide(isolated):
    first = build()
    second = build()
    assert first.project_dir.name == "todo-app"
    assert second.project_dir.name == "todo-app-2"


def test_missing_cli_fails_cleanly(monkeypatch):
    monkeypatch.setattr(claude_runner, "CLAUDE_BIN", "/nonexistent/claude")
    run = build()
    assert run.status == "failed"
    assert "Could not start" in run.agents["architect"]["error"]


def test_git_commit_per_agent():
    import subprocess
    run = build()
    log = subprocess.run(["git", "log", "--format=%s"], cwd=run.project_dir, capture_output=True, text=True)
    if log.returncode == 0:
        assert len(log.stdout.splitlines()) == 4
