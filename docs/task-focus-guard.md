# Task Focus Guard

## Goal

Prevent silent task drift in long-running agent sessions by making the current task visible and by adding a lightweight reminder path when a new prompt appears to be about a different task.

## Non-goals

- do not auto-switch tasks
- do not block normal prompts by default
- do not add an extra LLM classifier in P0
- do not make Claude-only hooks the source of truth

## Shared core

P0 should be host-agnostic and work anywhere the file-based protocol already works.

Shared pieces:

- `skill/scripts/current-task.sh`
- `skill/scripts/check-task-drift.sh`
- `skill/scripts/task_guard.py`

The wrappers stay shell-friendly. The Python core owns the selection logic and drift heuristics so Claude Code, OpenCode, and Codex can reuse one contract.

## Current-task contract

`current-task.sh` resolves the task the same way the workflow already does:

1. explicit `--task <slug>`
2. `PLAN_TASK`
3. `.planning/.active_task`
4. latest auto-selectable task

P0 outputs:

- human-readable summary by default
- `--compact` for shell prompt, tmux, or status bar usage
- `--json` for host adapters and plugins

Recommended JSON fields:

- `found`
- `selection_source`
- `workspace_root`
- `plan_root`
- `plan_dir`
- `requested_slug`
- `session_pin`
- `active_pointer`
- `slug`
- `title`
- `status`
- `mode`
- `current_phase`
- `next_action`
- `blockers`
- `active_delegates`

## Drift-check contract

`check-task-drift.sh` compares a candidate prompt with the current task signature.

P0 classifications:

- `related`
- `unclear`
- `likely-unrelated`
- `no-active-task`
- `empty-prompt`

P0 input sources:

- `--prompt "..."`
- stdin

P0 decision rules:

- short follow-up prompts like `continue`, `按上面的改`, or `刚才那个` should pass as `related`
- explicit switch cues like `另外`, `顺便`, `new task`, or `separately` should bias toward `likely-unrelated`
- low-overlap prompts without strong switch evidence should stay `unclear`
- P0 should remind only; adapters decide how to surface that reminder

Recommended JSON fields:

- `classification`
- `recommendation`
- `matched_terms`
- `switch_cues`
- `complex_prompt`
- `followup_prompt`
- `task`

## Capability matrix

| Host | Current task visibility | Prompt drift reminder | Tool-time reminder | P0 path | Confidence |
|------|-------------------------|-----------------------|--------------------|---------|------------|
| Claude Code | `current-task.sh` in shell or tmux now; `statusLine` can also render the active task natively | `UserPromptSubmit` can call the shared checker | `PreToolUse` can reuse the same result or re-check tool text | shared core + Claude hooks + `claude-hooks/scripts/statusline.py` | high |
| OpenCode | `current-task.sh` in shell or tmux now; plugin can also inject current task summary, prefix the session title, and show a toast | plugin can call the shared checker on chat messages | plugin can warn before `Task` and pin shell commands with `PLAN_TASK` | shared core + `skill/opencode-plugin/task-focus-guard.js` | medium |
| Codex | `current-task.sh` in shell or tmux now | best-effort reminder through skill text, docs, and future metadata | none in P0 | shared core + skill-level policy | medium-low |

## Rollout

### P0

- ship `current-task.sh`
- ship `check-task-drift.sh`
- keep reminders advisory only
- document the capability matrix and JSON contract

### P1

- tune the Claude hook wording and false-positive rate
- iterate on the OpenCode plugin adapter from real usage feedback
- add optional task focus terms or routing hints if false positives stay high

### P2

- explore host-native UI surfaces where they exist
- consider stricter modes only after dogfooding proves the reminders are accurate enough

## Why this shape

The canonical truth remains `.planning/<slug>/`. The guard is not a smart router; it is a lightweight safety rail that makes the active task visible and nudges the agent to confirm before silently mixing unrelated work into the same planning lane.

For OpenCode specifically, the current plugin SDK appears to support hooks, session title updates, and TUI toasts, but not a dedicated custom sidebar or statusbar widget surface. The plugin therefore uses the session title as the closest sidebar-visible fallback.
