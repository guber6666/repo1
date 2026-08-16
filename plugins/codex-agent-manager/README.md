# Codex Agent Manager

Codex plugin for a spec-first coding workflow that can execute with the current Codex Agent or
delegate to Kiro CLI, Cursor Agent CLI, or Claude Code CLI.

## Install from GitHub

```bash
codex plugin marketplace add guber6666/repo1 --ref main
codex plugin add codex-agent-manager@guber6666-repo1
```

Restart Codex and start a new task after installation. The complete discovery flow depends on the
`grilling` and `to-spec` Skills; external CLIs are optional unless their executor is selected.

## Workflow

1. Codex decides whether the request needs `grilling`; ambiguous decisions are clarified one at a
   time.
2. Codex asks whether to enter `to-spec`.
3. Every `to-spec` run asks whether to publish an issue plus a local snapshot, or create local-only
   Markdown without issue or Git operations.
4. The user chooses the current Codex Agent, a recommended agent, Kiro, Cursor, Claude, or no
   execution.
5. The selected writer runs only after approval. Every prompt, event stream, error, status, and
   spec snapshot is stored under
   `.codex-agent-manager/runs/`.
6. Codex inspects the resulting diff and runs appropriate verification.

The MVP deliberately allows only one writer per run. Parallel writers in one checkout create
ambiguous ownership and merge risk; use separate worktrees for parallel implementations.

## Quick start

```bash
python3 scripts/agent_manager.py doctor
python3 scripts/agent_manager.py new-spec \
  --title "Add request id middleware" \
  --request "Add request IDs to every HTTP response"
python3 scripts/agent_manager.py plan \
  --spec .codex-agent-manager/specs/add-request-id-middleware.md
python3 scripts/agent_manager.py run \
  --spec .codex-agent-manager/specs/add-request-id-middleware.md \
  --agent claude

# Audit an implementation performed by the current Codex session
python3 scripts/agent_manager.py current-start \
  --spec .codex-agent-manager/specs/add-request-id-middleware.md
```

Run from the target repository. `run` never uses a shell to construct the agent command, so spec
text cannot become shell syntax.

## Configuration

Defaults live in `assets/agents.default.json`. Override only the fields you need in either:

- `<workspace>/.codex/agent-manager.json`
- a file passed with `--config`

Example:

```json
{
  "selection_order": ["cursor", "claude", "kiro"],
  "agents": {
    "claude": {
      "args": ["-p", "--output-format", "stream-json", "--verbose", "--permission-mode", "dontAsk"]
    }
  }
}
```

Use permission overrides carefully. The bundled defaults prefer scoped, non-interactive modes and
record the exact command used for every run.

## Supported CLIs

- Claude Code: `claude`
- Cursor Agent: `agent` or `cursor-agent`
- Kiro CLI: `kiro-cli`

The full discovery workflow also composes the installed `grilling` and `to-spec` skills.

Use `doctor --json` to see which adapter is currently ready.

## Run artifacts

Each run contains:

- `metadata.json`: selected agent, executable, workspace, and command arguments
- `spec.md`: immutable copy of the executed spec
- `prompt.md`: exact orchestration prompt sent to the agent
- `events.ndjson`: stdout/event stream for external agents
- `stderr.log`: stderr stream
- `status.json`: exit status and timing
- `result.md`: current-Codex outcome, changed files, and verification record

These files may contain repository context produced by the external agent. Do not publish them
without review.
