#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import time
from pathlib import Path

RESET = "\033[0m"
BLACK = "\033[30m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
WHITE = "\033[97m"
GRAY = "\033[90m"
BG_BLUE = "\033[44m"
BG_GREEN = "\033[42m"
BG_MAGENTA = "\033[45m"
BG_RED = "\033[41m"

SPINNER_FRAMES = ("-", "\\", "|", "/")

TASK_GUARD_IMPORT_OK = False
try:
    scripts_dir = Path(__file__).resolve().parents[2] / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from task_guard import resolve_task as resolve_guard_task  # type: ignore

    TASK_GUARD_IMPORT_OK = True
except ImportError:
    resolve_guard_task = None  # type: ignore


def color(text: str, ansi: str) -> str:
    return f"{ansi}{text}{RESET}"


def pick_cwd(payload: dict) -> str:
    candidates = [
        payload.get("workspace", {}).get("current_dir"),
        payload.get("workspace", {}).get("cwd"),
        payload.get("cwd"),
        payload.get("current_dir"),
        os.getcwd(),
    ]
    for value in candidates:
        if isinstance(value, str) and value:
            return value
    return os.getcwd()


def shorten_path(cwd: str) -> str:
    home = str(Path.home())
    display = cwd
    if cwd == home:
        return "~"
    if cwd.startswith(home + os.sep):
        display = "~" + cwd[len(home) :]

    parts = [part for part in display.split("/") if part]
    if display.startswith("~"):
        parts = ["~", *parts[1:]] if parts and parts[0] == "~" else ["~", *parts]

    if len(parts) <= 3:
        return "/".join(parts)

    head = parts[0]
    middle = [p[0] if p not in {"~", ""} else p for p in parts[1:-2]]
    tail = parts[-2:]
    return "/".join([head, *middle, *tail])


def shorten_label(text: str, max_length: int = 30) -> str:
    if len(text) <= max_length:
        return text
    if max_length < 9:
        return text[:max_length]
    head = (max_length - 1) // 2
    tail = max_length - head - 1
    return f"{text[:head]}~{text[-tail:]}"


def run_git(cwd: str, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True,
            text=True,
            timeout=0.4,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def git_branch(cwd: str) -> str:
    branch = run_git(cwd, "symbolic-ref", "--short", "HEAD")
    if branch:
        return branch
    return run_git(cwd, "rev-parse", "--short", "HEAD")


def git_dirty(cwd: str) -> bool:
    output = run_git(cwd, "status", "--porcelain")
    return bool(output)


def context_color(used: float) -> str:
    if used >= 85:
        return RED
    if used >= 70:
        return YELLOW
    return GREEN


def format_k_tokens(value: float) -> str:
    return f"{value / 1000:.1f}k"


def extract_context_usage(
    payload: dict,
) -> tuple[float | None, float | None, float | None]:
    context = payload.get("context_window", {})

    used_pct = context.get("used_percentage")
    used_tokens = context.get("used_tokens")
    max_tokens = context.get("max_tokens")

    current_usage = payload.get("current_usage")
    if isinstance(current_usage, dict):
        if not isinstance(used_pct, (int, float)):
            used_pct = current_usage.get("context_window_used_percentage")
        if not isinstance(used_tokens, (int, float)):
            used_tokens = current_usage.get("context_window_used_tokens")
        if not isinstance(max_tokens, (int, float)):
            max_tokens = current_usage.get("context_window_max_tokens")

    used_pct = float(used_pct) if isinstance(used_pct, (int, float)) else None
    used_tokens = float(used_tokens) if isinstance(used_tokens, (int, float)) else None
    max_tokens = float(max_tokens) if isinstance(max_tokens, (int, float)) else None
    return used_pct, used_tokens, max_tokens


def is_busy(payload: dict) -> bool:
    candidates = [
        payload.get("busy"),
        payload.get("is_busy"),
        payload.get("isBusy"),
        payload.get("in_progress"),
        payload.get("is_running"),
        payload.get("isRunning"),
        payload.get("streaming"),
        payload.get("workspace", {}).get("busy"),
        payload.get("status", {}).get("busy")
        if isinstance(payload.get("status"), dict)
        else None,
    ]
    return any(value is True for value in candidates)


def spinner_frame() -> str:
    return SPINNER_FRAMES[int(time.time() * 10) % len(SPINNER_FRAMES)]


def resolve_task(cwd: str) -> dict | None:
    if not TASK_GUARD_IMPORT_OK or resolve_guard_task is None:
        return None
    try:
        return resolve_guard_task(cwd, "")
    except Exception:
        return None


def task_segment(cwd: str) -> str | None:
    task = resolve_task(cwd)
    if not task:
        return None

    if task.get("found"):
        slug = shorten_label(task.get("slug") or "(unknown)")
        prefix = "task"
        style = BG_BLUE + WHITE
        if task.get("selection_source") == "session_pin":
            prefix = "task!"
            style = BG_GREEN + BLACK
        return color(f" {prefix}:{slug} ", style)

    plan_root = task.get("plan_root")
    if isinstance(plan_root, str) and Path(plan_root).is_dir():
        return color(" task:none ", YELLOW)
    return None


def main() -> int:
    try:
        raw = sys.stdin.read().strip()
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    cwd = pick_cwd(payload)
    path_text = shorten_path(cwd)
    branch = git_branch(cwd)
    dirty = git_dirty(cwd) if branch else False

    parts = []
    if is_busy(payload):
        parts.append(color(spinner_frame(), BLUE))
    else:
        parts.append(color(">", GREEN))

    parts.append(color(path_text, CYAN))

    task_text = task_segment(cwd)
    if task_text:
        parts.append(task_text)

    if branch:
        branch_mark = "*" if dirty else ""
        git_text = f" git:{branch}{branch_mark} "
        git_style = BG_RED + WHITE if dirty else BG_MAGENTA + WHITE
        parts.append(color(git_text, git_style))

    used_pct, used_tokens, max_tokens = extract_context_usage(payload)
    if used_pct is not None:
        usage_text = f"CTX {used_pct:.0f}%"
        if used_tokens is not None and max_tokens is not None and max_tokens > 0:
            usage_text += (
                f" ({format_k_tokens(used_tokens)}/{format_k_tokens(max_tokens)})"
            )
        elif used_tokens is not None:
            usage_text += f" ({format_k_tokens(used_tokens)})"
        parts.append(color(usage_text, context_color(used_pct)))

    model = payload.get("model", {}).get("display_name")
    if isinstance(model, str) and model:
        parts.append(color(f"MODEL {model}", GRAY))

    separator = color(" | ", WHITE)
    sys.stdout.write(separator.join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
