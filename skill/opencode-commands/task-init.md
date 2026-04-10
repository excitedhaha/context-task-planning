---
description: Initialize a tracked task
---

Initialize a new `context-task-planning` task for this workspace using the user's argument text as the task title.

Requirements:
- Treat `$ARGUMENTS` as the task title and pass it to `sh ~/.config/opencode/skills/context-task-planning/scripts/init-task.sh`.
- Run the command from the current workspace.
- If the dirty-worktree guard asks for a decision, stop and ask the user instead of choosing `--stash` or `--allow-dirty` yourself.
- After the command succeeds, summarize the created task slug and the next action.

Run:

```bash
sh ~/.config/opencode/skills/context-task-planning/scripts/init-task.sh "$ARGUMENTS"
```
