---
name: task-validate
description: Validate the current context-task-planning task without auto-fixing warnings. Use this whenever the user wants to check task consistency, validate planning state, verify the task files are in sync, or explicitly invokes /task-validate.
allowed-tools: Bash
---

# Task Validate

Validate the current `context-task-planning` task without automatically fixing warnings.

## Requirements

- Expect the main `context-task-planning` skill to be installed alongside this entry skill.
- If this entry skill is loaded from a Claude Code plugin, prefer the bundled core script at `${CLAUDE_SKILL_DIR}/../../skill/scripts/validate-task.sh`.
- Otherwise prefer the standalone core skill script at `~/.claude/skills/context-task-planning/scripts/validate-task.sh`.
- If neither installed path exists but the current workspace contains `skill/scripts/validate-task.sh`, use the repo-local path instead.
- Run the command from the current workspace.
- Do not add `--fix-warnings`.
- After the command succeeds, summarize whether validation passed and mention any reported issues.

## Run

```bash
core="${CLAUDE_SKILL_DIR}/../../skill/scripts/validate-task.sh"
[ -f "$core" ] || core="$HOME/.claude/skills/context-task-planning/scripts/validate-task.sh"
[ -f "$core" ] || core="skill/scripts/validate-task.sh"
sh "$core"
```
