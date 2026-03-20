#!/usr/bin/env python3

import sys
from pathlib import Path

try:
    from .hook_common import (
        delegate_hint_for_text,
        load_state,
        pre_tool_payload,
        read_hook_input,
        resolve_plan_dir,
        state_summary,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from hook_common import (  # type: ignore
        delegate_hint_for_text,
        load_state,
        pre_tool_payload,
        read_hook_input,
        resolve_plan_dir,
        state_summary,
    )


def main():
    payload = read_hook_input()
    cwd = payload.get("cwd")
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    plan_dir = resolve_plan_dir(cwd=cwd)

    if not plan_dir:
        return

    state = load_state(plan_dir)
    if not state:
        return

    context = state_summary(state, tool_name=tool_name)
    if tool_name == "Task":
        task_text = " ".join(
            str(tool_input.get(key, ""))
            for key in ("description", "prompt", "command", "subagent_type")
        )
        delegate_hint = delegate_hint_for_text(task_text, state)
        if delegate_hint:
            context += "\n" + delegate_hint

    print(pre_tool_payload(context))


if __name__ == "__main__":
    main()
