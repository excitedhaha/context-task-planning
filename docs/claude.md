# Claude Code Notes

This page only covers Claude-specific setup and behavior. Use `README.md` for the first success case and `docs/onboarding.md` for the shared workflow.

## Install

Recommended install:

```bash
claude plugin marketplace add excitedhaha/context-task-planning
claude plugin install context-task-planning@context-task-planning
```

Then run `/reload-plugins` or restart Claude Code. The plugin bundles the main `context-task-planning` skill, the `task-*` entry skills, and the Claude lifecycle hooks.

Local fallback while developing from a clone:

```bash
claude --plugin-dir .
```

Standalone skill fallback:

```bash
npx skills add excitedhaha/context-task-planning -g
```

Choose `context-task-planning`, the Claude Code agent, and any bundled `task-*` entry skills you want when prompted.

Local symlink fallback while developing from a clone:

```bash
sh skill/scripts/install-macos.sh
```

That local installer links the main `context-task-planning` skill plus the bundled `task-*` Claude entry skills into `~/.claude/skills/`. It does not install the Claude plugin.

A global install keeps the main skill under:

```text
~/.claude/skills/context-task-planning
```

Any selected bundled `task-*` entry skills are installed as sibling directories under `~/.claude/skills/`.

## What Claude adds

After you enable the plugin or standalone adapter, Claude Code can surface the shared file-backed task state through:

- optional native status line cues such as `task!:<slug>`, `obs:<slug>`, or `wksp:<slug>` when you enable the status-line fallback
- strong task-context recovery on session start for explicit bindings or `PLAN_TASK`, while workspace fallback stays advisory
- safe compact-time sync before Claude compresses context: writer sessions may repair warning-level snapshot drift and refresh `.derived/context_compact.json`, while observer sessions only refresh the derived compact artifact
- prompt-time route evidence only for high-signal `likely-unrelated` prompts; normal and heuristic-`unclear` prompts stay quiet so Claude can use conversation context
- stronger routing guidance before native `Task` launches when the fit is truly mismatched
- shared `subagent-preflight` context before native `Task` launches, including repo/worktree prefixes for related or heuristic-unclear work and routing or delegate escalation when the fit is wrong for explicitly bound sessions; fallback-only sessions stay routing-only
- linked or ambiguous spec context such as auto-detected OpenSpec refs in startup and native-`Task` preflight context when the current task has a clear external artifact candidate or multiple plausible ones, including a short candidate hint when the runtime refuses to guess
- repo context such as `primary_repo` and `repo_scope` when a task spans multiple repos

## Enable the Claude adapter

Recommended: install the Claude Code plugin. Its `skill/claude-hooks/hooks.json` is loaded as plugin hooks and does not require hand-merging hook settings.

Manual standalone fallback:

1. Install the skill with `npx skills add` or the local script.
2. Merge `skill/claude-hooks/settings.example.json` into one of:

- `~/.claude/settings.json`
- `.claude/settings.local.json`

For first-time testing, `.claude/settings.local.json` is the safest option.

The standalone fallback config includes both hooks and `statusLine`, so copying it is enough to enable the visible task cue. Do not enable both plugin hooks and the manual hook entries at the same time, or Claude will receive duplicate reminders.

## Bundled task skills

Claude Code now also supports bundled thin task-entry skills for the same high-frequency flows that OpenCode exposes as slash commands. Plugin installs expose these under the plugin namespace, for example `/context-task-planning:task-current`; standalone skill installs expose `/task-current` directly:

- `task-init <task title>` - create a tracked task from a confirmed title and a final task slug, previewing both when the task is inferred
- `task-current` - inspect the current task and next action
- `task-list` - list existing tasks in the workspace
- `task-validate` - validate the current task without auto-fixing warnings
- `task-drift <new request>` - check whether a new ask still fits the current task
- `task-done [slug]` - mark the current or named task done after verification

These are implemented as skills, not a separate Claude `commands/` directory. They stay thin on purpose and reuse the same shared shell scripts under `skill/scripts/`.

## What you should notice

After restarting Claude Code, you should see:

- automatic strong task-context recovery when the session starts for explicit bindings; fallback-only sessions get a short advisory instead of the full task snapshot
- on context compaction, Claude refreshes compact recovery context from the shared helper for explicit bindings instead of replaying only the shorter session-start snapshot; fallback-only sessions do not inherit compact recovery payloads
- internal route evidence for Claude when a prompt has strong switch signals, without drift toasts or repeated task summaries on ordinary turns
- the same task still resolving when Claude starts inside a registered repo path or recorded worktree under a parent workspace
- startup and native-`Task` preflight summaries can mention one linked spec ref, or a few candidate refs when the runtime refuses to guess
- treat that spec line as scoping help, not as extra setup; only use the manual override path if the work really needs one authoritative ref

If you also enabled the optional status-line fallback, you should see an explicit task cue in the native status line for per-session bindings, or a weaker workspace fallback cue when only `.planning/.active_task` is set.

Sample illustration:

![Claude Code status line sample](assets/claude-statusline-sample.svg)

This is a sample illustration of the expected task cue, not a live screenshot from your machine.

## Task preflight

Claude's `PreToolUse` hook now calls the shared shell-first helper before native `Task` launches:

```bash
sh skill/scripts/subagent-preflight.sh \
  --cwd "$PWD" \
  --host claude \
  --tool-name Task \
  --task-text "Implement the auth migration subagent" \
  --json
```

The helper returns one decision for the launch:

- `payload_only` or `payload_plus_delegate_recommended` - Claude prepends the canonical task and repo/worktree prefix
- `routing_only` - Claude shows routing confirmation only and does not inject the repo/worktree payload
- `delegate_required` - Claude tells you to create or reuse a delegate lane first

If the task resolves a linked OpenSpec context for an explicitly bound session, Claude surfaces that summary at session start, and the injected `Task` preflight prefix includes the same spec context summary and primary linked ref in addition to the repo/worktree scope. When the runtime reports `status=ambiguous`, Claude receives the candidate refs plus an explicit manual-override hint in those recovery or preflight contexts. Treat that as routing help first; exploratory work can usually continue without resolving candidates up front. Workspace fallback alone does not trigger that strong payload.

`UserPromptSubmit` stays quiet for normal turns and only injects route evidence for high-signal switch prompts; the actual native-Task preflight happens in `PreToolUse`.

## If you prefer no hooks

The core skill still works without Claude-specific hooks. You keep the file-backed task workflow, but you lose the native status line, route-evidence hints, and native-`Task` preflight.

Claude's compact hook only does the safe MVP path: it never invents progress from transcript history. For writer sessions it may repair warning-level markdown snapshot drift with `validate-task.sh --fix-warnings`, then it refreshes `.planning/<slug>/.derived/context_compact.json`. For observer sessions it only refreshes the derived compact artifact.

## Manual fallback

Useful shell commands when you want direct control instead of the bundled task-entry skills:

- `sh skill/scripts/init-task.sh "Implement auth flow"`
- `sh skill/scripts/current-task.sh --compact`
- `sh skill/scripts/compact-sync.sh`
- `sh skill/scripts/check-task-drift.sh --prompt "Also investigate the billing webhook regression" --json`
- `sh skill/scripts/subagent-preflight.sh --cwd "$PWD" --host claude --tool-name Task --task-text "Investigate auth entry points" --text`
- `sh skill/scripts/validate-task.sh`
- `sh skill/scripts/set-task-spec-context.sh --task <slug> --ref <spec-ref>`

Use `set-task-spec-context.sh` only when the work really needs one authoritative spec ref. If Claude only shows a few candidate refs during exploration, you can usually keep going without recording a manual override yet.

For the shared progression from first success to multi-session and multi-repo usage, go back to `docs/onboarding.md`. For the deeper architecture behind Claude's task resolution, use `docs/design.md`.
