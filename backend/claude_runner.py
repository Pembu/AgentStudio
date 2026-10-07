"""Run one headless Claude Code agent and turn its stream-json output into simple events.

Each agent is a separate `claude -p` process using your Claude Code login. With
`--output-format stream-json`, the CLI prints one JSON object per line:
  system/init  -> model and session id
  assistant    -> what the agent says and which tools it calls, plus token usage for that API call
  user         -> tool results fed back to the agent
  result       -> final answer, exact token totals and cost
"""
import asyncio
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")

# Tools the agents may use without asking. Bash is needed to install packages and run builds.
ALLOWED_TOOLS = "Read,Write,Edit,MultiEdit,Glob,Grep,Bash,TodoWrite"

MAX_TEXT = 1500  # characters of agent text kept per activity line


@dataclass
class Usage:
    input: int = 0          # fresh input tokens
    output: int = 0         # tokens the model wrote
    cache_read: int = 0     # input tokens served from the prompt cache (cheap)
    cache_write: int = 0    # input tokens written to the prompt cache
    context: int = 0        # size of the agent's context window on its latest call
    context_window: int = 0  # the model's maximum context (known once the agent finishes)
    cost_usd: float = 0.0
    turns: int = 0
    api_calls: int = 0

    @property
    def total(self) -> int:
        return self.input + self.output + self.cache_read + self.cache_write

    def to_dict(self) -> dict:
        return {**asdict(self), "total": self.total}


@dataclass
class AgentResult:
    ok: bool
    text: str
    usage: Usage
    error: str = ""
    session_id: str = ""


@dataclass
class _StreamState:
    usage: Usage = field(default_factory=Usage)
    # One API response can arrive as several `assistant` lines with the same message id
    # (one per content block) carrying the same usage, so we keep usage per id.
    per_message: dict = field(default_factory=dict)
    session_id: str = ""
    result: dict | None = None


def _short(text: str, limit: int = MAX_TEXT) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + " …"


def describe_tool(name: str, args: dict, cwd: Path) -> str:
    """A one-line, human-readable summary of a tool call."""
    def rel(p: str) -> str:
        try:
            return str(Path(p).resolve().relative_to(cwd.resolve()))
        except (ValueError, OSError):
            return p

    if name == "Bash":
        return "$ " + _short(args.get("command", ""), 300)
    if name in ("Read", "Write", "Edit", "MultiEdit"):
        return f"{name} {rel(args.get('file_path', ''))}"
    if name in ("Glob", "Grep"):
        return f"{name} {args.get('pattern', '')}"
    if name == "TodoWrite":
        return "Updated its task list"
    return name


def _sum_usage(state: _StreamState) -> None:
    u = state.usage
    calls = state.per_message.values()
    u.input = sum(m.get("input_tokens", 0) for m in calls)
    u.output = sum(m.get("output_tokens", 0) for m in calls)
    u.cache_read = sum(m.get("cache_read_input_tokens", 0) for m in calls)
    u.cache_write = sum(m.get("cache_creation_input_tokens", 0) for m in calls)
    u.api_calls = len(state.per_message)


def handle_line(line: str, state: _StreamState, cwd: Path, emit: Callable[[str, dict], None]) -> None:
    """Parse one stream-json line, update `state`, and emit UI events."""
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        return
    kind = msg.get("type")

    if kind == "system" and msg.get("subtype") == "init":
        state.session_id = msg.get("session_id", "")
        emit("init", {"model": msg.get("model", ""), "session_id": state.session_id})

    elif kind == "assistant":
        m = msg.get("message", {})
        main_thread = msg.get("parent_tool_use_id") is None  # False for the agent's own subagents
        if m.get("usage") and m.get("id"):
            state.per_message[m["id"]] = m["usage"]
            if main_thread:
                mu = m["usage"]
                state.usage.context = (mu.get("input_tokens", 0) + mu.get("cache_read_input_tokens", 0)
                                       + mu.get("cache_creation_input_tokens", 0))
            _sum_usage(state)
            emit("usage", state.usage.to_dict())
        for block in m.get("content", []):
            if block.get("type") == "text" and block.get("text", "").strip():
                emit("activity", {"kind": "say", "text": _short(block["text"])})
            elif block.get("type") == "tool_use":
                args = block.get("input") or {}
                emit("activity", {"kind": "tool", "tool": block.get("name", ""),
                                  "text": describe_tool(block.get("name", ""), args, cwd)})
                if block.get("name") == "TodoWrite" and main_thread:
                    emit("todos", {"todos": [
                        {"content": t.get("content", ""), "status": t.get("status", "pending")}
                        for t in args.get("todos", [])
                    ]})

    elif kind == "user":
        content = msg.get("message", {}).get("content", [])
        for block in content if isinstance(content, list) else []:
            if block.get("type") == "tool_result" and block.get("is_error"):
                body = block.get("content")
                if isinstance(body, list):
                    body = " ".join(b.get("text", "") for b in body if isinstance(b, dict))
                emit("activity", {"kind": "error", "text": _short(str(body or "Tool failed"), 400)})

    elif kind == "result":
        state.result = msg
        u = state.usage
        # modelUsage is the authoritative total, including any subagents the agent spawned.
        models = (msg.get("modelUsage") or {}).values()
        if models:
            u.input = sum(x.get("inputTokens", 0) for x in models)
            u.output = sum(x.get("outputTokens", 0) for x in models)
            u.cache_read = sum(x.get("cacheReadInputTokens", 0) for x in models)
            u.cache_write = sum(x.get("cacheCreationInputTokens", 0) for x in models)
            u.context_window = max(x.get("contextWindow", 0) for x in models)
        u.cost_usd = float(msg.get("total_cost_usd") or 0)
        u.turns = int(msg.get("num_turns") or 0)
        emit("usage", state.usage.to_dict())


async def run_agent(
    prompt: str,
    cwd: Path,
    *,
    system_prompt: str,
    model: str = "",
    emit: Callable[[str, dict], None],
    on_process: Callable[[asyncio.subprocess.Process], None] = lambda p: None,
) -> AgentResult:
    """Run one agent to completion. `emit(kind, data)` is called for every event."""
    cmd = [
        CLAUDE_BIN, "-p",
        "--output-format", "stream-json", "--verbose",
        "--permission-mode", "acceptEdits",
        "--allowedTools", ALLOWED_TOOLS,
        "--append-system-prompt", system_prompt,
    ]
    if model:
        cmd += ["--model", model]

    state = _StreamState()
    try:
        # The prompt goes in on stdin so it can never be mistaken for a command-line flag.
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=cwd,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            limit=32 * 1024 * 1024,  # a single stream-json line can be large
        )
    except OSError as exc:
        return AgentResult(False, "", state.usage, f"Could not start `{CLAUDE_BIN}`: {exc}")
    on_process(proc)

    proc.stdin.write(prompt.encode())
    await proc.stdin.drain()
    proc.stdin.close()

    stderr_task = asyncio.create_task(proc.stderr.read())
    async for raw in proc.stdout:
        handle_line(raw.decode(errors="replace"), state, cwd, emit)
    code = await proc.wait()
    stderr = (await stderr_task).decode(errors="replace").strip()

    res = state.result
    if res is None:
        reason = "Stopped" if code < 0 else f"claude exited with code {code}"
        return AgentResult(False, "", state.usage, _short(f"{reason}. {stderr}", 800), state.session_id)
    if res.get("is_error") or res.get("subtype") != "success":
        detail = res.get("result") or res.get("subtype") or "unknown error"
        return AgentResult(False, res.get("result", ""), state.usage, _short(str(detail), 800), state.session_id)
    return AgentResult(True, res.get("result", ""), state.usage, "", state.session_id)
