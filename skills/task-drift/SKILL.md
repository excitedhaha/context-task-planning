---
name: task-drift
description: Check whether a new request still fits the current context-task-planning task and summarize the routing recommendation. Use this whenever the user asks whether a new ask belongs in the same task, wants a drift check, is about to switch scope, or explicitly invokes /task-drift.
allowed-tools: Bash
---

# Task Drift

Check whether a new request still fits the current `context-task-planning` task.

## Requirements

- Expect the main `context-task-planning` skill to be installed alongside this entry skill.
- Treat the invocation argument text as the candidate new request.
- If no request text was provided, stop and ask the user to provide the request they want to compare against the current task.
- Prefer the installed core skill script at `~/.claude/skills/context-task-planning/scripts/check-task-drift.sh`.
- If that path does not exist but the current workspace contains `skill/scripts/check-task-drift.sh`, use the repo-local path instead.
- Run the command from the current workspace.
- After the command succeeds, summarize whether the request still fits the current task and mention any routing recommendation.

## Run

```bash
sh ~/.claude/skills/context-task-planning/scripts/check-task-drift.sh --prompt "<new request>" --json
```
