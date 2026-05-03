#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
SKILL_DIR="$REPO_ROOT/skill"
PLUGIN_SOURCE="$SKILL_DIR/opencode-plugin/task-focus-guard.js"
COMMANDS_SOURCE_DIR="$SKILL_DIR/opencode-commands"
VERSION=$(cat "$REPO_ROOT/VERSION" | tr -d '[:space:]')
PACKAGE_DIR="$REPO_ROOT/packages/opencode-plugin"

# Validate inputs
if [ ! -f "$PLUGIN_SOURCE" ]; then
    echo "Missing plugin source: $PLUGIN_SOURCE" >&2
    exit 1
fi
if [ ! -d "$COMMANDS_SOURCE_DIR" ]; then
    echo "Missing commands source directory: $COMMANDS_SOURCE_DIR" >&2
    exit 1
fi

# Prepare package directory
mkdir -p "$PACKAGE_DIR/commands"

# Copy plugin source as index.js (the source already has resolveSkillRoot)
cp "$PLUGIN_SOURCE" "$PACKAGE_DIR/index.js"

# Update version constant in index.js to match VERSION file
sed -i.bak "s/^const PLUGIN_VERSION = \"[^\"]*\"/const PLUGIN_VERSION = \"$VERSION\"/" "$PACKAGE_DIR/index.js"
rm -f "$PACKAGE_DIR/index.js.bak"

# Copy and template command files (replace hardcoded skill paths with template variable)
for cmd in "$COMMANDS_SOURCE_DIR"/*.md; do
    if [ ! -f "$cmd" ]; then
        continue
    fi
    name=$(basename "$cmd")
    sed 's|~/.config/opencode/skills/context-task-planning/scripts|{{SKILL_SCRIPTS_DIR}}|g' "$cmd" \
        > "$PACKAGE_DIR/commands/$name"
done

# Generate package.json with version from VERSION file
cat > "$PACKAGE_DIR/package.json" <<PKGJSON
{
  "name": "context-task-planning-opencode",
  "version": "$VERSION",
  "description": "OpenCode plugin for context-task-planning: task-scoped context engineering with session binding, route evidence, and freshness tracking",
  "type": "module",
  "main": "index.js",
  "exports": {
    ".": "./index.js"
  },
  "keywords": [
    "opencode",
    "opencode-plugin",
    "task-planning",
    "context-engineering"
  ],
  "author": {
    "name": "excitedhaha"
  },
  "license": "MIT",
  "repository": {
    "type": "git",
    "url": "https://github.com/excitedhaha/context-task-planning.git",
    "directory": "packages/opencode-plugin"
  },
  "files": [
    "index.js",
    "commands/"
  ]
}
PKGJSON

echo "Built npm package at $PACKAGE_DIR (version $VERSION)"

# Validate
if command -v node >/dev/null 2>&1; then
    node --check "$PACKAGE_DIR/index.js" && echo "index.js syntax OK"
fi

echo ""
echo "To publish: cd $PACKAGE_DIR && npm publish --access public"
echo "To test locally: opencode plugin file://$PACKAGE_DIR --global"
