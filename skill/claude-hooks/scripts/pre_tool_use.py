#!/usr/bin/env python3

import sys
from pathlib import Path

try:
    from .hook_common import (
        allow_delegate_hint,
        delegate_hint_for_text,
        load_state,
        pre_tool_payload,
        read_hook_input,
        resolve_task_meta,
        resolve_plan_dir,
        session_key_from_payload,
        state_summary,
        task_drift_hint,
        task_drift_result,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from hook_common import (  # type: ignore
        allow_delegate_hint,
        delegate_hint_for_text,
        load_state,
        pre_tool_payload,
        read_hook_input,
        resolve_task_meta,
        resolve_plan_dir,
        session_key_from_payload,
        state_summary,
        task_drift_hint,
        task_drift_result,
    )


def main():
    payload = read_hook_input()
    cwd = payload.get("cwd")
    session_key = session_key_from_payload(payload)
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    plan_dir = resolve_plan_dir(cwd=cwd, session_key=session_key)
    task_meta = resolve_task_meta(cwd=cwd, session_key=session_key)

    if not plan_dir:
        return

    state = load_state(plan_dir)
    if not state:
        return

    task_text = ""
    drift_result = None
    if tool_name == "Task":
        task_text = " ".join(
            str(tool_input.get(key, ""))
            for key in ("description", "prompt", "command", "subagent_type")
        )
        drift_result = task_drift_result(task_text, cwd, session_key=session_key)

    summary_tool_name = tool_name
    if tool_name == "Task" and not allow_delegate_hint(drift_result):
        summary_tool_name = None

    context = state_summary(state, task_meta=task_meta, tool_name=summary_tool_name)
    if tool_name == "Task":
        drift_hint = task_drift_hint(drift_result, tool_name=tool_name)
        if drift_hint:
            context += "\n" + drift_hint
        if allow_delegate_hint(drift_result):
            delegate_hint = delegate_hint_for_text(task_text, state)
            if delegate_hint:
                context += "\n" + delegate_hint

    print(pre_tool_payload(context))


if __name__ == "__main__":
    main()
