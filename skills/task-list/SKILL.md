---
name: task-list
description: List the existing context-task-planning tasks in this workspace and summarize the active pointer plus the most relevant tasks. Use this whenever the user asks what tasks exist, what they can resume, wants a task list, or explicitly invokes /task-list.
allowed-tools: Bash
---

# Task List

List the existing `context-task-planning` tasks for this workspace.

## Requirements

- Expect the main `context-task-planning` skill to be installed alongside this entry skill.
- Resolve the core script from the installed host path: prefer `${CLAUDE_SKILL_DIR}/../../skill/scripts/list-tasks.sh` for Claude plugin installs, `${COCO_PLUGIN_ROOT}/skill/scripts/list-tasks.sh` for TraeCLI/Coco plugin installs, `$HOME/.codex/plugins/context-task-planning/skill/scripts/list-tasks.sh` for Codex plugin installs, then standalone skill paths under `$HOME/.claude/skills/`, `$HOME/.codex/skills/`, `$HOME/.config/opencode/skills/`, and finally repo-local `skill/scripts/list-tasks.sh`.
- Run the command from the current workspace.
- Do not modify task state.
- After the command succeeds, summarize the active task pointer and the most relevant tasks from the output.

## Run

```bash
core=""
for candidate in \
  "${CLAUDE_SKILL_DIR:-}/../../skill/scripts/list-tasks.sh" \
  "${COCO_PLUGIN_ROOT:-}/skill/scripts/list-tasks.sh" \
  "$HOME/.codex/plugins/context-task-planning/skill/scripts/list-tasks.sh" \
  "$HOME/.claude/skills/context-task-planning/scripts/list-tasks.sh" \
  "$HOME/.codex/skills/context-task-planning/scripts/list-tasks.sh" \
  "$HOME/.config/opencode/skills/context-task-planning/scripts/list-tasks.sh" \
  "skill/scripts/list-tasks.sh"; do
  [ -f "$candidate" ] && core="$candidate" && break
done
[ -n "$core" ] || { echo "context-task-planning list-tasks.sh not found" >&2; exit 1; }
sh "$core"
```
