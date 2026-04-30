#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PLUGIN_DIR="$SCRIPT_DIR/../opencode-plugin"
COMMAND_FILE="$SCRIPT_DIR/../opencode-commands/task-init.md"
NODE_BIN="$(command -v node || true)"

fail() {
    echo "[context-task-planning] smoke test failed: $1" >&2
    exit 1
}

[ -n "$NODE_BIN" ] || fail "node is required for the OpenCode plugin smoke test"
[ -f "$COMMAND_FILE" ] || fail "missing OpenCode task-init command contract"

grep -F 'confirm or edit both the title and the slug' "$COMMAND_FILE" >/dev/null || fail "OpenCode task-init contract missed dual title/slug confirmation guidance"
grep -F 'If the user edits the title but does not explicitly override the slug, recompute the slug from the final title' "$COMMAND_FILE" >/dev/null || fail "OpenCode task-init contract missed title-to-slug recompute guidance"
grep -F -- '--title "<final task title>" --slug "<final task slug>"' "$COMMAND_FILE" >/dev/null || fail "OpenCode task-init contract missed explicit --title/--slug invocation guidance"

"$NODE_BIN" "$PLUGIN_DIR/task-focus-guard.binding-title.smoke.mjs"
"$NODE_BIN" "$PLUGIN_DIR/task-focus-guard.smoke.mjs"
"$NODE_BIN" "$PLUGIN_DIR/task-focus-guard.compact-sync.smoke.mjs"
"$NODE_BIN" "$PLUGIN_DIR/task-focus-guard.ancestor-fallback.smoke.mjs"

echo "[context-task-planning] smoke test passed: OpenCode plugin smoke suite"
