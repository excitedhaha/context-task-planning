---
name: task-done
description: Mark a context-task-planning task done after verification and summarize any blockers if completion is refused. Use this whenever the user wants to finish a task, mark tracked work done, close the current task after verification, or explicitly invokes /task-done.
allowed-tools: Bash
---

# Task Done

Mark a `context-task-planning` task done after verification.

## Requirements

- Expect the main `context-task-planning` skill to be installed alongside this entry skill.
- If the user provided an invocation argument, treat it as the task slug; otherwise operate on the current task.
- If this entry skill is loaded from a Claude Code plugin, prefer the bundled core script at `${CLAUDE_SKILL_DIR}/../../skill/scripts/done-task.sh`.
- Otherwise prefer the standalone core skill script at `~/.claude/skills/context-task-planning/scripts/done-task.sh`.
- If neither installed path exists but the current workspace contains `skill/scripts/done-task.sh`, use the repo-local path instead.
- Run the command from the current workspace.
- Do not bypass the script's safety checks. If the script reports blockers, active delegates, or blocked phases, stop and summarize the issue instead of trying to force completion.
- After the command succeeds, summarize which task was marked done and remind the user that they can archive it later when they no longer need it in active lists.

## Run

Run the matching command for whether a slug argument was provided.

```bash
core="${CLAUDE_SKILL_DIR}/../../skill/scripts/done-task.sh"
[ -f "$core" ] || core="$HOME/.claude/skills/context-task-planning/scripts/done-task.sh"
[ -f "$core" ] || core="skill/scripts/done-task.sh"
sh "$core" [slug]
```
