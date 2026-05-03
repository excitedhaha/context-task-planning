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

echo "[context-task-planning] smoke test passed: Trae/Coco plugin packaging"
