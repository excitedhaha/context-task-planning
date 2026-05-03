---
description: Show the current tracked task
---

Inspect the currently resolved `context-task-planning` task for this workspace and summarize the result.

Requirements:
- Run `sh {{SKILL_SCRIPTS_DIR}}/current-task.sh` from the current workspace.
- Do not modify task state.
- After the command succeeds, summarize the current task, status, and next recommended action.

Run:

```bash
sh {{SKILL_SCRIPTS_DIR}}/current-task.sh
```
