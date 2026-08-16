# Workflow state model

```text
REQUEST
  -> CLASSIFY
  -> GRILLING (only when needed)
  -> NEXT_STEP_CHOICE
  -> TO_SPEC_OUTPUT_CHOICE
  -> TEST_SEAM_CONFIRMATION
  -> SPEC_SNAPSHOT
  -> EXECUTOR_CHOICE
  -> EXECUTION_APPROVAL
  -> RUNNING
  -> VERIFYING
  -> COMPLETE | BLOCKED | FAILED
```

## Required prompts

After grilling reaches shared understanding:

1. Enter `to-spec` (recommended)
2. Continue clarification
3. Pause and keep the current conclusions

Each time `to-spec` starts:

1. Publish an issue and save a local snapshot (recommended)
2. Save local Markdown only; do not publish an issue or run Git commands during spec production

After the local spec snapshot exists:

1. Current Codex Agent
2. Recommended Agent
3. Kiro
4. Cursor
5. Claude
6. Do not execute yet

## Invariants

- User decisions come from one-at-a-time grilling questions; repository facts come from inspection.
- Test seams are confirmed before the spec is published or saved.
- The local snapshot, not a mutable issue, is the execution input.
- Executor selection and execution approval are separate decisions.
- A missing implementation decision returns the workflow to focused grilling.
- One checkout has at most one write-capable executor at a time.
