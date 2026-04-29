#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
REPO_ROOT=$(cd "$SKILL_DIR/.." && pwd)
PLUGIN_JSON="$REPO_ROOT/.claude-plugin/plugin.json"
MARKETPLACE_JSON="$REPO_ROOT/.claude-plugin/marketplace.json"
HOOK_JSON="$SKILL_DIR/claude-hooks/hooks.json"
PYTHON_BIN="$(command -v python3 || command -v python || true)"

fail() {
    echo "[context-task-planning] Claude plugin smoke test failed: $1" >&2
    exit 1
}

[ -n "$PYTHON_BIN" ] || fail "python is required for the Claude plugin smoke test"
[ -f "$PLUGIN_JSON" ] || fail "missing plugin manifest"
[ -f "$MARKETPLACE_JSON" ] || fail "missing marketplace manifest"
[ -f "$HOOK_JSON" ] || fail "missing Claude plugin hooks"

TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/context-task-planning-claude-plugin.XXXXXX")

cleanup() {
    rm -rf "$TMP_ROOT"
}

trap cleanup EXIT HUP INT TERM

"$PYTHON_BIN" -m json.tool "$PLUGIN_JSON" >/dev/null
"$PYTHON_BIN" -m json.tool "$MARKETPLACE_JSON" >/dev/null
"$PYTHON_BIN" -m json.tool "$HOOK_JSON" >/dev/null
"$PYTHON_BIN" -m py_compile "$SKILL_DIR"/claude-hooks/scripts/*.py

"$PYTHON_BIN" - "$PLUGIN_JSON" "$MARKETPLACE_JSON" "$HOOK_JSON" <<'PY'
import json
import sys

plugin_path, marketplace_path, hook_path = sys.argv[1:4]
with open(plugin_path, encoding="utf-8") as fh:
    plugin = json.load(fh)
with open(marketplace_path, encoding="utf-8") as fh:
    marketplace = json.load(fh)
with open(hook_path, encoding="utf-8") as fh:
    hooks = json.load(fh)

if plugin.get("name") != "context-task-planning":
    raise SystemExit(f"unexpected plugin name: {plugin.get('name')!r}")
if plugin.get("skills") != ["./skill", "./skills"]:
    raise SystemExit(f"unexpected plugin skills paths: {plugin.get('skills')!r}")
if plugin.get("hooks") != "./skill/claude-hooks/hooks.json":
    raise SystemExit(f"unexpected plugin hooks path: {plugin.get('hooks')!r}")

entries = marketplace.get("plugins") or []
if len(entries) != 1:
    raise SystemExit(f"expected one marketplace plugin, got: {len(entries)}")
entry = entries[0]
if entry.get("name") != "context-task-planning" or entry.get("source") != "./":
    raise SystemExit(f"unexpected marketplace entry: {entry!r}")

expected_events = {"SessionStart", "UserPromptSubmit", "PreToolUse"}
actual_events = set((hooks.get("hooks") or {}).keys())
if not expected_events.issubset(actual_events):
    raise SystemExit(f"missing hook events: {expected_events - actual_events}")

for event_name, groups in hooks["hooks"].items():
    for group in groups:
        for hook in group.get("hooks", []):
            command = hook.get("command", "")
            if "${CLAUDE_PLUGIN_ROOT}/skill/claude-hooks/scripts/" not in command:
                raise SystemExit(f"{event_name} command is not plugin-root relative: {command!r}")
PY

PLUGIN_HINT=$(
    cd "$TMP_ROOT" &&
        printf '%s' "{\"cwd\":\"$TMP_ROOT\",\"session_id\":\"plugin-smoke\",\"prompt\":\"Implement a multi-step migration that needs recovery and verification.\"}" |
        CLAUDE_PLUGIN_ROOT="$REPO_ROOT" "$PYTHON_BIN" "$SKILL_DIR/claude-hooks/scripts/user_prompt_submit.py"
)

"$PYTHON_BIN" - "$PLUGIN_HINT" "$REPO_ROOT" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
repo_root = sys.argv[2]
context = payload.get("additionalContext", "")
expected = f'sh "{repo_root}/skill/scripts/init-task.sh"'
if expected not in context:
    raise SystemExit(f"plugin-root command missing from hint: {context!r}")
PY

echo "[context-task-planning] smoke test passed: Claude plugin packaging"
