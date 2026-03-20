#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
SKILL_NAME="context-task-planning"

link_skill() {
    target="$1"
    parent=$(dirname "$target")

    mkdir -p "$parent"

    if [ -L "$target" ]; then
        current=$(readlink "$target" || true)
        if [ "$current" = "$SKILL_DIR" ]; then
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

    ln -s "$SKILL_DIR" "$target"
    echo "Linked: $target -> $SKILL_DIR"
}

link_skill "$HOME/.claude/skills/$SKILL_NAME"
link_skill "$HOME/.codex/skills/$SKILL_NAME"
link_skill "$HOME/.config/opencode/skills/$SKILL_NAME"

echo ""
echo "Install complete."
echo "If OpenCode uses a custom skill source list, make sure ~/.config/opencode/skills is enabled."
