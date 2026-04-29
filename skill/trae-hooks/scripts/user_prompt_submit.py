#!/usr/bin/env python3

from trae_hook_common import (
    HOST,
    allow_delegate_hint,
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
    trae_planning_guard_text,
    trae_session_key,
)


def main() -> None:
    payload = read_hook_input()
    cwd = payload.get("cwd")
    prompt = str(payload.get("prompt") or "")
    session_key = trae_session_key(payload)
    plan_dir = resolve_plan_dir(cwd=cwd, session_key=session_key)
    task_meta = resolve_task_meta(cwd=cwd, session_key=session_key)

    if plan_dir:
        state = load_state(plan_dir)
        if state:
            create_turn_marker(plan_dir, payload, task_meta, prompt)

            if not explicit_task_context_eligible(task_meta):
                print_context(fallback_task_advisory(task_meta, host=HOST))
                return

            slug = str(state.get("slug") or "")
            context = state_summary(state, task_meta=task_meta, include_spec=True)
            drift_result = task_drift_result(prompt, cwd, session_key=session_key)
            drift_hint = task_drift_hint(drift_result)
            if drift_hint:
                context += "\n" + drift_hint
            if allow_delegate_hint(drift_result):
                delegate_hint = delegate_hint_for_text(prompt, state, host=HOST)
                if delegate_hint:
                    context += "\n" + delegate_hint
            context += "\n" + trae_planning_guard_text(slug)
            print_context(context)
            return

    hint = no_active_task_hint(cwd, host=HOST)
    if hint:
        print_context(hint)
        return

    if looks_complex(prompt):
        print_context(init_task_hint(host=HOST))


if __name__ == "__main__":
    main()
