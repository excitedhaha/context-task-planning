#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
PACKAGE_DIR="$REPO_ROOT/packages/opencode-plugin"
VERSION=$(cat "$REPO_ROOT/VERSION" | tr -d '[:space:]')

fail() { echo "FAIL: $1" >&2; exit 1; }

echo "=== OpenCode npm package smoke test ==="

# 1. Build the package first
sh "$REPO_ROOT/scripts/build-opencode-npm-package.sh"

# 2. Validate package.json
[ -f "$PACKAGE_DIR/package.json" ] || fail "package.json missing"
node -e "
  const p = require('$PACKAGE_DIR/package.json');
  if (p.name !== 'context-task-planning-opencode') throw new Error('invalid name: ' + p.name);
  if (p.version !== '$VERSION') throw new Error('version mismatch: ' + p.version + ' vs $VERSION');
  if (p.type !== 'module') throw new Error('type must be module');
  console.log('package.json OK (v' + p.version + ')');
"

# 3. Validate index.js syntax
[ -f "$PACKAGE_DIR/index.js" ] || fail "index.js missing"
node --check "$PACKAGE_DIR/index.js" || fail "index.js syntax error"

# 4. Validate PLUGIN_VERSION matches
node -e "
  const fs = require('fs');
  const src = fs.readFileSync('$PACKAGE_DIR/index.js', 'utf8');
  const m = src.match(/^const PLUGIN_VERSION = [\"']([^\"']+)[\"']/m);
  if (!m) throw new Error('PLUGIN_VERSION not found');
  if (m[1] !== '$VERSION') throw new Error('PLUGIN_VERSION mismatch: ' + m[1] + ' vs $VERSION');
  console.log('PLUGIN_VERSION OK (' + m[1] + ')');
"

# 5. Validate resolveSkillRoot exists
node -e "
  const fs = require('fs');
  const src = fs.readFileSync('$PACKAGE_DIR/index.js', 'utf8');
  if (!src.includes('function resolveSkillRoot')) throw new Error('resolveSkillRoot not found');
  if (!src.includes('CONTEXT_TASK_PLANNING_SKILL_DIR')) throw new Error('env override not found');
  console.log('resolveSkillRoot OK');
"

# 6. Validate autoInstallCommands exists
node -e "
  const fs = require('fs');
  const src = fs.readFileSync('$PACKAGE_DIR/index.js', 'utf8');
  if (!src.includes('function autoInstallCommands')) throw new Error('autoInstallCommands not found');
  console.log('autoInstallCommands OK');
"

# 7. Validate command files exist and have template variables
for cmd in task-current task-done task-drift task-init task-list task-validate; do
  cmdfile="$PACKAGE_DIR/commands/$cmd.md"
  [ -f "$cmdfile" ] || fail "Missing command: $cmd.md"
  grep -q '{{SKILL_SCRIPTS_DIR}}' "$cmdfile" || fail "Command $cmd.md missing {{SKILL_SCRIPTS_DIR}} placeholder"
done
echo "Commands OK (6 files with template variables)"

# 8. Validate npm pack --dry-run works
cd "$PACKAGE_DIR"
PACK_OUTPUT=$(npm pack --dry-run 2>&1) || fail "npm pack failed"
echo "$PACK_OUTPUT" | grep -q "context-task-planning-opencode" || fail "npm pack output unexpected"
echo "npm pack OK"

echo ""
echo "=== All OpenCode npm package smoke tests passed ==="
