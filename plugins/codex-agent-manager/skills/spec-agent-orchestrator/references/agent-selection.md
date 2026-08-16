# Agent selection

Availability is a hard constraint. Run `doctor --json` before choosing.

## Current Codex Agent

Prefer the current Codex Agent when the user requests it, the relevant repository context is
already loaded, or the task is small enough that an external handoff adds more overhead than value.
It still uses the same immutable spec, approval gate, audit record, and independent verification.

## Kiro

Prefer Kiro when the user explicitly requests it or the work is a feature with strong spec-driven
requirements and Kiro CLI is installed. The adapter uses Kiro's documented non-interactive chat
mode. Its default write profile trusts all tools, so run it only after the approval gate and in a
workspace the user intends to modify.

## Cursor

Prefer Cursor when the user explicitly requests it or the task benefits from fast editor-style
iteration in a known workspace and Cursor Agent CLI is installed. The desktop Cursor application
alone is not sufficient; the `agent` or `cursor-agent` executable must resolve on `PATH`.

## Claude

Prefer Claude when the user explicitly requests it, the change requires broad repository reasoning,
or it is the only available supported agent. The default adapter uses print mode with structured
streaming output and `acceptEdits`, avoiding the dangerous permission-bypass flag.

## Auto

Use `auto` only when the user has no preference among external agents. The deterministic fallback order comes from
`assets/agents.default.json` or the repository override. Explain the selected agent rather than
presenting `auto` as a model-quality judgment.

## Multiple agents

Do not let agents race to edit the same checkout. For independent comparison, give each agent a
separate git worktree and the same approved spec, then have Codex compare diffs and verification
results. For a pipeline, give agents distinct phases such as implementation then read-only review.
