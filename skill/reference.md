# Reference

## Context engineering layers

This skill treats context engineering as three coordinated layers:

1. `Persistence` - durable files hold the state that a live context window will lose
2. `Isolation` - each task gets its own planning workspace
3. `Delegation` - independent subproblems can be handled in their own scratch lanes

## Principles

### Clarify before build

Capture goals, non-goals, constraints, and open questions before implementation.

### Hot context over full replay

Repeated reads should prefer a compact snapshot over reloading entire notes.

### Markdown for humans, JSON for tools

Use markdown for explanation and review. Use `state.json` for stable machine-readable state.

### Single writer, multiple readers

The coordinator owns main planning files. Delegates do not.

### Distill before promote

External inputs become conclusions only after distillation. Keep raw or untrusted inputs out of repeated reads.

### Verify explicitly

Task completion should include real verification commands and recorded results.

### Archive instead of overwrite

Finished tasks are preserved as history. New work gets a new slug.

## Delegate-friendly work

Good delegate candidates:

- repository scanning
- implementation option comparison
- test failure triage
- code review or diff review
- long-session catchup summaries

Minimal delegate loop:

1. create a lane with `prepare-delegate.sh` or `create-delegate.sh`
2. switch the lane to `running` with `start-delegate.sh`
3. let the isolated worker answer the bounded question in `result.md`
4. if the lane stalls, use `block-delegate.sh`; if it is no longer needed, use `cancel-delegate.sh`
5. close the lane with `complete-delegate.sh`
6. merge durable conclusions with `promote-delegate.sh`

Use delegate lanes proactively for discovery, review, and verify subproblems instead of mixing those side quests into the coordinator's main context.

## Validation

Run `validate-task.sh` whenever you suspect drift between `state.json`, markdown snapshots, and delegate status files.

- hard failures should cover missing files, invalid JSON, or active delegate mismatches
- softer warnings can cover stale `progress.md` snapshots or other recoverable drift

## Task focus guard

Use `current-task.sh` when a shell prompt, tmux status line, or host adapter needs a compact view of the current task.

Use `check-task-drift.sh` when you want a lightweight answer to: does this new request still fit the active task, or should the agent confirm before mixing it in?

Use `check-switch-safety.sh --target-task <slug> --json` when you are about to switch tasks in a git repository and want to know whether the current worktree should be stashed or committed first.

`init-task.sh`, `resume-task.sh`, and `set-active-task.sh` now enforce that guard automatically. In a dirty git worktree they will prompt to stash, stop so you can commit manually, continue dirty, or cancel. Use `--stash` to auto-stash or `--allow-dirty` to bypass the guard deliberately.

On hosts without runtime adapters, treat `likely-unrelated` and `unclear` as a prompt to confirm routing before you edit `.planning/`.

For OpenCode specifically, the bundled plugin can be installed with `install-opencode-plugin.sh`; it is designed to stay quiet in repositories that do not already use `.planning/`.

P0 classifications are:

- `related`
- `unclear`
- `likely-unrelated`
- `no-active-task`

Poor delegate candidates:

- concurrent writes to main planning files
- risky shared-state operations
- destructive release or migration steps

## Recovery checklist

If context feels stale, answer these in order:

1. Which task is active?
2. What mode is it in?
3. What is the next action?
4. What is blocked?
5. What proves the task is done?

Those answers should be available from the task folder without relying on session history.

## Status semantics

- `active` - the task is the current working target
- `paused` - the task is intentionally parked; keep the next action intact
- `blocked` - the task cannot advance until blockers are resolved
- `verifying` - the task is in an explicit validation pass
- `done` - the task has cleared its completion bar but is not yet archived
- `archived` - the task is historical and should not be auto-selected
