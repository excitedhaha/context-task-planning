#!/usr/bin/env python3

import sys
from pathlib import Path

try:
    from .hook_common import (
        allow_delegate_hint,
        delegate_hint_for_text,
        explicit_task_context_eligible,
        fallback_task_advisory,
        init_task_hint,
        load_state,
        looks_complex,
        no_active_task_hint,
        read_hook_input,
        resolve_task_meta,
        resolve_plan_dir,
        session_key_from_payload,
        state_summary,
        task_drift_hint,
        task_drift_result,
        user_prompt_payload,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from hook_common import (  # type: ignore
        allow_delegate_hint,
        delegate_hint_for_text,
        explicit_task_context_eligible,
        fallback_task_advisory,
        init_task_hint,
        load_state,
        looks_complex,
        no_active_task_hint,
        read_hook_input,
        resolve_task_meta,
        resolve_plan_dir,
        session_key_from_payload,
        state_summary,
        task_drift_hint,
        task_drift_result,
        user_prompt_payload,
    )


def main():
    payload = read_hook_input()
    cwd = payload.get("cwd")
    prompt = payload.get("prompt", "")
    session_key = session_key_from_payload(payload)
    plan_dir = resolve_plan_dir(cwd=cwd, session_key=session_key)
    task_meta = resolve_task_meta(cwd=cwd, session_key=session_key)

    if plan_dir:
        state = load_state(plan_dir)
        if state:
            if not explicit_task_context_eligible(task_meta):
                advisory = fallback_task_advisory(task_meta)
                if advisory:
                    print(user_prompt_payload(advisory))
                return
            context = state_summary(state, task_meta=task_meta, include_spec=True)
            drift_result = task_drift_result(prompt, cwd, session_key=session_key)
            drift_hint = task_drift_hint(drift_result)
            if drift_hint:
                context += "\n" + drift_hint
            if allow_delegate_hint(drift_result):
                delegate_hint = delegate_hint_for_text(prompt, state)
                if delegate_hint:
                    context += "\n" + delegate_hint
            print(user_prompt_payload(context))
            return

    hint = no_active_task_hint(cwd)
    if hint:
        print(user_prompt_payload(hint))
        return

    if looks_complex(prompt):
        print(user_prompt_payload(init_task_hint()))


if __name__ == "__main__":
    main()
