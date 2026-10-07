import os
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

FAKE = ROOT / "tests" / "fake_claude.py"
FAKE.chmod(FAKE.stat().st_mode | stat.S_IXUSR)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Point every test at the fake CLI and throwaway folders."""
    import claude_runner
    import orchestrator

    monkeypatch.setattr(claude_runner, "CLAUDE_BIN", str(FAKE))
    monkeypatch.setattr(orchestrator, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(orchestrator, "OUTPUT_DIR", tmp_path / "out")
    monkeypatch.setattr(orchestrator, "_runs", {})
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "ok")
    os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    return tmp_path


SPEC = {
    "name": "Todo App",
    "idea": "A todo list with add, complete and delete.",
    "backend": "java-spring",
    "backend_custom": "",
    "frontend": "angular",
    "frontend_custom": "",
    "database": "sqlite",
    "database_custom": "",
    "notes": "",
    "model": "",
}
