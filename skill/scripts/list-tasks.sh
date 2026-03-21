#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WORKSPACE_ROOT=$(sh "$SCRIPT_DIR/resolve-workspace-root.sh")
PLAN_ROOT="$WORKSPACE_ROOT/.planning"
ACTIVE_SLUG=""
SESSION_KEY="${PLAN_SESSION_KEY:-}"

if [ -f "$PLAN_ROOT/.active_task" ]; then
    ACTIVE_SLUG=$(tr -d '\r\n' < "$PLAN_ROOT/.active_task")
fi

if [ ! -d "$PLAN_ROOT" ]; then
    echo "[context-task-planning] No .planning directory found under $WORKSPACE_ROOT"
    exit 0
fi

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "[context-task-planning] Python is required to list tasks."
    exit 0
fi

"$PYTHON_BIN" - "$PLAN_ROOT" "$ACTIVE_SLUG" "${PLAN_TASK:-}" "$SESSION_KEY" <<'PY'
import json
import sys
from pathlib import Path

plan_root = Path(sys.argv[1])
active_slug = sys.argv[2]
pinned_slug = sys.argv[3]
session_key = sys.argv[4]
workspace_fallback = "workspace:default"


def normalize_role(value: str) -> str:
    return "observer" if value == "observer" else "writer"


def display_session_key(value: str) -> str:
    if not value:
        return "-"
    if value == workspace_fallback:
        return "workspace-default"
    return value

observer_counts = {}
writer_by_slug = {}
session_binding_slug = ""
session_binding_role = ""
session_dir = plan_root / ".sessions"
if session_dir.is_dir():
    for entry in session_dir.iterdir():
        if not entry.is_file() or entry.suffix != ".json":
            continue
        try:
            binding = json.loads(entry.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        slug = str(binding.get("task_slug") or "").strip()
        role = normalize_role(str(binding.get("role") or "writer"))
        binding_session = str(binding.get("session_key") or "").strip()
        if slug:
            if role == "writer":
                writer_by_slug[slug] = display_session_key(binding_session)
            else:
                observer_counts[slug] = observer_counts.get(slug, 0) + 1
        if session_key and binding_session == session_key:
            session_binding_slug = slug
            session_binding_role = role

if active_slug and active_slug not in writer_by_slug:
    writer_by_slug[active_slug] = display_session_key(workspace_fallback)

rows = []
for entry in plan_root.iterdir():
    if not entry.is_dir() or entry.name.startswith('.'):
        continue

    state_file = entry / "state.json"
    state = {}
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {}

    slug = state.get("slug", entry.name)
    title = state.get("title", "")
    status = state.get("status", "unknown")
    mode = state.get("mode", "-")
    updated = state.get("updated_at", "")

    markers = []
    if slug == active_slug:
        markers.append("default")
    if pinned_slug and slug == pinned_slug:
        markers.append("pinned")
    if session_binding_slug and slug == session_binding_slug:
        markers.append("writer" if session_binding_role == "writer" else "observe")

    rows.append(
        {
            "markers": ",".join(markers) if markers else "-",
            "slug": slug,
            "status": status,
            "mode": mode,
            "writer": writer_by_slug.get(slug, "-"),
            "observers": str(observer_counts.get(slug, 0)),
            "updated": updated or "-",
            "title": title or "-",
        }
    )

if not rows:
    print(f"[context-task-planning] No tasks found in {plan_root}")
    sys.exit(0)

rows.sort(key=lambda row: row["updated"], reverse=True)
rows.sort(key=lambda row: row["status"] == "archived")

print(f"[context-task-planning] Workspace: {plan_root.parent}")
print(f"[context-task-planning] Task root: {plan_root}")
print(f"[context-task-planning] Active pointer: {active_slug or '(none)'}")
print(f"[context-task-planning] Session pin: {pinned_slug or '(none)'}")
print(f"[context-task-planning] Session key: {session_key or '(none)'}")
binding_text = session_binding_slug or '(none)'
if session_binding_slug:
    binding_text = f"{session_binding_slug} ({session_binding_role})"
print(f"[context-task-planning] Session binding: {binding_text}")
print("")

headers = ["MARK", "SLUG", "STATUS", "MODE", "WRITER", "OBS", "UPDATED", "TITLE"]
widths = [
    max(len(headers[0]), *(len(row["markers"]) for row in rows)),
    max(len(headers[1]), *(len(row["slug"]) for row in rows)),
    max(len(headers[2]), *(len(row["status"]) for row in rows)),
    max(len(headers[3]), *(len(row["mode"]) for row in rows)),
    max(len(headers[4]), *(len(row["writer"]) for row in rows)),
    max(len(headers[5]), *(len(row["observers"]) for row in rows)),
    max(len(headers[6]), *(len(row["updated"]) for row in rows)),
    max(len(headers[7]), *(len(row["title"]) for row in rows)),
]

fmt = "  ".join(f"{{:{width}}}" for width in widths)
print(fmt.format(*headers))
print(fmt.format(*["-" * width for width in widths]))
for row in rows:
    print(
        fmt.format(
            row["markers"],
            row["slug"],
            row["status"],
            row["mode"],
            row["writer"],
            row["observers"],
            row["updated"],
            row["title"],
        )
    )
PY
