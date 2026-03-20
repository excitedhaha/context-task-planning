# OpenCode Notes

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

## Usage

This skill is designed so that OpenCode does not need host-specific session parsing in order to recover context.

Most teammates should use it through normal conversation with the agent.

Good asks for OpenCode:

- use `context-task-planning` for the task
- create or resume the task under `.planning/<slug>/`
- recover from `.planning/` after context loss
- create delegate lanes for bounded discovery, review, or verify side quests

Example prompts:

```text
Use context-task-planning for this implementation. Create or resume the task, keep the hot context current, and verify before wrapping up.
```

```text
I lost context. Recover the active task from .planning/ and continue from the recorded next_action.
```

```text
Use context-task-planning and create a delegate lane to scan the repo for relevant entry points. Promote only the distilled findings.
```

If OpenCode does not invoke the skill automatically, mention the skill name explicitly or use the scripts directly.

The canonical state is the task folder itself under `.planning/<slug>/`.

If your OpenCode setup uses a custom skill source list, make sure `~/.config/opencode/skills` is enabled.

## Manual fallback

Useful commands when you want direct control:

- `sh skill/scripts/init-task.sh "Implement auth flow"`
- `sh skill/scripts/validate-task.sh`
- `sh skill/scripts/prepare-delegate.sh --kind discovery "Map auth entry points"`
