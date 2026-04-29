#!/usr/bin/env python3

from trae_hook_common import (
    explicit_task_context_eligible,
    read_hook_input,
    read_marker,
    resolve_plan_dir,
    resolve_task_meta,
    stop_block_payload,
    sync_files_updated,
    trae_planning_guard_text,
    trae_session_key,
    write_marker,
)


def main() -> None:
    payload = read_hook_input()
    if payload.get("stop_hook_active"):
        return

    cwd = payload.get("cwd")
    session_key = trae_session_key(payload)
    plan_dir = resolve_plan_dir(cwd=cwd, session_key=session_key)
    if not plan_dir:
        return

    task_meta = resolve_task_meta(cwd=cwd, session_key=session_key)
    if not explicit_task_context_eligible(task_meta):
        return

    marker = read_marker(plan_dir, payload)
    if not marker:
        return

    marker["planning_updated"] = bool(marker.get("planning_updated")) or sync_files_updated(
        plan_dir, marker.get("baseline_mtimes")
    )

    needs_read = bool(marker.get("needs_planning_read")) and not bool(marker.get("planning_read"))
    needs_update = bool(marker.get("tool_mutated")) and not bool(marker.get("planning_updated"))

    if marker.get("stop_prompted") or not (needs_read or needs_update):
        write_marker(plan_dir, payload, marker)
        return

    slug = str(marker.get("task_slug") or (task_meta or {}).get("slug") or "")
    lines = ["[context-task-planning] Before finishing this TraeCLI/Coco turn, sync planning context."]
    if needs_read:
        lines.append("- Refresh the current task from planning files before relying on long conversation context.")
    if needs_update:
        lines.append(
            f"- Update `.planning/{slug}/progress.md` and `.planning/{slug}/state.json` with code changes, verification status, blockers, and next_action."
        )
    lines.append(trae_planning_guard_text(slug))

    marker["stop_prompted"] = True
    write_marker(plan_dir, payload, marker)
    print(stop_block_payload("\n".join(lines)))


if __name__ == "__main__":
    main()
