#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_BIN="$(command -v python3 || command -v python || true)"
CLAUDE_HOOKS_DIR="$SCRIPT_DIR/../claude-hooks/scripts"
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

STATUSLINE_PY="$CLAUDE_HOOKS_DIR/statusline.py"

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

RESUME_STATUSLINE=$(printf '%s' '{"cwd":"'"$RESUME_ROOT"'"}' | "$PYTHON_BIN" "$STATUSLINE_PY")
printf '%s\n' "$RESUME_STATUSLINE" | grep -F " task!:" >/dev/null && fail "paused-only workspace status line should not show explicit task cue"
printf '%s\n' "$RESUME_STATUSLINE" | grep -F " obs:" >/dev/null && fail "paused-only workspace status line should not show observer cue"
printf '%s\n' "$RESUME_STATUSLINE" | grep -F " wksp:" >/dev/null && fail "paused-only workspace status line should not show workspace cue"

LATEST_ROOT="$WORKDIR/latest"
mkdir -p "$LATEST_ROOT"
cd "$LATEST_ROOT"
PLAN_SESSION_KEY= sh "$SCRIPT_DIR/init-task.sh" --slug latest-demo --title "Latest demo" >/dev/null
WORKSPACE_STATUSLINE=$(printf '%s' '{"cwd":"'"$LATEST_ROOT"'"}' | PLAN_SESSION_KEY= "$PYTHON_BIN" "$STATUSLINE_PY")
printf '%s\n' "$WORKSPACE_STATUSLINE" | grep -F "wksp:latest-demo" >/dev/null || fail "workspace fallback status line missed wksp cue"
WORKSPACE_SESSION_START=$(printf '%s' "{\"cwd\":\"$LATEST_ROOT\",\"session_id\":\"wksp-session\"}" | PLAN_SESSION_KEY= "$PYTHON_BIN" "$CLAUDE_HOOKS_DIR/session_start.py")
WORKSPACE_PROMPT_SUBMIT=$(printf '%s' "{\"cwd\":\"$LATEST_ROOT\",\"session_id\":\"wksp-session\",\"prompt\":\"Investigate the fallback task\"}" | PLAN_SESSION_KEY= "$PYTHON_BIN" "$CLAUDE_HOOKS_DIR/user_prompt_submit.py")
WORKSPACE_PRE_TOOL=$(printf '%s' "{\"cwd\":\"$LATEST_ROOT\",\"session_id\":\"wksp-session\",\"tool_name\":\"Task\",\"tool_input\":{\"description\":\"Investigate the fallback task\"}}" | PLAN_SESSION_KEY= "$PYTHON_BIN" "$CLAUDE_HOOKS_DIR/pre_tool_use.py")
WORKSPACE_COMPACT_START=$(printf '%s' "{\"cwd\":\"$LATEST_ROOT\",\"session_id\":\"wksp-session\"}" | PLAN_SESSION_KEY= "$PYTHON_BIN" "$CLAUDE_HOOKS_DIR/compact_session_start.py")
[ -z "$WORKSPACE_PROMPT_SUBMIT" ] || fail "fallback user prompt submit should stay quiet after session-start advisory"
"$PYTHON_BIN" - "$WORKSPACE_SESSION_START" "$WORKSPACE_PRE_TOOL" "$WORKSPACE_COMPACT_START" <<'PY'
import json
import sys

payloads = [json.loads(item) for item in sys.argv[1:]]
for payload in payloads:
    context = (
        payload.get("hookSpecificOutput", {}).get("additionalContext")
        or payload.get("additionalContext", "")
    )
    if "Workspace fallback resolved task `latest-demo`" not in context:
        raise SystemExit(f"fallback hook output missing advisory: {context!r}")
    forbidden = [
        "Task `latest-demo` | status `active`",
        "Next action:",
        "Keep Task launches scoped to the current task.",
        "Compact policy:",
    ]
    for item in forbidden:
        if item in context:
            raise SystemExit(f"fallback hook output unexpectedly included {item!r}: {context!r}")
PY
rm "$LATEST_ROOT/.planning/.active_task"
LATEST_JSON=$(sh "$SCRIPT_DIR/current-task.sh" --json)
"$PYTHON_BIN" - "$LATEST_JSON" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
if payload.get("slug") != "latest-demo":
    raise SystemExit(f"unexpected latest fallback task: {payload.get('slug')!r}")
if payload.get("selection_source") != "latest":
    raise SystemExit(f"unexpected latest fallback source: {payload.get('selection_source')!r}")
PY
LATEST_STATUSLINE=$(printf '%s' '{"cwd":"'"$LATEST_ROOT"'"}' | PLAN_SESSION_KEY= "$PYTHON_BIN" "$STATUSLINE_PY")
printf '%s\n' "$LATEST_STATUSLINE" | grep -F " task!:" >/dev/null && fail "latest fallback status line should not show explicit task cue"
printf '%s\n' "$LATEST_STATUSLINE" | grep -F " obs:" >/dev/null && fail "latest fallback status line should not show observer cue"
printf '%s\n' "$LATEST_STATUSLINE" | grep -F " wksp:" >/dev/null && fail "latest fallback status line should not show workspace cue"
printf '%s\n' "$LATEST_STATUSLINE" | grep -F "latest-demo" >/dev/null && fail "latest fallback status line leaked task slug"

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

BRIEF_ROOT="$WORKDIR/brief"
mkdir -p "$BRIEF_ROOT"
cd "$BRIEF_ROOT"
sh "$SCRIPT_DIR/init-task.sh" --slug brief-demo --title "Brief demo" >/dev/null
"$PYTHON_BIN" - "$BRIEF_ROOT/.planning/brief-demo" <<'PY'
import json
import sys
from pathlib import Path

plan_dir = Path(sys.argv[1])
state_path = plan_dir / "state.json"
task_plan_path = plan_dir / "task_plan.md"
progress_path = plan_dir / "progress.md"

state = json.loads(state_path.read_text(encoding="utf-8"))
if state.get("acceptance_criteria") != []:
    raise SystemExit(f"expected default acceptance_criteria list, got: {state.get('acceptance_criteria')!r}")
if state.get("edge_cases") != []:
    raise SystemExit(f"expected default edge_cases list, got: {state.get('edge_cases')!r}")
spec_context = state.get("spec_context") or {}
if spec_context.get("mode") != "embedded" or spec_context.get("provider") != "none":
    raise SystemExit(f"unexpected default spec_context: {spec_context!r}")

state["goal"] = "Ship brief warning coverage."
state["mode"] = "execute"
state["current_phase"] = "execute"
state["non_goals"] = ["Do not expand into provider linking."]
state["verify_commands"] = ["sh skill/scripts/validate-task.sh --task brief-demo"]
for phase in state.get("phases", []):
    if phase.get("id") == "clarify":
        phase["status"] = "complete"
    elif phase.get("id") == "plan":
        phase["status"] = "complete"
    elif phase.get("id") == "execute":
        phase["status"] = "in_progress"
state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

task_plan = task_plan_path.read_text(encoding="utf-8")
task_plan = task_plan.replace("- Goal: [fill this first]", "- Goal: Ship brief warning coverage.")
task_plan = task_plan.replace("- Current Mode: `clarify`", "- Current Mode: `execute`")
task_plan = task_plan.replace("- Current Phase: `clarify`", "- Current Phase: `execute`")
task_plan_path.write_text(task_plan, encoding="utf-8")

progress = progress_path.read_text(encoding="utf-8")
progress = progress.replace("- Current Mode: `clarify`", "- Current Mode: `execute`")
progress = progress.replace("- Current Phase: `clarify`", "- Current Phase: `execute`")
progress_path.write_text(progress, encoding="utf-8")
PY

BRIEF_JSON=$(sh "$SCRIPT_DIR/current-task.sh" --task brief-demo --json)
"$PYTHON_BIN" - "$BRIEF_JSON" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
if payload.get("brief_quality") != "needs-acceptance":
    raise SystemExit(f"unexpected brief_quality: {payload.get('brief_quality')!r}")
if payload.get("brief_missing_fields") != ["acceptance_criteria"]:
    raise SystemExit(f"unexpected brief_missing_fields: {payload.get('brief_missing_fields')!r}")
spec_context = payload.get("spec_context") or {}
if spec_context.get("mode") != "embedded":
    raise SystemExit(f"unexpected current-task spec_context: {spec_context!r}")
PY

BRIEF_WARN_OUTPUT=$(sh "$SCRIPT_DIR/validate-task.sh" --task brief-demo)
printf '%s\n' "$BRIEF_WARN_OUTPUT" | grep -F "state.json entered execute/verify without acceptance_criteria" >/dev/null || fail "validate-task missed acceptance warning"

SLUG_ROOT="$WORKDIR/slug-override"
mkdir -p "$SLUG_ROOT"
cd "$SLUG_ROOT"
sh "$SCRIPT_DIR/init-task.sh" --title "Readable title" --slug "Custom Slug Value!!!" >/dev/null
"$PYTHON_BIN" - "$SLUG_ROOT/.planning/custom-slug-value" <<'PY'
import json
import sys
from pathlib import Path

plan_dir = Path(sys.argv[1])
if not plan_dir.is_dir():
    raise SystemExit(f"expected normalized slug directory, got missing path: {plan_dir}")

state = json.loads((plan_dir / "state.json").read_text(encoding="utf-8"))
if state.get("title") != "Readable title":
    raise SystemExit(f"unexpected title after slug override: {state.get('title')!r}")
if state.get("slug") != "custom-slug-value":
    raise SystemExit(f"unexpected slug after slug override: {state.get('slug')!r}")
if state.get("planning_path") != ".planning/custom-slug-value":
    raise SystemExit(f"unexpected planning_path after slug override: {state.get('planning_path')!r}")

task_plan = (plan_dir / "task_plan.md").read_text(encoding="utf-8")
progress = (plan_dir / "progress.md").read_text(encoding="utf-8")
if "# Task Plan: Readable title" not in task_plan:
    raise SystemExit("task_plan title did not preserve the user-facing title")
if "- Task Slug: `custom-slug-value`" not in task_plan:
    raise SystemExit("task_plan hot context did not reflect the normalized custom slug")
if "# Progress Log: Readable title" not in progress:
    raise SystemExit("progress title did not preserve the user-facing title")
if "- Task Slug: `custom-slug-value`" not in progress:
    raise SystemExit("progress snapshot did not reflect the normalized custom slug")
PY

LINKED_ROOT="$WORKDIR/linked"
mkdir -p "$LINKED_ROOT/openspec/changes/auth-refresh"
git -C "$LINKED_ROOT" init >/dev/null 2>&1
printf "workspace\n" > "$LINKED_ROOT/README.md"
printf "# Proposal\n" > "$LINKED_ROOT/openspec/changes/auth-refresh/proposal.md"
git -C "$LINKED_ROOT" add README.md openspec/changes/auth-refresh/proposal.md
git -C "$LINKED_ROOT" -c user.name="Smoke Test" -c user.email="smoke@example.com" commit -m "init" >/dev/null 2>&1

cd "$LINKED_ROOT"
sh "$SCRIPT_DIR/init-task.sh" --slug bridge-task --title "Linked provider bridge" >/dev/null
PREFLIGHT_TEXT=$(sh "$SCRIPT_DIR/subagent-preflight.sh" --task bridge-task --host codex --tool-name Task --task-text "Review the linked provider artifact" --text)
PLAN_SESSION_KEY=claude:linked-session sh "$SCRIPT_DIR/set-active-task.sh" --allow-dirty --steal bridge-task >/dev/null
LINKED_JSON=$(sh "$SCRIPT_DIR/current-task.sh" --task bridge-task --json)
LINKED_TEXT=$(sh "$SCRIPT_DIR/current-task.sh" --task bridge-task)
LINKED_SESSION_START=$(printf '%s' "{\"cwd\":\"$LINKED_ROOT\",\"session_id\":\"linked-session\"}" | "$PYTHON_BIN" "$CLAUDE_HOOKS_DIR/session_start.py")
"$PYTHON_BIN" - "$LINKED_JSON" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
spec_context = payload.get("spec_context") or {}
if spec_context.get("provider") != "openspec":
    raise SystemExit(f"unexpected provider: {spec_context!r}")
if spec_context.get("status") != "linked":
    raise SystemExit(f"unexpected spec status: {spec_context!r}")
if spec_context.get("primary_ref") != "openspec/changes/auth-refresh":
    raise SystemExit(f"unexpected primary_ref: {spec_context.get('primary_ref')!r}")
artifact_refs = spec_context.get("artifact_refs") or []
if "openspec/changes/auth-refresh/proposal.md" not in artifact_refs:
    raise SystemExit(f"proposal ref missing from artifact_refs: {artifact_refs!r}")
PY
printf '%s\n' "$LINKED_TEXT" | grep -F "Primary spec ref: openspec/changes/auth-refresh" >/dev/null || fail "current-task text output missed linked primary spec ref"
"$PYTHON_BIN" - "$LINKED_SESSION_START" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
context = payload.get("hookSpecificOutput", {}).get("additionalContext", "")
required = [
    "Spec context: mode=linked | provider=openspec | status=linked",
    "Primary spec ref: openspec/changes/auth-refresh",
]
for item in required:
    if item not in context:
        raise SystemExit(f"session_start output missing {item!r}: {context!r}")
PY

COMPACT_TEXT=$(sh "$SCRIPT_DIR/compact-context.sh" --task bridge-task)
printf '%s\n' "$COMPACT_TEXT" | grep -F "Linked artifacts:" >/dev/null || fail "compact-context text output missed linked artifacts heading"
printf '%s\n' "$COMPACT_TEXT" | grep -F "openspec/changes/auth-refresh/proposal.md" >/dev/null || fail "compact-context text output missed linked proposal ref"
printf '%s\n' "$PREFLIGHT_TEXT" | grep -F "Primary spec ref: openspec/changes/auth-refresh" >/dev/null || fail "subagent-preflight text output missed linked primary spec ref"

DRIFT_JSON=$(sh "$SCRIPT_DIR/check-task-drift.sh" --task bridge-task --prompt "Continue work in openspec/changes/auth-refresh/proposal.md" --json)
"$PYTHON_BIN" - "$DRIFT_JSON" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
if payload.get("classification") != "related":
    raise SystemExit(f"unexpected drift classification for linked spec ref: {payload.get('classification')!r}")
PY

UNCLEAR_PROMPT_SUBMIT=$(printf '%s' "{\"cwd\":\"$LINKED_ROOT\",\"session_id\":\"linked-session\",\"prompt\":\"调研任务漂移检查怎么做，需要梳理原因\"}" | "$PYTHON_BIN" "$CLAUDE_HOOKS_DIR/user_prompt_submit.py")
[ -z "$UNCLEAR_PROMPT_SUBMIT" ] || fail "unclear same-task prompt should not emit a visible drift reminder"
LIKELY_UNRELATED_PROMPT_SUBMIT=$(printf '%s' "{\"cwd\":\"$LINKED_ROOT\",\"session_id\":\"linked-session\",\"prompt\":\"另外新任务：修复 billing webhook\"}" | "$PYTHON_BIN" "$CLAUDE_HOOKS_DIR/user_prompt_submit.py")
"$PYTHON_BIN" - "$LIKELY_UNRELATED_PROMPT_SUBMIT" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
context = payload.get("additionalContext", "")
if "Route evidence for the assistant" not in context:
    raise SystemExit(f"likely-unrelated prompt did not emit route evidence: {context!r}")
if "may be drifting away" in context or "looks likely unrelated" in context:
    raise SystemExit(f"route evidence used old drift conclusion wording: {context!r}")
PY

UNCLEAR_PREFLIGHT_JSON=$(PLAN_SESSION_KEY= sh "$SCRIPT_DIR/subagent-preflight.sh" --task bridge-task --host codex --tool-name Task --task-text "中文范围提问" --json)
"$PYTHON_BIN" - "$UNCLEAR_PREFLIGHT_JSON" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
routing = payload.get("routing") or {}
if routing.get("classification") != "unclear":
    raise SystemExit(f"expected unclear heuristic routing, got: {routing!r}")
if payload.get("decision") not in {"payload_only", "payload_plus_delegate_recommended"}:
    raise SystemExit(f"unclear native Task preflight should still inject route-judgment payload: {payload.get('decision')!r}")
if "Heuristic task fit is unclear" not in str(payload.get("prompt_prefix") or ""):
    raise SystemExit(f"unclear preflight prefix missed route-judgment wording: {payload.get('prompt_prefix')!r}")
PY

AMBIG_ROOT="$WORKDIR/ambiguous"
mkdir -p "$AMBIG_ROOT/openspec/changes/session-runtime" "$AMBIG_ROOT/openspec/changes/runtime-session"
git -C "$AMBIG_ROOT" init >/dev/null 2>&1
printf "workspace\n" > "$AMBIG_ROOT/README.md"
printf "# Proposal\n" > "$AMBIG_ROOT/openspec/changes/session-runtime/proposal.md"
printf "# Proposal\n" > "$AMBIG_ROOT/openspec/changes/runtime-session/proposal.md"
git -C "$AMBIG_ROOT" add README.md openspec/changes/session-runtime/proposal.md openspec/changes/runtime-session/proposal.md
git -C "$AMBIG_ROOT" -c user.name="Smoke Test" -c user.email="smoke@example.com" commit -m "init" >/dev/null 2>&1

cd "$AMBIG_ROOT"
sh "$SCRIPT_DIR/init-task.sh" --slug runtime --title "Runtime" >/dev/null
AMBIG_JSON=$(sh "$SCRIPT_DIR/current-task.sh" --task runtime --json)
AMBIG_TEXT=$(sh "$SCRIPT_DIR/current-task.sh" --task runtime)
AMBIG_COMPACT=$(sh "$SCRIPT_DIR/compact-context.sh" --task runtime)
AMBIG_PREFLIGHT_JSON=$(sh "$SCRIPT_DIR/subagent-preflight.sh" --task runtime --host codex --tool-name Task --task-text "Investigate the runtime candidates" --json)
AMBIG_PREFLIGHT_TEXT=$(sh "$SCRIPT_DIR/subagent-preflight.sh" --task runtime --host codex --tool-name Task --task-text "Investigate the runtime candidates" --text)
PLAN_SESSION_KEY=claude:runtime-session sh "$SCRIPT_DIR/set-active-task.sh" --allow-dirty --steal runtime >/dev/null
AMBIG_SESSION_START=$(printf '%s' "{\"cwd\":\"$AMBIG_ROOT\",\"session_id\":\"runtime-session\"}" | "$PYTHON_BIN" "$CLAUDE_HOOKS_DIR/session_start.py")
"$PYTHON_BIN" - "$AMBIG_JSON" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
spec_context = payload.get("spec_context") or {}
if spec_context.get("status") != "ambiguous":
    raise SystemExit(f"unexpected ambiguous status before override: {spec_context!r}")
refs = spec_context.get("artifact_refs") or []
expected = {
    "openspec/changes/runtime-session",
    "openspec/changes/session-runtime",
}
if set(refs) != expected:
    raise SystemExit(f"unexpected ambiguous refs before override: {refs!r}")
candidate_refs = payload.get("spec_candidate_refs") or []
if set(candidate_refs) != expected:
    raise SystemExit(f"unexpected spec_candidate_refs before override: {candidate_refs!r}")
hint = payload.get("spec_resolution_hint") or ""
if "set-task-spec-context.sh --task runtime --ref <chosen-spec-ref>" not in hint:
    raise SystemExit(f"unexpected spec_resolution_hint before override: {hint!r}")
PY
"$PYTHON_BIN" - "$AMBIG_SESSION_START" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
context = payload.get("hookSpecificOutput", {}).get("additionalContext", "")
required = [
    "Spec context: mode=linked | provider=openspec | status=ambiguous",
    "Spec candidates:",
    "openspec/changes/runtime-session",
    "openspec/changes/session-runtime",
    "Resolve explicitly: sh skill/scripts/set-task-spec-context.sh --task runtime --ref <chosen-spec-ref>",
]
for item in required:
    if item not in context:
        raise SystemExit(f"session_start output missing {item!r}: {context!r}")
PY
"$PYTHON_BIN" - "$AMBIG_PREFLIGHT_JSON" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
task = payload.get("task") or {}
if payload.get("decision") not in {"payload_only", "payload_plus_delegate_recommended"}:
    raise SystemExit(f"unexpected preflight decision for ambiguous spec context: {payload.get('decision')!r}")
if task.get("spec_candidate_refs") != ["openspec/changes/session-runtime", "openspec/changes/runtime-session"] and task.get("spec_candidate_refs") != ["openspec/changes/runtime-session", "openspec/changes/session-runtime"]:
    raise SystemExit(f"unexpected preflight spec_candidate_refs: {task.get('spec_candidate_refs')!r}")
hint = task.get("spec_resolution_hint") or ""
if "set-task-spec-context.sh --task runtime --ref <chosen-spec-ref>" not in hint:
    raise SystemExit(f"unexpected preflight spec_resolution_hint: {hint!r}")
commands = task.get("spec_resolution_commands") or []
if len(commands) < 2:
    raise SystemExit(f"unexpected preflight spec_resolution_commands: {commands!r}")
PY
printf '%s\n' "$AMBIG_TEXT" | grep -F "Spec candidates:" >/dev/null || fail "current-task text output missed ambiguous candidates heading"
printf '%s\n' "$AMBIG_TEXT" | grep -F "openspec/changes/runtime-session" >/dev/null || fail "current-task text output missed runtime-session candidate"
printf '%s\n' "$AMBIG_TEXT" | grep -F "openspec/changes/session-runtime" >/dev/null || fail "current-task text output missed session-runtime candidate"
printf '%s\n' "$AMBIG_TEXT" | grep -F "Resolve with: sh skill/scripts/set-task-spec-context.sh --task runtime --ref openspec/changes/" >/dev/null || fail "current-task text output missed ambiguous resolve command"
printf '%s\n' "$AMBIG_COMPACT" | grep -F "Spec candidates:" >/dev/null || fail "compact-context output missed ambiguous candidates heading"
printf '%s\n' "$AMBIG_COMPACT" | grep -F "Resolve explicitly: sh skill/scripts/set-task-spec-context.sh --task runtime --ref <chosen-spec-ref>" >/dev/null || fail "compact-context output missed ambiguous resolve hint"
printf '%s\n' "$AMBIG_PREFLIGHT_TEXT" | grep -F "Spec candidates:" >/dev/null || fail "subagent-preflight text output missed ambiguous candidates heading"
printf '%s\n' "$AMBIG_PREFLIGHT_TEXT" | grep -F "Resolve explicitly: sh skill/scripts/set-task-spec-context.sh --task runtime --ref <chosen-spec-ref>" >/dev/null || fail "subagent-preflight text output missed ambiguous resolve hint"
printf '%s\n' "$AMBIG_PREFLIGHT_TEXT" | grep -F "Exploratory work may reference these as non-authoritative candidates." >/dev/null || fail "subagent-preflight text output missed ambiguous exploratory guidance"

sh "$SCRIPT_DIR/set-task-spec-context.sh" --task runtime --ref openspec/changes/runtime-session --artifact openspec/changes/runtime-session/proposal.md >/dev/null
OVERRIDDEN_JSON=$(sh "$SCRIPT_DIR/current-task.sh" --task runtime --json)
"$PYTHON_BIN" - "$OVERRIDDEN_JSON" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
spec_context = payload.get("spec_context") or {}
if spec_context.get("status") != "linked":
    raise SystemExit(f"unexpected status after manual override: {spec_context!r}")
if spec_context.get("primary_ref") != "openspec/changes/runtime-session":
    raise SystemExit(f"unexpected primary_ref after manual override: {spec_context.get('primary_ref')!r}")
artifacts = spec_context.get("artifact_refs") or []
if artifacts != ["openspec/changes/runtime-session/proposal.md"]:
    raise SystemExit(f"unexpected artifact refs after manual override: {artifacts!r}")
PY
grep -F 'mode=`linked` | provider=`openspec` | status=`linked`' "$AMBIG_ROOT/.planning/runtime/task_plan.md" >/dev/null || fail "manual spec_context override did not sync task_plan hot context"

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
    "- Next Action: Fill in goal, non-goals, acceptance criteria, constraints, and open questions before implementation.",
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

"$PYTHON_BIN" - "$VALIDATE_ROOT/.planning/warning-demo" <<'PY'
import json
import sys
from pathlib import Path

plan_dir = Path(sys.argv[1])
state_path = plan_dir / "state.json"
progress_path = plan_dir / "progress.md"

state = json.loads(state_path.read_text(encoding="utf-8"))
state["goal"] = "Refresh compact hook writer coverage."
state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

progress = progress_path.read_text(encoding="utf-8")
progress = progress.replace(
    "- Next Action: Fill in goal, non-goals, acceptance criteria, constraints, and open questions before implementation.",
    "- Next Action: compact hook stale action",
)
progress_path.write_text(progress, encoding="utf-8")
PY

PLAN_SESSION_KEY=claude:compact-writer sh "$SCRIPT_DIR/set-active-task.sh" --allow-dirty --steal warning-demo >/dev/null
COMPACT_SESSION_START=$(printf '%s' "{\"cwd\":\"$VALIDATE_ROOT\",\"session_id\":\"compact-writer\"}" | "$PYTHON_BIN" "$CLAUDE_HOOKS_DIR/compact_session_start.py")
"$PYTHON_BIN" - "$COMPACT_SESSION_START" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
context = payload.get("hookSpecificOutput", {}).get("additionalContext", "")
required = [
    "Task `warning-demo` | status `active`",
    "Goal: Refresh compact hook writer coverage.",
    "Compact policy:",
]
for item in required:
    if item not in context:
        raise SystemExit(f"compact_session_start output missing {item!r}: {context!r}")
PY
POST_COMPACT_VALIDATE=$(sh "$SCRIPT_DIR/validate-task.sh" --task warning-demo)
printf '%s\n' "$POST_COMPACT_VALIDATE" | grep -F "Validation passed." >/dev/null || fail "compact_session_start did not leave writer task clean"
[ -f "$VALIDATE_ROOT/.planning/warning-demo/.derived/context_compact.json" ] || fail "compact_session_start did not refresh compact artifact"

sh "$SCRIPT_DIR/init-task.sh" --slug compact-fail --title "Compact fail" >/dev/null
PLAN_SESSION_KEY=claude:compact-fail sh "$SCRIPT_DIR/set-active-task.sh" --allow-dirty --steal compact-fail >/dev/null
rm "$VALIDATE_ROOT/.planning/compact-fail/progress.md"
COMPACT_FAIL_SESSION_START=$(printf '%s' "{\"cwd\":\"$VALIDATE_ROOT\",\"session_id\":\"compact-fail\"}" | "$PYTHON_BIN" "$CLAUDE_HOOKS_DIR/compact_session_start.py")
"$PYTHON_BIN" - "$COMPACT_FAIL_SESSION_START" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
context = payload.get("hookSpecificOutput", {}).get("additionalContext", "")
required = [
    "Compact sync warning for `compact-fail`:",
    "Missing required file: progress.md",
    "Task `compact-fail` | status `active`",
]
for item in required:
    if item not in context:
        raise SystemExit(f"compact_session_start failure output missing {item!r}: {context!r}")
if "Compression estimate:" in context:
    raise SystemExit(f"compact_session_start failure output unexpectedly used compact context: {context!r}")
PY

sh "$SCRIPT_DIR/init-task.sh" --slug observer-demo --title "Observer demo" >/dev/null
"$PYTHON_BIN" - "$VALIDATE_ROOT/.planning/observer-demo" <<'PY'
import json
import sys
from pathlib import Path

plan_dir = Path(sys.argv[1])
state_path = plan_dir / "state.json"
progress_path = plan_dir / "progress.md"

state = json.loads(state_path.read_text(encoding="utf-8"))
state["goal"] = "Observer compact sync should stay derived-only."
state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

progress = progress_path.read_text(encoding="utf-8")
progress = progress.replace(
    "- Next Action: Fill in goal, non-goals, acceptance criteria, constraints, and open questions before implementation.",
    "- Next Action: observer stale action",
)
progress_path.write_text(progress, encoding="utf-8")
PY
PLAN_SESSION_KEY=claude:observer-compact sh "$SCRIPT_DIR/set-active-task.sh" --allow-dirty --observe observer-demo >/dev/null
OBSERVER_SYNC_JSON=$(cd "$VALIDATE_ROOT" && PLAN_SESSION_KEY=claude:observer-compact sh "$SCRIPT_DIR/compact-sync.sh" --task observer-demo --json)
"$PYTHON_BIN" - "$OBSERVER_SYNC_JSON" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
if payload.get("task", {}).get("binding_role") != "observer":
    raise SystemExit(f"unexpected observer binding role: {payload!r}")
if payload.get("main_sync", {}).get("status") != "skipped_observer":
    raise SystemExit(f"observer compact sync unexpectedly touched main planning: {payload!r}")
if payload.get("artifact_sync", {}).get("status") != "persisted":
    raise SystemExit(f"observer compact sync did not refresh artifact: {payload!r}")
PY
[ -f "$VALIDATE_ROOT/.planning/observer-demo/.derived/context_compact.json" ] || fail "observer compact sync did not write compact artifact"
OBSERVER_VALIDATE=$(sh "$SCRIPT_DIR/validate-task.sh" --task observer-demo)
printf '%s\n' "$OBSERVER_VALIDATE" | grep -F "Validation passed with warnings." >/dev/null || fail "observer compact sync should preserve main-planning warnings"
printf '%s\n' "$OBSERVER_VALIDATE" | grep -F "task_plan.md Hot Context goal differs from state.json goal" >/dev/null || fail "observer compact sync unexpectedly cleared task_plan warning"
printf '%s\n' "$OBSERVER_VALIDATE" | grep -F "progress.md Snapshot \`next_action\` differs from state.json" >/dev/null || fail "observer compact sync unexpectedly cleared progress warning"

echo "[context-task-planning] smoke test passed: CLI guidance, warning autofix, and compact sync"
