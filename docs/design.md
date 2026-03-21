# Design Notes

## Goal

Build a planning skill that treats context engineering as a first-class system, not only a set of reminders.

## Non-goals for v0.1.0

- no Claude plugin packaging
- no full host-specific session-history parsing
- no cross-machine git sync
- no mega-plan or story graph orchestration
- no GUI or MCP server

## Design pillars

### 1. Task-scoped isolation

Every task lives in `.planning/<slug>/`.

This avoids the root-level file collision model and makes multiple long-running tasks practical in a single repository.

### 2. Dual state

The system keeps both:

- markdown files for narrative, reasoning, and human review
- `state.json` for machine-readable state and deterministic recovery

`state.json` is the authoritative operational snapshot.

### 3. Hot context vs cold context

Not all task data should be repeatedly re-read.

- `Hot Context` lives at the top of `task_plan.md`
- durable conclusions live in `findings.md`
- chronological evidence lives in `progress.md`
- large or untrusted inputs stay out of repeatedly-read sections

### 4. Single writer

Only the coordinator updates:

- `task_plan.md`
- `progress.md`
- `state.json`

Delegates may write only inside `delegates/<delegate-id>/`.

Session-scoped routing does not change that rule: a task may have one writer session plus additional observer sessions, and observers stay out of the main planning files.

For parent workspaces that contain multiple git repos, the planning root stays shared at the parent level, while repo ownership is declared per task through explicit repo registration and repo scope metadata.

Ancestor `.planning/` directories are only reused when the current path still belongs to that workspace root, its planning tree, a registered repo, or a recorded worktree checkout. Otherwise resolution falls back to the current session directory so unrelated parent workspaces do not capture a new task by accident.

### 5. Pure-file recovery

Recovery should work even when:

- the agent is switched
- the session is cleared
- a host does not expose reliable session history

The recovery order is:

1. `state.json`
2. `task_plan.md` Hot Context
3. latest `progress.md` entries
4. unresolved delegate statuses

### 6. Verification as a contract

A task is not complete only because phases are checked off. It should define:

- what done means
- which commands or checks validate it
- what remains blocked when validation fails

## Lifecycle model

Task mode:

- `clarify`
- `plan`
- `execute`
- `verify`
- `archive`

Task status:

- `active`
- `paused`
- `blocked`
- `verifying`
- `done`
- `archived`

Additional intent:

- `paused` preserves the current phase and next action for later resumption
- `done` means completion is recorded, but the task can still be reviewed before archival

Phase status:

- `pending`
- `in_progress`
- `complete`
- `blocked`

## Delegate protocol

Delegates are optional. They exist to isolate independent work such as:

- repository exploration
- design spikes
- verification triage
- implementation review
- catchup summarization

Each delegate has a scratch folder:

```text
delegates/<delegate-id>/
  brief.md
  result.md
  status.json
```

The coordinator decides whether findings should be promoted into the main task files.

## Cross-agent portability

The canonical bundle lives in `skill/` and avoids host-specific hooks in v0.1.0.

This keeps the workflow usable in:

- Claude Code
- Codex
- OpenCode

Host-specific enhancements can be added later as thin wrappers.
