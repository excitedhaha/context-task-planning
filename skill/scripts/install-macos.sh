#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
SKILL_NAME="context-task-planning"
CLAUDE_EXTRA_SKILLS_DIR="$SKILL_DIR/../skills"
INSTALL_OPENCODE_PLUGIN=1
INSTALL_OPENCODE_COMMANDS=1
FORCE=0

for arg in "$@"; do
    case "$arg" in
        --skip-opencode-plugin)
            INSTALL_OPENCODE_PLUGIN=0
            ;;
        --skip-opencode-commands)
            INSTALL_OPENCODE_COMMANDS=0
            ;;
        --force)
            FORCE=1
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            echo "Usage: sh skill/scripts/install-macos.sh [--skip-opencode-plugin] [--skip-opencode-commands] [--force]" >&2
            exit 1
            ;;
    esac
done

link_skill() {
    target="$1"
    source_path="${2:-$SKILL_DIR}"
    parent=$(dirname "$target")

    mkdir -p "$parent"

    if [ -L "$target" ]; then
        current=$(readlink "$target" || true)
        if [ "$current" = "$source_path" ]; then
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

    ln -s "$source_path" "$target"
    echo "Linked: $target -> $source_path"
}

link_skill "$HOME/.claude/skills/$SKILL_NAME"
link_skill "$HOME/.codex/skills/$SKILL_NAME"
link_skill "$HOME/.config/opencode/skills/$SKILL_NAME"

if [ -d "$CLAUDE_EXTRA_SKILLS_DIR" ]; then
    for extra_skill in "$CLAUDE_EXTRA_SKILLS_DIR"/*; do
        if [ ! -d "$extra_skill" ] || [ ! -f "$extra_skill/SKILL.md" ]; then
            continue
        fi
        link_skill "$HOME/.claude/skills/$(basename "$extra_skill")" "$extra_skill"
    done
fi

if [ "$INSTALL_OPENCODE_PLUGIN" -eq 1 ]; then
    if [ "$FORCE" -eq 1 ]; then
        sh "$SCRIPT_DIR/install-opencode-plugin.sh" --force
    else
        sh "$SCRIPT_DIR/install-opencode-plugin.sh"
    fi
else
    echo "Skipped OpenCode plugin install."
fi

if [ "$INSTALL_OPENCODE_COMMANDS" -eq 1 ]; then
    if [ "$FORCE" -eq 1 ]; then
        sh "$SCRIPT_DIR/install-opencode-commands.sh" --force
    else
        sh "$SCRIPT_DIR/install-opencode-commands.sh"
    fi
else
    echo "Skipped OpenCode command install."
fi

echo ""
echo "Install complete."
echo "If OpenCode uses a custom skill source list, make sure ~/.config/opencode/skills is enabled."
echo "Use --skip-opencode-plugin if you want the skill without the OpenCode runtime plugin."
echo "Use --skip-opencode-commands if you want the skill without the OpenCode slash commands."
