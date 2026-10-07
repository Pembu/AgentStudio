#!/usr/bin/env python3
"""Stands in for the `claude` CLI in tests: prints realistic stream-json without calling any model.

FAKE_CLAUDE_MODE controls it:
  ok            every agent succeeds
  fail_backend  the backend builder reports an error
  slow          sleeps so a test can cancel the run
"""
import json
import os
import sys
import time
from pathlib import Path

args = sys.argv[1:]
system_prompt = args[args.index("--append-system-prompt") + 1]
role = next(r for r in ("ARCHITECT", "BACKEND BUILDER", "FRONTEND BUILDER", "INTEGRATOR")
            if f"You are the {r}" in system_prompt).split()[0].lower()
prompt = sys.stdin.read()
mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")

# Record what this agent received so tests can check the context passing.
Path(".fake").mkdir(exist_ok=True)
Path(f".fake/{role}.prompt.txt").write_text(prompt)


def out(obj):
    print(json.dumps(obj), flush=True)


usage = {"input_tokens": 10, "output_tokens": 20, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 500}
out({"type": "system", "subtype": "init", "session_id": f"s-{role}", "model": "fake-model"})
# The same message id twice, as the real CLI does when a reply has several content blocks.
out({"type": "assistant", "parent_tool_use_id": None,
     "message": {"id": "m1", "usage": usage, "content": [{"type": "text", "text": f"{role} working"}]}})
out({"type": "assistant", "parent_tool_use_id": None,
     "message": {"id": "m1", "usage": usage, "content": [
         {"type": "tool_use", "name": "Write", "input": {"file_path": os.path.join(os.getcwd(), f"{role}.txt")}},
         {"type": "tool_use", "name": "TodoWrite", "input": {"todos": [{"content": "step one", "status": "completed"}]}},
     ]}})
out({"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True, "content": "boom"}]}})
Path(f"{role}.txt").write_text("hi")

if mode == "slow":
    time.sleep(30)

failed = mode == "fail_backend" and role == "backend"
out({
    "type": "result", "subtype": "success", "is_error": failed,
    "result": f"{role} failed" if failed else f"HANDOFF from {role}",
    "total_cost_usd": 0.25, "num_turns": 3,
    "modelUsage": {"fake-model": {"inputTokens": 10, "outputTokens": 20, "cacheReadInputTokens": 1000,
                                  "cacheCreationInputTokens": 500, "contextWindow": 200000}},
})
