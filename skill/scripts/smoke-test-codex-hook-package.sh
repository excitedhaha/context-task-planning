#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
REPO_ROOT=$(cd "$SKILL_DIR/.." && pwd)
HOOK_PACKAGE="$REPO_ROOT/hooks/context-task-planning"
HOOK_JSON="$HOOK_PACKAGE/hooks.json"

if [ ! -f "$HOOK_JSON" ]; then
    echo "Missing hook package: $HOOK_JSON" >&2
    exit 1
fi

TMP_ROOT=$(mktemp -d /tmp/context-task-planning-codex-hooks.XXXXXX)
CODEX_HOME_DIR="$TMP_ROOT/codex-home"
PROJECT_DIR="$TMP_ROOT/project"
PROJECT_SUBDIR="$PROJECT_DIR/subdir"

mkdir -p "$CODEX_HOME_DIR/hooks" "$CODEX_HOME_DIR/skills" "$PROJECT_SUBDIR"
ln -s "$HOOK_PACKAGE" "$CODEX_HOME_DIR/hooks/context-task-planning"
ln -s "$SKILL_DIR" "$CODEX_HOME_DIR/skills/context-task-planning"

python3 -m json.tool "$HOOK_JSON" >/dev/null
python3 -m py_compile "$HOOK_PACKAGE/scripts/run-hook.py" "$SKILL_DIR"/codex-hooks/scripts/*.py

run_hook() {
    hook_name="$1"
    payload="$2"

    printf '%s' "$payload" |
        CODEX_HOME="$CODEX_HOME_DIR" \
        CONTEXT_TASK_PLANNING_SKILL_DIR="$SKILL_DIR" \
        python3 "$HOOK_PACKAGE/scripts/run-hook.py" "$hook_name" >/dev/null
}

run_hook session_start "{\"hook_event_name\":\"SessionStart\",\"cwd\":\"$REPO_ROOT\",\"session_id\":\"smoke\",\"turn_id\":\"start\"}"
run_hook user_prompt_submit "{\"hook_event_name\":\"UserPromptSubmit\",\"cwd\":\"$REPO_ROOT\",\"session_id\":\"smoke\",\"turn_id\":\"prompt\",\"prompt\":\"Continue the current task.\"}"
run_hook post_tool_use "{\"hook_event_name\":\"PostToolUse\",\"cwd\":\"$REPO_ROOT\",\"session_id\":\"smoke\",\"turn_id\":\"prompt\",\"tool_name\":\"Bash\",\"tool_input\":{\"cmd\":\"sh skill/scripts/current-task.sh --compact\"}}"
run_hook stop "{\"hook_event_name\":\"Stop\",\"cwd\":\"$REPO_ROOT\",\"session_id\":\"smoke\",\"turn_id\":\"prompt\",\"stop_hook_active\":true}"

command_for_event() {
    event_name="$1"
    python3 - "$HOOK_JSON" "$event_name" <<'PY'
import json
import sys

path, event_name = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)
entries = data["hooks"][event_name]
print(entries[0]["hooks"][0]["command"])
PY
}

SESSION_START_COMMAND=$(command_for_event SessionStart)
PROJECT_HOOK_DIR="$PROJECT_DIR/.codex/hooks"
PROJECT_SKILL_DIR="$PROJECT_DIR/.codex/skills"
mkdir -p "$PROJECT_HOOK_DIR" "$PROJECT_SKILL_DIR"
ln -s "$HOOK_PACKAGE" "$PROJECT_HOOK_DIR/context-task-planning"
ln -s "$SKILL_DIR" "$PROJECT_SKILL_DIR/context-task-planning"

(
    cd "$PROJECT_SUBDIR"
    printf '%s' "{\"hook_event_name\":\"SessionStart\",\"cwd\":\"$PROJECT_SUBDIR\",\"session_id\":\"project-smoke\",\"turn_id\":\"start\"}" |
        CODEX_HOME="$TMP_ROOT/no-global-codex-home" \
        CONTEXT_TASK_PLANNING_SKILL_DIR="$SKILL_DIR" \
        sh -c "$SESSION_START_COMMAND" >/dev/null
)

echo "Codex hook package smoke test passed."
echo "Temporary test workspace: $TMP_ROOT"
