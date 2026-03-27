# OpenCode Notes

This page only covers OpenCode-specific setup and behavior. Use `README.md` for the first success case and `docs/onboarding.md` for the shared workflow.

## Install

Recommended install:

```bash
npx skills add excitedhaha/context-task-planning -g
```

Choose `context-task-planning` and the OpenCode agent when prompted.

Local fallback while developing from a clone:

```bash
sh skill/scripts/install-macos.sh
```

A global install makes the skill available under:

```text
~/.config/opencode/skills/context-task-planning
```

## What OpenCode adds

The OpenCode plugin is a thin UI layer over the same file-backed task state. Once enabled, it can:

- prefix the session title as `task:<slug> | ...`
- show toasts when the current task is first detected or when drift looks likely
- warn when tracked work happens but `.planning/<slug>/` looks stale
- export `PLAN_SESSION_KEY` so task-aware shell commands bind to the current OpenCode session
- call the shared `subagent-preflight` helper before native `Task` launches and prepend the canonical repo/worktree prefix when the request still fits the current task
- carry repo context for parent-workspace multi-repo tasks
- stay quiet in repositories that do not already use `.planning/`

## Enable the OpenCode plugin

If you installed from a local clone with:

```bash
sh skill/scripts/install-macos.sh
```

the OpenCode plugin is installed automatically by default.

If you installed through `npx skills add`, run the bundled helper once because OpenCode loads skills and plugins from different directories:

```bash
sh ~/.config/opencode/skills/context-task-planning/scripts/install-opencode-plugin.sh
```

You can also run the helper from a local clone:

```bash
sh skill/scripts/install-opencode-plugin.sh
```

Then restart OpenCode.

If you want the skill symlink but not the runtime plugin from the local installer, use:

```bash
sh skill/scripts/install-macos.sh --skip-opencode-plugin
```

## What you should notice

After the plugin is enabled and OpenCode is restarted, you should see:

- the session title prefixed as `task:<slug> | ...`
- an info toast when the current task is first detected
- a warning toast when a prompt looks like likely task drift
- a warning toast when tracked work has happened but planning files look stale
- the first task-creation shell command in a fresh OpenCode session now bootstraps a real session binding instead of falling back to the shared workspace pointer
- the same task still resolving when OpenCode starts inside a registered repo path or recorded worktree under a parent workspace

Sample illustration:

![OpenCode title and toast sample](assets/opencode-title-toast-sample.svg)

This is a sample illustration of the expected title/toast fallback, not a live screenshot from your machine.

## Task preflight

The plugin's `tool.execute.before` hook now calls the same shell-first helper as Claude:

```bash
sh skill/scripts/subagent-preflight.sh \
  --cwd "$PWD" \
  --host opencode \
  --tool-name Task \
  --task-text "Investigate the auth entry points across repos" \
  --json
```

OpenCode keeps freshness reminders separate from the preflight decision:

- `payload_only` or `payload_plus_delegate_recommended` - prepend the canonical task and repo/worktree prefix to the outbound `Task` prompt
- `routing_only` - prepend routing confirmation only
- `delegate_required` - prepend delegate-required guidance instead of treating the native `Task` launch as sufficient

The plugin still keeps title and toast behavior unchanged in this first pass.

## Current limits

- the plugin SDK exposes hooks, session title updates, and TUI toasts, but not a dedicated custom sidebar or status bar widget API
- the plugin is advisory, not a second planner; the model and tools still update `.planning/`
- if you do not see a dedicated sidebar widget, that is expected today

## Manual fallback

Useful commands when you want direct control:

- `sh skill/scripts/init-task.sh "Implement auth flow"`
- `sh skill/scripts/current-task.sh --compact`
- `sh skill/scripts/check-task-drift.sh --prompt "Also investigate the billing webhook regression" --json`
- `sh skill/scripts/subagent-preflight.sh --cwd "$PWD" --host opencode --tool-name Task --task-text "Investigate auth entry points" --text`
- `sh skill/scripts/validate-task.sh`

For the shared progression from first success to multi-session and multi-repo usage, go back to `docs/onboarding.md`. For the deeper architecture behind OpenCode's task resolution and repo/worktree behavior, use `docs/design.md`.
