# Examples

## Agent-first usage

Most users do not need to call the scripts directly for normal work.

For multi-step or recovery-sensitive work, the agent should usually pick this skill automatically from the task description alone.

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
- constraints
- verification commands

## Example 2: Resume after context loss

1. Read `.planning/<slug>/state.json`
2. Read `Hot Context` at the top of `task_plan.md`
3. Read the most recent session section in `progress.md`
4. Continue from `next_action`

## Example 2b: Check for task drift before switching scope

```bash
sh scripts/current-task.sh --compact
sh scripts/check-task-drift.sh --prompt "Also investigate the billing webhook regression" --json
```

If the result is `likely-unrelated` or `unclear`, confirm whether to continue the current task, switch tasks, or create a new task before editing `.planning/`.

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

Pin each terminal or agent session to a different task:

```bash
export PLAN_TASK=feature-auth
export PLAN_TASK=bugfix-login
```

This avoids accidental switching through the shared `.planning/.active_task` pointer.

## Example 5: List tasks in one repository

```bash
sh scripts/list-tasks.sh
```

Use this when you need to see:

- active pointer
- session pin
- archived vs non-archived tasks
- most recently updated tasks

## Example 6: Archive a finished task

```bash
sh scripts/archive-task.sh feature-auth
```

This updates `state.json`, appends an archive note to `progress.md`, updates the `Hot Context` snapshot in `task_plan.md`, and clears `.planning/.active_task` if it pointed at the archived task.

## Example 7: Pause a task mid-stream

```bash
sh scripts/pause-task.sh feature-auth
```

This keeps the current phase and next action intact, marks the task as `paused`, and clears the shared active pointer if needed.

## Example 8: Mark a task done before archival

```bash
sh scripts/done-task.sh feature-auth
```

This marks all non-blocked phases complete, sets the task status to `done`, updates the Hot Context snapshot, and leaves the task ready for later archival.

## Example 9: Resume a paused task

```bash
sh scripts/resume-task.sh feature-auth
```

This switches task status back to `active`, records a resume checkpoint, and restores `.planning/.active_task` to the resumed task.

If the git worktree is dirty and the switch would carry local code changes into another task, the script now warns before switching. Use `--stash` to stash automatically:

```bash
sh scripts/resume-task.sh --stash feature-auth
```

You can inspect the recommendation first with:

```bash
sh scripts/check-switch-safety.sh --target-task feature-auth --json
```

## Example 10: Done guard when delegates are still open

If `delegation.active` still contains delegates, `done-task.sh` will refuse to mark the task done until those lanes are completed or otherwise resolved.

## Example 11: Validate task consistency

```bash
sh scripts/validate-task.sh
```

Use this before wrapping up a long task or after a manual edit to planning files.
