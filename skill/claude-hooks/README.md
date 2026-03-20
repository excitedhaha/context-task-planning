# Claude Hooks

This directory contains an optional Claude Code automation layer for `context-task-planning`.

The core skill remains portable across Claude Code, Codex, and OpenCode.
These hooks are Claude-only enhancements for users who want automatic context injection.

When enabled, the most visible cue is Claude Code's native status line showing the active task as `task:<slug>`.

## What the hooks do

- `statusLine` - show the current task in Claude Code's native status line
- `SessionStart` - recover the current task snapshot from `.planning/<slug>/`
- `UserPromptSubmit` - add planning guidance and task-drift reminders before Claude handles the prompt
- `PreToolUse` - inject compact task context before key tools run, with a stronger mismatch warning before `Task`

## What the hooks do not do

- they do not replace the core file protocol
- they do not parse host-specific session history
- they do not auto-update planning files on your behalf

## Install

1. Make sure the skill is installed at `~/.claude/skills/context-task-planning`
2. Merge `settings.example.json` into either:
   - `~/.claude/settings.json`
   - `.claude/settings.json`
   - `.claude/settings.local.json`

For first-time testing, project-local `.claude/settings.local.json` is the safest option.

The bundled example config enables both the hooks and the Claude status line. Restart Claude Code after merging it so the status-line command reloads.
