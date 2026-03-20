# Codex Notes

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

## Usage

Use the skill when work is large enough that normal context retention is not reliable.

Most teammates should start with normal conversation, not with shell scripts.

Good asks for Codex:

- describe the real task in normal language
- mention when the work is multi-step, long-running, or likely to be resumed later
- expect Codex to create or resume the task under `.planning/<slug>/` when needed
- ask for bounded discovery, review, or verify subproblems when they should stay isolated

Example prompts:

```text
Refactor the auth flow across backend and frontend. This will take multiple steps, may get interrupted, and should be verified before you wrap up.
```

```text
I lost context. Recover the active task from .planning/ and continue from next_action.
```

```text
Review the risky parts of this diff. Keep the main task focused, and if you need a bounded side investigation, promote only the distilled findings back.
```

For multi-step or recovery-sensitive work, Codex should usually pick the skill automatically. If it does not, mention `context-task-planning` explicitly or fall back to the scripts.

## What users should notice

Codex does not currently have a bundled native task UI adapter like Claude Code's status line or OpenCode's plugin.

So the intended fallback is:

- keep the active task visible with `sh skill/scripts/current-task.sh --compact` in your shell prompt, tmux status line, or a quick manual check
- use `sh skill/scripts/check-task-drift.sh --prompt "..." --json` when a new request may be a different task
- expect Codex to ask whether to continue the current task, switch tasks, or create a new task before updating planning state when the request looks mismatched

If you want to force that behavior in a prompt, say it explicitly:

```text
Before mixing this request into the active task, check whether it still fits the current task and ask me whether to continue, switch tasks, or create a new task if it does not.
```

Quick check:

```bash
sh skill/scripts/current-task.sh --compact
```

If that prints `task=<slug> ...`, the fallback visibility path is working.

The portable contract is file-based, so even without host-specific hooks you can recover from:

- long sessions
- model switches
- agent changes

The core recovery sequence is always:

1. `state.json`
2. `task_plan.md`
3. `progress.md`
4. unresolved delegates

## Manual fallback

Useful commands when you want direct control:

- `sh skill/scripts/init-task.sh "Implement auth flow"`
- `sh skill/scripts/current-task.sh --compact`
- `sh skill/scripts/check-task-drift.sh --prompt "Also investigate the billing webhook regression" --json`
- `sh skill/scripts/validate-task.sh`
- `sh skill/scripts/prepare-delegate.sh --kind discovery "Map auth entry points"`
