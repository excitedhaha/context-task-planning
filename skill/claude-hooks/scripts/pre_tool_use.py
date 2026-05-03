#!/usr/bin/env python3

import sys
from pathlib import Path

try:
    from .hook_common import (
        allow_delegate_hint,
        delegate_hint_from_preflight,
        explicit_task_context_eligible,
        fallback_task_advisory,
        load_state,
        pre_tool_ask_payload,
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
        delegate_hint_from_preflight,
        explicit_task_context_eligible,
        fallback_task_advisory,
        load_state,
        pre_tool_ask_payload,
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

    explicit_task_context = explicit_task_context_eligible(task_meta)

    if not explicit_task_context:
        advisory = fallback_task_advisory(task_meta, tool_name=tool_name)
        if tool_name == "Task":
            task_text = task_tool_text(tool_input)
            preflight = subagent_preflight_result(
                task_text,
                cwd=cwd,
                session_key=session_key,
                host="claude",
                tool_name=tool_name,
            )
            operator_message = ""
            if preflight:
                operator_message = str(preflight.get("operator_message") or "").strip()
            context = "\n".join(
                item for item in (advisory, operator_message) if item
            )
            if context:
                print(pre_tool_payload(context))
            return

        return

    if tool_name == "Task":
        # PreToolUse on Task: only handle delegate_required gating.
        # Context injection (state_summary + prompt_prefix) is handled by
        # SubagentStart, which injects at the start of the subagent
        # conversation rather than next to the tool call result.
        task_text = task_tool_text(tool_input)
        preflight = subagent_preflight_result(
            task_text,
            cwd=cwd,
            session_key=session_key,
            host="claude",
            tool_name=tool_name,
        )

        if preflight and preflight.get("decision") == "delegate_required":
            operator_message = str(preflight.get("operator_message") or "").strip()
            delegate = preflight.get("delegate") or {}
            delegate_reason = str(
                delegate.get("reason") or operator_message or "a delegate lane is required"
            ).strip()
            ask_reason = (
                f"[context-task-planning] delegate_required: {delegate_reason}. "
                "Consider creating a delegate lane instead."
            )
            print(pre_tool_ask_payload(operator_message, reason=ask_reason))

        # For non-delegate_required decisions, SubagentStart handles
        # context injection. No additional PreToolUse output needed.
        return

    return


if __name__ == "__main__":
    main()
