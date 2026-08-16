---
name: spec-agent-orchestrator
description: Clarify coding requirements with grilling, use to-spec to publish an issue-backed spec or save local-only Markdown, then choose the current Codex Agent, Kiro CLI, Cursor Agent CLI, or Claude Code CLI to implement and verify it. Use this skill whenever the user asks to analyze or clarify a coding requirement, create or execute a spec, hand coding to another agent, choose a coding agent, or orchestrate a spec-first implementation workflow.
compatibility: Requires Python 3.10+. The grilling and to-spec skills are required for the full discovery workflow. Kiro, Cursor, or Claude CLI is required only when that external executor is selected.
---

# Spec Agent Orchestrator

Use Codex as the accountable workflow owner. Requirements clarification, spec publication,
implementation, and verification are separate state transitions so external writes never happen as
a side effect of planning.

Read `references/workflow.md` before starting discovery and `references/agent-selection.md` before
recommending an executor.

## Locate the manager

Resolve this skill's directory, then use `../../scripts/agent_manager.py` with Python 3. Run it
from the target repository unless `--workspace` is supplied.

## 1. Classify the request

Inspect repository instructions and enough relevant code to distinguish facts from user decisions.
Use these branches:

- Ambiguous, cross-module, architectural, or missing acceptance criteria: invoke the installed
  `grilling` skill. Ask one decision question at a time, include a recommended answer, and do not
  produce or execute a spec until the user confirms shared understanding.
- Small and unambiguous: offer to enter `to-spec` without forcing an interview.
- User-supplied approved spec: skip grilling and spec production; continue to executor selection.
- User explicitly asks to be grilled: invoke `grilling` even if the request initially looks clear.

Discoverable repository facts should be inspected rather than asked. Preserve user changes and do
not broaden scope.

## 2. Offer the next step

After shared understanding, show exactly these choices and wait:

1. Enter `to-spec` (recommended)
2. Continue clarification
3. Pause and keep the current conclusions

Do not silently transition into spec publication.

## 3. Run to-spec with an output choice

Every time the user enters `to-spec`, ask which output mode to use; never remember a previous
choice:

1. Publish an issue and save a local snapshot (recommended)
2. Save local Markdown only; do not publish an issue or run Git commands during spec production

Use the installed `to-spec` skill for synthesis, its spec structure, test-seam reasoning, and issue
publication behavior. It intentionally performs no new requirements interview. Confirm the proposed
testing seams with the user before finalizing either mode.

For mode 1:

- Confirm the project issue tracker and triage vocabulary are configured.
- If they are missing, offer: configure them, switch to local-only mode, or cancel. Do not silently
  downgrade or change project configuration.
- Publish the issue with the `ready-for-agent` label as required by `to-spec`.
- Save the exact published spec under `.codex-agent-manager/specs/` with issue URL, issue number,
  publication timestamp, and `source_mode: issue-and-local` metadata.

For mode 2:

- Follow the `to-spec` synthesis and template but skip all issue-tracker operations.
- Do not run `git` during spec production.
- Save under `.codex-agent-manager/specs/` with `source_mode: local-only` and a creation timestamp.

The local Markdown snapshot is the immutable execution input. Later issue edits do not change the
scope of an existing execution. Use `references/spec-template.md` for the persisted shape.

## 4. Select the executor

Run readiness detection before presenting external choices:

```bash
python3 <plugin-root>/scripts/agent_manager.py doctor --workspace <workspace> --json
```

Recommend one executor based on `references/agent-selection.md`, then show:

1. Current Codex Agent
2. Recommended Agent
3. Kiro
4. Cursor
5. Claude
6. Do not execute yet

Mark unavailable external CLIs instead of pretending they can run. Selecting an executor is not
execution approval; show the spec, scope, verification, and risks, then obtain explicit approval.

## 5. Execute with one writer

### Current Codex Agent

Start an audit record before editing:

```bash
python3 <plugin-root>/scripts/agent_manager.py current-start \
  --workspace <workspace> \
  --spec <spec-path>
```

Implement the immutable spec in the current session. When complete or blocked, finalize the exact
run directory printed by `current-start`:

```bash
python3 <plugin-root>/scripts/agent_manager.py current-finish \
  --workspace <workspace> \
  --run-dir <run-directory> \
  --outcome <completed|failed|blocked> \
  --summary <concise-summary> \
  --verification <check-and-result>
```

Repeat `--verification` and `--changed` as needed.

### External Agent

Preview when useful, then run only after approval:

```bash
python3 <plugin-root>/scripts/agent_manager.py plan \
  --workspace <workspace> --spec <spec-path> --agent <claude|cursor|kiro|auto>

python3 <plugin-root>/scripts/agent_manager.py run \
  --workspace <workspace> --spec <spec-path> --agent <claude|cursor|kiro|auto>
```

Do not add unsafe permission flags ad hoc. Use one write-capable agent per checkout. Competing
implementations require isolated worktrees and separately approved scope.

## 6. Handle ambiguity during implementation

An executor may not silently reinterpret or expand the spec. If it finds a missing decision,
conflict, or material ambiguity:

1. Stop the affected implementation work.
2. Return to focused `grilling` for that decision.
3. Create a new local spec revision. If an issue was published, append or synchronize a visible
   change record.
4. Ask the user to approve the revised execution input before resuming.

## 7. Verify independently

Treat process exit code zero as process success, not correctness.

1. Read the run's `status.json` and output artifacts.
2. Inspect the complete workspace changes and ensure they match the immutable local spec.
3. Run the agreed verification commands when safe and relevant.
4. Report implementation gaps explicitly; never commit or push unless separately requested.

## User-facing completion

Report result, run directory, changed files, verification outcomes, issue URL when applicable, and
remaining gaps. Keep secrets out of specs and prompts because external agents may transmit context
to their service providers.
