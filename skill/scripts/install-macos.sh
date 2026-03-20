#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
SKILL_NAME="context-task-planning"
INSTALL_OPENCODE_PLUGIN=1

for arg in "$@"; do
    case "$arg" in
        --skip-opencode-plugin)
            INSTALL_OPENCODE_PLUGIN=0
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            echo "Usage: sh skill/scripts/install-macos.sh [--skip-opencode-plugin]" >&2
            exit 1
            ;;
    esac
done

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

if [ "$INSTALL_OPENCODE_PLUGIN" -eq 1 ]; then
    sh "$SCRIPT_DIR/install-opencode-plugin.sh"
else
    echo "Skipped OpenCode plugin install."
fi

echo ""
echo "Install complete."
echo "If OpenCode uses a custom skill source list, make sure ~/.config/opencode/skills is enabled."
echo "Use --skip-opencode-plugin if you want the skill without the OpenCode runtime plugin."
