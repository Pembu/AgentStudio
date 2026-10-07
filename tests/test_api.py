import time

import pytest
from fastapi.testclient import TestClient

from app import app
from conftest import SPEC


@pytest.fixture
def client():
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        yield c


def test_catalog_lists_stacks_and_toolchains(client):
    data = client.get("/api/catalog").json()
    ids = {b["id"] for b in data["backends"]}
    assert {"python-fastapi", "java-spring"} <= ids
    assert {"react-vite", "angular"} <= {f["id"] for f in data["frontends"]}
    assert isinstance(data["toolchains"]["node"], bool)


def test_create_run_and_poll_until_done(client):
    res = client.post("/api/runs", json=SPEC)
    assert res.status_code == 201
    run_id = res.json()["id"]
    for _ in range(100):
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] not in ("queued", "running"):
            break
        time.sleep(0.05)
    assert run["status"] == "done"
    assert run["totals"]["total"] == 4 * 1530
    assert client.get("/api/runs").json()[0]["id"] == run_id


@pytest.mark.parametrize("change, message", [
    ({"backend": "cobol-magic"}, "Unknown backend"),
    ({"backend": "custom"}, "Describe your custom backend"),
    ({"backend": "none", "frontend": "none"}, "at least a backend or a frontend"),
    ({"name": "../../etc"}, "pattern"),
    ({"idea": "short"}, "at least 10"),
    ({"model": "gpt-9"}, "Unknown model"),
])
def test_invalid_specs_are_rejected(client, change, message):
    res = client.post("/api/runs", json={**SPEC, **change})
    assert res.status_code == 422
    assert message in res.text


def test_custom_stack_is_accepted(client):
    res = client.post("/api/runs", json={**SPEC, "backend": "custom", "backend_custom": "Elixir Phoenix"})
    assert res.status_code == 201
    assert res.json()["layers"]["backend"] == "Elixir Phoenix"


def test_unknown_run_is_404(client):
    assert client.get("/api/runs/nope").status_code == 404


def test_cross_site_requests_are_blocked(client):
    evil = client.post("/api/runs", json=SPEC, headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    form = client.post("/api/runs", content="{}", headers={"Content-Type": "text/plain"})
    assert form.status_code == 415
    rebinding = client.get("/api/catalog", headers={"Host": "evil.example"})
    assert rebinding.status_code == 403
