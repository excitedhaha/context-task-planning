#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
REPO_ROOT=$(cd "$SKILL_DIR/.." && pwd)
COCO_YAML="$REPO_ROOT/coco.yaml"
COMMAND_DIR="$REPO_ROOT/commands"
TRAE_HOOK_DIR="$SKILL_DIR/trae-hooks/scripts"
TRAE_SKILL="$REPO_ROOT/skills/context-task-planning/SKILL.md"
PYTHON_BIN="$(command -v python3 || command -v python || true)"

fail() {
    echo "[context-task-planning] Trae/Coco plugin smoke test failed: $1" >&2
    exit 1
}

[ -n "$PYTHON_BIN" ] || fail "python is required for the Trae/Coco plugin smoke test"
[ -f "$COCO_YAML" ] || fail "missing coco.yaml"
[ -d "$COMMAND_DIR" ] || fail "missing commands directory"
[ -d "$TRAE_HOOK_DIR" ] || fail "missing Trae hook scripts"
[ -f "$TRAE_SKILL" ] || fail "missing Trae-visible context-task-planning skill"

"$PYTHON_BIN" -m py_compile "$TRAE_HOOK_DIR"/*.py

"$PYTHON_BIN" - "$COCO_YAML" "$COMMAND_DIR" "$TRAE_SKILL" <<'PY'
import sys
from pathlib import Path

coco_yaml = Path(sys.argv[1]).read_text(encoding="utf-8")
command_dir = Path(sys.argv[2])
trae_skill = Path(sys.argv[3]).read_text(encoding="utf-8")

for event in [
    "session_start",
    "user_prompt_submit",
    "pre_tool_use",
    "post_tool_use",
    "stop",
]:
    if f"event: {event}" not in coco_yaml:
        raise SystemExit(f"missing hook event in coco.yaml: {event}")

for script in [
    "session_start.py",
    "user_prompt_submit.py",
    "pre_tool_use.py",
    "post_tool_use.py",
    "stop.py",
]:
    expected = f'${{COCO_PLUGIN_ROOT}}/skill/trae-hooks/scripts/{script}'
    if expected not in coco_yaml:
        raise SystemExit(f"missing plugin-root hook command: {expected}")

for command in [
    "task-current.md",
    "task-done.md",
    "task-drift.md",
    "task-init.md",
    "task-list.md",
    "task-validate.md",
]:
    path = command_dir / command
    if not path.is_file():
        raise SystemExit(f"missing command file: {path}")
    text = path.read_text(encoding="utf-8")
    if "${COCO_PLUGIN_ROOT}/skill/scripts/" not in text:
        raise SystemExit(f"command is not plugin-root relative: {path}")
    if command == "task-init.md":
        required = [
            "confirm or edit both the title and the slug",
            "--title \"<final task title>\" --slug \"<final task slug>\"",
            "If the user edits the title but does not explicitly override the slug, recompute the slug from the final title",
        ]
        for item in required:
            if item not in text:
                raise SystemExit(f"task-init contract missing expected guidance {item!r}: {path}")

if "name: context-task-planning" not in trae_skill:
    raise SystemExit("Trae-visible main skill has the wrong name")
if "${COCO_PLUGIN_ROOT}/skill/scripts/" not in trae_skill:
    raise SystemExit("Trae-visible main skill does not point at the bundled core scripts")
PY

TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/context-task-planning-trae-plugin.XXXXXX")

cleanup() {
    rm -rf "$TMP_ROOT"
}

trap cleanup EXIT HUP INT TERM

TRAE_HINT=$(
    cd "$TMP_ROOT" &&
        printf '%s' "{\"cwd\":\"$TMP_ROOT\",\"session_id\":\"trae-smoke\",\"prompt\":\"Implement a multi-step migration that needs recovery and verification.\"}" |
        COCO_PLUGIN_ROOT="$REPO_ROOT" "$PYTHON_BIN" "$TRAE_HOOK_DIR/user_prompt_submit.py"
)

"$PYTHON_BIN" - "$TRAE_HINT" "$REPO_ROOT" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
repo_root = sys.argv[2]
context = payload.get("hookSpecificOutput", {}).get("additionalContext", "")
expected = f'sh "{repo_root}/skill/scripts/init-task.sh"'
if expected not in context:
    raise SystemExit(f"plugin-root command missing from Trae hint: {context!r}")
PY

TASK_TITLE="Bootstrap session binding"
TASK_SLUG="bootstrap-session-binding"
(
    cd "$TMP_ROOT"
    sh "$REPO_ROOT/skill/scripts/init-task.sh" --title "$TASK_TITLE" --slug "$TASK_SLUG" >/dev/null
)

printf '%s' "{\"cwd\":\"$TMP_ROOT\",\"session_id\":\"trae-bootstrap-smoke\",\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"sh \\\"$REPO_ROOT/skill/scripts/init-task.sh\\\" --title \\\"$TASK_TITLE\\\" --slug \\\"$TASK_SLUG\\\"\"}}" |
    COCO_PLUGIN_ROOT="$REPO_ROOT" "$PYTHON_BIN" "$TRAE_HOOK_DIR/post_tool_use.py" >/dev/null

CURRENT_JSON=$(
    cd "$TMP_ROOT" &&
        PLAN_SESSION_KEY="trae:trae-bootstrap-smoke" sh "$REPO_ROOT/skill/scripts/current-task.sh" --json 2>/dev/null || true
)

"$PYTHON_BIN" - "$CURRENT_JSON" "$TASK_SLUG" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
task_slug = sys.argv[2]
if payload.get("selection_source") != "session_binding":
    raise SystemExit(f"expected session_binding after Trae bootstrap, got {payload.get('selection_source')!r}")
if payload.get("session_binding") != task_slug:
    raise SystemExit(f"expected session binding for {task_slug!r}, got {payload.get('session_binding')!r}")
if payload.get("binding_role") != "writer":
    raise SystemExit(f"expected writer binding after Trae bootstrap, got {payload.get('binding_role')!r}")
PY

AUTO_TASK_TITLE="Automatic progress sync"
AUTO_TASK_SLUG="automatic-progress-sync"
AUTO_SESSION_ID="trae-autosync-smoke"
AUTO_PROMPT="Update the task runtime to persist automatic sync progress."
AUTO_FILE="$TMP_ROOT/src/demo.py"
(
    cd "$TMP_ROOT"
    sh "$REPO_ROOT/skill/scripts/init-task.sh" --title "$AUTO_TASK_TITLE" --slug "$AUTO_TASK_SLUG" >/dev/null
    "$PYTHON_BIN" "$REPO_ROOT/skill/scripts/task_guard.py" bind-session-task \
        --cwd "$TMP_ROOT" \
        --session-key "trae:$AUTO_SESSION_ID" \
        --task "$AUTO_TASK_SLUG" \
        --role writer \
        --steal >/dev/null
)

printf '%s' "{\"cwd\":\"$TMP_ROOT\",\"session_id\":\"$AUTO_SESSION_ID\",\"prompt\":\"$AUTO_PROMPT\"}" |
    COCO_PLUGIN_ROOT="$REPO_ROOT" "$PYTHON_BIN" "$TRAE_HOOK_DIR/user_prompt_submit.py" >/dev/null

printf '%s' "{\"cwd\":\"$TMP_ROOT\",\"session_id\":\"$AUTO_SESSION_ID\",\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$AUTO_FILE\"}}" |
    COCO_PLUGIN_ROOT="$REPO_ROOT" "$PYTHON_BIN" "$TRAE_HOOK_DIR/post_tool_use.py" >/dev/null

STOP_OUTPUT=$(
    printf '%s' "{\"cwd\":\"$TMP_ROOT\",\"session_id\":\"$AUTO_SESSION_ID\"}" |
        COCO_PLUGIN_ROOT="$REPO_ROOT" "$PYTHON_BIN" "$TRAE_HOOK_DIR/stop.py"
)

"$PYTHON_BIN" - "$TMP_ROOT" "$AUTO_TASK_SLUG" "$STOP_OUTPUT" <<'PY'
import json
import sys
from pathlib import Path

tmp_root = Path(sys.argv[1])
task_slug = sys.argv[2]
stop_output = sys.argv[3].strip()
if stop_output:
    raise SystemExit(f"expected auto sync to avoid stop block, got {stop_output!r}")

plan_dir = tmp_root / ".planning" / task_slug
state = json.loads((plan_dir / "state.json").read_text(encoding="utf-8"))
progress = (plan_dir / "progress.md").read_text(encoding="utf-8")

checkpoint = str(state.get("latest_checkpoint") or "")
if not checkpoint.startswith("Handled: Update the task runtime to persist automatic sync progress."):
    raise SystemExit(f"unexpected auto-sync checkpoint: {checkpoint!r}")
if "src/demo.py" not in progress:
    raise SystemExit("auto-synced progress is missing touched file entry")
if "Automated Trae/Coco turn sync appended this journal entry." not in progress:
    raise SystemExit("auto-synced progress is missing Trae sync note")
PY

echo "[context-task-planning] smoke test passed: Trae/Coco plugin packaging"
