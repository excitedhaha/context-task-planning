#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

TASK_SLUG=""
FIX_WARNINGS=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --task)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --task" >&2; exit 1; }
            TASK_SLUG="$1"
            ;;
        --fix-warnings)
            FIX_WARNINGS=1
            ;;
        -h|--help)
            echo "Usage: $0 [--task slug] [--fix-warnings]" >&2
            exit 0
            ;;
        *)
            echo "Unexpected argument: $1" >&2
            exit 1
            ;;
    esac
    shift
done

PLAN_DIR=$(sh "$SCRIPT_DIR/resolve-plan-dir.sh" "$TASK_SLUG")
if [ -z "$PLAN_DIR" ] || [ ! -d "$PLAN_DIR" ]; then
    echo "[context-task-planning] No task found to validate." >&2
    exit 1
fi

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "[context-task-planning] Python is required to validate tasks." >&2
    exit 1
fi

"$PYTHON_BIN" - "$PLAN_DIR" "$FIX_WARNINGS" "$SCRIPT_DIR" <<'PY'
import json
import re
import sys
from pathlib import Path

plan_dir = Path(sys.argv[1])
fix_warnings = sys.argv[2] == "1"
script_dir = Path(sys.argv[3])
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

import compact_context
import task_guard

state_file = plan_dir / "state.json"
task_plan_file = plan_dir / "task_plan.md"
findings_file = plan_dir / "findings.md"
progress_file = plan_dir / "progress.md"
delegates_dir = plan_dir / "delegates"

valid_task_statuses = {"active", "paused", "blocked", "verifying", "done", "archived"}
valid_modes = {"clarify", "plan", "execute", "verify", "archive"}
valid_phase_statuses = {"pending", "in_progress", "complete", "blocked"}
active_delegate_statuses = {"pending", "running", "blocked"}
terminal_delegate_statuses = {"complete", "cancelled"}


def extract_inline_value(line: str) -> str:
    text = line.split(":", 1)[1].strip()
    if text.startswith("`") and text.endswith("`") and text.count("`") == 2:
        return text[1:-1].strip()
    return text


def normalize_free_text(value: str) -> str:
    return " ".join(value.replace("`", "").split())


def normalized_items(values: list[str]) -> list[str]:
    return [normalize_free_text(str(value)) for value in values if str(value).strip()]


def read_json(path: Path, label: str, issues: list[str]):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        issues.append(f"Missing required file: {label} ({path})")
    except json.JSONDecodeError as exc:
        issues.append(f"Invalid JSON in {label}: {exc}")
    return None


def parse_task_plan_hot_context(path: Path):
    fields = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    in_hot_context = False
    for line in lines:
        if line.startswith("## Hot Context"):
            in_hot_context = True
            continue
        if in_hot_context and line.startswith("## "):
            break
        if not in_hot_context:
            continue

        if line.startswith("- Task Slug:"):
            fields["slug"] = extract_inline_value(line)
        elif line.startswith("- Task Status:"):
            fields["status"] = extract_inline_value(line)
        elif line.startswith("- Goal:"):
            fields["goal"] = extract_inline_value(line)
        elif line.startswith("- Current Mode:"):
            fields["mode"] = extract_inline_value(line)
        elif line.startswith("- Current Phase:"):
            fields["phase"] = extract_inline_value(line)
        elif line.startswith("- Next Action:"):
            fields["next_action"] = extract_inline_value(line)
        elif line.startswith("- Primary Repo:"):
            fields["primary_repo"] = extract_inline_value(line)
        elif line.startswith("- Repo Scope:"):
            fields["repo_scope"] = extract_inline_value(line)
    return fields


def parse_progress_snapshot(path: Path):
    fields = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    in_snapshot = False
    for line in lines:
        if line.startswith("## Snapshot"):
            in_snapshot = True
            continue
        if in_snapshot and line.startswith("## "):
            break
        if not in_snapshot:
            continue

        if line.startswith("- Task Slug:"):
            fields["slug"] = extract_inline_value(line)
        elif line.startswith("- Status:"):
            fields["status"] = extract_inline_value(line)
        elif line.startswith("- Current Mode:"):
            fields["mode"] = extract_inline_value(line)
        elif line.startswith("- Current Phase:"):
            fields["phase"] = extract_inline_value(line)
        elif line.startswith("- Next Action:"):
            fields["next_action"] = extract_inline_value(line)
        elif line.startswith("- Primary Repo:"):
            fields["primary_repo"] = extract_inline_value(line)
        elif line.startswith("- Repo Scope:"):
            fields["repo_scope"] = extract_inline_value(line)
        elif line.startswith("- Last Updated:"):
            fields["last_updated"] = extract_inline_value(line)
    return fields


def section_bounds(lines: list[str], heading: str) -> tuple[int, int]:
    start = -1
    for index, line in enumerate(lines):
        if line.startswith(heading):
            start = index + 1
            break
    if start < 0:
        return -1, -1

    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return start, end


def replace_or_insert_section_lines(
    lines: list[str],
    heading: str,
    replacements: list[tuple[str, str]],
) -> tuple[list[str], list[str]]:
    start, end = section_bounds(lines, heading)
    if start < 0:
        return lines, []

    applied = []
    section = lines[start:end]
    for prefix, replacement in replacements:
        replaced = False
        for index, line in enumerate(section):
            if line.startswith(prefix):
                if section[index] != replacement:
                    section[index] = replacement
                    applied.append(replacement)
                replaced = True
                break
        if not replaced:
            insert_at = len(section)
            for index, line in enumerate(section):
                if line.startswith("- Last Updated:"):
                    insert_at = index
                    break
            section.insert(insert_at, replacement)
            applied.append(replacement)

    return lines[:start] + section + lines[end:], applied


def sync_task_plan_hot_context(path: Path, state: dict, spec_context: dict | None = None) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    replacements = []
    state_goal = str(state.get("goal", "")).strip()
    if state_goal:
        replacements.append(("- Goal:", f"- Goal: {state_goal}"))
    next_action = str(state.get("next_action", "")).strip()
    if next_action:
        replacements.append(("- Next Action:", f"- Next Action: {next_action}"))
    replacements.append(
        (
            "- Acceptance Summary:",
            f"- Acceptance Summary: {task_guard.brief_summary_for_state(state)}",
        )
    )
    replacements.append(
        (
            "- Spec Context:",
            f"- Spec Context: {task_guard.spec_context_summary_text(spec_context or state.get('spec_context', {}))}",
        )
    )
    updated_lines, applied = replace_or_insert_section_lines(
        lines, "## Hot Context", replacements
    )
    if applied:
        path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    return applied


def sync_progress_snapshot(path: Path, state: dict) -> list[str]:
    repo_scope = state.get("repo_scope", [])
    replacements = [
        ("- Task Slug:", f"- Task Slug: `{state.get('slug', '')}`"),
        ("- Status:", f"- Status: `{state.get('status', '')}`"),
        ("- Current Mode:", f"- Current Mode: `{state.get('mode', '')}`"),
        ("- Current Phase:", f"- Current Phase: `{state.get('current_phase', '')}`"),
        ("- Next Action:", f"- Next Action: {state.get('next_action', '')}"),
    ]
    if state.get("primary_repo") or repo_scope:
        replacements.append(
            (
                "- Primary Repo:",
                f"- Primary Repo: {state.get('primary_repo', '') or '(unset)'}",
            )
        )
        replacements.append(
            (
                "- Repo Scope:",
                f"- Repo Scope: {', '.join(repo_scope) if repo_scope else '(unset)'}",
            )
        )

    lines = path.read_text(encoding="utf-8").splitlines()
    updated_lines, applied = replace_or_insert_section_lines(
        lines, "## Snapshot", replacements
    )
    if applied:
        path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    return applied


def compact_validation_context(state: dict) -> dict | None:
    if not state:
        return None

    source_path = str(state.get("source_path") or "").strip()
    workspace_root = Path(source_path) if source_path else plan_dir.parent.parent
    task = {
        "workspace_root": str(workspace_root),
        "plan_dir": str(plan_dir),
    }
    artifact_path, _, current, is_fresh = compact_context.freshness_state(task)
    read_policy = current.get("read_policy", {})
    payload_profile = str(read_policy.get("payload_profile") or "compact_optional")
    artifact_exists = artifact_path.exists()
    warning = ""
    if artifact_exists and not is_fresh:
        warning = (
            "Derived compact context artifact is stale: "
            f"{compact_context.rel_path(workspace_root, artifact_path)}"
        )
    elif not artifact_exists and read_policy.get("should_prefer_compact"):
        warning = (
            "Derived compact context artifact is missing for a "
            f"`{payload_profile}` task: {compact_context.rel_path(workspace_root, artifact_path)}"
        )

    return {
        "workspace_root": workspace_root,
        "artifact_path": artifact_path,
        "current": current,
        "artifact_exists": artifact_exists,
        "warning": warning,
    }


def refresh_compact_artifact(state: dict) -> str | None:
    context = compact_validation_context(state)
    if not context or not context.get("warning"):
        return None

    compact_context.persist_payload(context["current"], plan_dir)
    rel_artifact = compact_context.rel_path(
        context["workspace_root"], context["artifact_path"]
    )
    action = "refreshed" if context.get("artifact_exists") else "created"
    return f"{rel_artifact} -> {action} derived compact context"


def effective_spec_context_for_state(state: dict) -> dict:
    source_path = str(state.get("source_path") or "").strip()
    workspace_root = Path(source_path) if source_path else plan_dir.parent.parent
    plan_root = workspace_root / ".planning"
    task_slug = str(state.get("slug") or plan_dir.name)
    repo_bindings = task_guard.effective_task_repo_bindings(
        plan_root, workspace_root, task_slug, state
    )
    return task_guard.detect_openspec_spec_context(workspace_root, state, repo_bindings)


def validate_task() -> tuple[dict, list[str], list[str], dict]:
    issues: list[str] = []
    warnings: list[str] = []

    for required in (task_plan_file, findings_file, progress_file, state_file):
        if not required.exists():
            issues.append(f"Missing required file: {required.name}")

    state = read_json(state_file, "state.json", issues) if state_file.exists() else None
    if state is None:
        state = {}

    required_state_keys = [
        "slug",
        "title",
        "status",
        "mode",
        "goal",
        "planning_path",
        "current_phase",
        "next_action",
        "blockers",
        "verify_commands",
        "phases",
        "delegation",
    ]
    for key in required_state_keys:
        if key not in state:
            issues.append(f"state.json is missing required key `{key}`")

    if state:
        if state.get("status") not in valid_task_statuses:
            issues.append(f"Unknown task status in state.json: {state.get('status')}")
        if state.get("mode") not in valid_modes:
            issues.append(f"Unknown task mode in state.json: {state.get('mode')}")

        for key in ("acceptance_criteria", "edge_cases"):
            if key in state and not isinstance(state.get(key), list):
                issues.append(f"state.json `{key}` must be a list when present")

        raw_spec_context = state.get("spec_context", {})
        if "spec_context" in state and not isinstance(raw_spec_context, dict):
            issues.append("state.json `spec_context` must be an object when present")
            raw_spec_context = {}
        if isinstance(raw_spec_context, dict):
            for field, allowed in (
                ("mode", task_guard.SPEC_CONTEXT_MODES),
                ("provider", task_guard.SPEC_CONTEXT_PROVIDERS),
                ("status", task_guard.SPEC_CONTEXT_STATUSES),
            ):
                value = str(raw_spec_context.get(field) or "").strip()
                if value and value not in allowed:
                    issues.append(
                        f"state.json spec_context.{field} has invalid value `{value}`"
                    )

        phases = state.get("phases", [])
        phase_ids = []
        for phase in phases:
            phase_id = phase.get("id")
            if not phase_id:
                issues.append("A phase in state.json is missing `id`")
                continue
            phase_ids.append(phase_id)
            if phase.get("status") not in valid_phase_statuses:
                issues.append(
                    f"Unknown phase status for `{phase_id}`: {phase.get('status')}"
                )
        current_phase = state.get("current_phase")
        if current_phase and current_phase not in phase_ids and current_phase != "archive":
            issues.append(
                f"current_phase `{current_phase}` is not present in state.json phases"
            )

        delegation = state.get("delegation", {})
        active_delegates = delegation.get("active", [])
        if not isinstance(active_delegates, list):
            issues.append("state.json delegation.active must be a list")
            active_delegates = []
        if len(active_delegates) != len(set(active_delegates)):
            issues.append("state.json delegation.active contains duplicate delegate ids")

        repo_scope = state.get("repo_scope", [])
        if repo_scope and not isinstance(repo_scope, list):
            issues.append("state.json repo_scope must be a list when present")
            repo_scope = []
        if isinstance(repo_scope, list):
            normalized_repo_scope = []
            for repo_id in repo_scope:
                if not isinstance(repo_id, str) or not re.fullmatch(
                    r"[a-z0-9]+(?:-[a-z0-9]+)*", repo_id
                ):
                    issues.append(
                        f"Invalid repo id in state.json repo_scope: {repo_id!r}"
                    )
                    continue
                normalized_repo_scope.append(repo_id)
            if len(normalized_repo_scope) != len(set(normalized_repo_scope)):
                issues.append("state.json repo_scope contains duplicate repo ids")
            primary_repo = state.get("primary_repo", "")
            if primary_repo and primary_repo not in normalized_repo_scope:
                issues.append(
                    "state.json primary_repo must be included in repo_scope"
                )

    if task_plan_file.exists() and state:
        task_plan_sections = compact_context.extract_level2_sections(
            task_plan_file.read_text(encoding="utf-8")
        )
        hot = parse_task_plan_hot_context(task_plan_file)
        required_hot = ["slug", "status", "goal", "mode", "phase", "next_action"]
        for key in required_hot:
            if key not in hot:
                issues.append(f"task_plan.md Hot Context is missing `{key}`")

        expected_hot = {
            "slug": state.get("slug", ""),
            "status": state.get("status", ""),
            "mode": state.get("mode", ""),
            "phase": state.get("current_phase", ""),
            "next_action": state.get("next_action", ""),
        }
        if state.get("primary_repo") or state.get("repo_scope"):
            expected_hot["primary_repo"] = state.get("primary_repo", "") or "(unset)"
            expected_hot["repo_scope"] = (
                ", ".join(state.get("repo_scope", []))
                if state.get("repo_scope")
                else "(unset)"
            )
        for key, expected in expected_hot.items():
            actual = hot.get(key)
            if actual is None:
                continue
            actual_cmp = normalize_free_text(actual) if key == "next_action" else actual
            expected_cmp = (
                normalize_free_text(expected) if key == "next_action" else expected
            )
            if actual_cmp != expected_cmp:
                if key == "next_action" and actual.strip() == "[fill this first]":
                    warnings.append(
                        "task_plan.md Hot Context next_action is still a placeholder; sync it with state.json"
                    )
                    continue
                issues.append(
                    f"task_plan.md Hot Context `{key}` does not match state.json (`{actual}` != `{expected}`)"
                )

        state_goal = str(state.get("goal", "")).strip()
        hot_goal = str(hot.get("goal", "")).strip()
        if state_goal:
            if not hot_goal:
                warnings.append(
                    "task_plan.md Hot Context goal is empty while state.json goal is populated"
                )
            elif normalize_free_text(hot_goal) != normalize_free_text(state_goal):
                warnings.append(
                    "task_plan.md Hot Context goal differs from state.json goal"
                )

        state_acceptance = task_guard.nonempty_text_list(state.get("acceptance_criteria"))
        plan_acceptance = compact_context.bullet_items(
            task_plan_sections.get("Acceptance Criteria", [])
        )
        if normalized_items(state_acceptance) != normalized_items(plan_acceptance):
            warnings.append(
                "task_plan.md Acceptance Criteria does not match state.json acceptance_criteria"
            )

        state_edge_cases = task_guard.nonempty_text_list(state.get("edge_cases"))
        plan_edge_cases = compact_context.bullet_items(
            task_plan_sections.get("Edge Cases", [])
        )
        if normalized_items(state_edge_cases) != normalized_items(plan_edge_cases):
            warnings.append(
                "task_plan.md Edge Cases does not match state.json edge_cases"
            )

    if progress_file.exists() and state:
        snapshot = parse_progress_snapshot(progress_file)
        expected_snapshot = {
            "slug": state.get("slug", ""),
            "status": state.get("status", ""),
            "mode": state.get("mode", ""),
            "phase": state.get("current_phase", ""),
            "next_action": state.get("next_action", ""),
        }
        if state.get("primary_repo") or state.get("repo_scope"):
            expected_snapshot["primary_repo"] = (
                state.get("primary_repo", "") or "(unset)"
            )
            expected_snapshot["repo_scope"] = (
                ", ".join(state.get("repo_scope", []))
                if state.get("repo_scope")
                else "(unset)"
            )
        for key, expected in expected_snapshot.items():
            actual = snapshot.get(key)
            if actual is None:
                warnings.append(f"progress.md Snapshot is missing `{key}`")
            else:
                actual_cmp = normalize_free_text(actual) if key == "next_action" else actual
                expected_cmp = (
                    normalize_free_text(expected) if key == "next_action" else expected
                )
                if actual_cmp == expected_cmp:
                    continue
                warnings.append(
                    f"progress.md Snapshot `{key}` differs from state.json (`{actual}` != `{expected}`)"
                )

    delegate_states = {}
    if delegates_dir.exists():
        for entry in delegates_dir.iterdir():
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            status_path = entry / "status.json"
            brief_path = entry / "brief.md"
            result_path = entry / "result.md"

            if not brief_path.exists():
                issues.append(f"Delegate `{entry.name}` is missing brief.md")
            if not result_path.exists():
                issues.append(f"Delegate `{entry.name}` is missing result.md")
            dstate = (
                read_json(status_path, f"delegate {entry.name} status.json", issues)
                if status_path.exists()
                else None
            )
            if dstate is None:
                continue

            delegate_id = dstate.get("delegate_id", entry.name)
            if delegate_id != entry.name:
                issues.append(
                    f"Delegate directory `{entry.name}` does not match status.json delegate_id `{delegate_id}`"
                )
            status = dstate.get("status")
            if status not in active_delegate_statuses | terminal_delegate_statuses:
                issues.append(f"Delegate `{delegate_id}` has invalid status `{status}`")
            delegate_states[delegate_id] = dstate
    else:
        issues.append("delegates/ directory is missing")

    if state:
        active_delegates = state.get("delegation", {}).get("active", [])
        for delegate_id in active_delegates:
            dstate = delegate_states.get(delegate_id)
            if dstate is None:
                issues.append(
                    f"state.json marks delegate `{delegate_id}` active, but no matching delegate status file exists"
                )
                continue
            status = dstate.get("status")
            if status not in active_delegate_statuses:
                warnings.append(
                    f"Delegate `{delegate_id}` is active in state.json but has terminal status `{status}`"
                )

        for delegate_id, dstate in delegate_states.items():
            status = dstate.get("status")
            if status in active_delegate_statuses and delegate_id not in active_delegates:
                warnings.append(
                    f"Delegate `{delegate_id}` has status `{status}` but is missing from state.json delegation.active"
                )
            if status in terminal_delegate_statuses and delegate_id in active_delegates:
                warnings.append(
                    f"Delegate `{delegate_id}` has terminal status `{status}` but is still listed as active"
                )

    effective_spec_context = task_guard.normalize_spec_context({})
    if state and not issues:
        effective_spec_context = effective_spec_context_for_state(state)
        state_goal = str(state.get("goal") or "").strip()
        state_acceptance = task_guard.nonempty_text_list(state.get("acceptance_criteria"))
        if state_goal and not state_acceptance and (
            state.get("mode") in {"execute", "verify"}
            or state.get("current_phase") in {"execute", "verify"}
            or state.get("status") == "verifying"
        ):
            warnings.append(
                "state.json entered execute/verify without acceptance_criteria; capture at least one observable acceptance criterion or move the task back to clarify/plan"
            )

        spec_context = effective_spec_context
        if (
            spec_context.get("status") == "ambiguous"
            and not task_guard.nonempty_text_list(state.get("open_questions"))
            and not spec_context.get("summary")
        ):
            warnings.append(
                "state.json spec_context is ambiguous without an open question or summary note recording how to resolve it"
            )

        compact_info = compact_validation_context(state)
        if compact_info and compact_info.get("warning"):
            warnings.append(str(compact_info["warning"]))

    return state, issues, warnings, effective_spec_context


def print_report(state: dict, issues: list[str], warnings: list[str]) -> None:
    print(
        f"[context-task-planning] Validating task: {state.get('slug', plan_dir.name) if state else plan_dir.name}"
    )
    print(f"[context-task-planning] Task directory: {plan_dir}")

    if issues:
        print("[context-task-planning] Validation failed.")
        print("[context-task-planning] Issues:")
        for item in issues:
            print(f"  - {item}")
        if warnings:
            print("[context-task-planning] Warnings:")
            for item in warnings:
                print(f"  - {item}")
        return

    if warnings:
        print("[context-task-planning] Validation passed with warnings.")
        print("[context-task-planning] Warnings:")
        for item in warnings:
            print(f"  - {item}")
        return

    print("[context-task-planning] Validation passed.")


state, issues, warnings, effective_spec_context = validate_task()
if fix_warnings and not issues:
    applied_fixes = []
    if task_plan_file.exists():
        for line in sync_task_plan_hot_context(task_plan_file, state, effective_spec_context):
            applied_fixes.append(f"task_plan.md -> {line}")
    if progress_file.exists():
        for line in sync_progress_snapshot(progress_file, state):
            applied_fixes.append(f"progress.md -> {line}")
    compact_fix = refresh_compact_artifact(state)
    if compact_fix:
        applied_fixes.append(compact_fix)

    if applied_fixes:
        print(
            f"[context-task-planning] Applied warning fixes for {state.get('slug', plan_dir.name)}:"
        )
        for item in applied_fixes:
            print(f"  - {item}")
        state, issues, warnings, effective_spec_context = validate_task()
    else:
        print(
            f"[context-task-planning] No warning-level fixes were needed for {state.get('slug', plan_dir.name)}."
        )

print_report(state, issues, warnings)
if issues:
    sys.exit(1)
sys.exit(0)
PY
