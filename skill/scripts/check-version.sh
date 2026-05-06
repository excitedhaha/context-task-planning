#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)

python3 - "$REPO_ROOT" <<'PY'
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
version_path = root / "VERSION"
skill_path = root / "skill" / "SKILL.md"
plugin_path = root / ".claude-plugin" / "plugin.json"
marketplace_path = root / ".claude-plugin" / "marketplace.json"
codex_plugin_path = root / ".codex-plugin" / "plugin.json"
changelog_path = root / "CHANGELOG.md"

if not version_path.is_file():
    raise SystemExit("VERSION is missing")

version = version_path.read_text(encoding="utf-8").strip()
if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
    raise SystemExit(f"VERSION must be MAJOR.MINOR.PATCH, got {version!r}")

skill_text = skill_path.read_text(encoding="utf-8")
skill_match = re.search(r'^\s+version:\s+["\']([^"\']+)["\']\s*$', skill_text, re.MULTILINE)
if not skill_match:
    raise SystemExit("skill/SKILL.md metadata.version is missing")
if skill_match.group(1) != version:
    raise SystemExit(
        f"skill/SKILL.md metadata.version {skill_match.group(1)!r} does not match VERSION {version!r}"
    )

with plugin_path.open(encoding="utf-8") as fh:
    plugin = json.load(fh)
plugin_version = plugin.get("version")
if plugin_version != version:
    raise SystemExit(
        f".claude-plugin/plugin.json version {plugin_version!r} does not match VERSION {version!r}"
    )

# Check Codex plugin version
if codex_plugin_path.is_file():
    with codex_plugin_path.open(encoding="utf-8") as fh:
        codex_plugin = json.load(fh)
    codex_plugin_version = codex_plugin.get("version")
    if codex_plugin_version != version:
        raise SystemExit(
            f".codex-plugin/plugin.json version {codex_plugin_version!r} does not match VERSION {version!r}"
        )

with marketplace_path.open(encoding="utf-8") as fh:
    marketplace = json.load(fh)
for entry in marketplace.get("plugins") or []:
    if entry.get("name") == plugin.get("name") and "version" in entry:
        raise SystemExit(
            ".claude-plugin/marketplace.json must not set the plugin version; plugin.json is the authority"
        )

changelog = changelog_path.read_text(encoding="utf-8")
heading = rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}\s*$"
if not re.search(heading, changelog, re.MULTILINE):
    raise SystemExit(f"CHANGELOG.md is missing a dated section for {version}")
if "## [Unreleased]" not in changelog:
    raise SystemExit("CHANGELOG.md must keep an Unreleased section")

# Check OpenCode plugin version
opencode_plugin_path = root / "skill" / "opencode-plugin" / "task-focus-guard.js"
if opencode_plugin_path.is_file():
    plugin_text = opencode_plugin_path.read_text(encoding="utf-8")
    plugin_version_match = re.search(r'^const PLUGIN_VERSION\s*=\s*["\']([^"\']+)["\']', plugin_text, re.MULTILINE)
    if not plugin_version_match:
        raise SystemExit("skill/opencode-plugin/task-focus-guard.js PLUGIN_VERSION is missing")
    if plugin_version_match.group(1) != version:
        raise SystemExit(
            f"skill/opencode-plugin/task-focus-guard.js PLUGIN_VERSION {plugin_version_match.group(1)!r} "
            f"does not match VERSION {version!r}"
        )

# Check OpenCode command files exist
opencode_commands_dir = root / "skill" / "opencode-commands"
expected_commands = ["task-current.md", "task-done.md", "task-drift.md", "task-init.md", "task-list.md", "task-validate.md"]
for cmd in expected_commands:
    if not (opencode_commands_dir / cmd).is_file():
        raise SystemExit(f"Missing OpenCode command file: skill/opencode-commands/{cmd}")

# Check npm package version (if built)
npm_package_path = root / "packages" / "opencode-plugin" / "package.json"
if npm_package_path.is_file():
    with npm_package_path.open(encoding="utf-8") as fh:
        npm_pkg = json.load(fh)
    npm_version = npm_pkg.get("version")
    if npm_version != version:
        raise SystemExit(
            f"packages/opencode-plugin/package.json version {npm_version!r} "
            f"does not match VERSION {version!r}"
        )

print(f"Version metadata is consistent: {version}")
PY
