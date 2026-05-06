#!/bin/sh

# Smoke test for Codex plugin structure
# Validates plugin manifest, hooks config, and version consistency

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)

echo "=== Codex Plugin Smoke Test ==="

# 1. Validate plugin.json
echo "1. Checking .codex-plugin/plugin.json..."
python3 -m json.tool "$REPO_ROOT/.codex-plugin/plugin.json" > /dev/null
echo "   ✓ Valid JSON"

# 2. Validate hooks.json
echo "2. Checking .codex-plugin/hooks.json..."
python3 -m json.tool "$REPO_ROOT/.codex-plugin/hooks.json" > /dev/null
echo "   ✓ Valid JSON"

# 3. Check skill paths exist
echo "3. Checking skill paths..."
python3 - "$REPO_ROOT" <<'PY'
import json
from pathlib import Path

root = Path(sys.argv[1]) if (sys := __import__('sys')).argv[1:] else Path(".")

with (root / ".codex-plugin" / "plugin.json").open() as f:
    plugin = json.load(f)

for skill_path in plugin.get("skills", []):
    skill_dir = root / skill_path.lstrip("./")
    if not skill_dir.is_dir():
        raise SystemExit(f"Skill directory not found: {skill_path}")
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise SystemExit(f"SKILL.md not found in: {skill_dir}")

print("   ✓ All skill paths exist")
PY

# 4. Check hook scripts exist
echo "4. Checking hook scripts..."
for script in session_start.py user_prompt_submit.py post_tool_use.py stop.py; do
    path="$REPO_ROOT/skill/codex-hooks/scripts/$script"
    if [ ! -f "$path" ]; then
        echo "   ✗ Missing: $script"
        exit 1
    fi
done
echo "   ✓ All hook scripts exist"

# 5. Check version consistency
echo "5. Checking version consistency..."
sh "$SCRIPT_DIR/check-version.sh"
echo "   ✓ Versions consistent"

# 6. Check hooks config structure
echo "6. Checking hooks configuration..."
python3 - "$REPO_ROOT" <<'PY'
import json
from pathlib import Path

root = Path(sys.argv[1]) if (sys := __import__('sys')).argv[1:] else Path(".")

with (root / ".codex-plugin" / "hooks.json").open() as f:
    hooks = json.load(f)

expected_hooks = ["SessionStart", "UserPromptSubmit", "PostToolUse", "Stop"]
hooks_config = hooks.get("hooks", {})

for hook_name in expected_hooks:
    if hook_name not in hooks_config:
        raise SystemExit(f"Missing hook: {hook_name}")
    hook_list = hooks_config[hook_name]
    if not isinstance(hook_list, list) or len(hook_list) == 0:
        raise SystemExit(f"Hook {hook_name} has no configuration")

print("   ✓ All hooks configured")
PY

echo ""
echo "=== All checks passed ==="
