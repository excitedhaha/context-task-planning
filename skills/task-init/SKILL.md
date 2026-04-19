---
name: task-init
description: Initialize a new context-task-planning task for this workspace from the user's task title. Use this whenever the user wants to start tracking a new task, create a planning lane, initialize task files, or explicitly invokes /task-init.
allowed-tools: Bash
---

# Task Init

Initialize a new `context-task-planning` task for this workspace using the user's argument text as the task title.

## Requirements

- Expect the main `context-task-planning` skill to be installed alongside this entry skill.
- Treat the invocation argument text as the task title.
- If no task title was provided, stop and ask the user for one.
- Prefer the installed core skill script at `~/.claude/skills/context-task-planning/scripts/init-task.sh`.
- If that path does not exist but the current workspace contains `skill/scripts/init-task.sh`, use the repo-local path instead.
- Run the command from the current workspace.
- If the dirty-worktree guard asks for a decision, stop and ask the user instead of choosing `--stash` or `--allow-dirty` yourself.
- After the command succeeds, summarize the created task slug and the next action.

## Run

```bash
sh ~/.claude/skills/context-task-planning/scripts/init-task.sh "<task title>"
```
