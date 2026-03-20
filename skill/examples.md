# Examples

## Agent-first usage

Most users do not need to call the scripts directly for normal work.

Useful prompts:

```text
Use context-task-planning for this task. Create or resume the task, keep the hot context current, and verify before wrapping up.
```

```text
I lost context. Recover the active task from .planning/ and continue from the recorded next_action.
```

```text
Use context-task-planning and create a delegate lane to review the risky parts of this change. Promote only the distilled findings.
```

If the host does not auto-invoke the skill reliably, mention the skill name explicitly or use the scripts below.

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

## Example 10: Done guard when delegates are still open

If `delegation.active` still contains delegates, `done-task.sh` will refuse to mark the task done until those lanes are completed or otherwise resolved.

## Example 11: Validate task consistency

```bash
sh scripts/validate-task.sh
```

Use this before wrapping up a long task or after a manual edit to planning files.
