#!/usr/bin/env python3
"""
Session binding management for context-task-planning.

Handles the relationship between sessions and tasks, including:
- Session key resolution and normalization
- Binding creation, reading, and clearing
- Writer/observer role management
"""

import hashlib
import json
import os
import re
from pathlib import Path

from constants import (
    ROLE_OBSERVER,
    ROLE_WRITER,
    SESSION_DIR_NAME,
    SESSION_KEY_ENV,
    WORKSPACE_FALLBACK_SESSION_KEY,
)
from file_utils import atomic_write_json
from file_lock import file_lock, lock_path_for


def utc_now() -> str:
    """Return current UTC timestamp in ISO format."""
    from datetime import datetime, timezone

    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def safe_json(path: Path) -> dict:
    """Safely read a JSON file, returning empty dict on error."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def resolve_session_key(explicit: str = "") -> str:
    """Resolve session key from explicit value or environment."""
    for candidate in (explicit.strip(), os.environ.get(SESSION_KEY_ENV, "").strip()):
        if candidate:
            return candidate
    return ""


def effective_session_key(explicit: str = "", fallback: bool = False) -> str:
    """Get effective session key with optional fallback."""
    session_key = resolve_session_key(explicit)
    if session_key:
        return session_key
    if fallback:
        return WORKSPACE_FALLBACK_SESSION_KEY
    return ""


def normalize_role(value: str) -> str:
    """Normalize role to either 'writer' or 'observer'."""
    return ROLE_OBSERVER if value == ROLE_OBSERVER else ROLE_WRITER


def display_session_key(session_key: str) -> str:
    """Format session key for display."""
    if not session_key:
        return "(none)"
    if session_key == WORKSPACE_FALLBACK_SESSION_KEY:
        return "workspace-default"
    return session_key


def session_registry_dir(plan_root: Path) -> Path:
    """Get the session registry directory path."""
    return plan_root / SESSION_DIR_NAME


def session_binding_name(session_key: str) -> str:
    """Generate binding filename from session key."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", session_key).strip("-.") or "session"
    digest = hashlib.sha1(session_key.encode("utf-8")).hexdigest()[:12]
    return f"{cleaned[:48]}-{digest}.json"


def session_binding_path(plan_root: Path, session_key: str) -> Path | None:
    """Get the binding file path for a session."""
    key = resolve_session_key(session_key)
    if not key:
        return None
    return session_registry_dir(plan_root) / session_binding_name(key)


def iter_session_bindings(plan_root: Path) -> list[tuple[Path, dict]]:
    """Iterate over all session bindings in a plan."""
    registry = session_registry_dir(plan_root)
    if not registry.is_dir():
        return []

    bindings = []
    for entry in registry.iterdir():
        if not entry.is_file() or entry.suffix != ".json":
            continue
        bindings.append((entry, safe_json(entry)))
    return bindings


def read_session_binding(plan_root: Path, session_key: str) -> dict:
    """Read a session binding, returning empty dict if not found."""
    key = resolve_session_key(session_key)
    if not key:
        return {}

    path = session_binding_path(plan_root, key)
    if path is None:
        return {}

    binding = safe_json(path)
    if not binding:
        return {}
    if binding.get("session_key") and binding.get("session_key") != key:
        return {}
    binding.setdefault("session_key", key)
    binding["role"] = normalize_role(str(binding.get("role") or ROLE_WRITER))
    binding.setdefault("path", str(path))
    return binding


def write_session_binding(
    plan_root: Path, session_key: str, task_slug: str, role: str = ROLE_WRITER
) -> None:
    """Write a session binding with concurrent safety."""
    key = resolve_session_key(session_key)
    if not key or not task_slug:
        return

    path = session_binding_path(plan_root, key)
    if path is None:
        return

    payload = {
        "schema_version": "1.0.0",
        "session_key": key,
        "task_slug": task_slug,
        "role": normalize_role(role),
        "updated_at": utc_now(),
    }

    # Use file lock for concurrent safety
    lock_file = lock_path_for(path, plan_root)
    with file_lock(lock_file):
        atomic_write_json(path, payload, indent=2)


def clear_session_binding(plan_root: Path, session_key: str) -> bool:
    """Clear a session binding, return True if successful."""
    path = session_binding_path(plan_root, session_key)
    if path is None or not path.exists():
        return False
    path.unlink()
    return True


def clear_task_session_bindings(plan_root: Path, task_slug: str) -> list[str]:
    """Clear all session bindings for a task, return cleared session keys."""
    cleared = []
    for path, binding in iter_session_bindings(plan_root):
        if binding.get("task_slug") != task_slug:
            continue
        session_key = str(binding.get("session_key") or "").strip()
        try:
            path.unlink()
            if session_key:
                cleared.append(session_key)
        except OSError:
            continue
    return cleared


def task_bindings(plan_root: Path, task_slug: str) -> list[dict]:
    """Get all bindings for a task."""
    bindings = []
    for path, binding in iter_session_bindings(plan_root):
        if str(binding.get("task_slug") or "").strip() != task_slug:
            continue
        session_key = str(binding.get("session_key") or "").strip()
        if not session_key:
            continue
        bindings.append(
            {
                "path": str(path),
                "session_key": session_key,
                "task_slug": task_slug,
                "role": normalize_role(str(binding.get("role") or ROLE_WRITER)),
                "updated_at": str(binding.get("updated_at") or ""),
            }
        )
    bindings.sort(
        key=lambda item: (
            item["role"] != ROLE_WRITER,
            item["updated_at"],
            item["session_key"],
        )
    )
    return bindings


def writer_binding_for_task(plan_root: Path, task_slug: str) -> dict:
    """Get the writer binding for a task, if any."""
    for binding in task_bindings(plan_root, task_slug):
        if binding["role"] == ROLE_WRITER:
            return binding
    return {}


def binding_role_for_task(plan_root: Path, session_key: str, task_slug: str) -> str:
    """Get the role of a session for a task."""
    binding = read_session_binding(plan_root, session_key)
    if str(binding.get("task_slug") or "").strip() != task_slug:
        return ""
    return normalize_role(str(binding.get("role") or ROLE_WRITER))


def demote_writer_binding(plan_root: Path, task_slug: str) -> str:
    """Demote the writer binding for a task to observer, return session key."""
    writer = writer_binding_for_task(plan_root, task_slug)
    session_key = str(writer.get("session_key") or "").strip()
    if not session_key:
        return ""
    write_session_binding(plan_root, session_key, task_slug, ROLE_OBSERVER)
    return session_key
