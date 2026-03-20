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

- use `context-task-planning` for the task
- create or resume the task under `.planning/<slug>/`
- recover from `.planning/` after context loss
- create delegate lanes for bounded discovery, review, or verify subproblems

Example prompts:

```text
Use context-task-planning for this task. Create or resume the task workspace, keep the hot context current, and verify before wrapping up.
```

```text
I lost context. Recover the active task from .planning/ and continue from next_action.
```

```text
Use context-task-planning and create a delegate lane to review the risky parts of this diff. Promote only the distilled findings.
```

If Codex does not pick the skill automatically, mention the skill name explicitly or fall back to the scripts.

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
- `sh skill/scripts/validate-task.sh`
- `sh skill/scripts/prepare-delegate.sh --kind discovery "Map auth entry points"`
