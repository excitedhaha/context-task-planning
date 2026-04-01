#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import compact_context
import task_guard


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="compact_sync.py")
    parser.add_argument("--task", default="")
    parser.add_argument("--cwd", default="")
    parser.add_argument("--session-key", default="")
    parser.add_argument("--host", default="")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def run_validate_fix(cwd: str, task_slug: str) -> dict:
    command = [
        "sh",
        str(SCRIPT_DIR / "validate-task.sh"),
        "--task",
        task_slug,
        "--fix-warnings",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=cwd or None,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        return {
            "status": "failed",
            "attempted": True,
            "applied": False,
            "message": str(exc),
            "output": "",
        }

    output = (result.stdout or "").strip()
    if result.returncode != 0:
        message = (result.stderr or output or "validate-task failed").strip()
        return {
            "status": "failed",
            "attempted": True,
            "applied": False,
            "message": message,
            "output": output,
        }

    applied = "Applied warning fixes for" in output
    return {
        "status": "applied" if applied else "no_changes",
        "attempted": True,
        "applied": applied,
        "message": "warning-level planning sync complete",
        "output": output,
    }


def refresh_compact_artifact(task: dict) -> dict:
    plan_dir = Path(task["plan_dir"])
    artifact_path = compact_context.artifact_path_for(plan_dir)
    workspace_root = Path(task["workspace_root"])

    try:
        current = compact_context.build_payload(task)
        compact_context.persist_payload(current, plan_dir)
    except Exception as exc:  # pragma: no cover - defensive fail-open path
        return {
            "status": "failed",
            "persisted": False,
            "path": compact_context.rel_path(workspace_root, artifact_path),
            "message": str(exc),
        }

    return {
        "status": "persisted",
        "persisted": True,
        "path": compact_context.rel_path(workspace_root, artifact_path),
        "message": "derived compact context refreshed",
    }


def render_text(result: dict) -> str:
    if not result.get("found"):
        return "[context-task-planning] No task found for compact sync."

    task_slug = result.get("task", {}).get("slug") or "(unknown)"
    role = result.get("task", {}).get("binding_role") or "unbound"
    host = result.get("host") or "(unspecified)"
    lines = [
        f"[context-task-planning] Compact sync task `{task_slug}` | role `{role}` | host `{host}`",
        f"[context-task-planning] Main planning sync: {result.get('main_sync', {}).get('status', 'skipped')}",
        (
            "[context-task-planning] Compact artifact: "
            f"{result.get('artifact_sync', {}).get('path', '(unknown)')} -> "
            f"{result.get('artifact_sync', {}).get('status', 'unknown')}"
        ),
    ]

    warnings = list(result.get("warnings") or [])
    if warnings:
        lines.append("[context-task-planning] Warnings:")
        for item in warnings:
            lines.append(f"  - {item}")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    task = task_guard.resolve_task(args.cwd, args.task, args.session_key)
    result = {
        "ok": True,
        "found": bool(task.get("found")),
        "host": args.host,
        "task": {
            "slug": str(task.get("slug") or ""),
            "binding_role": str(task.get("binding_role") or ""),
            "selection_source": str(task.get("selection_source") or ""),
        },
        "main_sync": {
            "status": "skipped",
            "attempted": False,
            "applied": False,
            "message": "",
            "output": "",
        },
        "artifact_sync": {
            "status": "skipped",
            "persisted": False,
            "path": "",
            "message": "",
        },
        "warnings": [],
    }

    if not task.get("found"):
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(render_text(result))
        return

    role = str(task.get("binding_role") or "").strip()
    if role == task_guard.ROLE_WRITER:
        main_sync = run_validate_fix(args.cwd, str(task.get("slug") or ""))
        result["main_sync"] = main_sync
        if main_sync["status"] == "failed":
            result["ok"] = False
            result["warnings"].append(main_sync["message"])
    elif role == task_guard.ROLE_OBSERVER:
        result["main_sync"] = {
            "status": "skipped_observer",
            "attempted": False,
            "applied": False,
            "message": "observer sessions must not edit main planning files",
            "output": "",
        }
    else:
        result["main_sync"] = {
            "status": "skipped_unbound",
            "attempted": False,
            "applied": False,
            "message": "no writer binding resolved for main planning sync",
            "output": "",
        }

    artifact_sync = refresh_compact_artifact(task)
    result["artifact_sync"] = artifact_sync
    if artifact_sync["status"] == "failed":
        result["ok"] = False
        result["warnings"].append(artifact_sync["message"])

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(render_text(result))


if __name__ == "__main__":
    main()
