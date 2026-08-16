# Persisted to-spec snapshot

Persist the exact synthesized spec with execution metadata. Do not add specific file paths or code
snippets unless a prototype snippet is the clearest durable representation of an agreed decision.

````markdown
---
status: approved
source_mode: issue-and-local | local-only
issue_url: <URL or null>
issue_number: <number or null>
published_at: <ISO-8601 timestamp or null>
created_at: <ISO-8601 timestamp>
execution_source: local-snapshot
---

# <Feature or change title>

## Problem Statement

The problem from the user's perspective.

## Solution

The agreed solution from the user's perspective.

## User Stories

1. As an <actor>, I want <feature>, so that <benefit>.

Include an extensive numbered list covering normal behavior, failure behavior, permissions,
compatibility, and operational needs when relevant.

## Implementation Decisions

- Agreed modules and interfaces.
- Architectural, schema, API, compatibility, and interaction decisions.

## Testing Decisions

- The confirmed highest practical test seam.
- Observable behaviors to test and relevant prior art in the repository.

## Out of Scope

Explicit exclusions.

## Further Notes

Risks, rollout or rollback considerations, and unresolved non-blocking notes.
````
