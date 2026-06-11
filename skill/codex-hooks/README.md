# Codex Hooks

This directory contains the Codex automation layer for `context-task-planning`.

The core skill remains shell-first and file-backed. These hooks only adapt Codex's lifecycle events to the shared scripts and `.planning/<slug>/` state.

## What The Hooks Do

- `SessionStart` - inject the current task snapshot for explicit Codex session bindings; fallback-only task resolution stays advisory
- `UserPromptSubmit` - record turn markers and inject route evidence only for high-signal `likely-unrelated` prompts
- `SubagentStart` - inject a concise current-task guardrail into native Codex subagents
- `PostToolUse` - record lightweight per-turn evidence that Codex read planning files, changed tools, or updated planning files
- `Stop` - if a complex or mutating turn is about to finish without the needed planning read/update evidence, ask Codex to continue once and sync planning first

## What The Hooks Do Not Do

- they do not provide a Codex status line or session title surface
- they do not mutate Codex tool inputs or native subagent prompts
- they do not use `PermissionRequest`, `PreToolUse`, `PreCompact`, or `PostCompact`
- they do not infer semantic progress from transcript history
- they do not replace the shared shell scripts or durable `.planning/` files

## Install

These hooks are bundled with the Codex plugin. Install the plugin:

```bash
git clone https://github.com/excitedhaha/context-task-planning.git
cd context-task-planning
sh skill/scripts/install-codex-plugin.sh
```

Make sure `codex --version` is a build that exposes `hooks` in `codex features list`; `codex_hooks` is the deprecated feature-key alias.

After plugin installation or upgrade, open `/hooks` in Codex and trust the plugin-bundled hooks if prompted. `codex exec "Do not modify files or run commands. Reply exactly: OK"` should return `OK` without hook trust or plugin manifest errors. Depending on Codex UI/CLI mode, hook completion may appear in `/hooks` or persisted hook trust state rather than in `codex exec` stdout.
