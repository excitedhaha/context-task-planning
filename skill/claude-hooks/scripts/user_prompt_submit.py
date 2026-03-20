#!/usr/bin/env python3

import sys
from pathlib import Path

try:
    from .hook_common import (
        allow_delegate_hint,
        delegate_hint_for_text,
        init_task_hint,
        load_state,
        looks_complex,
        no_active_task_hint,
        read_hook_input,
        resolve_plan_dir,
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
        init_task_hint,
        load_state,
        looks_complex,
        no_active_task_hint,
        read_hook_input,
        resolve_plan_dir,
        state_summary,
        task_drift_hint,
        task_drift_result,
        user_prompt_payload,
    )


def main():
    payload = read_hook_input()
    cwd = payload.get("cwd")
    prompt = payload.get("prompt", "")
    plan_dir = resolve_plan_dir(cwd=cwd)

    if plan_dir:
        state = load_state(plan_dir)
        if state:
            context = state_summary(state)
            drift_result = task_drift_result(prompt, cwd)
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
