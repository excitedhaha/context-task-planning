# Codex Notes

This page only covers Codex-specific setup and behavior. Use `README.md` for the first success case and `docs/onboarding.md` for the shared workflow.

## Install

Recommended local plugin install from this repository checkout (skills + hooks bundled):

```bash
git clone https://github.com/excitedhaha/context-task-planning.git
cd context-task-planning
sh skill/scripts/install-codex-plugin.sh
```

This is the project-local install path, not the general Codex marketplace install command. The official plugin entry point is to add an available marketplace, then install or enable the plugin from the Codex app plugin browser or CLI `/plugins`.

The script creates a stable local Codex marketplace wrapper under `~/.codex/context-task-planning-marketplace` and registers `context-task-planning@context-task-planning-local`. Current Codex marketplace descriptors expect plugins under `./plugins/<name>`, so this bare repository root is not enough for direct marketplace registration.

Some Codex builds still expose a non-interactive plugin install command, and the script uses it when available. Current Codex builds may only expose marketplace management in the CLI; after the script finishes, open `/plugins` in Codex or the Codex app plugin browser, then install or enable `context-task-planning@context-task-planning-local`.

Alternative skill-only install:

```bash
npx skills add excitedhaha/context-task-planning -g
```

Choose `context-task-planning` and the Codex agent when prompted.

A global install makes the skill available under:

```text
~/.codex/skills/context-task-planning
```

## What Codex relies on

Codex now has lifecycle hooks, so the recommended path is:

- the same shared file-backed core under `.planning/<slug>/`
- optional Codex hooks that inject task context on session start, after compaction recovery, and when native subagents start
- prompt-time route evidence only for high-signal scope switches
- a `Stop` hook that asks Codex to continue once when a complex or mutating turn is about to finish without planning read/update evidence
- shell-first visibility with `sh skill/scripts/current-task.sh` as the fallback and debugging surface

Codex still does not expose the same surfaces as Claude Code or OpenCode:

- no native status line or session-title API for a persistent task cue
- this plugin does not use Codex `PreToolUse` for command rewriting or policy enforcement
- no native subagent prompt mutation equivalent to Claude `Task` or OpenCode `tool.execute.before`; `SubagentStart` injects a concise task guardrail instead
- compaction recovery uses `SessionStart` with the `compact` source; this plugin does not block or rewrite compaction with `PreCompact` / `PostCompact`

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

## Codex hooks

The plugin bundles hooks that enable:

- `SessionStart` - inject explicit task context on startup, resume, clear, or compact recovery
- `UserPromptSubmit` - record turn markers and inject route evidence only for high-signal `likely-unrelated` prompts
- `SubagentStart` - inject a concise current-task guardrail into native Codex subagents
- `PostToolUse` - track whether this turn read planning files, used mutating tools, or updated planning files
- `Stop` - continue once if Codex is about to finish without the required planning read or update

The injected task context can also include a shared context-prune hint when `progress.md` is large enough to summarize and prune manually.

Codex hooks use the canonical `hooks` configuration surface. Some Codex builds still list the deprecated `codex_hooks` feature key in `codex features list`; either `hooks` or `codex_hooks` indicates hook support.

Quick verification after plugin install:

```bash
codex --version
codex features list | grep -E '^(hooks|codex_hooks|plugins)\b'
codex exec "Do not modify files or run commands. Reply exactly: OK"
```

The last command should return `OK` without hook trust or plugin manifest errors. Depending on Codex UI/CLI mode, hook completion may appear in `/hooks` or persisted hook trust state rather than in `codex exec` stdout. A native subagent smoke run with `--json` should show `spawn_agent` / `wait` / `close_agent` events and no `context-task-planning` manifest warnings.

Plugin-bundled hooks are reviewed by hash. After upgrading this plugin, open `/hooks` in Codex and trust the changed hook definitions before expecting them to run.

Contributor/package verification from a checkout:

```bash
sh skill/scripts/smoke-test-codex-plugin.sh
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

- there is still no native Codex task UI today
- with hooks enabled, session start and compact recovery should receive task context, while normal new turns stay quiet unless route evidence is high-signal
- native subagents should receive a concise task guardrail when the Codex session is explicitly bound to a planning task
- after a code-changing turn, Codex may automatically continue once to update or explicitly justify not updating planning files
- `current-task.sh` should show the resolved task, access mode, repo/worktree summary, and a recommended next step
- `current-task.sh` can also show one linked spec ref, or a few candidate refs when the runtime refuses to guess
- treat that spec line as scoping help; only use the manual override path when the work really needs one authoritative ref
- `current-task.sh --compact` should still show the resolved task in prompt-friendly form
- `check-task-drift.sh` should provide heuristic route evidence when a new ask may be a different task
- the same task should still resolve from a registered repo path or recorded `.worktrees/...` checkout inside a parent workspace

If that quick check prints `task=<slug> ...`, the fallback visibility path is working.

## Shell-first Task preflight

Codex hooks now provide `SubagentStart` context injection, but they still do not rewrite native subagent prompts. Two explicit preflight approaches remain useful when you want the full prompt prefix or delegate decision before launch:

### Option A: Custom agent with preflight awareness

Copy the `context-aware-worker.toml` agent definition to your project or user config:

```bash
# Project-scoped
cp skill/codex-hooks/agents/context-aware-worker.toml .codex/agents/
# User-scoped
cp skill/codex-hooks/agents/context-aware-worker.toml ~/.codex/agents/
```

Then tell Codex: "Use the context-aware-worker agent to investigate the auth module."

The agent's `developer_instructions` tell it to run `subagent-preflight.sh` before starting and follow the routing guidance. This complements the plugin's automatic `SubagentStart` guardrail when a full preflight decision is useful.

### Option B: Manual preflight invocation

Use the shared helper directly when you launch native subagents manually or through a wrapper:

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
- `sh skill/scripts/check-task-drift.sh --prompt "Also investigate the billing webhook regression" --json`
- `sh skill/scripts/subagent-preflight.sh --cwd "$PWD" --host codex --tool-name Task --task-text "Investigate auth entry points" --json`
- `sh skill/scripts/validate-task.sh`
- `sh skill/scripts/validate-task.sh --fix-warnings`
- `sh skill/scripts/set-task-spec-context.sh --task <slug> --ref <spec-ref>`
- `sh skill/scripts/prepare-delegate.sh --kind discovery "Map auth entry points"`

Keep `current-task.sh --compact` for prompt-sized status. Use `set-task-spec-context.sh` only when implementation needs one authoritative spec ref; if the summary only shows a few candidates during exploration, you can usually keep going without resolving them yet.

For the shared progression from first success to multi-session and multi-repo usage, go back to `docs/onboarding.md`. For the deeper architecture behind session bindings, repo scope, and worktree attachment, use `docs/design.md`.
