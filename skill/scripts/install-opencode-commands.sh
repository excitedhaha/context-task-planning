#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
COMMAND_SOURCE_DIR="$SKILL_DIR/opencode-commands"
COMMAND_TARGET_DIR="$HOME/.config/opencode/commands"

link_command() {
    target="$1"
    source="$2"

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

if [ ! -d "$COMMAND_SOURCE_DIR" ]; then
    echo "OpenCode command source directory not found: $COMMAND_SOURCE_DIR" >&2
    exit 1
fi

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
