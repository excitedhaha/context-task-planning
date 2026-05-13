#!/usr/bin/env python3

from trae_hook_common import (
    bootstrap_session_binding_after_init,
    read_hook_input,
    resolve_plan_dir,
    trae_session_key,
    update_marker_for_tool,
)


def main() -> None:
    payload = read_hook_input()
    cwd = payload.get("cwd")
    session_key = trae_session_key(payload)
    plan_dir = resolve_plan_dir(cwd=cwd, session_key=session_key)
    if not plan_dir:
        return

    update_marker_for_tool(plan_dir, payload)
    bootstrap_session_binding_after_init(cwd, payload)


if __name__ == "__main__":
    main()
