# Context Task Planning

Context engineering skill for Claude Code, Codex, and OpenCode.

`context-task-planning` turns long-running agent work into task-scoped, recoverable workspaces on disk. It combines:

- task-scoped planning workspaces
- durable local context and recovery after context loss
- compact hot-context snapshots for repeated reads
- delegate lanes for sub-agents or isolated side quests
- verification as part of the task contract

## Visible task cues

Once enabled, users should be able to notice the active task without opening `.planning/` manually:

- `Claude Code` - the active task shows up in Claude Code's native status line, and hooks can warn before likely task drift
- `OpenCode` - the optional plugin prefixes the session title with `task:<slug> | ...` and shows toasts when task focus changes or drifts
- `Codex` - the portable fallback is `current-task.sh --compact` in the shell or tmux, plus an explicit confirm-before-switch prompt when work looks unrelated
- `Any shell or tmux` - `sh skill/scripts/current-task.sh --compact` prints a one-line task summary for prompts, status bars, or scripts

The goal is simple: make the current task visible, and make silent task mixing harder.

## Why this exists

`planning-with-files` proved that durable local files are a powerful form of context engineering. This project takes the next step for day-to-day multi-agent work:

- multiple long-running tasks in one repository
- safe recovery after context clears, model switches, or agent switches
- a smaller hot-context surface for repeated reads
- delegate or sub-agent work without shared-state collisions
- explicit done criteria and verification logs
- a workflow that still works when host-specific hooks differ

## Core ideas

- `task-scoped isolation` - each task is a separate planning workspace
- `clarify before build` - capture goals, constraints, non-goals, and open questions first
- `single writer` - only the coordinator updates main planning files
- `dual state` - markdown for humans, JSON for tools and recovery
- `hot context` - only the smallest current snapshot should be read repeatedly
- `pure-file recovery` - no reliance on agent-specific session history

## File layout

```text
.planning/
  .active_task
  feature-auth/
    task_plan.md
    findings.md
    progress.md
    state.json
    delegates/
      repo-scan/
        brief.md
        result.md
        status.json
```

## Install

This repository keeps one canonical skill bundle in `skill/`.

Recommended install:

```bash
npx skills add excitedhaha/context-task-planning -g
```

The CLI will discover the skill under `skill/` automatically. Choose `context-task-planning` and the agent(s) you want when prompted.

If you want to preview what will be installed first:

```bash
npx skills add excitedhaha/context-task-planning -l
```

Local clone fallback for development or manual inspection:

```bash
git clone https://github.com/excitedhaha/context-task-planning.git
cd context-task-planning
sh skill/scripts/install-macos.sh
```

See agent-specific notes in:

- `docs/claude.md`
- `docs/codex.md`
- `docs/opencode.md`
- `docs/sharing.md`

## Optional UX adapters

The core file workflow works without host-specific UI.

If you want visible task cues inside the host itself:

- `Claude Code` - enable the bundled hook + status-line config in `docs/claude.md`
- `OpenCode` - enable the bundled plugin in `docs/opencode.md`
- `Codex` - use the shared shell commands and prompt-level confirm-before-switch guidance in `docs/codex.md`; native runtime UI is not bundled yet

## Quick verification after enable

Use these as the fastest sanity checks that task visibility is actually working:

- `Claude Code` - restart Claude Code and look for `task:<slug>` in the native status line
- `OpenCode` - restart OpenCode, send one message, and look for `task:<slug> | ...` in the session title plus task/drift toasts
- `Codex` - run `sh skill/scripts/current-task.sh --compact` and expect the current task slug in the output

## Recommended usage

Most users should start by talking to the agent, not by memorizing shell scripts.

The most natural path is to just give the agent a complex task. For multi-step, long-running, recovery-sensitive, or delegation-heavy work, the expected behavior is that the agent decides to use `context-task-planning` automatically.

If you want to force the workflow, or if a host does not auto-invoke skills reliably, mention the skill name explicitly.

In either mode, the agent should:

- create or resume the task workspace in `.planning/<slug>/`
- keep `Hot Context`, `next_action`, and verification state current
- recover from local planning files after context loss
- create delegate lanes for bounded review, discovery, or verify side quests when useful

Example prompts:

```text
Refactor the auth flow across backend and frontend. This will take multiple steps, so keep progress on disk, recover cleanly if context is lost, and verify before wrapping up.
```

```text
I lost context on this task. Recover the active task from local planning files and continue from the recorded next step.
```

```text
Use context-task-planning and open a delegate lane to review migration risks. Promote only the distilled findings back to the main task.
```

```text
Use context-task-planning for this refactor. Create or resume a task, keep the hot context current, and verify before wrapping up.
```

If a host does not auto-invoke the skill reliably, mention the skill name explicitly or fall back to the scripts below.

## Script escape hatches

Scripts are still useful when you want explicit control, debugging, or automation.

Start or resume a task:

```bash
sh skill/scripts/init-task.sh "Implement auth flow"
```

Then read and keep current:

- `task_plan.md`
- `findings.md`
- `progress.md`
- `state.json`

Pin one terminal or agent session to a task:

```bash
export PLAN_TASK=feature-auth
```

Switch the shared default task:

```bash
sh skill/scripts/set-active-task.sh feature-auth
```

List tasks in the current workspace:

```bash
sh skill/scripts/list-tasks.sh
```

Validate task consistency before wrap-up:

```bash
sh skill/scripts/validate-task.sh
```

Show the current task in a shell prompt, tmux status line, or host adapter:

```bash
sh skill/scripts/current-task.sh --compact
```

Check whether a new request looks like task drift before mixing it into the active lane:

```bash
sh skill/scripts/check-task-drift.sh --prompt "Also investigate the billing webhook regression" --json
```

Create, inspect, complete, and promote a delegate lane:

```bash
sh skill/scripts/prepare-delegate.sh --kind discovery "Map auth entry points"
sh skill/scripts/list-delegates.sh
sh skill/scripts/complete-delegate.sh repo-scan
sh skill/scripts/promote-delegate.sh repo-scan
```

Block or cancel a lane instead:

```bash
sh skill/scripts/block-delegate.sh --summary "Waiting on API clarification" repo-scan
sh skill/scripts/resume-delegate.sh --summary "Clarification received" repo-scan
sh skill/scripts/cancel-delegate.sh --summary "No longer needed after design change" repo-scan
```

Pause, resume, finish, or archive a task:

```bash
sh skill/scripts/pause-task.sh feature-auth
sh skill/scripts/resume-task.sh feature-auth
sh skill/scripts/done-task.sh feature-auth
sh skill/scripts/archive-task.sh feature-auth
```

## Task lifecycle

1. `clarify` - define goal, non-goals, constraints, open questions
2. `plan` - define phases, definition of done, verification targets
3. `execute` - implement incrementally and keep state current
4. `verify` - run checks and record actual results
5. `archive` - remove active pointer and keep the task history

## Sharing

- The reusable artifact is the repository itself: `README.md`, `docs/`, `skill/`, and `LICENSE`
- Real task state under `.planning/` is intentionally local and ignored by Git
- If a teammate already uses `planning-with-files`, disable its hooks or old skill link before enabling this skill's Claude hooks
- `npx skills add` is the preferred install path for teammates; local scripts remain the fallback for contributors
- Public install target: `excitedhaha/context-task-planning`

## Publishing

Before pushing to GitHub, run the checklist in `docs/sharing.md`.

## Repository layout

```text
context-task-planning/
  docs/
  skill/
    SKILL.md
    claude-hooks/
    reference.md
    examples.md
    templates/
    schemas/
    scripts/
```

## Inspirations

This project is informed by:

- `planning-with-files`
- `devis`
- `multi-manus-planning`
- `plan-cascade`

All of them explore different forms of context engineering, planning, and coordination.

## Status

`v0.2.0` keeps the core small, but the public workflow now includes:

- repository-local `.planning/`
- slug-based task isolation
- pure-file recovery
- task state schema
- delegate lanes for sub-agents and bounded side quests
- agent-first usage with script escape hatches
- shared task focus guard primitives for visibility and drift checks
- `npx skills add` friendly distribution
- optional Claude Code hooks/status line and OpenCode plugin adapter

It still does not include host-specific session catchup or cross-machine sync.

Today that means users can already get visible task cues in two places:

- `Claude Code` - native status line task display
- `OpenCode` - session title prefix + drift toasts
