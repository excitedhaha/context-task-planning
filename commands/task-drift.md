---
description: Show route evidence for a new ask
argument-hint: "<new request>"
---

Return heuristic route evidence for whether a new request still fits the current `context-task-planning` task.

Requirements:
- Treat `$ARGUMENTS` as the candidate new request text.
- If `$ARGUMENTS` is empty, stop and ask the user to provide the request they want to compare against the current task.
- Run `sh "${COCO_PLUGIN_ROOT}/skill/scripts/check-task-drift.sh" --prompt "$ARGUMENTS" --json` from the current workspace.
- After the command succeeds, summarize the route evidence and mention any routing recommendation; do not present `unclear` as a final drift conclusion.

Run:

```bash
sh "${COCO_PLUGIN_ROOT}/skill/scripts/check-task-drift.sh" --prompt "$ARGUMENTS" --json
```
