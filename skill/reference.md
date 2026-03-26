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

The coordinator owns main planning files. Delegates do not. A task may have one writer session plus additional observer sessions.

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

## Subagent preflight

Use `subagent-preflight.sh` when a host or wrapper is about to launch a native subagent and needs one shared routing and repo/worktree decision:

```bash
sh skill/scripts/subagent-preflight.sh \
  --cwd "$PWD" \
  --host claude \
  --tool-name Task \
  --task-text "Investigate auth entry points" \
  --json
```

The shared decisions are:

- `routing_only` - do not inject canonical repo/worktree payload; show routing confirmation only
- `payload_only` - inject the canonical prompt prefix for a related native `Task` launch
- `payload_plus_delegate_recommended` - inject the canonical prompt prefix and add non-blocking delegate guidance
- `delegate_required` - do not treat the native subagent launch as sufficient; create or reuse a delegate lane first

The shell wrapper calls `task_guard.py subagent-preflight`, so task resolution, drift classification, repo scope, and worktree bindings stay in one place.

## Validation

Run `validate-task.sh` whenever you suspect drift between `state.json`, markdown snapshots, and delegate status files.

- hard failures should cover missing files, invalid JSON, or active delegate mismatches
- softer warnings can cover stale `progress.md` snapshots or other recoverable drift
- `validate-task.sh --fix-warnings` should only repair warning-level snapshot drift, not hard failures or operational truth in `state.json`

## Task focus guard

Use `current-task.sh` when you need the resolved task plus the next recommended action. Keep `current-task.sh --compact` for shell prompts, tmux status lines, or other space-constrained surfaces.

For the deeper architecture behind session bindings, repo scope, and worktree isolation, see `docs/design.md`.

Resolution order is: explicit `--task`, `PLAN_TASK`, the session binding selected by `PLAN_SESSION_KEY`, `.planning/.active_task`, then the latest auto-selectable task.

Treat those sources differently in UI: `session_binding` is the strong per-session signal, `.planning/.active_task` is the shared `workspace-default` fallback, and `latest` is only a recovery/default guess.

The default human-readable output should answer:

- what task is currently selected
- whether this session is writer or observer
- which repos are shared versus isolated worktrees
- what command the operator should run next

The JSON output keeps the existing task fields and appends recommendation metadata such as `repo_summary`, `recommended_action`, `recommended_reason`, `recommended_commands`, and `resume_candidates`.

`set-active-task.sh` accepts `--observe` for read-only bindings and `--steal` when a new session intentionally takes over the writer lease.

Use `check-task-drift.sh` when you want a lightweight answer to: does this new request still fit the active task, or should the agent confirm before mixing it in?

Use `check-switch-safety.sh --target-task <slug> --json` when you are about to switch tasks in a git repository and want to know whether the current worktree should be stashed or committed first.

`init-task.sh`, `resume-task.sh`, and `set-active-task.sh` now enforce that guard automatically. In a dirty git worktree they will prompt to stash, stop so you can commit manually, continue dirty, or cancel. Use `--stash` to auto-stash or `--allow-dirty` to bypass the guard deliberately. When `PLAN_SESSION_KEY` is present, those commands update the current session binding instead of treating `.planning/.active_task` as the only live pointer; without a session key, they operate on the shared `workspace-default` fallback.

Observer sessions may still create or update delegate lanes under `delegates/<delegate-id>/`, but they must leave `task_plan.md`, `progress.md`, `state.json`, and `findings.md` to the writer.

For parent workspaces that contain multiple repos, register repos explicitly with `register-repo.sh`, attach them to tasks with `set-task-repos.sh`, and only use auto-discovery as a review aid before you confirm the registrations.

Parent-workspace resolution is path-aware: unrelated ancestor `.planning/` roots should not capture the current session.

If two writer tasks need the same repo concurrently, prepare a dedicated
checkout for the overlapping repo with
`prepare-task-worktree.sh --task <slug> --repo <repo-id>`. By default that
creates `.worktrees/<task-slug>/<repo-id>/`. Use `--path` only when you
intentionally need a nonstandard checkout location.

`set-task-repos.sh` and writer-bind failures should also tell you which repos are:

- safe to keep shared
- already isolated in a task worktree
- blocked until you run `prepare-task-worktree.sh`

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

- `active` - the task is open for ongoing work and may be the current target for one or more sessions
- `paused` - the task is intentionally parked; keep the next action intact
- `blocked` - the task cannot advance until blockers are resolved
- `verifying` - the task is in an explicit validation pass
- `done` - the task has cleared its completion bar but is not yet archived
- `archived` - the task is historical and should not be auto-selected
