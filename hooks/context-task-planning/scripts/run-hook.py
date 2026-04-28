#!/usr/bin/env python3

import json
import os
import subprocess
import sys
from pathlib import Path


SKILL_NAME = "context-task-planning"
HOOK_SCRIPTS = {
    "session_start": "session_start.py",
    "user_prompt_submit": "user_prompt_submit.py",
    "post_tool_use": "post_tool_use.py",
    "stop": "stop.py",
}


def expand(path: str) -> Path:
    return Path(path).expanduser()


def git_root(cwd: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(cwd),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    root = result.stdout.strip()
    return Path(root) if root else None


def candidate_skill_dirs() -> list[Path]:
    candidates: list[Path] = []

    override = os.environ.get("CONTEXT_TASK_PLANNING_SKILL_DIR", "").strip()
    if override:
        candidates.append(expand(override))

    cwd = Path.cwd()
    root = git_root(cwd)
    if root:
        candidates.append(root / ".codex" / "skills" / SKILL_NAME)
    candidates.append(cwd / ".codex" / "skills" / SKILL_NAME)

    codex_home = expand(os.environ.get("CODEX_HOME", "~/.codex"))
    candidates.append(codex_home / "skills" / SKILL_NAME)
    candidates.append(expand("~/.codex") / "skills" / SKILL_NAME)
    candidates.append(expand("~/.agents") / "skills" / SKILL_NAME)
    candidates.append(expand("~/.claude") / "skills" / SKILL_NAME)

    # Source checkout layout: hooks/context-task-planning/scripts/run-hook.py
    for parent in Path(__file__).resolve().parents:
        candidates.append(parent / "skill")
        candidates.append(parent / ".codex" / "skills" / SKILL_NAME)

    seen: set[str] = set()
    unique: list[Path] = []
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def resolve_hook_script(hook_name: str) -> Path | None:
    script_name = HOOK_SCRIPTS.get(hook_name)
    if not script_name:
        return None
    relative = Path("codex-hooks") / "scripts" / script_name
    for skill_dir in candidate_skill_dirs():
        script = skill_dir / relative
        if script.is_file():
            return script
    return None


def warn(message: str) -> None:
    print(
        json.dumps(
            {
                "continue": True,
                "systemMessage": message,
            },
            ensure_ascii=False,
        )
    )


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in HOOK_SCRIPTS:
        names = ", ".join(sorted(HOOK_SCRIPTS))
        warn(f"context-task-planning Codex hook package was called with an unknown hook. Expected one of: {names}.")
        return 0

    hook_name = sys.argv[1]
    script = resolve_hook_script(hook_name)
    if not script:
        warn(
            "context-task-planning Codex hooks are installed, but the skill was not found. "
            "Install it with: npx skills add excitedhaha/context-task-planning -g"
        )
        return 0

    python = sys.executable or "python3"
    result = subprocess.run([python, str(script)])
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
