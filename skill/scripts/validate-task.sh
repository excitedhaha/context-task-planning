#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

TASK_SLUG=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --task)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --task" >&2; exit 1; }
            TASK_SLUG="$1"
            ;;
        -h|--help)
            echo "Usage: $0 [--task slug]" >&2
            exit 0
            ;;
        *)
            echo "Unexpected argument: $1" >&2
            exit 1
            ;;
    esac
    shift
done

PLAN_DIR=$(sh "$SCRIPT_DIR/resolve-plan-dir.sh" "$TASK_SLUG")
if [ -z "$PLAN_DIR" ] || [ ! -d "$PLAN_DIR" ]; then
    echo "[context-task-planning] No task found to validate." >&2
    exit 1
fi

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "[context-task-planning] Python is required to validate tasks." >&2
    exit 1
fi

"$PYTHON_BIN" - "$PLAN_DIR" <<'PY'
import json
import re
import sys
from pathlib import Path

plan_dir = Path(sys.argv[1])
state_file = plan_dir / "state.json"
task_plan_file = plan_dir / "task_plan.md"
findings_file = plan_dir / "findings.md"
progress_file = plan_dir / "progress.md"
delegates_dir = plan_dir / "delegates"

issues: list[str] = []
warnings: list[str] = []


def add_issue(message: str) -> None:
    issues.append(message)


def add_warning(message: str) -> None:
    warnings.append(message)


def read_json(path: Path, label: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        add_issue(f"Missing required file: {label} ({path})")
    except json.JSONDecodeError as exc:
        add_issue(f"Invalid JSON in {label}: {exc}")
    return None


def extract_inline_value(line: str) -> str:
    text = line.split(":", 1)[1].strip()
    if text.startswith("`") and text.endswith("`") and text.count("`") == 2:
        return text[1:-1].strip()
    return text


def parse_task_plan_hot_context(path: Path):
    fields = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    in_hot_context = False
    for line in lines:
        if line.startswith("## Hot Context"):
            in_hot_context = True
            continue
        if in_hot_context and line.startswith("## "):
            break
        if not in_hot_context:
            continue

        if line.startswith("- Task Slug:"):
            fields["slug"] = extract_inline_value(line)
        elif line.startswith("- Task Status:"):
            fields["status"] = extract_inline_value(line)
        elif line.startswith("- Goal:"):
            fields["goal"] = extract_inline_value(line)
        elif line.startswith("- Current Mode:"):
            fields["mode"] = extract_inline_value(line)
        elif line.startswith("- Current Phase:"):
            fields["phase"] = extract_inline_value(line)
        elif line.startswith("- Next Action:"):
            fields["next_action"] = extract_inline_value(line)
    return fields


def parse_progress_snapshot(path: Path):
    fields = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    in_snapshot = False
    for line in lines:
        if line.startswith("## Snapshot"):
            in_snapshot = True
            continue
        if in_snapshot and line.startswith("## "):
            break
        if not in_snapshot:
            continue

        if line.startswith("- Task Slug:"):
            fields["slug"] = extract_inline_value(line)
        elif line.startswith("- Status:"):
            fields["status"] = extract_inline_value(line)
        elif line.startswith("- Current Mode:"):
            fields["mode"] = extract_inline_value(line)
        elif line.startswith("- Current Phase:"):
            fields["phase"] = extract_inline_value(line)
        elif line.startswith("- Next Action:"):
            fields["next_action"] = extract_inline_value(line)
        elif line.startswith("- Last Updated:"):
            fields["last_updated"] = extract_inline_value(line)
    return fields


def normalize_free_text(value: str) -> str:
    return " ".join(value.replace("`", "").split())


for required in (task_plan_file, findings_file, progress_file, state_file):
    if not required.exists():
        add_issue(f"Missing required file: {required.name}")

state = read_json(state_file, "state.json") if state_file.exists() else None
if state is None:
    state = {}

required_state_keys = [
    "slug",
    "title",
    "status",
    "mode",
    "goal",
    "planning_path",
    "current_phase",
    "next_action",
    "blockers",
    "verify_commands",
    "phases",
    "delegation",
]
for key in required_state_keys:
    if key not in state:
        add_issue(f"state.json is missing required key `{key}`")

valid_task_statuses = {"active", "paused", "blocked", "verifying", "done", "archived"}
valid_modes = {"clarify", "plan", "execute", "verify", "archive"}
valid_phase_statuses = {"pending", "in_progress", "complete", "blocked"}
active_delegate_statuses = {"pending", "running", "blocked"}
terminal_delegate_statuses = {"complete", "cancelled"}

if state:
    if state.get("status") not in valid_task_statuses:
        add_issue(f"Unknown task status in state.json: {state.get('status')}")
    if state.get("mode") not in valid_modes:
        add_issue(f"Unknown task mode in state.json: {state.get('mode')}")

    phases = state.get("phases", [])
    phase_ids = []
    for phase in phases:
        phase_id = phase.get("id")
        if not phase_id:
            add_issue("A phase in state.json is missing `id`")
            continue
        phase_ids.append(phase_id)
        if phase.get("status") not in valid_phase_statuses:
            add_issue(f"Unknown phase status for `{phase_id}`: {phase.get('status')}")
    current_phase = state.get("current_phase")
    if current_phase and current_phase not in phase_ids and current_phase != "archive":
        add_issue(f"current_phase `{current_phase}` is not present in state.json phases")

    delegation = state.get("delegation", {})
    active_delegates = delegation.get("active", [])
    if not isinstance(active_delegates, list):
        add_issue("state.json delegation.active must be a list")
        active_delegates = []
    if len(active_delegates) != len(set(active_delegates)):
        add_issue("state.json delegation.active contains duplicate delegate ids")

if task_plan_file.exists() and state:
    hot = parse_task_plan_hot_context(task_plan_file)
    required_hot = ["slug", "status", "goal", "mode", "phase", "next_action"]
    for key in required_hot:
        if key not in hot:
            add_issue(f"task_plan.md Hot Context is missing `{key}`")

    expected_hot = {
        "slug": state.get("slug", ""),
        "status": state.get("status", ""),
        "mode": state.get("mode", ""),
        "phase": state.get("current_phase", ""),
        "next_action": state.get("next_action", ""),
    }
    for key, expected in expected_hot.items():
        actual = hot.get(key)
        if actual is None:
            continue
        actual_cmp = normalize_free_text(actual) if key == "next_action" else actual
        expected_cmp = normalize_free_text(expected) if key == "next_action" else expected
        if actual_cmp != expected_cmp:
            if key == "next_action" and actual.strip() == "[fill this first]":
                add_warning("task_plan.md Hot Context next_action is still a placeholder; sync it with state.json")
                continue
            add_issue(f"task_plan.md Hot Context `{key}` does not match state.json (`{actual}` != `{expected}`)")

    state_goal = str(state.get("goal", "")).strip()
    hot_goal = str(hot.get("goal", "")).strip()
    if state_goal:
        if not hot_goal:
            add_warning("task_plan.md Hot Context goal is empty while state.json goal is populated")
        elif normalize_free_text(hot_goal) != normalize_free_text(state_goal):
            add_warning("task_plan.md Hot Context goal differs from state.json goal")

if progress_file.exists() and state:
    snapshot = parse_progress_snapshot(progress_file)
    expected_snapshot = {
        "slug": state.get("slug", ""),
        "status": state.get("status", ""),
        "mode": state.get("mode", ""),
        "phase": state.get("current_phase", ""),
        "next_action": state.get("next_action", ""),
    }
    for key, expected in expected_snapshot.items():
        actual = snapshot.get(key)
        if actual is None:
            add_warning(f"progress.md Snapshot is missing `{key}`")
        else:
            actual_cmp = normalize_free_text(actual) if key == "next_action" else actual
            expected_cmp = normalize_free_text(expected) if key == "next_action" else expected
            if actual_cmp == expected_cmp:
                continue
            add_warning(f"progress.md Snapshot `{key}` differs from state.json (`{actual}` != `{expected}`)")

delegate_states = {}
if delegates_dir.exists():
    for entry in delegates_dir.iterdir():
        if not entry.is_dir() or entry.name.startswith('.'):
            continue
        status_path = entry / "status.json"
        brief_path = entry / "brief.md"
        result_path = entry / "result.md"

        if not brief_path.exists():
            add_issue(f"Delegate `{entry.name}` is missing brief.md")
        if not result_path.exists():
            add_issue(f"Delegate `{entry.name}` is missing result.md")
        dstate = read_json(status_path, f"delegate {entry.name} status.json") if status_path.exists() else None
        if dstate is None:
            continue

        delegate_id = dstate.get("delegate_id", entry.name)
        if delegate_id != entry.name:
            add_issue(f"Delegate directory `{entry.name}` does not match status.json delegate_id `{delegate_id}`")
        status = dstate.get("status")
        if status not in active_delegate_statuses | terminal_delegate_statuses:
            add_issue(f"Delegate `{delegate_id}` has invalid status `{status}`")
        delegate_states[delegate_id] = dstate
else:
    add_issue("delegates/ directory is missing")

if state:
    active_delegates = state.get("delegation", {}).get("active", [])
    for delegate_id in active_delegates:
        dstate = delegate_states.get(delegate_id)
        if dstate is None:
            add_issue(f"state.json marks delegate `{delegate_id}` active, but no matching delegate status file exists")
            continue
        status = dstate.get("status")
        if status not in active_delegate_statuses:
            add_issue(f"Delegate `{delegate_id}` is active in state.json but has terminal status `{status}`")

    for delegate_id, dstate in delegate_states.items():
        status = dstate.get("status")
        if status in active_delegate_statuses and delegate_id not in active_delegates:
            add_issue(f"Delegate `{delegate_id}` has status `{status}` but is missing from state.json delegation.active")
        if status in terminal_delegate_statuses and delegate_id in active_delegates:
            add_issue(f"Delegate `{delegate_id}` has terminal status `{status}` but is still listed as active")

print(f"[context-task-planning] Validating task: {state.get('slug', plan_dir.name) if state else plan_dir.name}")
print(f"[context-task-planning] Task directory: {plan_dir}")

if issues:
    print("[context-task-planning] Validation failed.")
    print("[context-task-planning] Issues:")
    for item in issues:
        print(f"  - {item}")
    if warnings:
        print("[context-task-planning] Warnings:")
        for item in warnings:
            print(f"  - {item}")
    sys.exit(1)

if warnings:
    print("[context-task-planning] Validation passed with warnings.")
    print("[context-task-planning] Warnings:")
    for item in warnings:
        print(f"  - {item}")
    sys.exit(0)

print("[context-task-planning] Validation passed.")
PY
