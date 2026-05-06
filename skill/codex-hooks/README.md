# Codex Hooks

This directory contains the Codex automation layer for `context-task-planning`.

The core skill remains shell-first and file-backed. These hooks only adapt Codex's lifecycle events to the shared scripts and `.planning/<slug>/` state.

## What The Hooks Do

- `SessionStart` - inject the current task snapshot for explicit Codex session bindings; fallback-only task resolution stays advisory
- `UserPromptSubmit` - record turn markers and inject route evidence only for high-signal `likely-unrelated` prompts
- `PostToolUse` - record lightweight per-turn evidence that Codex read planning files, changed tools, or updated planning files
- `Stop` - if a complex or mutating turn is about to finish without the needed planning read/update evidence, ask Codex to continue once and sync planning first

## What The Hooks Do Not Do

- they do not provide a Codex status line or session title surface
- they do not mutate Codex tool inputs or native subagent prompts
- they do not infer semantic progress from transcript history
- they do not replace the shared shell scripts or durable `.planning/` files

## Install

These hooks are bundled with the Codex plugin. Install the plugin:

```bash
codex plugin marketplace add excitedhaha/context-task-planning
codex plugin install context-task-planning@context-task-planning
```

Make sure `codex --version` is a build that exposes `codex_hooks` in `codex features list`; `codex-cli 0.125.0` is verified.

After plugin installation, `codex exec "Do not modify files or run commands. Reply exactly: OK"` should report `SessionStart Completed`, `UserPromptSubmit Completed`, and `Stop Completed`. A turn that runs a shell command should also report `PostToolUse Completed`.
