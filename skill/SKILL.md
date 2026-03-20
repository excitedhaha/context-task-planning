---
name: context-task-planning
description: Task-scoped context engineering for complex multi-step work. Use when a task needs clarification, phased execution, durable file-based state, recovery after context loss, or optional sub-agent delegation.
license: MIT
metadata:
  version: "0.2.0"
allowed-tools: Read Write Edit Bash Glob Grep WebFetch Task
---

# Context Task Planning

Use persistent planning files as a task-scoped context system.

This skill is for work that is too large or too stateful to trust to the live context window alone.

## When to use

Use this skill when the work involves one or more of the following:

- more than a few steps
- requirements that still need clarification
- long-running implementation or research
- recovery after context loss or agent switching
- optional delegate or sub-agent work on isolated subproblems

## Core operating model

Each task lives in its own directory:

```text
.planning/<slug>/
  task_plan.md
  findings.md
  progress.md
  state.json
  delegates/
```

### File roles

- `state.json` - machine-readable source of truth for current task status
- `task_plan.md` - human-readable plan, with a compact `Hot Context` section at the top
- `findings.md` - durable discoveries, external information, and material to distill later
- `progress.md` - session log, checkpoints, and verification results

## First steps

1. Run `scripts/init-task.sh "<task title>"`
2. Read `.planning/<slug>/state.json`
3. Read `.planning/<slug>/task_plan.md`
4. Fill in missing goal, non-goals, constraints, and open questions before implementation

If multiple sessions are active, pin the current session to one task:

```bash
export PLAN_TASK=<slug>
```

## Workflow

### 1. Clarify first

Do not jump into implementation until the task has:

- a clear goal
- explicit non-goals
- constraints
- open questions or assumptions listed

### 2. Keep the hot context small

Repeated reads should focus on the smallest useful snapshot:

- task status
- goal
- current mode
- current phase
- next action
- blockers
- verification target

Do not repeatedly reload large notes when a compact snapshot will do.

### 3. Treat `state.json` as operational truth

Whenever the task status changes, update `state.json` first and keep markdown aligned with it.

### 4. Distill findings intentionally

External or untrusted content belongs in `findings.md`, not in `Hot Context`.

Promote only the distilled conclusions into the main plan.

### 5. Verify before marking done

Every task should declare its verification targets and record actual results in `progress.md`.

### 6. Archive, do not overwrite

When a task is complete, keep the task directory as history. Switch or remove the active pointer instead of reusing the directory for unrelated work.

## Delegate protocol

Delegates are optional and should be used only for isolated work such as:

- discovery
- spikes
- verification triage
- review
- catchup summarization

Delegate folders live under:

```text
delegates/<delegate-id>/
  brief.md
  result.md
  status.json
```

### Delegate workflow

1. For faster setup, use `scripts/prepare-delegate.sh` to infer and create a lane in one step, or use `scripts/create-delegate.sh` for full manual control
2. Fill `brief.md` with the bounded question, constraints, and expected deliverable
3. Mark the lane `running` with `scripts/start-delegate.sh` when work begins
4. Let the subagent or isolated worker operate only inside that delegate directory
5. If the lane stalls, use `scripts/block-delegate.sh`; if it becomes irrelevant, use `scripts/cancel-delegate.sh`
6. Mark the lane complete with `scripts/complete-delegate.sh`
7. Merge useful results back with `scripts/promote-delegate.sh`

Blocked lanes can be resumed explicitly with `scripts/resume-delegate.sh`.

### Delegate triggers

Create a delegate lane when the main task produces a bounded subproblem such as:

- repository exploration or entry-point mapping
- option comparison or feasibility spike
- test failure triage or validation pass
- diff review or focused code review

If you are about to launch a subagent for one of those questions, create the delegate lane first.

### Single writer rule

Only the coordinator updates:

- `task_plan.md`
- `progress.md`
- `state.json`

Delegates should write only inside their own scratch folders.

## Recovery order

When resuming a task, recover in this order:

1. `state.json`
2. `task_plan.md` Hot Context
3. latest relevant entries in `progress.md`
4. unresolved delegates

This keeps recovery portable across Claude Code, Codex, and OpenCode.

## Scripts

- `scripts/init-task.sh` - create or resume `.planning/<slug>/`
- `scripts/resolve-plan-dir.sh` - resolve current task from `PLAN_TASK`, `.active_task`, or latest plan
- `scripts/current-task.sh` - show the resolved task for shells, status bars, or host adapters
- `scripts/check-task-drift.sh` - classify whether a new prompt still fits the active task
- `scripts/set-active-task.sh <slug>` - update shared default pointer
- `scripts/validate-task.sh` - check task state consistency across `state.json`, markdown files, and delegates
- `scripts/prepare-delegate.sh` - infer and create a delegate lane, optionally auto-starting it
- `scripts/create-delegate.sh` - create a delegate lane under the current task
- `scripts/list-delegates.sh` - show delegate lanes for the current task
- `scripts/start-delegate.sh <delegate-id>` - mark a delegate lane running when active work begins
- `scripts/resume-delegate.sh <delegate-id>` - resume a blocked delegate lane back to running
- `scripts/block-delegate.sh <delegate-id>` - mark a delegate lane blocked while keeping it open
- `scripts/cancel-delegate.sh <delegate-id>` - cancel a delegate lane and remove it from active delegates
- `scripts/complete-delegate.sh <delegate-id>` - mark a delegate lane complete and remove it from active delegates
- `scripts/promote-delegate.sh <delegate-id>` - append delegate results into `findings.md`
- `scripts/list-tasks.sh` - show all task workspaces and their states
- `scripts/pause-task.sh [slug]` - pause a task without losing its current phase or next action
- `scripts/resume-task.sh [slug]` - reactivate a paused task and restore it as the shared default
- `scripts/done-task.sh [slug]` - mark a task done after verification and clear the shared pointer if needed
- `scripts/archive-task.sh [slug]` - archive a task and clear the shared pointer if needed
- `scripts/check-complete.sh` - summarize current task completion state
- `scripts/install-macos.sh` - install symlinks for Claude Code, Codex, and OpenCode

## Safety rules

- Keep untrusted external content in `findings.md`
- Do not let delegates mutate the main planning files
- Do not mark tasks done without recording real verification results
- Do not reuse an old slug for unrelated work
