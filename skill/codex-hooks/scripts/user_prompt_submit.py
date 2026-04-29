#!/usr/bin/env python3

from codex_hook_common import (
    HOST,
    allow_delegate_hint,
    codex_planning_guard_text,
    codex_session_key,
    create_turn_marker,
    delegate_hint_for_text,
    explicit_task_context_eligible,
    fallback_task_advisory,
    init_task_hint,
    load_state,
    looks_complex,
    no_active_task_hint,
    print_context,
    read_hook_input,
    resolve_plan_dir,
    resolve_task_meta,
    state_summary,
    task_drift_hint,
    task_drift_result,
)


def main() -> None:
    payload = read_hook_input()
    hook_event_name = str(payload.get("hook_event_name") or "UserPromptSubmit")
    cwd = payload.get("cwd")
    prompt = str(payload.get("prompt") or "")
    session_key = codex_session_key(payload)
    plan_dir = resolve_plan_dir(cwd=cwd, session_key=session_key)
    task_meta = resolve_task_meta(cwd=cwd, session_key=session_key)

    if plan_dir:
        state = load_state(plan_dir)
        if state:
            create_turn_marker(plan_dir, payload, task_meta, prompt)

            if not explicit_task_context_eligible(task_meta):
                return

            drift_result = task_drift_result(prompt, cwd, session_key=session_key)
            drift_hint = task_drift_hint(drift_result)
            if drift_hint:
                print_context(drift_hint, hook_event_name)
            return

    hint = no_active_task_hint(cwd, host=HOST)
    if hint:
        print_context(hint, hook_event_name)
        return

    if looks_complex(prompt):
        print_context(init_task_hint(host=HOST), hook_event_name)


if __name__ == "__main__":
    main()
