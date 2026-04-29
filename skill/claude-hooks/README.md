# Claude Hooks

This directory contains an optional Claude Code automation layer for `context-task-planning`.

The core skill remains portable across Claude Code, OpenCode, Codex, and TraeCLI/Coco.
These hooks are Claude-only enhancements for users who want automatic context injection.

When plugin hooks are enabled, Claude Code receives task context on lifecycle events. The native status line remains an optional standalone fallback because Claude Code plugins do not currently distribute the main `statusLine` setting.

## What the hooks do

- optional `statusLine` fallback - show the current task in Claude Code's native status line when configured through settings
- `SessionStart` - recover the current task snapshot from `.planning/<slug>/` for explicit bindings, while workspace fallback stays advisory
- `SessionStart` on `compact` - run a safe compact-time sync, then inject compact recovery context only for explicit bindings
- `UserPromptSubmit` - stay quiet for normal turns and inject route evidence only for high-signal `likely-unrelated` prompts
- `PreToolUse` - run native-`Task` preflight for explicit bindings, with stronger routing guidance when the request is truly mismatched

## What the hooks do not do

- they do not replace the core file protocol
- they do not parse host-specific session history
- they do not auto-write semantic progress updates from session history; compact-time sync only repairs warning-level drift for writers and refreshes the derived compact artifact

## Install

Recommended plugin install:

```bash
claude plugin marketplace add excitedhaha/context-task-planning
claude plugin install context-task-planning@context-task-planning
```

The plugin loads `hooks.json` directly and uses `${CLAUDE_PLUGIN_ROOT}` to locate the bundled scripts.

Manual standalone fallback:

1. Make sure the skill is installed at `~/.claude/skills/context-task-planning`
2. Merge `settings.example.json` into either:
   - `~/.claude/settings.json`
   - `.claude/settings.json`
   - `.claude/settings.local.json`

For first-time testing, project-local `.claude/settings.local.json` is the safest option.

The standalone example config enables both the hooks and the Claude status line. Restart Claude Code after merging it so the status-line command reloads. Do not enable both plugin hooks and these manual hook entries at the same time.
