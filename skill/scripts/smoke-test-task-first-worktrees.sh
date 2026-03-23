#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WORKDIR=$(mktemp -d "${TMPDIR:-/tmp}/ctp-task-first-worktrees.XXXXXX")
WORKDIR_REAL=$(cd "$WORKDIR" && pwd -P)

cleanup() {
    rm -rf "$WORKDIR"
}

fail() {
    echo "[context-task-planning] smoke test failed: $1" >&2
    exit 1
}

create_repo() {
    repo_name="$1"
    repo_dir="$WORKDIR/$repo_name"

    mkdir -p "$repo_dir"
    git -C "$repo_dir" init >/dev/null 2>&1
    printf "%s\n" "$repo_name" > "$repo_dir/README.md"
    git -C "$repo_dir" add README.md
    git -C "$repo_dir" -c user.name="Smoke Test" -c user.email="smoke@example.com" commit -m "init" >/dev/null 2>&1
}

trap cleanup EXIT HUP INT TERM

create_repo frontend
create_repo backend

cd "$WORKDIR"

sh "$SCRIPT_DIR/register-repo.sh" --id frontend frontend >/dev/null
sh "$SCRIPT_DIR/register-repo.sh" --id backend backend >/dev/null

sh "$SCRIPT_DIR/init-task.sh" --slug cross-repo-auth-flow --repo frontend --repo backend --primary frontend --title "Cross-repo auth flow" >/dev/null
sh "$SCRIPT_DIR/prepare-task-worktree.sh" --task cross-repo-auth-flow --repo frontend >/dev/null
sh "$SCRIPT_DIR/prepare-task-worktree.sh" --task cross-repo-auth-flow --repo backend >/dev/null

[ -d "$WORKDIR/.worktrees/cross-repo-auth-flow/frontend" ] || fail "missing frontend worktree for cross-repo-auth-flow"
[ -d "$WORKDIR/.worktrees/cross-repo-auth-flow/backend" ] || fail "missing backend worktree for cross-repo-auth-flow"

sh "$SCRIPT_DIR/init-task.sh" --slug billing-cleanup --repo frontend --primary frontend --title "Billing cleanup" >/dev/null
sh "$SCRIPT_DIR/prepare-task-worktree.sh" --task billing-cleanup --repo frontend >/dev/null

[ -d "$WORKDIR/.worktrees/billing-cleanup/frontend" ] || fail "missing frontend worktree for billing-cleanup"

TEXT_OUTPUT=$(sh "$SCRIPT_DIR/list-worktrees.sh")
python3 - "$TEXT_OUTPUT" <<'PY'
import sys

text = sys.argv[1]
required_fragments = [
    "task=billing-cleanup",
    "repo=frontend path=.worktrees/billing-cleanup/frontend",
    "task=cross-repo-auth-flow",
    "repo=backend path=.worktrees/cross-repo-auth-flow/backend",
    "repo=frontend path=.worktrees/cross-repo-auth-flow/frontend",
]
for fragment in required_fragments:
    if fragment not in text:
        raise SystemExit(f"missing text fragment: {fragment}")
PY

JSON_OUTPUT=$(sh "$SCRIPT_DIR/list-worktrees.sh" --json)
python3 - "$JSON_OUTPUT" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
worktrees = payload.get("worktrees", [])
expected = {
    ("billing-cleanup", "frontend", ".worktrees/billing-cleanup/frontend"),
    ("cross-repo-auth-flow", "backend", ".worktrees/cross-repo-auth-flow/backend"),
    ("cross-repo-auth-flow", "frontend", ".worktrees/cross-repo-auth-flow/frontend"),
}
actual = {
    (
        item.get("task_slug"),
        item.get("repo_id"),
        item.get("checkout_path"),
    )
    for item in worktrees
}
if actual != expected:
    raise SystemExit(f"unexpected JSON worktree bindings: {sorted(actual)!r}")
PY

RESOLVED_ROOT=$(cd "$WORKDIR/.worktrees/cross-repo-auth-flow/frontend" && sh "$SCRIPT_DIR/resolve-workspace-root.sh")
[ "$RESOLVED_ROOT" = "$WORKDIR_REAL" ] || fail "worktree path did not resolve back to parent workspace"

cd "$WORKDIR/.worktrees/cross-repo-auth-flow/frontend"
sh "$SCRIPT_DIR/resume-task.sh" cross-repo-auth-flow >/dev/null
CURRENT_TASK_JSON=$(sh "$SCRIPT_DIR/current-task.sh" --json)
python3 - "$CURRENT_TASK_JSON" "$WORKDIR_REAL" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
workspace_root = sys.argv[2]
if payload.get("workspace_root") != workspace_root:
    raise SystemExit(f"unexpected workspace root: {payload.get('workspace_root')!r}")
if payload.get("slug") != "cross-repo-auth-flow":
    raise SystemExit(f"unexpected active task: {payload.get('slug')!r}")
if payload.get("selection_source") not in {"active_pointer", "latest_auto_selectable", "session_binding"}:
    raise SystemExit(f"unexpected selection source: {payload.get('selection_source')!r}")
PY

echo "[context-task-planning] smoke test passed: task-first worktree layout"
