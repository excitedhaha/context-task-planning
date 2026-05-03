#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
COMMAND_SOURCE_DIR="$SKILL_DIR/opencode-commands"
COMMAND_TARGET_DIR="$HOME/.config/opencode/commands"
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
    if [ ! -d "$COMMAND_SOURCE_DIR" ]; then
        echo "Nothing to uninstall (source directory not found)." >&2
        exit 0
    fi
    removed=0
    for source in "$COMMAND_SOURCE_DIR"/*.md; do
        if [ ! -f "$source" ]; then
            continue
        fi
        name=$(basename "$source")
        target="$COMMAND_TARGET_DIR/$name"
        if [ -L "$target" ] || [ -e "$target" ]; then
            rm -f "$target"
            echo "Removed: $target"
            removed=1
        fi
    done
    if [ "$removed" -eq 0 ]; then
        echo "No installed commands found."
    fi
    exit 0
fi

if [ ! -d "$COMMAND_SOURCE_DIR" ]; then
    echo "OpenCode command source directory not found: $COMMAND_SOURCE_DIR" >&2
    exit 1
fi

link_command() {
    target="$1"
    source="$2"

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

mkdir -p "$COMMAND_TARGET_DIR"

found=0
for source in "$COMMAND_SOURCE_DIR"/*.md; do
    if [ ! -f "$source" ]; then
        continue
    fi
    found=1
    name=$(basename "$source")
    link_command "$COMMAND_TARGET_DIR/$name" "$source"
done

if [ "$found" -eq 0 ]; then
    echo "No OpenCode command files found under: $COMMAND_SOURCE_DIR" >&2
    exit 1
fi

echo ""
echo "OpenCode command install complete. Restart OpenCode if the new slash commands do not appear immediately."
echo ""
echo "Note: symlink-based install is deprecated. Use: opencode plugin context-task-planning-opencode --global"
