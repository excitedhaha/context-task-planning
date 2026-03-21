# Claude Code Notes

## Install

Recommended install:

```bash
npx skills add excitedhaha/context-task-planning -g
```

Choose `context-task-planning` and the Claude Code agent when prompted.

Local fallback while developing from a clone:

```bash
sh skill/scripts/install-macos.sh
```

A global install makes the skill available under:

```text
~/.claude/skills/context-task-planning
```

## Recommended usage

Most teammates should talk to Claude, not drive the shell scripts by hand.

Good asks for Claude:

- describe the real task in normal language
- mention when the work is multi-step, long-running, or likely to be resumed later
- expect Claude to create or resume the task under `.planning/<slug>/` when needed
- ask for bounded side investigations when review, discovery, or verify work should stay isolated

Example prompts:

```text
Refactor the auth flow across backend and frontend. This will take multiple steps, may get interrupted, and should be verified before you wrap up.
```

```text
I lost context. Recover the active task from .planning/ and continue from the recorded next_action.
```

```text
Review migration risks for this refactor. Keep the main task focused, and if you need a bounded side investigation, promote only the distilled findings back to the main task.
```

For multi-step or recovery-sensitive work, Claude should usually pick the skill automatically. If it does not, mention `context-task-planning` explicitly. The scripts remain the fallback for explicit control.

## Manual fallback

Useful commands when you want direct control:

- `sh skill/scripts/init-task.sh "Implement auth flow"`
- `sh skill/scripts/validate-task.sh`
- `sh skill/scripts/prepare-delegate.sh --kind review "Review migration risks"`

## Hooks

The core skill still works without hooks. That remains the portability baseline for Codex and OpenCode.

`v0.2.0` now includes an optional Claude-only hook adapter under `skill/claude-hooks/`.

## What users should notice

After enabling the bundled Claude settings and restarting Claude Code, you should see:

- the current task in Claude Code's native status line, usually as `task:<slug>`
- if the session is observe-only, the status line cue changes to `obs:<slug>`
- task context recovered automatically on session start from the current Claude session binding when available, otherwise from the workspace fallback
- when a task declares multiple repos, the injected task context includes `primary_repo` and `repo_scope`
- if Claude starts inside a registered repo path or recorded worktree under a parent workspace, the recovered task still resolves to that shared parent `.planning/` instead of to an unrelated ancestor workspace
- a reminder before Claude silently mixes likely-unrelated work into the current task
- a stronger warning before `Task` launches when the request looks like a different task

Sample illustration:

![Claude Code status line sample](assets/claude-statusline-sample.svg)

This is a sample illustration of the expected task cue, not a live screenshot from your machine.

### Recommended enable path

1. Install the skill with `npx skills add` or the local script.

2. Merge `skill/claude-hooks/settings.example.json` into one of:

- `~/.claude/settings.json`
- `.claude/settings.local.json`

For first-time testing, `.claude/settings.local.json` is the safest option.

The bundled config now includes both hooks and `statusLine`, so copying it is enough to enable the visible task cue.

### Included automation

- `statusLine` - show the current task in Claude Code's native status line
- `SessionStart` - recover the current task snapshot from `.planning/<slug>/`
- `UserPromptSubmit` - inject task context, init-task guidance, and task-drift reminders before Claude handles the prompt
- `PreToolUse` - inject compact task context before key tools run, with a stronger mismatch warning before `Task`

### Conflict note

Do not enable these hooks at the same time as `planning-with-files` hooks or plugin hooks in the same Claude environment. The two systems solve the same problem and will duplicate or fight over planning context.

If the status line does not update right away, restart Claude Code or re-open the session so the new `statusLine.command` is picked up.
