---
description: Validate the current task state
---

Validate the current `context-task-planning` task without automatically fixing warnings.

Requirements:
- Run `sh {{SKILL_SCRIPTS_DIR}}/validate-task.sh` from the current workspace.
- Do not add `--fix-warnings` in this command.
- After the command succeeds, summarize whether validation passed and mention any reported issues.

Run:

```bash
sh {{SKILL_SCRIPTS_DIR}}/validate-task.sh
```
