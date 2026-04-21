#!/usr/bin/env python3

import sys
from pathlib import Path

try:
    from .hook_common import (
        explicit_task_context_eligible,
        fallback_task_advisory,
        load_state,
        no_active_task_hint,
        read_hook_input,
        resolve_task_meta,
        resolve_plan_dir,
        session_key_from_payload,
        session_start_payload,
        state_summary,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from hook_common import (  # type: ignore
        explicit_task_context_eligible,
        fallback_task_advisory,
        load_state,
        no_active_task_hint,
        read_hook_input,
        resolve_task_meta,
        resolve_plan_dir,
        session_key_from_payload,
        session_start_payload,
        state_summary,
    )


def main():
    payload = read_hook_input()
    cwd = payload.get("cwd")
    session_key = session_key_from_payload(payload)
    plan_dir = resolve_plan_dir(cwd=cwd, session_key=session_key)
    task_meta = resolve_task_meta(cwd=cwd, session_key=session_key)

    if plan_dir:
        state = load_state(plan_dir)
        if state:
            if not explicit_task_context_eligible(task_meta):
                advisory = fallback_task_advisory(task_meta)
                if advisory:
                    print(session_start_payload(advisory))
                return
            print(
                session_start_payload(
                    state_summary(state, task_meta=task_meta, include_spec=True)
                )
            )
            return

    hint = no_active_task_hint(cwd)
    if hint:
        print(session_start_payload(hint))


if __name__ == "__main__":
    main()
