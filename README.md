# Agent Studio

Pick any backend and frontend stack, describe an app, click **Build it**, and a team of
Claude Code agents builds it while you watch every step and every token.

## Start

```bash
./start.sh        # first run installs everything; then open http://127.0.0.1:8765
```

Needs Python 3, Node.js and the `claude` CLI (logged in). Generated projects land in
`../generated/<project-name>/`, each with its own git history (one commit per agent).

## How it works

```
Architect ──┬──> Backend builder ──┬──> Integrator & QA
            └──> Frontend builder ─┘      (builders run in parallel)
```

| Piece | File |
|---|---|
| Runs one agent (`claude -p --output-format stream-json`) and parses its events and token usage | `backend/claude_runner.py` |
| What each agent is told, and how handoffs are put into prompts | `backend/prompts.py` |
| The pipeline: dependencies, parallelism, status, handoffs, git commits | `backend/orchestrator.py` |
| API and live updates (Server-Sent Events) | `backend/app.py` |
| Stack catalog and toolchain detection | `backend/stacks.py` |
| UI: form, pipeline, agent detail, token sidebar | `frontend/src/` |

**Context passing:** the Architect writes `docs/PLAN.md` and `docs/API_CONTRACT.md`, which
the later agents read. Each agent's final message is its *handoff*, which gets pasted into
the prompt of every agent that depends on it. The UI shows both, under the
"Context received" and "Handoff sent" tabs.

**Tokens:** every API call reports input, output, cache-read and cache-write tokens.
These stream to the sidebar live. The exact totals and cost come from each agent's final
`result` event.

## Safety

Agents run with `--permission-mode acceptEdits` and may use Bash, so they can run commands
on your machine. They're told to stay in the project folder and never use sudo or install
anything system-wide, but these are instructions, not a sandbox. The server listens on
127.0.0.1 only and rejects cross-site requests.

## Tests

```bash
.venv/bin/python -m pytest -q     # uses tests/fake_claude.py, so no tokens are spent
```

For UI work without spending tokens: `CLAUDE_BIN=$PWD/tests/fake_claude.py ./start.sh`
