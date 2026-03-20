#!/bin/sh

set -eu

if [ "$#" -eq 0 ]; then
    echo "Usage: $0 <text>" >&2
    exit 1
fi

INPUT="$*"

if command -v python3 >/dev/null 2>&1; then
    python3 - "$INPUT" <<'PY'
import datetime
import re
import sys
import unicodedata

text = " ".join(sys.argv[1:]).strip()
normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")

if not slug:
    slug = "task-" + datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")

print(slug)
PY
    exit 0
fi

slug=$(printf '%s' "$INPUT" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-')
slug=${slug#-}
slug=${slug%-}

if [ -z "$slug" ]; then
    slug="task-$(date -u +%Y%m%d-%H%M%S)"
fi

printf '%s\n' "$slug"
