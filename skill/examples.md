# Examples

## Agent-first usage

Most users do not need to call the scripts directly for normal work.

For multi-step or recovery-sensitive work, the agent should usually pick this skill automatically from the task description alone.

When the user has not explicitly named the task, the agent should propose the inferred title and slug, then wait for confirmation before creating `.planning/<slug>/`.

Useful prompts:

```text
Refactor the auth flow across backend and frontend. This will take multiple steps, may get interrupted, and should be verified before you wrap up.
```

```text
I lost context. Recover the active task from .planning/ and continue from the recorded next_action.
```

```text
Review the risky parts of this change. Keep the main task focused, and if you need a bounded side investigation, promote only the distilled findings.
```

If the host does not auto-invoke the skill reliably, mention `context-task-planning` explicitly or use the scripts below.

If the host also lacks a native task UI adapter, add one more instruction:

```text
Before mixing this request into the active task, check whether it still fits the current task and ask whether to continue, switch tasks, or create a new task if it does not.
```

## Example 1: Start a new task

```bash
sh scripts/init-task.sh "Implement auth flow"
```

Result:

```text
.planning/implement-auth-flow/
  task_plan.md
  findings.md
  progress.md
  state.json
```

Then fill in:

- goal
- non-goals
- acceptance criteria
- constraints
- verification commands

## Example 2: Resume after context loss

1. Read `.planning/<slug>/state.json`
2. Read `Hot Context` at the top of `task_plan.md`
3. Read the most recent session section in `progress.md`
4. Continue from `next_action`

When the task has grown enough that replaying the markdown files feels noisy, use the derived compact view first:

```bash
sh scripts/compact-context.sh
sh scripts/compact-context.sh --json
```

The command prefers a fresh `.planning/<slug>/.derived/context_compact.json` when available and otherwise rebuilds an ephemeral compact snapshot from the current task files.

## Example 2b: Check for task drift before switching scope

```bash
sh scripts/current-task.sh
sh scripts/current-task.sh --compact
sh scripts/check-task-drift.sh --prompt "Also investigate the billing webhook regression" --json
```

If the result is `likely-unrelated` or `unclear`, confirm whether to continue the current task, switch tasks, or create a new task before editing `.planning/`.

The default `current-task.sh` output is the operator-facing summary: it shows the resolved task, access mode, repo/worktree state, and the next recommended command.

## Example 3: Use a delegate lane

Create the lane:

```bash
sh scripts/prepare-delegate.sh --kind discovery "Map auth entry points"
```

Use it for a bounded question such as:

- identify auth entry points
- list tests that already cover auth
- compare two implementation options

Then close and promote it:

```bash
sh scripts/list-delegates.sh
sh scripts/complete-delegate.sh repo-scan
sh scripts/promote-delegate.sh repo-scan
```

Promote only the distilled result back into the main task files.

If the lane stalls or becomes irrelevant:

```bash
sh scripts/block-delegate.sh --summary "Waiting on API clarification" repo-scan
sh scripts/resume-delegate.sh --summary "Clarification received" repo-scan
sh scripts/cancel-delegate.sh --summary "No longer needed after design change" repo-scan
```

## Example 4: Parallel sessions

Give each terminal or agent session its own session key, then bind a task inside that session:

```bash
PLAN_SESSION_KEY=manual:feature-auth sh scripts/set-active-task.sh feature-auth
PLAN_SESSION_KEY=manual:bugfix-login sh scripts/set-active-task.sh bugfix-login
```

Host adapters can do this automatically with their own session IDs. `PLAN_TASK` remains a one-off manual override, while `.planning/.active_task` is only the shared `workspace-default` fallback. In host UI, treat explicit session bindings as the only strong source for per-session task cues.

If two sessions need the same task, keep one writer and bind the others as observers:

```bash
PLAN_SESSION_KEY=manual:writer sh scripts/set-active-task.sh feature-auth
PLAN_SESSION_KEY=manual:reviewer sh scripts/set-active-task.sh --observe feature-auth
```

Observers may update delegate lanes, but they should not edit `task_plan.md`, `progress.md`, or `state.json`.

## Example 5: Parent workspace with multiple repos

Register repos explicitly, then bind them to the task:

```bash
sh scripts/list-repos.sh --discover
sh scripts/register-repo.sh --id frontend frontend
sh scripts/register-repo.sh --id backend backend
sh scripts/init-task.sh --repo frontend --repo backend --primary frontend "Cross-repo auth flow"
```

After that parent workspace owns `.planning/`, you can keep working from `frontend/`, `backend/`, or a recorded `.worktrees/...` checkout and still resolve the same shared task state. Unrelated ancestor `.planning/` directories should not capture the session.

If another writer task needs `frontend` at the same time, prepare a dedicated checkout for that repo:

```bash
sh scripts/prepare-task-worktree.sh --task billing-cleanup --repo frontend
sh scripts/set-task-repos.sh cross-repo-auth-flow --repo frontend --repo backend --primary frontend
sh scripts/list-worktrees.sh
```

The default checkout path is `.worktrees/billing-cleanup/frontend/`, and
`list-worktrees.sh` shows isolated checkouts grouped by task. `set-task-repos.sh`
now also tells you which repos are safe to keep shared, which already have a
task worktree, and which need `prepare-task-worktree.sh` next.

## Example 6: List tasks in one repository

```bash
sh scripts/list-tasks.sh
```

Use this when you need to see:

- active pointer
- current session binding
- how many sessions point at each task
- archived vs non-archived tasks
- most recently updated tasks

## Example 7: Archive a finished task

```bash
sh scripts/archive-task.sh feature-auth
```

This updates `state.json`, appends an archive note to `progress.md`, updates the `Hot Context` snapshot in `task_plan.md`, and clears `.planning/.active_task` if it pointed at the archived task.

## Example 8: Pause a task mid-stream

```bash
sh scripts/pause-task.sh feature-auth
```

This keeps the current phase and next action intact, marks the task as `paused`, and clears any session bindings or workspace fallback pointers that still pointed at the task.

## Example 9: Mark a task done before archival

```bash
sh scripts/done-task.sh feature-auth
```

This marks all non-blocked phases complete, sets the task status to `done`, updates the Hot Context snapshot, and leaves the task ready for later archival.

## Example 10: Resume a paused task

```bash
sh scripts/resume-task.sh feature-auth
```

This switches task status back to `active`, records a resume checkpoint, and binds the resumed task to the current session when `PLAN_SESSION_KEY` is present; otherwise it updates the workspace fallback pointer.

If another session already owns the writer lease for that task, use `--steal` only when you intentionally want to take over that ownership.

If the git worktree is dirty and the switch would carry local code changes into another task, the script now warns before switching. Use `--stash` to stash automatically:

```bash
sh scripts/resume-task.sh --stash feature-auth
```

You can inspect the recommendation first with:

```bash
sh scripts/check-switch-safety.sh --target-task feature-auth --json
```

## Example 11: Done guard when delegates are still open

If `delegation.active` still contains delegates, `done-task.sh` will refuse to mark the task done until those lanes are completed or otherwise resolved.

## Example 12: Validate task consistency

```bash
sh scripts/validate-task.sh
sh scripts/validate-task.sh --fix-warnings
```

Use `validate-task.sh` before wrapping up a long task or after a manual edit to planning files. It now also warns when a derived compact artifact is stale, or missing for a task that prefers compact reads. Use `--fix-warnings` when the only drift is warning-level markdown snapshot staleness that should be resynced from `state.json` or a derived compact artifact that should be refreshed.
