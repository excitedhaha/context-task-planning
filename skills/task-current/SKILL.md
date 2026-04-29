---
name: task-current
description: Inspect the current context-task-planning task in this workspace and summarize the resolved task, status, and next action. Use this whenever the user asks what task is active, what the next step is, wants a task summary, or explicitly invokes /task-current.
allowed-tools: Bash
---

# Task Current

Show the currently resolved `context-task-planning` task for this workspace.

## Requirements

- Expect the main `context-task-planning` skill to be installed alongside this entry skill.
- If this entry skill is loaded from a Claude Code plugin, prefer the bundled core script at `${CLAUDE_SKILL_DIR}/../../skill/scripts/current-task.sh`.
- Otherwise prefer the standalone core skill script at `~/.claude/skills/context-task-planning/scripts/current-task.sh`.
- If neither installed path exists but the current workspace contains `skill/scripts/current-task.sh`, use the repo-local path instead.
- Run the command from the current workspace.
- Do not modify task state.
- After the command succeeds, summarize the current task, status, mode, and next recommended action.

## Run

```bash
core="${CLAUDE_SKILL_DIR}/../../skill/scripts/current-task.sh"
[ -f "$core" ] || core="$HOME/.claude/skills/context-task-planning/scripts/current-task.sh"
[ -f "$core" ] || core="skill/scripts/current-task.sh"
sh "$core"
```
