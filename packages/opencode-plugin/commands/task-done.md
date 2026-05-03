---
description: Mark a task done after verification
---

Mark a `context-task-planning` task done after verification.

Requirements:
- If `$ARGUMENTS` is empty, run `sh {{SKILL_SCRIPTS_DIR}}/done-task.sh` for the current task.
- If `$ARGUMENTS` is present, treat it as the task slug and run `sh {{SKILL_SCRIPTS_DIR}}/done-task.sh "$ARGUMENTS"`.
- Do not bypass the script's safety checks. If the script reports blockers, active delegates, or blocked phases, stop and summarize the issue instead of trying to force completion.
- After the command succeeds, summarize which task was marked done and remind the user that they can archive it later when they no longer need it in active lists.

Run the matching command for the presence or absence of `$ARGUMENTS`.
