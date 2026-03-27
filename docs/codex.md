# Codex Notes

This page only covers Codex-specific setup and behavior. Use `README.md` for the first success case and `docs/onboarding.md` for the shared workflow.

## Install

Recommended install:

```bash
npx skills add excitedhaha/context-task-planning -g
```

Choose `context-task-planning` and the Codex agent when prompted.

Local fallback while developing from a clone:

```bash
sh skill/scripts/install-macos.sh
```

A global install makes the skill available under:

```text
~/.codex/skills/context-task-planning
```

## What Codex relies on

Codex does not currently have a bundled native task UI adapter like Claude Code's status line or OpenCode's plugin.

So the intended Codex path is the shared file-backed core plus shell-first visibility:

- keep the active task visible with `sh skill/scripts/current-task.sh` when you want the full summary and next step, or `sh skill/scripts/current-task.sh --compact` when you only need a short cue
- use `sh skill/scripts/check-task-drift.sh --prompt "..." --json` when a new request may be a different task
- use `sh skill/scripts/subagent-preflight.sh --task-text "..." --text` before manual or wrapper-driven native subagent launches when you want the same routing and repo/worktree context as Claude or OpenCode
- expect Codex to ask whether to continue the current task, switch tasks, or create a new task before updating planning state when the match looks wrong
- use `PLAN_SESSION_KEY` when multiple Codex shells or wrappers should keep different current tasks
- rely on the same parent-workspace repo registration and recorded worktree rules as the other hosts

## Recommended Codex setup

If you keep several Codex threads open in one repository, give each shell or wrapper a different `PLAN_SESSION_KEY`, then bind the session explicitly:

```bash
export PLAN_SESSION_KEY=manual:feature-auth
sh skill/scripts/set-active-task.sh feature-auth
```

Use observe mode when a second thread should watch the same task without becoming a second writer:

```bash
sh skill/scripts/set-active-task.sh --observe feature-auth
```

If you want the current task visible all the time, put this in your shell prompt, tmux status line, or a quick manual check:

```bash
sh skill/scripts/current-task.sh --compact
```

If you want the shell to answer "what should I do next?" instead of only "what task is active?", use:

```bash
sh skill/scripts/current-task.sh
```

## What you should notice

- there is no bundled native Codex task UI today
- `current-task.sh` should show the resolved task, access mode, repo/worktree summary, and a recommended next step
- `current-task.sh --compact` should still show the resolved task in prompt-friendly form
- `check-task-drift.sh` should help when a new ask may be a different task
- the same task should still resolve from a registered repo path or recorded `.worktrees/...` checkout inside a parent workspace

If that quick check prints `task=<slug> ...`, the fallback visibility path is working.

## Shell-first Task preflight

Codex has no native interception surface in this first pass, so use the shared helper directly when you launch native subagents manually or through a wrapper:

```bash
sh skill/scripts/subagent-preflight.sh \
  --cwd "$PWD" \
  --host codex \
  --tool-name Task \
  --task-text "Investigate the auth entry points across repos" \
  --text
```

Use `--json` instead of `--text` when a wrapper wants the structured decision. The decisions match the other hosts:

- `payload_only` / `payload_plus_delegate_recommended` - include the canonical prompt prefix in the Task input
- `routing_only` - stop and confirm routing instead of injecting repo/worktree context
- `delegate_required` - create or reuse a delegate lane first, then launch the bounded side work from there

## Manual fallback

Useful commands when you want direct control:

- `sh skill/scripts/init-task.sh "Implement auth flow"`
- `sh skill/scripts/current-task.sh`
- `sh skill/scripts/current-task.sh --compact`
- `sh skill/scripts/compact-context.sh`
- `sh skill/scripts/check-task-drift.sh --prompt "Also investigate the billing webhook regression" --json`
- `sh skill/scripts/subagent-preflight.sh --cwd "$PWD" --host codex --tool-name Task --task-text "Investigate auth entry points" --json`
- `sh skill/scripts/validate-task.sh`
- `sh skill/scripts/validate-task.sh --fix-warnings`
- `sh skill/scripts/prepare-delegate.sh --kind discovery "Map auth entry points"`

Keep `current-task.sh --compact` for prompt-sized status. Use `compact-context.sh` when you want the richer derived recovery view for a larger task. `validate-task.sh --fix-warnings` also refreshes stale derived compact artifacts when needed.

For the shared progression from first success to multi-session and multi-repo usage, go back to `docs/onboarding.md`. For the deeper architecture behind session bindings, repo scope, and worktree attachment, use `docs/design.md`.
