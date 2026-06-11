#!/usr/bin/env python3

from codex_hook_common import (
    HOST,
    concise_subagent_preflight_context,
    codex_session_key,
    explicit_task_context_eligible,
    fallback_task_advisory,
    read_hook_input,
    resolve_plan_dir,
    resolve_task_meta,
    subagent_preflight_result,
    subagent_preflight_should_inject_concise,
    subagent_start_payload,
)


def main() -> None:
    payload = read_hook_input()
    cwd = payload.get("cwd")
    session_key = codex_session_key(payload)
    agent_type = str(payload.get("agent_type") or "").strip()
    plan_dir = resolve_plan_dir(cwd=cwd, session_key=session_key)
    task_meta = resolve_task_meta(cwd=cwd, session_key=session_key)

    if not plan_dir or not task_meta or not task_meta.get("found"):
        return

    if not explicit_task_context_eligible(task_meta):
        advisory = fallback_task_advisory(task_meta, tool_name="Task", host=HOST)
        if advisory:
            print(subagent_start_payload(advisory))
        return

    # Codex SubagentStart exposes the agent type/profile but not the parent
    # prompt. Use the profile as a lightweight routing hint and keep the output
    # to task guardrails instead of attempting prompt mutation.
    preflight = subagent_preflight_result(
        agent_type,
        cwd=cwd,
        session_key=session_key,
        host=HOST,
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
        elif decision in {"routing_only", "delegate_required"} and operator_message:
            context_parts.append(operator_message)
    else:
        context_parts.append(concise_subagent_preflight_context(None, task_meta=task_meta))

    if context_parts:
        print(subagent_start_payload("\n".join(context_parts)))


if __name__ == "__main__":
    main()
