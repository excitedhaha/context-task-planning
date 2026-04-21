# Claude Hooks

This directory contains an optional Claude Code automation layer for `context-task-planning`.

The core skill remains portable across Claude Code, Codex, and OpenCode.
These hooks are Claude-only enhancements for users who want automatic context injection.

When enabled, the most visible cue is Claude Code's native status line showing explicit writer bindings as `task!:<slug>`, explicit observer bindings as `obs:<slug>`, and workspace fallback selection as `wksp:<slug>`.

## What the hooks do

- `statusLine` - show the current task in Claude Code's native status line
- `SessionStart` - recover the current task snapshot from `.planning/<slug>/` for explicit bindings, while workspace fallback stays advisory
- `SessionStart` on `compact` - run a safe compact-time sync, then inject compact recovery context only for explicit bindings
- `UserPromptSubmit` - add planning guidance and task-drift reminders before Claude handles the prompt; fallback-only sessions get advisory routing text instead of the full task snapshot
- `PreToolUse` - inject compact task context before key tools run for explicit bindings, with a stronger mismatch warning before `Task`

## What the hooks do not do

- they do not replace the core file protocol
- they do not parse host-specific session history
- they do not auto-write semantic progress updates from session history; compact-time sync only repairs warning-level drift for writers and refreshes the derived compact artifact

## Install

1. Make sure the skill is installed at `~/.claude/skills/context-task-planning`
2. Merge `settings.example.json` into either:
   - `~/.claude/settings.json`
   - `.claude/settings.json`
   - `.claude/settings.local.json`

For first-time testing, project-local `.claude/settings.local.json` is the safest option.

The bundled example config enables both the hooks and the Claude status line. Restart Claude Code after merging it so the status-line command reloads.
