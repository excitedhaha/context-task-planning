#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
PLUGIN_NAME="context-task-planning"
MARKETPLACE_NAME="${CODEX_MARKETPLACE_NAME:-context-task-planning-local}"
CODEX_BIN="${CODEX_BIN:-codex}"
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
MARKETPLACE_DIR="${CODEX_MARKETPLACE_DIR:-$CODEX_HOME_DIR/context-task-planning-marketplace}"
MARKETPLACE_JSON="$MARKETPLACE_DIR/.agents/plugins/marketplace.json"
PLUGIN_LINK="$MARKETPLACE_DIR/plugins/$PLUGIN_NAME"

if ! command -v "$CODEX_BIN" >/dev/null 2>&1; then
    echo "codex CLI not found. Install Codex first, then rerun this script." >&2
    exit 1
fi

mkdir -p "$MARKETPLACE_DIR/.agents/plugins" "$MARKETPLACE_DIR/plugins"

if [ -L "$PLUGIN_LINK" ]; then
    current=$(readlink "$PLUGIN_LINK" || true)
    if [ "$current" != "$REPO_ROOT" ]; then
        echo "Refusing to replace existing symlink: $PLUGIN_LINK -> $current" >&2
        exit 1
    fi
elif [ -e "$PLUGIN_LINK" ]; then
    echo "Refusing to overwrite existing path: $PLUGIN_LINK" >&2
    exit 1
else
    ln -s "$REPO_ROOT" "$PLUGIN_LINK"
fi

cat > "$MARKETPLACE_JSON" <<EOF
{
  "name": "$MARKETPLACE_NAME",
  "interface": {
    "displayName": "Context Task Planning Local"
  },
  "plugins": [
    {
      "name": "$PLUGIN_NAME",
      "source": {
        "source": "local",
        "path": "./plugins/$PLUGIN_NAME"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      },
      "category": "Productivity"
    }
  ]
}
EOF

# Re-point repeat installs to this stable wrapper if an older local wrapper used the same name.
"$CODEX_BIN" plugin marketplace remove "$MARKETPLACE_NAME" >/dev/null 2>&1 || true
"$CODEX_BIN" plugin marketplace add "$MARKETPLACE_DIR"
"$CODEX_BIN" plugin add "$PLUGIN_NAME@$MARKETPLACE_NAME"

echo ""
echo "Codex plugin install complete."
echo "Marketplace: $MARKETPLACE_DIR"
echo "Plugin: $PLUGIN_NAME@$MARKETPLACE_NAME"
