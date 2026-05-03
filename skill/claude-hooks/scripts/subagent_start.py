#!/usr/bin/env python3

"""SubagentStart hook: inject task context into a newly spawned subagent.

This runs when a subagent is launched via the Agent/Task tool. The
additionalContext is placed at the start of the subagent's conversation,
before its first prompt — making it more prominent than PreToolUse
additionalContext which appears next to the tool call result.
"""

import sys
from pathlib import Path

try:
    from .hook_common import (
        read_hook_input,
        resolve_plan_dir,
        resolve_task_meta,
        session_key_from_payload,
        state_summary,
        subagent_preflight_result,
        subagent_start_payload,
        task_tool_text,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from hook_common import (  # type: ignore
        read_hook_input,
        resolve_plan_dir,
        resolve_task_meta,
        session_key_from_payload,
        state_summary,
        subagent_preflight_result,
        subagent_start_payload,
        task_tool_text,
    )


def main():
    payload = read_hook_input()
    cwd = payload.get("cwd")
    session_key = session_key_from_payload(payload)
    agent_type = str(payload.get("agent_type") or "").strip()
    plan_dir = resolve_plan_dir(cwd=cwd, session_key=session_key)
    task_meta = resolve_task_meta(cwd=cwd, session_key=session_key)

    if not plan_dir or not task_meta or not task_meta.get("found"):
        return

    # SubagentStart fires after the Agent tool is invoked, so we cannot
    # retrieve the original task_text. Use the agent_type as a hint to
    # compute a lightweight preflight for context injection.
    preflight = subagent_preflight_result(
        agent_type,
        cwd=cwd,
        session_key=session_key,
        host="claude",
        tool_name="Task",
    )

    context_parts = []

    # Always include task state summary so the subagent knows the current task.
    from hook_common import load_state
    state = load_state(plan_dir)
    if state:
        context_parts.append(state_summary(state, task_meta=task_meta))

    if preflight:
        decision = preflight.get("decision")
        prompt_prefix = str(preflight.get("prompt_prefix") or "").strip()
        operator_message = str(preflight.get("operator_message") or "").strip()

        # Inject prompt_prefix for payload and delegate-recommended decisions.
        if decision in {"payload_only", "payload_plus_delegate_recommended"} and prompt_prefix:
            context_parts.append(prompt_prefix)

        # For routing_only, include the operator message as guidance.
        if decision == "routing_only" and operator_message:
            context_parts.append(operator_message)

        # delegate_required should have been caught by PreToolUse, but
        # include the message as a reminder if the user allowed the launch.
        if decision == "delegate_required" and operator_message:
            context_parts.append(operator_message)

    if context_parts:
        print(subagent_start_payload("\n".join(context_parts)))


if __name__ == "__main__":
    main()
