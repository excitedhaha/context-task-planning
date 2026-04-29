---
name: task-drift
description: Return heuristic route evidence for whether a new request still fits the current context-task-planning task and summarize the routing recommendation. Use this whenever the user asks whether a new ask belongs in the same task, wants a drift check, is about to switch scope, or explicitly invokes /task-drift.
allowed-tools: Bash
---

# Task Drift

Return heuristic route evidence for whether a new request still fits the current `context-task-planning` task.

## Requirements

- Expect the main `context-task-planning` skill to be installed alongside this entry skill.
- Treat the invocation argument text as the candidate new request.
- If no request text was provided, stop and ask the user to provide the request they want to compare against the current task.
- If this entry skill is loaded from a Claude Code plugin, prefer the bundled core script at `${CLAUDE_SKILL_DIR}/../../skill/scripts/check-task-drift.sh`.
- Otherwise prefer the standalone core skill script at `~/.claude/skills/context-task-planning/scripts/check-task-drift.sh`.
- If neither installed path exists but the current workspace contains `skill/scripts/check-task-drift.sh`, use the repo-local path instead.
- Run the command from the current workspace.
- After the command succeeds, summarize the route evidence and mention any routing recommendation; do not present `unclear` as a final drift conclusion.

## Run

```bash
core="${CLAUDE_SKILL_DIR}/../../skill/scripts/check-task-drift.sh"
[ -f "$core" ] || core="$HOME/.claude/skills/context-task-planning/scripts/check-task-drift.sh"
[ -f "$core" ] || core="skill/scripts/check-task-drift.sh"
sh "$core" --prompt "<new request>" --json
```
