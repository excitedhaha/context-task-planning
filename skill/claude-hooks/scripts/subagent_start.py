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
        concise_subagent_preflight_context,
        explicit_task_context_eligible,
        fallback_task_advisory,
        read_hook_input,
        resolve_plan_dir,
        resolve_task_meta,
        session_key_from_payload,
        subagent_preflight_result,
        subagent_preflight_should_inject_concise,
        subagent_start_payload,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from hook_common import (  # type: ignore
        concise_subagent_preflight_context,
        explicit_task_context_eligible,
        fallback_task_advisory,
        read_hook_input,
        resolve_plan_dir,
        resolve_task_meta,
        session_key_from_payload,
        subagent_preflight_result,
        subagent_preflight_should_inject_concise,
        subagent_start_payload,
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

    if not explicit_task_context_eligible(task_meta):
        advisory = fallback_task_advisory(task_meta, tool_name="Task", host="claude")
        if advisory:
            print(subagent_start_payload(advisory))
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

    if preflight:
        decision = preflight.get("decision")
        operator_message = str(preflight.get("operator_message") or "").strip()

        if subagent_preflight_should_inject_concise(preflight):
            context_parts.append(
                concise_subagent_preflight_context(preflight, task_meta=task_meta)
            )

        # For routing_only, include the operator message as guidance.
        elif decision == "routing_only" and operator_message:
            context_parts.append(operator_message)

        # delegate_required should have been caught by PreToolUse, but
        # include the message as a reminder if the user allowed the launch.
        elif decision == "delegate_required" and operator_message:
            context_parts.append(operator_message)
    else:
        context_parts.append(concise_subagent_preflight_context(None, task_meta=task_meta))

    if context_parts:
        print(subagent_start_payload("\n".join(context_parts)))


if __name__ == "__main__":
    main()
