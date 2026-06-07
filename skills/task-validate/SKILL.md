---
name: task-validate
description: Validate the current context-task-planning task without auto-fixing warnings. Use this whenever the user wants to check task consistency, validate planning state, verify the task files are in sync, or explicitly invokes /task-validate.
allowed-tools: Bash
---

# Task Validate

Validate the current `context-task-planning` task without automatically fixing warnings.

## Requirements

- Expect the main `context-task-planning` skill to be installed alongside this entry skill.
- Resolve the core script from the installed host path: prefer `${CLAUDE_SKILL_DIR}/../../skill/scripts/validate-task.sh` for Claude plugin installs, `${COCO_PLUGIN_ROOT}/skill/scripts/validate-task.sh` for TraeCLI/Coco plugin installs, `$HOME/.codex/plugins/context-task-planning/skill/scripts/validate-task.sh` for Codex plugin installs, then standalone skill paths under `$HOME/.claude/skills/`, `$HOME/.codex/skills/`, `$HOME/.config/opencode/skills/`, and finally repo-local `skill/scripts/validate-task.sh`.
- Run the command from the current workspace.
- Do not add `--fix-warnings`.
- After the command succeeds, summarize whether validation passed and mention any reported issues.

## Run

```bash
core=""
for candidate in \
  "${CLAUDE_SKILL_DIR:-}/../../skill/scripts/validate-task.sh" \
  "${COCO_PLUGIN_ROOT:-}/skill/scripts/validate-task.sh" \
  "$HOME/.codex/plugins/context-task-planning/skill/scripts/validate-task.sh" \
  "$HOME/.claude/skills/context-task-planning/scripts/validate-task.sh" \
  "$HOME/.codex/skills/context-task-planning/scripts/validate-task.sh" \
  "$HOME/.config/opencode/skills/context-task-planning/scripts/validate-task.sh" \
  "skill/scripts/validate-task.sh"; do
  [ -f "$candidate" ] && core="$candidate" && break
done
[ -n "$core" ] || { echo "context-task-planning validate-task.sh not found" >&2; exit 1; }
sh "$core"
```
