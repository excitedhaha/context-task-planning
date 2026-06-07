---
name: task-current
description: Inspect the current context-task-planning task in this workspace and summarize the resolved task, status, and next action. Use this whenever the user asks what task is active, what the next step is, wants a task summary, or explicitly invokes /task-current.
allowed-tools: Bash
---

# Task Current

Show the currently resolved `context-task-planning` task for this workspace.

## Requirements

- Expect the main `context-task-planning` skill to be installed alongside this entry skill.
- Resolve the core script from the installed host path: prefer `${CLAUDE_SKILL_DIR}/../../skill/scripts/current-task.sh` for Claude plugin installs, `${COCO_PLUGIN_ROOT}/skill/scripts/current-task.sh` for TraeCLI/Coco plugin installs, `$HOME/.codex/plugins/context-task-planning/skill/scripts/current-task.sh` for Codex plugin installs, then standalone skill paths under `$HOME/.claude/skills/`, `$HOME/.codex/skills/`, `$HOME/.config/opencode/skills/`, and finally repo-local `skill/scripts/current-task.sh`.
- Run the command from the current workspace.
- Do not modify task state.
- After the command succeeds, summarize the current task, status, mode, and next recommended action.

## Run

```bash
core=""
for candidate in \
  "${CLAUDE_SKILL_DIR:-}/../../skill/scripts/current-task.sh" \
  "${COCO_PLUGIN_ROOT:-}/skill/scripts/current-task.sh" \
  "$HOME/.codex/plugins/context-task-planning/skill/scripts/current-task.sh" \
  "$HOME/.claude/skills/context-task-planning/scripts/current-task.sh" \
  "$HOME/.codex/skills/context-task-planning/scripts/current-task.sh" \
  "$HOME/.config/opencode/skills/context-task-planning/scripts/current-task.sh" \
  "skill/scripts/current-task.sh"; do
  [ -f "$candidate" ] && core="$candidate" && break
done
[ -n "$core" ] || { echo "context-task-planning current-task.sh not found" >&2; exit 1; }
sh "$core"
```
