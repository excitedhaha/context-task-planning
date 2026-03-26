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
        subagent_preflight_result,
        task_drift_hint,
        task_drift_result,
        task_tool_text,
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
        subagent_preflight_result,
        task_drift_hint,
        task_drift_result,
        task_tool_text,
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

    if tool_name == "Task":
        task_text = task_tool_text(tool_input)
        preflight = subagent_preflight_result(
            task_text,
            cwd=cwd,
            session_key=session_key,
            host="claude",
            tool_name=tool_name,
        )
        if preflight:
            context = state_summary(state, task_meta=task_meta)
            decision = preflight.get("decision")
            prompt_prefix = str(preflight.get("prompt_prefix") or "").strip()
            operator_message = str(preflight.get("operator_message") or "").strip()
            if (
                decision in {"payload_only", "payload_plus_delegate_recommended"}
                and prompt_prefix
            ):
                context += "\n" + prompt_prefix
            if operator_message and (
                decision in {"routing_only", "delegate_required"} or not prompt_prefix
            ):
                context += "\n" + operator_message
            print(pre_tool_payload(context))
            return

        drift_result = task_drift_result(task_text, cwd, session_key=session_key)
        summary_tool_name = tool_name if allow_delegate_hint(drift_result) else None
        context = state_summary(state, task_meta=task_meta, tool_name=summary_tool_name)
        drift_hint = task_drift_hint(drift_result, tool_name=tool_name)
        if drift_hint:
            context += "\n" + drift_hint
        if allow_delegate_hint(drift_result):
            delegate_hint = delegate_hint_for_text(task_text, state)
            if delegate_hint:
                context += "\n" + delegate_hint
        print(pre_tool_payload(context))
        return

    context = state_summary(state, task_meta=task_meta, tool_name=tool_name)

    print(pre_tool_payload(context))


if __name__ == "__main__":
    main()
