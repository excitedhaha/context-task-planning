# Claude Hooks

This directory contains an optional Claude Code automation layer for `context-task-planning`.

The core skill remains portable across Claude Code, Codex, and OpenCode.
These hooks are Claude-only enhancements for users who want automatic context injection.

## What the hooks do

- `SessionStart` - recover the current task snapshot from `.planning/<slug>/`
- `UserPromptSubmit` - add planning guidance before Claude handles the prompt
- `PreToolUse` - inject compact task context before key tools run

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
