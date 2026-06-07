---
description: Mark a task done after verification
argument-hint: "[slug]"
---

Mark a `context-task-planning` task done after verification.

Requirements:
- If `$ARGUMENTS` is empty, run `sh "${COCO_PLUGIN_ROOT}/skill/scripts/done-task.sh"` for the current task.
- If `$ARGUMENTS` is present, treat it as the task slug and run `sh "${COCO_PLUGIN_ROOT}/skill/scripts/done-task.sh" "$ARGUMENTS"`.
- Do not bypass the script's safety checks. `done-task.sh` requires `state.verify_commands` and matching successful rows in `progress.md` under `## Verification Log`. If the script reports missing verification evidence, blockers, active delegates, or blocked phases, stop and summarize the issue instead of trying to force completion.
- After the command succeeds, summarize which task was marked done and remind the user that it can be archived later.

Run the matching command for the presence or absence of `$ARGUMENTS`.
