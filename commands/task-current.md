---
description: Show the current tracked task
---

Inspect the currently resolved `context-task-planning` task for this workspace and summarize the result.

Requirements:
- Run `sh "${COCO_PLUGIN_ROOT}/skill/scripts/current-task.sh"` from the current workspace.
- Do not modify task state.
- After the command succeeds, summarize the current task, status, mode, and next recommended action.

Run:

```bash
sh "${COCO_PLUGIN_ROOT}/skill/scripts/current-task.sh"
```
