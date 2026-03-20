#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
TEMPLATE_DIR="$SKILL_ROOT/templates"

TASK_TITLE=""
TASK_SLUG=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --slug)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --slug" >&2; exit 1; }
            TASK_SLUG="$1"
            ;;
        --title)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --title" >&2; exit 1; }
            TASK_TITLE="$1"
            ;;
        -h|--help)
            echo "Usage: $0 [--slug task-slug] [--title \"Task Title\"] [task title]" >&2
            exit 0
            ;;
        *)
            if [ -z "$TASK_TITLE" ]; then
                TASK_TITLE="$1"
            else
                TASK_TITLE="$TASK_TITLE $1"
            fi
            ;;
    esac
    shift
done

if [ -z "$TASK_TITLE" ] && [ -z "$TASK_SLUG" ]; then
    echo "Usage: $0 [--slug task-slug] [--title \"Task Title\"] [task title]" >&2
    exit 1
fi

if [ -z "$TASK_SLUG" ]; then
    TASK_SLUG=$(sh "$SCRIPT_DIR/slugify.sh" "$TASK_TITLE")
else
    TASK_SLUG=$(sh "$SCRIPT_DIR/slugify.sh" "$TASK_SLUG")
fi

if [ -z "$TASK_TITLE" ]; then
    TASK_TITLE="$TASK_SLUG"
fi

WORKSPACE_ROOT=$(sh "$SCRIPT_DIR/resolve-workspace-root.sh")
PLAN_ROOT="$WORKSPACE_ROOT/.planning"
PLAN_DIR="$PLAN_ROOT/$TASK_SLUG"
ACTIVE_FILE="$PLAN_ROOT/.active_task"

mkdir -p "$PLAN_DIR/delegates"

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "Python is required to initialize task files." >&2
    exit 1
fi

export TASK_TITLE TASK_SLUG WORKSPACE_ROOT PLAN_DIR TEMPLATE_DIR
"$PYTHON_BIN" <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

task_title = os.environ["TASK_TITLE"]
task_slug = os.environ["TASK_SLUG"]
workspace_root = Path(os.environ["WORKSPACE_ROOT"])
plan_dir = Path(os.environ["PLAN_DIR"])
template_dir = Path(os.environ["TEMPLATE_DIR"])

timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
planning_path = Path(".planning") / task_slug
initial_next_action = "Fill in goal, non-goals, constraints, and open questions before implementation."

replacements = {
    "{{TASK_TITLE}}": task_title,
    "{{TASK_SLUG}}": task_slug,
    "{{SOURCE_PATH}}": str(workspace_root),
    "{{CREATED_AT}}": timestamp,
    "{{INITIAL_NEXT_ACTION}}": initial_next_action,
    "{{DELEGATE_TITLE}}": "delegate-task",
    "{{DELEGATE_ID}}": "delegate-id",
    "{{DELEGATE_KIND}}": "discovery",
}

for template_name in ("task_plan.md", "findings.md", "progress.md"):
    target = plan_dir / template_name
    if target.exists():
        continue
    content = (template_dir / template_name).read_text(encoding="utf-8")
    for key, value in replacements.items():
        content = content.replace(key, value)
    target.write_text(content, encoding="utf-8")

state_path = plan_dir / "state.json"
if not state_path.exists():
    state = {
        "schema_version": "1.0.0",
        "slug": task_slug,
        "title": task_title,
        "status": "active",
        "mode": "clarify",
        "goal": "",
        "non_goals": [],
        "constraints": [
            f"Source path: {workspace_root}",
            f"Planning path: {planning_path}",
            "Only the coordinator updates task_plan.md, progress.md, and state.json",
        ],
        "open_questions": [],
        "source_path": str(workspace_root),
        "planning_path": str(planning_path),
        "current_phase": "clarify",
        "next_action": initial_next_action,
        "blockers": [],
        "verify_commands": [],
        "latest_checkpoint": "Task workspace initialized.",
        "phases": [
            {
                "id": "clarify",
                "title": "Clarify Requirements",
                "status": "in_progress",
                "definition_of_done": [
                    "Goal, non-goals, constraints, and open questions are captured"
                ],
                "verification": [
                    "Critical ambiguities are either resolved or explicitly tracked"
                ],
            },
            {
                "id": "plan",
                "title": "Plan Execution",
                "status": "pending",
                "definition_of_done": [
                    "Phases, decision points, and verification targets are documented"
                ],
                "verification": [
                    "Next action is concrete enough to start implementation"
                ],
            },
            {
                "id": "execute",
                "title": "Execute Work",
                "status": "pending",
                "definition_of_done": [
                    "Main work is completed in small, reviewable steps"
                ],
                "verification": [
                    "Implementation or research outputs are ready for validation"
                ],
            },
            {
                "id": "verify",
                "title": "Verify Results",
                "status": "pending",
                "definition_of_done": [
                    "Verification results are recorded with actual outcomes"
                ],
                "verification": [
                    "Definition of done is satisfied or blockers are recorded"
                ],
            },
        ],
        "delegation": {
            "enabled": True,
            "single_writer": True,
            "active": [],
        },
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
PY

mkdir -p "$PLAN_ROOT"
printf '%s\n' "$TASK_SLUG" > "$ACTIVE_FILE"

echo "Task ready: $TASK_TITLE"
echo "Task slug: $TASK_SLUG"
echo "Workspace root: $WORKSPACE_ROOT"
echo "Task directory: $PLAN_DIR"
echo "Set PLAN_TASK to pin this session:"
echo "  export PLAN_TASK=$TASK_SLUG"
