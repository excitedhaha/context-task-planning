#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
TEMPLATE_DIR="$SKILL_ROOT/templates"

TASK_TITLE=""
TASK_SLUG=""
TASK_REPOS=""
PRIMARY_REPO=""
ALLOW_DIRTY=0
AUTO_STASH=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --stash)
            AUTO_STASH=1
            ;;
        --allow-dirty)
            ALLOW_DIRTY=1
            ;;
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
        --repo)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --repo" >&2; exit 1; }
            TASK_REPOS="$TASK_REPOS $1"
            ;;
        --primary)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --primary" >&2; exit 1; }
            PRIMARY_REPO="$1"
            ;;
        -h|--help)
            echo "Usage: $0 [--stash] [--allow-dirty] [--slug task-slug] [--title \"Task Title\"] [--repo repo-id] [--primary repo-id] [task title]" >&2
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
    echo "Usage: $0 [--stash] [--allow-dirty] [--slug task-slug] [--title \"Task Title\"] [--repo repo-id] [--primary repo-id] [task title]" >&2
    exit 1
fi

if [ "$ALLOW_DIRTY" -eq 1 ] && [ "$AUTO_STASH" -eq 1 ]; then
    echo "Choose only one of --stash or --allow-dirty." >&2
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

if [ "$AUTO_STASH" -eq 1 ]; then
    sh "$SCRIPT_DIR/ensure-switch-safety.sh" --cwd "$WORKSPACE_ROOT" --target-task "$TASK_SLUG" --stash
elif [ "$ALLOW_DIRTY" -eq 1 ]; then
    sh "$SCRIPT_DIR/ensure-switch-safety.sh" --cwd "$WORKSPACE_ROOT" --target-task "$TASK_SLUG" --allow-dirty
else
    sh "$SCRIPT_DIR/ensure-switch-safety.sh" --cwd "$WORKSPACE_ROOT" --target-task "$TASK_SLUG"
fi

mkdir -p "$PLAN_DIR/delegates"

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "Python is required to initialize task files." >&2
    exit 1
fi

export TASK_TITLE TASK_SLUG WORKSPACE_ROOT PLAN_DIR TEMPLATE_DIR TASK_REPOS PRIMARY_REPO
"$PYTHON_BIN" <<'PY'
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

task_title = os.environ["TASK_TITLE"]
task_slug = os.environ["TASK_SLUG"]
workspace_root = Path(os.environ["WORKSPACE_ROOT"])
plan_dir = Path(os.environ["PLAN_DIR"])
template_dir = Path(os.environ["TEMPLATE_DIR"])
raw_repo_ids = os.environ.get("TASK_REPOS", "")
primary_repo = os.environ.get("PRIMARY_REPO", "").strip()
repo_registry_path = workspace_root / ".planning" / ".runtime" / "repos.json"

timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
planning_path = Path(".planning") / task_slug
initial_next_action = "Fill in goal, non-goals, constraints, and open questions before implementation."


def normalize_repo_id(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = re.sub(r"-+", "-", lowered).strip("-")
    return lowered


repo_scope = []
for item in raw_repo_ids.split():
    repo_id = normalize_repo_id(item)
    if repo_id and repo_id not in repo_scope:
        repo_scope.append(repo_id)

primary_repo = normalize_repo_id(primary_repo)
if primary_repo and primary_repo not in repo_scope:
    raise SystemExit("--primary must be part of the --repo scope.")
if not primary_repo and repo_scope:
    primary_repo = repo_scope[0]

if repo_scope:
    try:
        repo_registry = json.loads(repo_registry_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit("Register workspace repos before creating a task with --repo.")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid repo registry at {repo_registry_path}: {exc}")

    registered_ids = {
        normalize_repo_id(str(item.get("id") or ""))
        for item in repo_registry.get("repos", [])
        if isinstance(item, dict)
    }
    missing = [repo_id for repo_id in repo_scope if repo_id not in registered_ids]
    if missing:
        raise SystemExit(
            "Register these repos before using them in --repo: " + ", ".join(missing)
        )

repo_scope_text = ", ".join(f"`{repo_id}`" for repo_id in repo_scope) if repo_scope else "(unset)"
primary_repo_text = f"`{primary_repo}`" if primary_repo else "(unset)"

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
            f"Primary repo: {primary_repo or '(unset)'}",
            f"Repo scope: {', '.join(repo_scope) if repo_scope else '(unset)'}",
            "Only the coordinator updates task_plan.md, progress.md, and state.json",
        ],
        "open_questions": [],
        "repo_scope": repo_scope,
        "primary_repo": primary_repo,
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


def upsert_line(lines: list[str], prefix: str, replacement: str, after_prefix: str = "") -> list[str]:
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = replacement
            return lines
    if after_prefix:
        for index, line in enumerate(lines):
            if line.startswith(after_prefix):
                lines.insert(index + 1, replacement)
                return lines
    lines.append(replacement)
    return lines


task_plan_path = plan_dir / "task_plan.md"
if task_plan_path.exists():
    lines = task_plan_path.read_text(encoding="utf-8").splitlines()
    lines = upsert_line(lines, "- Primary Repo:", f"- Primary Repo: {primary_repo_text}", after_prefix="- Next Action:")
    lines = upsert_line(lines, "- Repo Scope:", f"- Repo Scope: {repo_scope_text}", after_prefix="- Primary Repo:")
    lines = upsert_line(lines, "- Primary Repo Constraint:", f"- Primary Repo Constraint: {primary_repo_text}", after_prefix="- Planning Path:")
    lines = upsert_line(lines, "- Repo Scope Constraint:", f"- Repo Scope Constraint: {', '.join(repo_scope) if repo_scope else '(unset)'}", after_prefix="- Primary Repo Constraint:")
    task_plan_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

progress_path = plan_dir / "progress.md"
if progress_path.exists():
    lines = progress_path.read_text(encoding="utf-8").splitlines()
    lines = upsert_line(lines, "- Primary Repo:", f"- Primary Repo: {primary_repo_text}", after_prefix="- Next Action:")
    lines = upsert_line(lines, "- Repo Scope:", f"- Repo Scope: {repo_scope_text}", after_prefix="- Primary Repo:")
    progress_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

mkdir -p "$PLAN_ROOT"

if [ -n "${PLAN_SESSION_KEY:-}" ]; then
    "$PYTHON_BIN" "$SCRIPT_DIR/task_guard.py" bind-session-task --cwd "$WORKSPACE_ROOT" --task "$TASK_SLUG" --role writer
else
    "$PYTHON_BIN" "$SCRIPT_DIR/task_guard.py" bind-session-task --cwd "$WORKSPACE_ROOT" --task "$TASK_SLUG" --role writer --fallback
    printf '%s\n' "$TASK_SLUG" > "$ACTIVE_FILE"
fi

echo "Task ready: $TASK_TITLE"
echo "Task slug: $TASK_SLUG"
echo "Workspace root: $WORKSPACE_ROOT"
echo "Task directory: $PLAN_DIR"
if [ -n "$PRIMARY_REPO" ]; then
    echo "Primary repo: $PRIMARY_REPO"
fi
if [ -n "$TASK_REPOS" ]; then
    echo "Repo scope:${TASK_REPOS}"
fi
if [ -n "${PLAN_SESSION_KEY:-}" ]; then
    echo "Session writer binding: ${PLAN_SESSION_KEY} -> $TASK_SLUG"
else
    echo "Workspace fallback writer task: $TASK_SLUG"
fi
echo "Manual task override:"
echo "  export PLAN_TASK=$TASK_SLUG"
