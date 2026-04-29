---
description: List tracked tasks in this workspace
---

List the existing `context-task-planning` tasks for this workspace and summarize the most relevant ones.

Requirements:
- Run `sh "${COCO_PLUGIN_ROOT}/skill/scripts/list-tasks.sh"` from the current workspace.
- Do not modify task state.
- After the command succeeds, summarize the active task pointer and the most relevant tasks from the output.

Run:

```bash
sh "${COCO_PLUGIN_ROOT}/skill/scripts/list-tasks.sh"
```
