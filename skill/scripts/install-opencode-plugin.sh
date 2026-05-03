#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
PLUGIN_SOURCE="$SKILL_DIR/opencode-plugin/task-focus-guard.js"
PLUGIN_TARGET="$HOME/.config/opencode/plugins/context-task-planning-task-focus-guard.js"
FORCE=0
UNINSTALL=0

for arg in "$@"; do
    case "$arg" in
        --force)
            FORCE=1
            ;;
        --uninstall)
            UNINSTALL=1
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            echo "Usage: sh $(basename "$0") [--force] [--uninstall]" >&2
            exit 1
            ;;
    esac
done

if [ "$UNINSTALL" -eq 1 ]; then
    if [ -L "$PLUGIN_TARGET" ] || [ -e "$PLUGIN_TARGET" ]; then
        rm -f "$PLUGIN_TARGET"
        echo "Removed: $PLUGIN_TARGET"
    else
        echo "Not installed: $PLUGIN_TARGET"
    fi
    exit 0
fi

if [ ! -f "$PLUGIN_SOURCE" ]; then
    echo "OpenCode plugin source not found: $PLUGIN_SOURCE" >&2
    exit 1
fi

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

        if [ "$FORCE" -eq 1 ]; then
            rm -f "$target"
            echo "Replacing symlink: $target (was -> $current)"
        else
            echo "Refusing to replace existing symlink: $target -> $current" >&2
            echo "Use --force to replace." >&2
            return 1
        fi
    fi

    if [ -e "$target" ]; then
        if [ "$FORCE" -eq 1 ]; then
            rm -f "$target"
            echo "Replacing existing file: $target"
        else
            echo "Refusing to overwrite existing path: $target" >&2
            echo "Use --force to replace." >&2
            return 1
        fi
    fi

    ln -s "$source" "$target"
    echo "Linked: $target -> $source"
}

link_plugin "$PLUGIN_TARGET" "$PLUGIN_SOURCE"

echo ""
echo "OpenCode plugin install complete. Restart OpenCode to load the plugin."
echo "The plugin stays quiet outside repositories that already use .planning/."
echo ""
echo "Note: symlink-based install is deprecated. Use: opencode plugin context-task-planning-opencode --global"
