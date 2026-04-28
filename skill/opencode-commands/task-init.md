---
description: Initialize a tracked task
---

Initialize a new `context-task-planning` task for this workspace using a confirmed task title.

Requirements:
- Treat `$ARGUMENTS` as an already-confirmed task title and pass it to `sh ~/.config/opencode/skills/context-task-planning/scripts/init-task.sh`.
- If `$ARGUMENTS` is empty but the surrounding user request implies a task, infer a concise candidate title, derive the slug that the core `slugify.sh` script would produce, and ask the user to confirm or edit the title before running `init-task.sh`.
- If `$ARGUMENTS` is empty and there is not enough surrounding request context to infer one, stop and ask the user for a task title.
- Do not create a task from an inferred title until the user confirms it.
- Run the command from the current workspace.
- If the dirty-worktree guard asks for a decision, stop and ask the user instead of choosing `--stash` or `--allow-dirty` yourself.
- After the command succeeds, summarize the created task slug and the next action.

Run:

```bash
sh ~/.config/opencode/skills/context-task-planning/scripts/init-task.sh "$ARGUMENTS"
```
