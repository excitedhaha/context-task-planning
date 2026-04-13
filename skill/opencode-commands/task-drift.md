---
description: Check whether a new ask fits this task
---

Check whether a new request still fits the current `context-task-planning` task.

Requirements:
- Treat `$ARGUMENTS` as the candidate new request text.
- If `$ARGUMENTS` is empty, stop and ask the user to provide the request they want to compare against the current task.
- Run `sh ~/.config/opencode/skills/context-task-planning/scripts/check-task-drift.sh --prompt "$ARGUMENTS" --json` from the current workspace.
- After the command succeeds, summarize whether the request still fits the current task and mention any routing recommendation.

Run:

```bash
sh ~/.config/opencode/skills/context-task-planning/scripts/check-task-drift.sh --prompt "$ARGUMENTS" --json
```
