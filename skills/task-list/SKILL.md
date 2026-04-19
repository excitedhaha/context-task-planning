---
name: task-list
description: List the existing context-task-planning tasks in this workspace and summarize the active pointer plus the most relevant tasks. Use this whenever the user asks what tasks exist, what they can resume, wants a task list, or explicitly invokes /task-list.
allowed-tools: Bash
---

# Task List

List the existing `context-task-planning` tasks for this workspace.

## Requirements

- Expect the main `context-task-planning` skill to be installed alongside this entry skill.
- Prefer the installed core skill script at `~/.claude/skills/context-task-planning/scripts/list-tasks.sh`.
- If that path does not exist but the current workspace contains `skill/scripts/list-tasks.sh`, use the repo-local path instead.
- Run the command from the current workspace.
- Do not modify task state.
- After the command succeeds, summarize the active task pointer and the most relevant tasks from the output.

## Run

```bash
sh ~/.claude/skills/context-task-planning/scripts/list-tasks.sh
```
