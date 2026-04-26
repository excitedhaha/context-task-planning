#!/usr/bin/env python3

from codex_hook_common import (
    codex_session_key,
    read_hook_input,
    resolve_plan_dir,
    update_marker_for_tool,
)


def main() -> None:
    payload = read_hook_input()
    cwd = payload.get("cwd")
    session_key = codex_session_key(payload)
    plan_dir = resolve_plan_dir(cwd=cwd, session_key=session_key)
    if not plan_dir:
        return

    update_marker_for_tool(plan_dir, payload)


if __name__ == "__main__":
    main()
