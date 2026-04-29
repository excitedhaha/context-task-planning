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

The wrappers stay shell-friendly. The Python core owns the selection logic and drift heuristics so Claude Code, OpenCode, Codex, and TraeCLI/Coco can reuse one contract.

For the deeper architecture behind session bindings, repo scope, and worktree-aware routing, see `docs/design.md`.

## Current-task contract

`current-task.sh` resolves the task the same way the workflow already does:

1. explicit `--task <slug>`
2. `PLAN_TASK`
3. session binding selected by `PLAN_SESSION_KEY`
4. `.planning/.active_task`
5. latest auto-selectable task

For host adapters, resolution and visible binding are related but not identical:

- `session_binding` is the only strong per-session binding source
- `.planning/.active_task` is the shared `workspace-default` fallback
- `latest` is a recovery/default guess and should not be surfaced like an explicit binding

P0 outputs:

- human-readable summary by default, including the recommended next step
- `--compact` for shell prompt, tmux, or status bar usage
- `--json` for host adapters and plugins

Recommended JSON fields:

- `found`
- `selection_source`
- `workspace_root`
- `plan_root`
- `plan_dir`
- `requested_slug`
- `session_key`
- `session_binding`
- `binding_role`
- `session_pin`
- `active_pointer`
- `writer_display`
- `observer_count`
- `primary_repo`
- `repo_scope`
- `repo_bindings`
- `repo_summary`
- `slug`
- `title`
- `status`
- `mode`
- `current_phase`
- `next_action`
- `blockers`
- `active_delegates`
- `recommended_action`
- `recommended_reason`
- `recommended_commands`
- `resume_candidates`

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
| Claude Code | `current-task.sh` in shell or tmux now; optional `statusLine` fallback can also render the active task natively | plugin or manual `UserPromptSubmit` hooks can call the shared checker | plugin or manual `PreToolUse` hooks can reuse the same result or re-check tool text | shared core + Claude plugin hooks + optional `claude-hooks/scripts/statusline.py` | high |
| OpenCode | `current-task.sh` in shell or tmux now; plugin can also inject current task summary, prefix the session title only for explicit session bindings, show a toast, and run best-effort compact sync when visible session events mention compact/compression | plugin can call the shared checker on chat messages | plugin can warn before `Task`, bind shell commands to the OpenCode session with `PLAN_SESSION_KEY`, and reuse the shared compact-sync helper on compact-like events | shared core + `skill/opencode-plugin/task-focus-guard.js` (quiet outside repos that already use `.planning/`) | medium |
| Codex | `current-task.sh` in shell or tmux now; optional hooks can inject task context but cannot render a native status cue | `UserPromptSubmit` can inject the shared task and drift context on every turn | `PostToolUse` records planning evidence and `Stop` can continue once to request planning sync; `PreToolUse` is not used for context injection | shared core + `skill/codex-hooks` + shell fallback | medium |
| TraeCLI/Coco | `current-task.sh` in shell or tmux now; plugin commands expose `/context-task-planning:task-current` and hooks inject task context but do not render a native status cue | plugin `user_prompt_submit` hook injects shared task and drift context | plugin `pre_tool_use` adds task/tool reminders, `post_tool_use` records planning evidence, and `stop` can continue once to request planning sync | shared core + `coco.yaml` + `skill/trae-hooks` + shell fallback | medium |

The guard consumes session, role, repo, and checkout context from the shared resolver, but the full concurrency and workspace model lives in `docs/design.md` rather than in this guard-specific note.

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
