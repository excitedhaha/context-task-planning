#!/usr/bin/env python3

from trae_hook_common import (
    HOST,
    compact_context_text,
    explicit_task_context_eligible,
    fallback_task_advisory,
    load_state,
    no_active_task_hint,
    print_context,
    print_system_message,
    read_hook_input,
    resolve_plan_dir,
    resolve_task_meta,
    run_compact_sync,
    state_summary,
    trae_session_key,
)


def compact_sync_detail(sync_result: dict | None) -> str:
    if not isinstance(sync_result, dict):
        return "shared compact-sync helper did not return a status"

    sources = []
    warnings = sync_result.get("warnings") or []
    if isinstance(warnings, list):
        sources.extend(warnings)

    for key in ("main_sync", "artifact_sync"):
        section = sync_result.get(key) or {}
        if isinstance(section, dict):
            sources.append(str(section.get("message") or ""))

    for source in sources:
        lines = [line.strip() for line in str(source).splitlines() if line.strip()]
        for line in reversed(lines):
            cleaned = line.removeprefix("[context-task-planning]").strip()
            cleaned = cleaned.removeprefix("-").strip()
            if cleaned:
                return cleaned

    return "compact sync did not complete cleanly"


def compact_sync_warning(sync_result: dict | None) -> str:
    if isinstance(sync_result, dict) and sync_result.get("ok", True):
        return ""

    slug = ""
    if isinstance(sync_result, dict):
        task = sync_result.get("task") or {}
        if isinstance(task, dict):
            slug = str(task.get("slug") or "").strip()

    detail = compact_sync_detail(sync_result)
    if slug:
        return (
            f"[context-task-planning] Compact sync warning for `{slug}`: {detail}. "
            f"Review `sh skill/scripts/validate-task.sh --task {slug}` before relying on compact recovery context."
        )

    return (
        f"[context-task-planning] Compact sync warning: {detail}. "
        "Review `.planning/<slug>/` manually before relying on compact recovery context."
    )


def join_context(prefix: str, body: str) -> str:
    return "\n".join(item for item in (prefix.strip(), body.strip()) if item)


def main() -> None:
    payload = read_hook_input()
    cwd = payload.get("cwd")
    session_key = trae_session_key(payload)
    sync_result = run_compact_sync(cwd=cwd, session_key=session_key, host=HOST)
    warning = compact_sync_warning(sync_result)
    task_meta = resolve_task_meta(cwd=cwd, session_key=session_key)
    explicit_task_context = explicit_task_context_eligible(task_meta)

    if explicit_task_context and isinstance(sync_result, dict) and sync_result.get("ok", True):
        compact_context = compact_context_text(cwd=cwd, session_key=session_key)
    else:
        compact_context = None

    if compact_context:
        print_context(join_context(warning, compact_context))
        return

    plan_dir = resolve_plan_dir(cwd=cwd, session_key=session_key)
    if plan_dir:
        state = load_state(plan_dir)
        if state:
            if not explicit_task_context:
                context = join_context(warning, fallback_task_advisory(task_meta, host=HOST) or "")
                print_context(context)
                return
            print_context(join_context(warning, state_summary(state, task_meta=task_meta, include_spec=True)))
            return

    hint = no_active_task_hint(cwd, host=HOST)
    context = join_context(warning, hint or "")
    if context:
        print_system_message(context)


if __name__ == "__main__":
    main()
