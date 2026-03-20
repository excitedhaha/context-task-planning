#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
PLUGIN_SOURCE="$SKILL_DIR/opencode-plugin/task-focus-guard.js"
PLUGIN_TARGET="$HOME/.config/opencode/plugins/context-task-planning-task-focus-guard.js"

link_plugin() {
    target="$1"
    source="$2"
    parent=$(dirname "$target")

    mkdir -p "$parent"

    if [ -L "$target" ]; then
        current=$(readlink "$target" || true)
        if [ "$current" = "$source" ]; then
            echo "Already linked: $target"
            return 0
        fi

        echo "Refusing to replace existing symlink: $target -> $current" >&2
        return 1
    fi

    if [ -e "$target" ]; then
        echo "Refusing to overwrite existing path: $target" >&2
        return 1
    fi

    ln -s "$source" "$target"
    echo "Linked: $target -> $source"
}

if [ ! -f "$PLUGIN_SOURCE" ]; then
    echo "OpenCode plugin source not found: $PLUGIN_SOURCE" >&2
    exit 1
fi

link_plugin "$PLUGIN_TARGET" "$PLUGIN_SOURCE"

echo ""
echo "OpenCode plugin install complete. Restart OpenCode to load the plugin."
echo "The plugin stays quiet outside repositories that already use .planning/."
