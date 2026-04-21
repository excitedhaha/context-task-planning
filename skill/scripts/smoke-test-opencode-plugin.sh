#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PLUGIN_DIR="$SCRIPT_DIR/../opencode-plugin"
NODE_BIN="$(command -v node || true)"

fail() {
    echo "[context-task-planning] smoke test failed: $1" >&2
    exit 1
}

[ -n "$NODE_BIN" ] || fail "node is required for the OpenCode plugin smoke test"

"$NODE_BIN" "$PLUGIN_DIR/task-focus-guard.binding-title.smoke.mjs"
"$NODE_BIN" "$PLUGIN_DIR/task-focus-guard.smoke.mjs"
"$NODE_BIN" "$PLUGIN_DIR/task-focus-guard.compact-sync.smoke.mjs"
"$NODE_BIN" "$PLUGIN_DIR/task-focus-guard.ancestor-fallback.smoke.mjs"

echo "[context-task-planning] smoke test passed: OpenCode plugin smoke suite"
