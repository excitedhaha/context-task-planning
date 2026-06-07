#!/usr/bin/env python3

from trae_hook_common import (
    HOST,
    concise_subagent_preflight_context,
    explicit_task_context_eligible,
    fallback_task_advisory,
    load_state,
    print_context,
    read_hook_input,
    resolve_plan_dir,
    resolve_task_meta,
    subagent_preflight_result,
    subagent_preflight_should_inject_concise,
    task_drift_hint,
    task_drift_result,
    task_tool_text,
    trae_session_key,
)


def main() -> None:
    payload = read_hook_input()
    cwd = payload.get("cwd")
    session_key = trae_session_key(payload)
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
        advisory = fallback_task_advisory(task_meta, tool_name=tool_name, host=HOST)
        if tool_name == "Task":
            task_text = task_tool_text(tool_input)
            preflight = subagent_preflight_result(
                task_text,
                cwd=cwd,
                session_key=session_key,
                host=HOST,
                tool_name=str(tool_name or "Task"),
            )
            operator_message = ""
            if preflight:
                operator_message = str(preflight.get("operator_message") or "").strip()
            print_context("\n".join(item for item in (advisory, operator_message) if item))
            return

        return

    if tool_name == "Task":
        task_text = task_tool_text(tool_input)
        preflight = subagent_preflight_result(
            task_text,
            cwd=cwd,
            session_key=session_key,
            host=HOST,
            tool_name=str(tool_name or "Task"),
        )
        if preflight:
            decision = preflight.get("decision")
            operator_message = str(preflight.get("operator_message") or "").strip()
            if subagent_preflight_should_inject_concise(preflight):
                print_context(
                    concise_subagent_preflight_context(preflight, task_meta=task_meta)
                )
                return
            if operator_message and decision in {"routing_only", "delegate_required"}:
                print_context(operator_message)
                return
            return

        drift_result = task_drift_result(task_text, cwd, session_key=session_key)
        context = concise_subagent_preflight_context(None, task_meta=task_meta)
        drift_hint = task_drift_hint(drift_result, tool_name=str(tool_name or ""))
        if drift_hint:
            context += "\n" + drift_hint
        print_context(context)
        return

    return


if __name__ == "__main__":
    main()
