#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

TASK_SLUG=""
DELEGATE_ID=""
DELEGATE_TITLE=""
DELEGATE_KIND=""
DELEGATE_GOAL=""
DELEGATE_DELIVERABLE=""
AUTO_START="yes"
DESCRIPTION=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --task)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --task" >&2; exit 1; }
            TASK_SLUG="$1"
            ;;
        --id)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --id" >&2; exit 1; }
            DELEGATE_ID="$1"
            ;;
        --title)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --title" >&2; exit 1; }
            DELEGATE_TITLE="$1"
            ;;
        --kind)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --kind" >&2; exit 1; }
            DELEGATE_KIND="$1"
            ;;
        --goal)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --goal" >&2; exit 1; }
            DELEGATE_GOAL="$1"
            ;;
        --deliverable)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --deliverable" >&2; exit 1; }
            DELEGATE_DELIVERABLE="$1"
            ;;
        --no-start)
            AUTO_START="no"
            ;;
        -h|--help)
            echo "Usage: $0 [--task slug] [--id delegate-id] [--kind kind] [--title \"title\"] [--goal \"goal\"] [--deliverable \"deliverable\"] [--no-start] <description>" >&2
            exit 0
            ;;
        *)
            if [ -z "$DESCRIPTION" ]; then
                DESCRIPTION="$1"
            else
                DESCRIPTION="$DESCRIPTION $1"
            fi
            ;;
    esac
    shift
done

if [ -z "$DESCRIPTION" ] && [ -z "$DELEGATE_GOAL" ] && [ -z "$DELEGATE_TITLE" ]; then
    echo "Usage: $0 [--task slug] [--id delegate-id] [--kind kind] [--title \"title\"] [--goal \"goal\"] [--deliverable \"deliverable\"] [--no-start] <description>" >&2
    exit 1
fi

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "Python is required to prepare delegates." >&2
    exit 1
fi

export DESCRIPTION DELEGATE_KIND DELEGATE_TITLE DELEGATE_GOAL DELEGATE_DELIVERABLE
INFERRED=$(
"$PYTHON_BIN" <<'PY'
import json
import os
import re

description = os.environ.get("DESCRIPTION", "").strip()
kind_override = os.environ.get("DELEGATE_KIND", "").strip()
title_override = os.environ.get("DELEGATE_TITLE", "").strip()
goal_override = os.environ.get("DELEGATE_GOAL", "").strip()
deliverable_override = os.environ.get("DELEGATE_DELIVERABLE", "").strip()

patterns = [
    ("review", ["review", "diff review", "code review", "pr review", "审查", "评审"]),
    ("verify", ["verify", "validation", "regression", "failing test", "test failure", "triage", "验证", "回归", "测试失败", "失败排查"]),
    ("spike", ["spike", "prototype", "poc", "feasibility", "compare options", "方案对比", "可行性"]),
    ("discovery", ["investigate", "analyze", "map", "scan", "explore", "entry point", "dependency", "research", "调研", "分析", "找入口", "排查"]),
]

deliverables = {
    "review": "List the main risks, regressions, and recommended follow-ups.",
    "verify": "Summarize failures, likely root causes, and the next validation steps.",
    "spike": "Compare options and recommend the most practical direction.",
    "discovery": "List key files, entry points, dependencies, and notable risks.",
    "catchup": "Summarize the current state, open questions, and next action.",
    "other": "Summarize the bounded findings and recommended follow-ups.",
}

def normalize(text: str) -> str:
    return " ".join(text.split())

def infer_kind(text: str) -> str:
    lowered = text.lower()
    for kind, keywords in patterns:
        if any(keyword in lowered for keyword in keywords):
            return kind
    return "other"

clean = normalize(description or goal_override or title_override)
kind = kind_override or infer_kind(clean)
title = title_override or clean or {
    "review": "Review lane",
    "verify": "Verification triage",
    "spike": "Option spike",
    "discovery": "Repo scan",
    "catchup": "Catchup lane",
    "other": "Delegate lane",
}.get(kind, "Delegate lane")
if len(title) > 72:
    title = title[:69].rstrip() + "..."

goal = goal_override or clean or f"Handle the bounded {kind} subproblem."
deliverable = deliverable_override or deliverables.get(kind, deliverables["other"])

print(json.dumps({
    "kind": kind,
    "title": title,
    "goal": goal,
    "deliverable": deliverable,
}))
PY
)

DELEGATE_KIND=$(printf '%s' "$INFERRED" | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["kind"])')
DELEGATE_TITLE=$(printf '%s' "$INFERRED" | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["title"])')
DELEGATE_GOAL=$(printf '%s' "$INFERRED" | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["goal"])')
DELEGATE_DELIVERABLE=$(printf '%s' "$INFERRED" | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["deliverable"])')

RESOLVED_ID="${DELEGATE_ID:-$DELEGATE_TITLE}"
RESOLVED_ID=$(sh "$SCRIPT_DIR/slugify.sh" "$RESOLVED_ID")

if [ -n "$TASK_SLUG" ]; then
    if [ -n "$DELEGATE_ID" ]; then
        sh "$SCRIPT_DIR/create-delegate.sh" --task "$TASK_SLUG" --id "$DELEGATE_ID" --kind "$DELEGATE_KIND" --goal "$DELEGATE_GOAL" --deliverable "$DELEGATE_DELIVERABLE" "$DELEGATE_TITLE"
    else
        sh "$SCRIPT_DIR/create-delegate.sh" --task "$TASK_SLUG" --kind "$DELEGATE_KIND" --goal "$DELEGATE_GOAL" --deliverable "$DELEGATE_DELIVERABLE" "$DELEGATE_TITLE"
    fi
elif [ -n "$DELEGATE_ID" ]; then
    sh "$SCRIPT_DIR/create-delegate.sh" --id "$DELEGATE_ID" --kind "$DELEGATE_KIND" --goal "$DELEGATE_GOAL" --deliverable "$DELEGATE_DELIVERABLE" "$DELEGATE_TITLE"
else
    sh "$SCRIPT_DIR/create-delegate.sh" --kind "$DELEGATE_KIND" --goal "$DELEGATE_GOAL" --deliverable "$DELEGATE_DELIVERABLE" "$DELEGATE_TITLE"
fi

if [ "$AUTO_START" = "yes" ]; then
    if [ -n "$TASK_SLUG" ]; then
        sh "$SCRIPT_DIR/start-delegate.sh" --task "$TASK_SLUG" --summary "Prepared from: $DELEGATE_GOAL" "$RESOLVED_ID"
    else
        sh "$SCRIPT_DIR/start-delegate.sh" --summary "Prepared from: $DELEGATE_GOAL" "$RESOLVED_ID"
    fi
fi

echo "[context-task-planning] Prepared delegate lane: $RESOLVED_ID"
echo "[context-task-planning] Kind: $DELEGATE_KIND"
echo "[context-task-planning] Goal: $DELEGATE_GOAL"
echo "[context-task-planning] Deliverable: $DELEGATE_DELIVERABLE"
