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

Codex now has lifecycle hooks, so the recommended path is:

- the same shared file-backed core under `.planning/<slug>/`
- optional Codex hooks that inject task context on session start and every user prompt
- a `Stop` hook that asks Codex to continue once when a complex or mutating turn is about to finish without planning read/update evidence
- shell-first visibility with `sh skill/scripts/current-task.sh` as the fallback and debugging surface

Codex still does not expose the same surfaces as Claude Code or OpenCode:

- no native status line or session-title API for a persistent task cue
- no supported `PreToolUse` context injection or tool input rewrite path
- no automatic native subagent prompt mutation equivalent to Claude `Task` or OpenCode `tool.execute.before`
- no dedicated compact hook; recovery happens on the next `SessionStart`, `UserPromptSubmit`, or `Stop` check

Use the hooks for long-context reminders and end-of-turn planning sync. Keep the shell scripts as the source of truth and as the manual escape hatch.

## Recommended Codex setup

If you keep several Codex threads open in one repository, give each shell or wrapper a different `PLAN_SESSION_KEY`, then bind the session explicitly:

```bash
export PLAN_SESSION_KEY=manual:feature-auth
sh skill/scripts/set-active-task.sh feature-auth
```

The Codex hooks use `PLAN_SESSION_KEY` when it is exported before Codex starts. If it is not set, they derive a key from Codex's `session_id`; shell commands that do not receive that key still update the workspace fallback pointer rather than an explicit Codex session binding.

Use observe mode when a second thread should watch the same task without becoming a second writer:

```bash
sh skill/scripts/set-active-task.sh --observe feature-auth
```

## Optional Codex hooks

Codex hooks require a Codex CLI build that lists `codex_hooks` in `codex features list`; this workflow has been verified with `codex-cli 0.125.0`. After installing the skill, merge this file into either `~/.codex/config.toml` or a trusted project `.codex/config.toml`:

```text
skill/codex-hooks/config.example.toml
```

The example enables:

- `SessionStart` - inject explicit task context on startup, resume, or clear
- `UserPromptSubmit` - inject task context, drift reminders, delegate hints, and long-context planning guidance on every user prompt
- `PostToolUse` - track whether this turn read planning files, used mutating tools, or updated planning files
- `Stop` - continue once if Codex is about to finish without the required planning read or update

The scripts emit Codex hook JSON with `hookSpecificOutput.additionalContext` for prompt-visible context. This avoids Codex treating bracket-prefixed plain text such as `[context-task-planning] ...` as malformed JSON-like output.

Codex project-local hooks only load after the project `.codex/` layer is trusted. User-level hooks in `~/.codex/config.toml` are simpler for first-time testing.

Quick verification after enabling hooks:

```bash
codex --version
codex features list | grep codex_hooks
codex exec "Do not modify files or run commands. Reply exactly: OK"
```

The last command should show `SessionStart Completed`, `UserPromptSubmit Completed`, and `Stop Completed`. If the prompt asks Codex to run a shell command, `PostToolUse Completed` should also appear.

If you want the current task visible all the time, put this in your shell prompt, tmux status line, or a quick manual check:

```bash
sh skill/scripts/current-task.sh --compact
```

If you want the shell to answer "what should I do next?" instead of only "what task is active?", use:

```bash
sh skill/scripts/current-task.sh
```

## What you should notice

- there is still no native Codex task UI today
- with hooks enabled, new turns should receive a planning reminder without you manually pasting one
- after a code-changing turn, Codex may automatically continue once to update or explicitly justify not updating planning files
- `current-task.sh` should show the resolved task, access mode, repo/worktree summary, and a recommended next step
- `current-task.sh` can also show one linked spec ref, or a few candidate refs when the runtime refuses to guess
- treat that spec line as scoping help; only use the manual override path when the work really needs one authoritative ref
- `current-task.sh --compact` should still show the resolved task in prompt-friendly form
- `check-task-drift.sh` should help when a new ask may be a different task
- the same task should still resolve from a registered repo path or recorded `.worktrees/...` checkout inside a parent workspace

If that quick check prints `task=<slug> ...`, the fallback visibility path is working.

## Shell-first Task preflight

Codex hooks currently do not provide a reliable native subagent prompt mutation path. Use the shared helper directly when you launch native subagents manually or through a wrapper:

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

When the shared core auto-links a clear OpenSpec artifact, the preflight text and JSON now include that spec context so Codex-side wrappers can keep native subagents scoped to the same external change or spec. When the runtime reports `status=ambiguous`, the same preflight payload now includes candidate refs plus the explicit manual-override hint so wrappers can preserve the "do not guess" behavior. Treat that as routing help first; exploratory work can usually continue without resolving candidates up front.

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
- `sh skill/scripts/set-task-spec-context.sh --task <slug> --ref <spec-ref>`
- `sh skill/scripts/prepare-delegate.sh --kind discovery "Map auth entry points"`

Keep `current-task.sh --compact` for prompt-sized status. Use `compact-context.sh` when you want the richer derived recovery view for a larger task. `validate-task.sh --fix-warnings` also refreshes stale derived compact artifacts when needed. Use `set-task-spec-context.sh` only when implementation needs one authoritative spec ref; if the summary only shows a few candidates during exploration, you can usually keep going without resolving them yet.

For the shared progression from first success to multi-session and multi-repo usage, go back to `docs/onboarding.md`. For the deeper architecture behind session bindings, repo scope, and worktree attachment, use `docs/design.md`.
