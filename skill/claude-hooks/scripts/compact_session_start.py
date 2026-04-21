#!/usr/bin/env python3

import sys
from pathlib import Path

try:
    from .hook_common import (
        explicit_task_context_eligible,
        fallback_task_advisory,
        compact_context_text,
        load_state,
        no_active_task_hint,
        read_hook_input,
        resolve_task_meta,
        resolve_plan_dir,
        run_compact_sync,
        session_key_from_payload,
        session_start_payload,
        state_summary,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from hook_common import (  # type: ignore
        explicit_task_context_eligible,
        fallback_task_advisory,
        compact_context_text,
        load_state,
        no_active_task_hint,
        read_hook_input,
        resolve_task_meta,
        resolve_plan_dir,
        run_compact_sync,
        session_key_from_payload,
        session_start_payload,
        state_summary,
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
    parts = [item for item in (prefix.strip(), body.strip()) if item]
    return "\n".join(parts)


def main():
    payload = read_hook_input()
    cwd = payload.get("cwd")
    session_key = session_key_from_payload(payload)
    sync_result = run_compact_sync(cwd=cwd, session_key=session_key, host="claude")
    warning = compact_sync_warning(sync_result)
    task_meta = resolve_task_meta(cwd=cwd, session_key=session_key)
    explicit_task_context = explicit_task_context_eligible(task_meta)

    if explicit_task_context and isinstance(sync_result, dict) and sync_result.get("ok", True):
        compact_context = compact_context_text(cwd=cwd, session_key=session_key)
    else:
        compact_context = None

    if compact_context:
        print(session_start_payload(join_context(warning, compact_context)))
        return

    plan_dir = resolve_plan_dir(cwd=cwd, session_key=session_key)

    if plan_dir:
        state = load_state(plan_dir)
        if state:
            if not explicit_task_context:
                advisory = fallback_task_advisory(task_meta)
                context = join_context(warning, advisory or "")
                if context:
                    print(session_start_payload(context))
                return
            print(
                session_start_payload(
                    join_context(
                        warning,
                        state_summary(state, task_meta=task_meta, include_spec=True),
                    )
                )
            )
            return

    hint = no_active_task_hint(cwd)
    context = join_context(warning, hint or "")
    if context:
        print(session_start_payload(context))


if __name__ == "__main__":
    main()
