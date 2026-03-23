#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_BIN="$(command -v python3 || command -v python || true)"
WORKDIR=$(mktemp -d "${TMPDIR:-/tmp}/ctp-cli-guidance.XXXXXX")

cleanup() {
    rm -rf "$WORKDIR"
}

fail() {
    echo "[context-task-planning] smoke test failed: $1" >&2
    exit 1
}

create_repo() {
    repo_name="$1"
    repo_dir="$2/$repo_name"

    mkdir -p "$repo_dir"
    git -C "$repo_dir" init >/dev/null 2>&1
    printf "%s\n" "$repo_name" > "$repo_dir/README.md"
    git -C "$repo_dir" add README.md
    git -C "$repo_dir" -c user.name="Smoke Test" -c user.email="smoke@example.com" commit -m "init" >/dev/null 2>&1
}

[ -n "$PYTHON_BIN" ] || fail "python is required for the smoke test"

trap cleanup EXIT HUP INT TERM

EMPTY_ROOT="$WORKDIR/empty"
mkdir -p "$EMPTY_ROOT"
EMPTY_JSON=$(cd "$EMPTY_ROOT" && sh "$SCRIPT_DIR/current-task.sh" --json)
EMPTY_TEXT=$(cd "$EMPTY_ROOT" && sh "$SCRIPT_DIR/current-task.sh")
"$PYTHON_BIN" - "$EMPTY_JSON" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
if payload.get("found"):
    raise SystemExit("expected no task in empty workspace")
if payload.get("recommended_action") != "init-task":
    raise SystemExit(f"unexpected empty-workspace action: {payload.get('recommended_action')!r}")
commands = payload.get("recommended_commands", [])
if not commands or "init-task.sh" not in commands[0]:
    raise SystemExit(f"expected init-task suggestion, got: {commands!r}")
PY
printf '%s\n' "$EMPTY_TEXT" | grep -F "Recommended next step: init-task" >/dev/null || fail "empty workspace text output missed init guidance"

RESUME_ROOT="$WORKDIR/resume"
mkdir -p "$RESUME_ROOT"
cd "$RESUME_ROOT"
sh "$SCRIPT_DIR/init-task.sh" --slug paused-task --title "Paused task" >/dev/null
sh "$SCRIPT_DIR/pause-task.sh" paused-task >/dev/null
RESUME_JSON=$(sh "$SCRIPT_DIR/current-task.sh" --json)
RESUME_TEXT=$(sh "$SCRIPT_DIR/current-task.sh")
"$PYTHON_BIN" - "$RESUME_JSON" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
if payload.get("found"):
    raise SystemExit("expected paused-only workspace to have no active task selection")
if payload.get("recommended_action") != "resume-task":
    raise SystemExit(f"unexpected resume action: {payload.get('recommended_action')!r}")
candidates = payload.get("resume_candidates", [])
if len(candidates) != 1 or candidates[0].get("slug") != "paused-task":
    raise SystemExit(f"unexpected resume candidates: {candidates!r}")
commands = payload.get("recommended_commands", [])
if not commands or "resume-task.sh paused-task" not in commands[0]:
    raise SystemExit(f"expected resume command, got: {commands!r}")
PY
printf '%s\n' "$RESUME_TEXT" | grep -F "Resume candidates:" >/dev/null || fail "resume text output missed resume candidates"

MULTI_ROOT="$WORKDIR/multi"
mkdir -p "$MULTI_ROOT"
MULTI_ROOT_REAL=$(cd "$MULTI_ROOT" && pwd -P)
create_repo frontend "$MULTI_ROOT"
create_repo backend "$MULTI_ROOT"

cd "$MULTI_ROOT"
sh "$SCRIPT_DIR/register-repo.sh" --id frontend frontend >/dev/null
sh "$SCRIPT_DIR/register-repo.sh" --id backend backend >/dev/null

PLAN_SESSION_KEY=session-alpha sh "$SCRIPT_DIR/init-task.sh" --slug alpha --repo frontend --repo backend --primary frontend --title "Alpha" >/dev/null
sh "$SCRIPT_DIR/prepare-task-worktree.sh" --task alpha --repo frontend >/dev/null

PLAN_SESSION_KEY=session-beta sh "$SCRIPT_DIR/init-task.sh" --slug beta --repo frontend --primary frontend --title "Beta" >/dev/null
SET_REPOS_TEXT=$(sh "$SCRIPT_DIR/set-task-repos.sh" --task beta --repo frontend --repo backend --primary frontend)
printf '%s\n' "$SET_REPOS_TEXT" | grep -F "Safe shared repos: frontend (frontend)" >/dev/null || fail "set-task-repos missed safe shared repo guidance"
printf '%s\n' "$SET_REPOS_TEXT" | grep -F "backend shares \`backend\` with alpha; run \`sh skill/scripts/prepare-task-worktree.sh --task beta --repo backend\`" >/dev/null || fail "set-task-repos missed backend worktree guidance"

sh "$SCRIPT_DIR/prepare-task-worktree.sh" --task beta --repo frontend >/dev/null
SET_REPOS_TEXT=$(sh "$SCRIPT_DIR/set-task-repos.sh" --task beta --repo frontend --repo backend --primary frontend)
printf '%s\n' "$SET_REPOS_TEXT" | grep -F "Already isolated repos: frontend (.worktrees/beta/frontend)" >/dev/null || fail "set-task-repos missed already isolated repo guidance"
printf '%s\n' "$SET_REPOS_TEXT" | grep -F "backend shares \`backend\` with alpha; run \`sh skill/scripts/prepare-task-worktree.sh --task beta --repo backend\`" >/dev/null || fail "set-task-repos lost backend worktree guidance after isolation"

if BIND_ERROR=$("$PYTHON_BIN" "$SCRIPT_DIR/task_guard.py" bind-session-task --cwd "$MULTI_ROOT" --task beta --role writer --session-key session-gamma 2>&1); then
    fail "expected bind-session-task to fail before backend isolation"
fi
printf '%s\n' "$BIND_ERROR" | grep -F "Writer isolation required before binding this task." >/dev/null || fail "bind-session-task failure missed headline"
printf '%s\n' "$BIND_ERROR" | grep -F "Safe shared repos: (none)" >/dev/null || fail "bind-session-task failure missed safe shared classification"
printf '%s\n' "$BIND_ERROR" | grep -F "backend shares \`backend\` with alpha; run \`sh skill/scripts/prepare-task-worktree.sh --task beta --repo backend\`" >/dev/null || fail "bind-session-task failure missed worktree command"
printf '%s\n' "$BIND_ERROR" | grep -F "Already isolated repos: frontend (.worktrees/beta/frontend)" >/dev/null || fail "bind-session-task failure missed already isolated classification"

BETA_WORKTREE="$MULTI_ROOT/.worktrees/beta/frontend"
CURRENT_JSON=$(cd "$BETA_WORKTREE" && PLAN_SESSION_KEY=session-beta sh "$SCRIPT_DIR/current-task.sh" --json)
CURRENT_TEXT=$(cd "$BETA_WORKTREE" && PLAN_SESSION_KEY=session-beta sh "$SCRIPT_DIR/current-task.sh")
"$PYTHON_BIN" - "$CURRENT_JSON" "$MULTI_ROOT_REAL" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
workspace_root = sys.argv[2]
if payload.get("workspace_root") != workspace_root:
    raise SystemExit(f"unexpected workspace root from worktree: {payload.get('workspace_root')!r}")
if payload.get("slug") != "beta":
    raise SystemExit(f"unexpected selected task from worktree: {payload.get('slug')!r}")
if payload.get("binding_role") != "writer":
    raise SystemExit(f"unexpected binding role in worktree: {payload.get('binding_role')!r}")
if payload.get("recommended_action") != "continue-current-task":
    raise SystemExit(f"unexpected current-task recommendation: {payload.get('recommended_action')!r}")
summary = payload.get("repo_summary", {})
if summary.get("shared_repo_ids") != ["backend"]:
    raise SystemExit(f"unexpected shared repo summary: {summary!r}")
if summary.get("worktree_repo_ids") != ["frontend"]:
    raise SystemExit(f"unexpected worktree repo summary: {summary!r}")
commands = payload.get("recommended_commands", [])
if not any("list-worktrees.sh --task beta" in command for command in commands):
    raise SystemExit(f"expected list-worktrees suggestion for multi-repo task, got: {commands!r}")
PY
printf '%s\n' "$CURRENT_TEXT" | grep -F "Repo bindings: shared=backend (backend) | worktree=frontend (.worktrees/beta/frontend)" >/dev/null || fail "current-task text output missed repo binding summary"

PLAN_SESSION_KEY=observer-1 sh "$SCRIPT_DIR/set-active-task.sh" --allow-dirty --observe beta >/dev/null
OBSERVER_JSON=$(cd "$MULTI_ROOT" && PLAN_SESSION_KEY=observer-1 sh "$SCRIPT_DIR/current-task.sh" --json)
"$PYTHON_BIN" - "$OBSERVER_JSON" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
if payload.get("binding_role") != "observer":
    raise SystemExit(f"unexpected observer role: {payload.get('binding_role')!r}")
if payload.get("recommended_action") != "observe-or-steal-writer":
    raise SystemExit(f"unexpected observer action: {payload.get('recommended_action')!r}")
commands = payload.get("recommended_commands", [])
required = {
    "sh skill/scripts/validate-task.sh --task beta",
    "sh skill/scripts/set-active-task.sh --steal beta",
    "sh skill/scripts/list-worktrees.sh --task beta",
}
if set(commands) != required:
    raise SystemExit(f"unexpected observer commands: {commands!r}")
PY

VALIDATE_ROOT="$WORKDIR/validate"
mkdir -p "$VALIDATE_ROOT"
cd "$VALIDATE_ROOT"
sh "$SCRIPT_DIR/init-task.sh" --slug warning-demo --title "Warning demo" >/dev/null
"$PYTHON_BIN" - "$VALIDATE_ROOT/.planning/warning-demo" <<'PY'
import json
import sys
from pathlib import Path

plan_dir = Path(sys.argv[1])
state_path = plan_dir / "state.json"
progress_path = plan_dir / "progress.md"

state = json.loads(state_path.read_text(encoding="utf-8"))
state["goal"] = "Ship warning autofix coverage."
state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

progress = progress_path.read_text(encoding="utf-8")
progress = progress.replace(
    "- Next Action: Fill in goal, non-goals, constraints, and open questions before implementation.",
    "- Next Action: stale snapshot action",
)
progress_path.write_text(progress, encoding="utf-8")
PY

WARN_OUTPUT=$(sh "$SCRIPT_DIR/validate-task.sh" --task warning-demo)
printf '%s\n' "$WARN_OUTPUT" | grep -F "Validation passed with warnings." >/dev/null || fail "validate-task did not report warnings before autofix"
printf '%s\n' "$WARN_OUTPUT" | grep -F "task_plan.md Hot Context goal differs from state.json goal" >/dev/null || fail "validate-task missed task_plan warning"
printf '%s\n' "$WARN_OUTPUT" | grep -F "progress.md Snapshot \`next_action\` differs from state.json" >/dev/null || fail "validate-task missed progress warning"

FIX_OUTPUT=$(sh "$SCRIPT_DIR/validate-task.sh" --task warning-demo --fix-warnings)
printf '%s\n' "$FIX_OUTPUT" | grep -F "Applied warning fixes for warning-demo:" >/dev/null || fail "validate-task --fix-warnings did not report applied fixes"
printf '%s\n' "$FIX_OUTPUT" | grep -F "Validation passed." >/dev/null || fail "validate-task --fix-warnings did not finish cleanly"

FINAL_VALIDATE=$(sh "$SCRIPT_DIR/validate-task.sh" --task warning-demo)
printf '%s\n' "$FINAL_VALIDATE" | grep -F "Validation passed." >/dev/null || fail "validate-task did not pass cleanly after autofix"
printf '%s\n' "$FINAL_VALIDATE" | grep -F "warnings" >/dev/null && fail "validate-task still reported warnings after autofix"

echo "[context-task-planning] smoke test passed: CLI guidance and warning autofix"
