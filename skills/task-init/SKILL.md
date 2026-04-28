---
name: task-init
description: Initialize a new context-task-planning task for this workspace from a confirmed task title. Use this whenever the user wants to start tracking a new task, create a planning lane, initialize task files, or explicitly invokes /task-init.
allowed-tools: Bash
---

# Task Init

Initialize a new `context-task-planning` task for this workspace using a confirmed task title.

## Requirements

- Expect the main `context-task-planning` skill to be installed alongside this entry skill.
- Treat the invocation argument text as an already-confirmed task title.
- If no task title was provided but the surrounding user request implies a task, infer a concise candidate title, derive the slug that the core `slugify.sh` script would produce, and ask the user to confirm or edit the title before running `init-task.sh`.
- If no task title was provided and there is not enough surrounding request context to infer one, stop and ask the user for a task title.
- Do not create a task from an agent-inferred title until the user confirms it.
- Prefer the installed core skill script at `~/.claude/skills/context-task-planning/scripts/init-task.sh`.
- If that path does not exist but the current workspace contains `skill/scripts/init-task.sh`, use the repo-local path instead.
- Run the command from the current workspace.
- If the dirty-worktree guard asks for a decision, stop and ask the user instead of choosing `--stash` or `--allow-dirty` yourself.
- After the command succeeds, summarize the created task slug and the next action.

## Run

```bash
sh ~/.claude/skills/context-task-planning/scripts/init-task.sh "<confirmed task title>"
```
