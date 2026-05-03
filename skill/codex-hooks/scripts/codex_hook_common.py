#!/usr/bin/env python3

import json
import os
import re
import time
from hashlib import sha256
from pathlib import Path


HOST = "codex"
TRACKED_PLANNING_FILES = ("state.json", "progress.md", "task_plan.md", "findings.md")
SYNC_REQUIRED_FILES = ("state.json", "progress.md")


def _import_shared_hooks():
    scripts_dir = Path(__file__).resolve().parents[2] / "claude-hooks" / "scripts"
    import sys

    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


_import_shared_hooks()

from hook_common import (  # noqa: E402
    allow_delegate_hint,
    delegate_hint_from_preflight,
    explicit_task_context_eligible,
    fallback_task_advisory,
    find_named_string,
    init_task_hint,
    installed_skill_command,
    load_state,
    looks_complex,
    no_active_task_hint,
    read_hook_input,
    resolve_plan_dir,
    resolve_task_meta,
    session_key_from_payload,
    state_summary,
    task_drift_hint,
    task_drift_result,
)


MUTATING_BASH_RE = re.compile(
    r"(\bapply_patch\b|(^|[;&|]\s*)(rm|mv|cp|mkdir|touch)\b|sed\s+-i|perl\s+-pi|\btee\b|>>|>\s*[^&]|\bgit\s+(commit|merge|rebase|checkout|switch|stash|apply|cherry-pick|reset)\b|\b(npm|pnpm|yarn|bun|cargo|go|python3?|node)\b.*\b(format|fmt|fix|codegen|generate|build)\b)",
    re.IGNORECASE,
)

PLANNING_READ_RE = re.compile(
    r"(current-task\.sh|compact-context\.sh|validate-task\.sh|\.planning/[^\s]*?(state\.json|progress\.md|task_plan\.md|findings\.md))"
)

STALE_CONTEXT_RE = re.compile(
    r"(continue|resume|recover|lost context|context loss|继续|恢复|上下文|压缩|compact)",
    re.IGNORECASE,
)


def codex_session_key(payload: dict) -> str:
    explicit = os.environ.get("PLAN_SESSION_KEY", "").strip()
    if explicit:
        return explicit
    return session_key_from_payload(payload, host=HOST)


def print_context(context: str | None, hook_event_name: str | None = None) -> None:
    text = str(context or "").strip()
    if text:
        event_name = str(hook_event_name or "").strip()
        if event_name:
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": event_name,
                            "additionalContext": text,
                        }
                    },
                    ensure_ascii=False,
                )
            )
        else:
            print(text)


def codex_planning_guard_text(slug: str | None = None) -> str:
    current_task = installed_skill_command("current-task.sh", host=HOST)
    compact_context = installed_skill_command("compact-context.sh", host=HOST)
    target = f"`.planning/{slug}/progress.md` and `.planning/{slug}/state.json`" if slug else "the current task's `progress.md` and `state.json`"
    return "\n".join(
        [
            "[context-task-planning] Codex long-context guard:",
            f"- If task context may be stale, refresh it with `{current_task}` or `{compact_context}` before acting on the task.",
            f"- If this turn changes code, decisions, verification status, blockers, or next action, update {target} before the final answer.",
            "- If no planning update is needed, say why explicitly instead of silently skipping it.",
        ]
    )


def marker_dir(plan_dir: Path) -> Path:
    return plan_dir / ".derived" / "codex-hooks"


def safe_fragment(value: object) -> str:
    text = str(value or "unknown").strip() or "unknown"
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "unknown"
    if len(text) <= 80:
        return text
    return text[:64].rstrip("-") + "-" + sha256(text.encode("utf-8")).hexdigest()[:12]


def marker_path(plan_dir: Path, payload: dict) -> Path:
    session_id = payload.get("session_id") or "session"
    turn_id = payload.get("turn_id") or "turn"
    return marker_dir(plan_dir) / f"{safe_fragment(session_id)}--{safe_fragment(turn_id)}.json"


def planning_mtimes(plan_dir: Path) -> dict[str, float]:
    mtimes = {}
    for name in TRACKED_PLANNING_FILES:
        path = plan_dir / name
        try:
            mtimes[name] = path.stat().st_mtime
        except OSError:
            mtimes[name] = 0.0
    return mtimes


def sync_files_updated(plan_dir: Path, baseline: dict | None) -> bool:
    if not isinstance(baseline, dict):
        return False
    current = planning_mtimes(plan_dir)
    for name in SYNC_REQUIRED_FILES:
        try:
            previous = float(baseline.get(name) or 0.0)
        except (TypeError, ValueError):
            previous = 0.0
        if current.get(name, 0.0) > previous:
            return True
    return False


def read_marker(plan_dir: Path, payload: dict) -> dict:
    path = marker_path(plan_dir, payload)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def write_marker(plan_dir: Path, payload: dict, marker: dict) -> None:
    path = marker_path(plan_dir, payload)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        return


def create_turn_marker(
    plan_dir: Path,
    payload: dict,
    task_meta: dict | None,
    prompt: str,
) -> dict:
    slug = ""
    if isinstance(task_meta, dict):
        slug = str(task_meta.get("slug") or "")
    needs_planning_read = explicit_task_context_eligible(task_meta) and (
        looks_complex(prompt) or bool(STALE_CONTEXT_RE.search(prompt or ""))
    )
    marker = {
        "session_id": str(payload.get("session_id") or ""),
        "turn_id": str(payload.get("turn_id") or ""),
        "session_key": codex_session_key(payload),
        "task_slug": slug,
        "started_at": time.time(),
        "baseline_mtimes": planning_mtimes(plan_dir),
        "needs_planning_read": bool(needs_planning_read),
        "planning_read": False,
        "planning_updated": False,
        "tool_mutated": False,
        "stop_prompted": False,
        "tools": [],
    }
    write_marker(plan_dir, payload, marker)
    return marker


def json_text(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(value or "")


def tool_text(payload: dict) -> str:
    tool_input = payload.get("tool_input") or {}
    command = find_named_string(tool_input, {"command", "cmd", "input", "patch"})
    if command:
        return command
    return json_text(tool_input)


def tool_mentions_planning(payload: dict) -> bool:
    text = tool_text(payload)
    return bool(PLANNING_READ_RE.search(text))


def tool_is_mutating(payload: dict) -> bool:
    tool_name = str(payload.get("tool_name") or "")
    lowered = tool_name.lower()
    text = tool_text(payload)
    if lowered == "apply_patch":
        return True
    if lowered == "bash" and MUTATING_BASH_RE.search(text):
        return True
    if lowered.startswith("mcp__") and re.search(
        r"__(write|edit|update|delete|remove|create|move|rename|patch)", lowered
    ):
        return True
    return False


def update_marker_for_tool(plan_dir: Path, payload: dict) -> dict:
    marker = read_marker(plan_dir, payload)
    if not marker:
        marker = {
            "session_id": str(payload.get("session_id") or ""),
            "turn_id": str(payload.get("turn_id") or ""),
            "session_key": codex_session_key(payload),
            "task_slug": "",
            "baseline_mtimes": planning_mtimes(plan_dir),
            "needs_planning_read": False,
            "planning_read": False,
            "planning_updated": False,
            "tool_mutated": False,
            "stop_prompted": False,
            "tools": [],
        }

    tool_name = str(payload.get("tool_name") or "")
    tools = marker.setdefault("tools", [])
    if isinstance(tools, list):
        tools.append(tool_name)
        del tools[:-20]

    marker["planning_read"] = bool(marker.get("planning_read")) or tool_mentions_planning(payload)
    marker["tool_mutated"] = bool(marker.get("tool_mutated")) or tool_is_mutating(payload)
    marker["planning_updated"] = bool(marker.get("planning_updated")) or sync_files_updated(
        plan_dir, marker.get("baseline_mtimes")
    )
    marker["updated_at"] = time.time()
    write_marker(plan_dir, payload, marker)
    return marker


def stop_block_payload(reason: str) -> str:
    return json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False)


__all__ = [
    "HOST",
    "allow_delegate_hint",
    "codex_planning_guard_text",
    "codex_session_key",
    "create_turn_marker",
    "delegate_hint_from_preflight",
    "explicit_task_context_eligible",
    "fallback_task_advisory",
    "init_task_hint",
    "load_state",
    "looks_complex",
    "no_active_task_hint",
    "print_context",
    "read_hook_input",
    "read_marker",
    "resolve_plan_dir",
    "resolve_task_meta",
    "state_summary",
    "stop_block_payload",
    "sync_files_updated",
    "task_drift_hint",
    "task_drift_result",
    "update_marker_for_tool",
    "write_marker",
]
