#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

TASK_SLUG=""
DELEGATE_ID=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --task)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --task" >&2; exit 1; }
            TASK_SLUG="$1"
            ;;
        -h|--help)
            echo "Usage: $0 [--task slug] <delegate-id>" >&2
            exit 0
            ;;
        *)
            if [ -z "$DELEGATE_ID" ]; then
                DELEGATE_ID="$1"
            else
                echo "Unexpected argument: $1" >&2
                exit 1
            fi
            ;;
    esac
    shift
done

if [ -z "$DELEGATE_ID" ]; then
    echo "Usage: $0 [--task slug] <delegate-id>" >&2
    exit 1
fi

DELEGATE_ID=$(sh "$SCRIPT_DIR/slugify.sh" "$DELEGATE_ID")
PLAN_DIR=$(sh "$SCRIPT_DIR/resolve-plan-dir.sh" "$TASK_SLUG")
if [ -z "$PLAN_DIR" ] || [ ! -d "$PLAN_DIR" ]; then
    echo "[context-task-planning] No task found to promote delegate into." >&2
    exit 1
fi

STATE_FILE="$PLAN_DIR/state.json"
PROGRESS_FILE="$PLAN_DIR/progress.md"
FINDINGS_FILE="$PLAN_DIR/findings.md"
DELEGATE_DIR="$PLAN_DIR/delegates/$DELEGATE_ID"
DELEGATE_STATUS_FILE="$DELEGATE_DIR/status.json"
DELEGATE_RESULT_FILE="$DELEGATE_DIR/result.md"
TASK_NAME=$(basename "$PLAN_DIR")

if [ ! -f "$STATE_FILE" ]; then
    echo "[context-task-planning] Missing state.json in $PLAN_DIR" >&2
    exit 1
fi

if [ ! -f "$DELEGATE_STATUS_FILE" ] || [ ! -f "$DELEGATE_RESULT_FILE" ]; then
    echo "[context-task-planning] Delegate result not found: $DELEGATE_DIR" >&2
    exit 1
fi

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "Python is required to promote delegates." >&2
    exit 1
fi

if [ -n "${PLAN_SESSION_KEY:-}" ]; then
    "$PYTHON_BIN" "$SCRIPT_DIR/task_guard.py" check-task-access --cwd "$PLAN_DIR" --task "$TASK_NAME"
else
    "$PYTHON_BIN" "$SCRIPT_DIR/task_guard.py" check-task-access --cwd "$PLAN_DIR" --task "$TASK_NAME" --fallback
fi

export STATE_FILE PROGRESS_FILE FINDINGS_FILE DELEGATE_STATUS_FILE DELEGATE_RESULT_FILE DELEGATE_ID
"$PYTHON_BIN" <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

state_path = Path(os.environ["STATE_FILE"])
progress_path = Path(os.environ["PROGRESS_FILE"])
findings_path = Path(os.environ["FINDINGS_FILE"])
delegate_status_path = Path(os.environ["DELEGATE_STATUS_FILE"])
delegate_result_path = Path(os.environ["DELEGATE_RESULT_FILE"])
delegate_id = os.environ["DELEGATE_ID"]


def collect_section_items(result_text: str, section_name: str) -> list[str]:
    current = None
    items: list[str] = []
    for line in result_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            current = stripped[3:]
            continue
        if current != section_name:
            continue
        if stripped.startswith("- "):
            candidate = stripped[2:].strip()
            if candidate and not candidate.startswith("["):
                items.append(candidate)
        elif stripped and not stripped.startswith("#"):
            items.append(stripped)
    return items


timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
state = json.loads(state_path.read_text(encoding="utf-8"))
delegate_state = json.loads(delegate_status_path.read_text(encoding="utf-8"))

if delegate_state.get("status") not in {"complete", "blocked"}:
    raise SystemExit("Only completed or blocked delegates can be promoted.")

if delegate_state.get("promoted_findings"):
    raise SystemExit("Delegate already has promoted findings recorded. Clear them manually if you need to promote again.")

result_text = delegate_result_path.read_text(encoding="utf-8")
summary_items = collect_section_items(result_text, "Summary")
finding_items = collect_section_items(result_text, "Findings")
promotion_items = collect_section_items(result_text, "Recommended Promotion")
open_risks = collect_section_items(result_text, "Open Risks")

summary_text = delegate_state.get("summary", "").strip()
if summary_text and summary_text not in summary_items:
    summary_items.insert(0, summary_text)

promoted_items = promotion_items or finding_items or summary_items
if not promoted_items:
    raise SystemExit("No promotable content found in delegate result.")

block = []
block.append("")
block.append(f"### Delegate: {delegate_state.get('title', delegate_id)} (`{delegate_id}`)")
block.append("")
block.append(f"- Kind: `{delegate_state.get('kind', 'other')}`")
block.append(f"- Status: `{delegate_state.get('status', 'unknown')}`")
block.append(f"- Promoted At: `{timestamp}`")
block.append(f"- Source: `{delegate_state.get('result_path', '')}`")
if summary_items:
    block.append("- Summary:")
    for item in summary_items:
        block.append(f"  - {item}")
if promoted_items:
    block.append("- Promoted Findings:")
    for item in promoted_items:
        block.append(f"  - {item}")
if open_risks:
    block.append("- Open Risks:")
    for item in open_risks:
        block.append(f"  - {item}")

with findings_path.open("a", encoding="utf-8") as fh:
    fh.write("\n".join(block) + "\n")

delegate_state["promoted_findings"] = promoted_items
delegate_state["updated_at"] = timestamp
delegate_status_path.write_text(json.dumps(delegate_state, indent=2) + "\n", encoding="utf-8")

state["latest_checkpoint"] = f"Delegate {delegate_id} promoted into findings.md at {timestamp}."
state["updated_at"] = timestamp
state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

if progress_path.exists():
    with progress_path.open("a", encoding="utf-8") as fh:
        fh.write("\n")
        fh.write(f"### Delegate Promoted: {timestamp}\n\n")
        fh.write(f"- Delegate: `{delegate_id}`\n")
        fh.write(f"- Findings Promoted: {len(promoted_items)}\n")
        fh.write("- Notes:\n")
        fh.write("  - Delegate findings promoted into findings.md via promote-delegate.sh\n")
PY

echo "[context-task-planning] Promoted delegate: $DELEGATE_ID"
echo "[context-task-planning] Findings file: $FINDINGS_FILE"
