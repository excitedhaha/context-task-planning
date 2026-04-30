---
description: Initialize a tracked task
---

Initialize a new `context-task-planning` task for this workspace using a confirmed task title and the final task slug.

Requirements:
- Treat `$ARGUMENTS` as an already-confirmed task title. Derive the slug that the core `slugify.sh` script would produce unless the user explicitly asks to override it.
- If `$ARGUMENTS` is empty but the surrounding user request implies a task, infer a concise candidate title, derive the slug that the core `slugify.sh` script would produce, and show both the candidate title and candidate slug before running `init-task.sh`.
- If `$ARGUMENTS` is empty and there is not enough surrounding request context to infer one, stop and ask the user for a task title.
- Do not create a task from an inferred title until the user confirms the final title and slug.
- When you surface a candidate task, ask the user to confirm or edit both the title and the slug.
- If the user edits the title but does not explicitly override the slug, recompute the slug from the final title before running the command.
- If the user explicitly edits the slug, pass that slug through `init-task.sh --slug`; the core script will still normalize it with `slugify.sh` before creating the task.
- Run the command from the current workspace.
- If the dirty-worktree guard asks for a decision, stop and ask the user instead of choosing `--stash` or `--allow-dirty` yourself.
- After the command succeeds, summarize the created task slug and the next action.

Run:

```bash
sh ~/.config/opencode/skills/context-task-planning/scripts/init-task.sh --title "<final task title>" --slug "<final task slug>"
```
