#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
VERSION_ARG="${1:-}"

python3 - "$REPO_ROOT" "$VERSION_ARG" <<'PY'
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
version = sys.argv[2].strip()
if not version:
    version = (root / "VERSION").read_text(encoding="utf-8").strip()

changelog_path = root / "CHANGELOG.md"
lines = changelog_path.read_text(encoding="utf-8").splitlines()

heading_re = re.compile(rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}\s*$")
start = None
for index, line in enumerate(lines):
    if heading_re.match(line):
        start = index + 1
        break
if start is None:
    raise SystemExit(f"CHANGELOG.md is missing release notes for {version}")

end = len(lines)
for index in range(start, len(lines)):
    if lines[index].startswith("## ["):
        end = index
        break

body = lines[start:end]
while body and not body[0].strip():
    body.pop(0)
while body and not body[-1].strip():
    body.pop()

if not body:
    raise SystemExit(f"CHANGELOG.md release notes for {version} are empty")

print("\n".join(body))
PY
