# Codex Hooks

This directory contains an optional Codex automation layer for `context-task-planning`.

The core skill remains shell-first and file-backed. These hooks only adapt Codex's lifecycle events to the shared scripts and `.planning/<slug>/` state.

## What The Hooks Do

- `SessionStart` - inject the current task snapshot for explicit Codex session bindings; fallback-only task resolution stays advisory
- `UserPromptSubmit` - re-inject task context and drift reminders on every user turn, with a long-context reminder to read and update planning files
- `PostToolUse` - record lightweight per-turn evidence that Codex read planning files, changed tools, or updated planning files
- `Stop` - if a complex or mutating turn is about to finish without the needed planning read/update evidence, ask Codex to continue once and sync planning first

## What The Hooks Do Not Do

- they do not provide a Codex status line or session title surface
- they do not mutate Codex tool inputs or native subagent prompts
- they do not infer semantic progress from transcript history
- they do not replace the shared shell scripts or durable `.planning/` files

## Install

1. Make sure `codex --version` is a build that exposes `codex_hooks` in `codex features list`; `codex-cli 0.125.0` is verified.
2. Make sure the skill is installed at `~/.codex/skills/context-task-planning`.
3. Prefer the packaged hook install:

```bash
npx codex-marketplace add excitedhaha/context-task-planning/hooks/context-task-planning --hook --global
```

Use `--project` from a repository for a trusted project-local install.

Manual fallback: merge `config.example.toml` into either:

- `~/.codex/config.toml`
- `.codex/config.toml`

For first-time testing, user-level hooks are usually simpler. Project-local `.codex/` hooks only load after Codex trusts the project.

Codex hooks are behind the `codex_hooks` feature flag, so keep this line when merging the example:

```toml
[features]
codex_hooks = true
```

After enabling hooks, `codex exec "Do not modify files or run commands. Reply exactly: OK"` should report `SessionStart Completed`, `UserPromptSubmit Completed`, and `Stop Completed`. A turn that runs a shell command should also report `PostToolUse Completed`.
