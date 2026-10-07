"""Agent Studio API.

Run it:  ./start.sh   then open http://127.0.0.1:8765
"""
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, model_validator

import orchestrator
import stacks

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    orchestrator.load_saved()
    yield


app = FastAPI(title="Agent Studio", lifespan=lifespan)

LOCAL_HOSTS = {"127.0.0.1", "localhost"}


@app.middleware("http")
async def local_only(request: Request, call_next):
    """Agents run shell commands, so only accept requests from this machine's own pages.

    - The Host check blocks DNS-rebinding attacks (a website pointing its domain at 127.0.0.1).
    - The Origin and Content-Type checks stop other websites open in your browser from
      starting builds with a cross-site POST.
    """
    host = (request.headers.get("host") or "").rsplit(":", 1)[0]
    if host not in LOCAL_HOSTS:
        return JSONResponse({"detail": "Forbidden host"}, status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).hostname not in LOCAL_HOSTS:
            return JSONResponse({"detail": "Cross-site request blocked"}, status_code=403)
        if request.url.path == "/api/runs" and not request.headers.get("content-type", "").startswith("application/json"):
            return JSONResponse({"detail": "Content-Type must be application/json"}, status_code=415)
    return await call_next(request)


class RunSpec(BaseModel):
    name: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9][A-Za-z0-9 _.-]*$")
    idea: str = Field(min_length=10, max_length=4000)
    backend: str
    backend_custom: str = Field("", max_length=200)
    frontend: str
    frontend_custom: str = Field("", max_length=200)
    database: str
    database_custom: str = Field("", max_length=200)
    notes: str = Field("", max_length=2000)
    model: str = ""

    @model_validator(mode="after")
    def check_choices(self):
        for layer, options in (("backend", stacks.BACKENDS), ("frontend", stacks.FRONTENDS),
                               ("database", stacks.DATABASES)):
            choice = getattr(self, layer)
            if choice not in stacks.SPECIAL and not stacks.find(options, choice):
                raise ValueError(f"Unknown {layer}: {choice}")
            if choice == "custom" and not getattr(self, f"{layer}_custom").strip():
                raise ValueError(f"Describe your custom {layer}")
        if self.backend == "none" and self.frontend == "none":
            raise ValueError("Choose at least a backend or a frontend")
        if not stacks.find(stacks.MODELS, self.model):
            raise ValueError(f"Unknown model: {self.model}")
        return self


def _run_or_404(run_id: str) -> orchestrator.Run:
    run = orchestrator.get_run(run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return run


@app.get("/api/catalog")
def catalog():
    return stacks.catalog()


@app.get("/api/runs")
def list_runs():
    return orchestrator.list_runs()


@app.post("/api/runs", status_code=201)
async def create_run(spec: RunSpec):
    run = orchestrator.start_run(spec.model_dump())
    return run.snapshot()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    return _run_or_404(run_id).snapshot()


@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str):
    run = _run_or_404(run_id)
    run.cancel()
    return run.snapshot()


@app.get("/api/runs/{run_id}/stream")
async def stream_run(run_id: str):
    """Server-Sent Events: pushes a fresh snapshot whenever the run changes (at most ~4 per second)."""
    run = _run_or_404(run_id)

    async def events():
        sent = -1
        while True:
            if run.version != sent:
                sent = run.version
                yield f"data: {json.dumps(run.snapshot())}\n\n"
                if run.finished:
                    return
                await asyncio.sleep(0.25)  # throttle bursts of tiny updates
            else:
                await run.wait_for_change(timeout=15)
                if run.version == sent:
                    yield ": keep-alive\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# Serve the built React app for every non-API path.
@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path.startswith("api/"):
        raise HTTPException(404)
    if not FRONTEND_DIST.exists():
        return {"message": "Frontend not built. Run ./start.sh, or `npm run dev` in frontend/."}
    file = (FRONTEND_DIST / path).resolve()
    if path and file.is_file() and file.is_relative_to(FRONTEND_DIST):
        return FileResponse(file)
    return FileResponse(FRONTEND_DIST / "index.html")
