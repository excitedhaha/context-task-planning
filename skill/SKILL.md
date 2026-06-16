---
name: context-task-planning
description: Task-scoped context engineering for complex multi-step work. Use when a task needs clarification, phased execution, durable file-based state, recovery after context loss, or optional sub-agent delegation.
license: MIT
metadata:
  version: "0.8.7"
allowed-tools: Read Write Edit Bash Glob Grep WebFetch Task
---

# Context Task Planning

Use `.planning/<slug>/` files as durable, task-scoped context for work that is too large or stateful to trust to the live chat window alone.

## Use When

Use this skill for multi-step work, unclear requirements, long-running implementation or research, context-loss recovery, task switching, or isolated sub-agent/delegate subproblems.

Skip it for one-shot edits, simple commands, or work that can be completed safely in a short turn without durable state.

Supported hosts expose thin entry points over the same scripts: Claude Code and Codex use `task-*` entry skills, OpenCode uses slash commands, and TraeCLI/Coco uses namespaced slash commands. Keep those wrappers thin; do not invent a second workflow.

## Task Files

Each task owns:

```text
.planning/<slug>/
  state.json      # operational truth
  task_plan.md    # human plan and small Hot Context
  findings.md     # durable discoveries and distilled external input
  progress.md     # checkpoints, session log, verification results
  delegates/      # optional isolated side lanes
```

Treat `state.json` as the source of truth for status, mode, phase, blockers, next action, verification targets, session role, repo scope, and active delegates. Keep markdown aligned with it.

## Start Or Resume

If the user did not explicitly provide a task title, infer a concise candidate title and the slug that `scripts/slugify.sh` would produce, then ask the user to confirm or edit both before creating files. Do not silently create a task from an inferred name.

Create the task only after title and slug are final:

```bash
sh scripts/init-task.sh --title "<final task title>" --slug "<final task slug>"
```

Then read `.planning/<slug>/state.json` and the Hot Context in `.planning/<slug>/task_plan.md`. Before implementation, capture goal, non-goals, acceptance criteria, constraints, open questions or assumptions, and verification targets.

When resuming, recover in this order:

1. `state.json`
2. `task_plan.md` Hot Context
3. recent relevant `progress.md` entries
4. unresolved delegates

Use `scripts/current-task.sh` when you need the selected task and next recommended action. Use `--compact` only for prompt/status-line contexts.

## Clarify Before Build

For complex or ambiguous work, run the clarify phase as a focused interview before planning or implementation:

- Ask one blocking question at a time instead of dumping a questionnaire.
- Include your recommended answer with each question so the user can approve, edit, or reject it quickly.
- If the answer can be discovered by reading code, tests, docs, task files, or linked spec artifacts, inspect those first instead of asking the user.
- Resolve dependent decisions in order: goal, non-goals, acceptance criteria, constraints, edge cases, verification target, then execution approach.
- Record resolved answers in `state.json` first, keep `task_plan.md` aligned, and log meaningful decisions or remaining uncertainty in `progress.md`.
- Keep unresolved but non-blocking uncertainty in `open_questions`; do not start implementation while critical ambiguity remains.

## Operating Rules

- Keep Hot Context small: status, goal, mode, phase, next action, blockers, verification target.
- Put raw or untrusted external content in `findings.md`, then promote only distilled conclusions into `task_plan.md`.
- Record meaningful progress, decisions, blockers, and verification results in `progress.md`.
- Declare completion checks in `state.verify_commands` and record matching successful rows in `progress.md` under `## Verification Log`.
- Do not mark a task done unless every declared verification target has a successful recorded result.
- Archive completed tasks instead of reusing old slugs for unrelated work.
- Before switching tasks in a git repo, let the dirty-worktree guard prompt you; do not silently carry changes into another task.

## Session And Repo Ownership

Use a stable `PLAN_SESSION_KEY` when multiple sessions are active:

```bash
export PLAN_SESSION_KEY=manual:<name>
sh scripts/set-active-task.sh <slug>
```

Use `PLAN_TASK` only as a one-off shell override. If another session already owns the writer lease, bind with `set-active-task.sh --observe <slug>` unless the user explicitly asks to take over.

Only the writer/coordinator edits main planning files:

- `task_plan.md`
- `findings.md`
- `progress.md`
- `state.json`

Observers may create or update delegate lanes, but must not edit main planning files.

For parent workspaces with multiple repos, register repos explicitly before binding them to tasks:

```bash
sh scripts/list-repos.sh --discover
sh scripts/register-repo.sh --id frontend frontend
sh scripts/set-task-repos.sh <slug> --repo frontend --primary frontend
```

Use discovery only to review candidates. If overlapping writer tasks need the same repo, create a task worktree with `scripts/prepare-task-worktree.sh --task <slug> --repo <repo-id>`.

## Drift And Routing

When a new complex request may not belong to the active task, use:

```bash
sh scripts/check-task-drift.sh --prompt "<new request>" --json
```

Treat `likely-unrelated` as route evidence: ask whether to continue the current task, switch tasks, or create a new task before changing planning state. Treat `unclear` as non-conclusive and decide from the conversation plus task goal.

## Delegates And Subagents

Use delegate lanes only for bounded side work such as discovery, feasibility spikes, verification triage, review, or catchup summarization. If you are about to launch a subagent for one of those bounded questions and durable isolation matters, create or reuse a delegate first.

Minimal delegate loop:

1. `scripts/prepare-delegate.sh` or `scripts/create-delegate.sh`
2. `scripts/start-delegate.sh <delegate-id>`
3. let the worker write only inside `delegates/<delegate-id>/`
4. `scripts/block-delegate.sh`, `cancel-delegate.sh`, or `complete-delegate.sh`
5. `scripts/promote-delegate.sh <delegate-id>` for useful conclusions

Never let delegates mutate `task_plan.md`, `findings.md`, `progress.md`, or `state.json`.

## Prune, Done, Archive

If `progress.md` is too large for repeated recovery reads, run `scripts/context-prune.sh --status`, then `--prepare`, summarize the older range, and apply only from the writer lane. In shell-only workspace-default mode, add `--fallback` deliberately for apply or restore.

Use `scripts/done-task.sh [slug]` only after verification evidence exists. Use `scripts/archive-task.sh [slug]` when the done task no longer needs to appear in active lists.

## Useful Commands

- Task lifecycle: `init-task.sh`, `current-task.sh`, `list-tasks.sh`, `pause-task.sh`, `resume-task.sh`, `done-task.sh`, `archive-task.sh`
- Consistency and routing: `validate-task.sh`, `check-task-drift.sh`, `check-switch-safety.sh`, `ensure-switch-safety.sh`
- Sessions: `set-active-task.sh`, `resolve-plan-dir.sh`
- Delegates: `prepare-delegate.sh`, `create-delegate.sh`, `list-delegates.sh`, `start-delegate.sh`, `resume-delegate.sh`, `block-delegate.sh`, `cancel-delegate.sh`, `complete-delegate.sh`, `promote-delegate.sh`
- Multi-repo/worktrees: `list-repos.sh`, `register-repo.sh`, `set-task-repos.sh`, `prepare-task-worktree.sh`, `list-worktrees.sh`
- Context maintenance: `context-prune.sh`, `check-complete.sh`

Read `reference.md` for detailed contracts, status semantics, host-specific behavior, spec context, and command output fields.

## Safety

- Do not create an inferred task without title and slug confirmation.
- Do not bypass writer/observer access checks.
- Do not mark done without recorded verification results.
- Do not reuse an old slug for unrelated work.
- Keep host adapters and entry skills thin over `skill/scripts/`.
