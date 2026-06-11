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
echo "2. Checking skill/codex-hooks/hooks.json..."
python3 -m json.tool "$REPO_ROOT/skill/codex-hooks/hooks.json" > /dev/null
echo "   ✓ Valid JSON"

# 3. Check skill path exists
echo "3. Checking skill path..."
python3 - "$REPO_ROOT" <<'PY'
import json
from pathlib import Path

root = Path(sys.argv[1]) if (sys := __import__('sys')).argv[1:] else Path(".")

with (root / ".codex-plugin" / "plugin.json").open() as f:
    plugin = json.load(f)

skill_path = plugin.get("skills")
if skill_path != "./skills":
    raise SystemExit('Codex plugin skills must be the string "./skills"')

skills_dir = root / skill_path.lstrip("./")
if not skills_dir.is_dir():
    raise SystemExit(f"Skill directory not found: {skill_path}")

for skill_name in (
    "context-task-planning",
    "task-current",
    "task-done",
    "task-drift",
    "task-init",
    "task-list",
    "task-validate",
):
    skill_md = skills_dir / skill_name / "SKILL.md"
    if not skill_md.is_file():
        raise SystemExit(f"SKILL.md not found for Codex skill: {skill_name}")

print("   ✓ Skill path and entry skills exist")
PY

# 4. Check hook scripts exist
echo "4. Checking hook scripts..."
for script in session_start.py user_prompt_submit.py subagent_start.py post_tool_use.py stop.py; do
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

with (root / ".codex-plugin" / "plugin.json").open() as f:
    plugin = json.load(f)

if plugin.get("hooks") != "./skill/codex-hooks/hooks.json":
    raise SystemExit("Codex plugin hooks path must be ./skill/codex-hooks/hooks.json")

if (root / ".codex-plugin" / "hooks.json").exists():
    raise SystemExit(".codex-plugin/hooks.json should not exist; keep only plugin.json in .codex-plugin/")

with (root / "skill" / "codex-hooks" / "hooks.json").open() as f:
    hooks = json.load(f)

expected_hooks = ["SessionStart", "UserPromptSubmit", "SubagentStart", "PostToolUse", "Stop"]
hooks_config = hooks.get("hooks", {})

for hook_name in expected_hooks:
    if hook_name not in hooks_config:
        raise SystemExit(f"Missing hook: {hook_name}")
    hook_list = hooks_config[hook_name]
    if not isinstance(hook_list, list) or len(hook_list) == 0:
        raise SystemExit(f"Hook {hook_name} has no configuration")

session_matcher = str(hooks_config["SessionStart"][0].get("matcher") or "")
if "compact" not in session_matcher.split("|"):
    raise SystemExit("SessionStart matcher must include compact")

for hook_name in expected_hooks:
    for group in hooks_config[hook_name]:
        for handler in group.get("hooks", []):
            command = str(handler.get("command") or "")
            if "${PLUGIN_ROOT}/skill/codex-hooks/scripts/" not in command:
                raise SystemExit(f"Hook {hook_name} does not use PLUGIN_ROOT: {command}")

interface = plugin.get("interface") or {}
for field in ("displayName", "shortDescription", "longDescription", "developerName", "defaultPrompt", "brandColor"):
    if field not in interface:
        raise SystemExit(f"Codex plugin interface.{field} is missing")

print("   ✓ All hooks configured")
PY

echo ""
echo "=== All checks passed ==="
