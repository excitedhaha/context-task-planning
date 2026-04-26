#!/usr/bin/env python3

from codex_hook_common import (
    HOST,
    codex_planning_guard_text,
    codex_session_key,
    explicit_task_context_eligible,
    fallback_task_advisory,
    load_state,
    no_active_task_hint,
    print_context,
    read_hook_input,
    resolve_plan_dir,
    resolve_task_meta,
    state_summary,
)


def main() -> None:
    payload = read_hook_input()
    hook_event_name = str(payload.get("hook_event_name") or "SessionStart")
    cwd = payload.get("cwd")
    session_key = codex_session_key(payload)
    plan_dir = resolve_plan_dir(cwd=cwd, session_key=session_key)
    task_meta = resolve_task_meta(cwd=cwd, session_key=session_key)

    if plan_dir:
        state = load_state(plan_dir)
        if state:
            if not explicit_task_context_eligible(task_meta):
                print_context(fallback_task_advisory(task_meta, host=HOST), hook_event_name)
                return

            if isinstance(task_meta, dict):
                slug = str(state.get("slug") or task_meta.get("slug") or "")
            else:
                slug = str(state.get("slug") or "")
            print_context(
                "\n".join(
                    [
                        state_summary(state, task_meta=task_meta, include_spec=True),
                        codex_planning_guard_text(slug),
                    ]
                ),
                hook_event_name,
            )
            return

    print_context(no_active_task_hint(cwd, host=HOST), hook_event_name)


if __name__ == "__main__":
    main()
