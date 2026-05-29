#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from constants import (
    ROLE_OBSERVER,
    ROLE_WRITER,
    SPEC_CONTEXT_MODES,
    SPEC_CONTEXT_PROVIDERS,
    SPEC_CONTEXT_STATUSES,
    TASK_REPO_BINDING_DIR,
    WORKSPACE_FALLBACK_SESSION_KEY,
)
from file_utils import atomic_write_json
from file_lock import file_lock, lock_path_for
from session_binding import (
    binding_role_for_task,
    clear_session_binding,
    clear_task_session_bindings,
    demote_writer_binding,
    display_session_key,
    effective_session_key,
    iter_session_bindings,
    normalize_role,
    read_session_binding,
    resolve_session_key,
    safe_json,
    session_binding_path,
    task_bindings,
    utc_now,
    write_session_binding,
    writer_binding_for_task,
)
from repo_registry import (
    discover_workspace_repos,
    git_root_for,
    load_task_state,
    normalize_repo_id,
    read_repo_registry,
    read_task_repo_binding_overrides,
    register_workspace_repo,
    registered_repo_absolute_path,
    relative_to_workspace,
    repo_by_id,
    repo_registry_path,
    resolve_path_in_workspace,
    runtime_dir,
    task_repo_binding_path,
    write_json_file,
    write_repo_registry,
    write_task_repo_binding_overrides,
)
from spec_context import (
    brief_missing_fields_for_state,
    brief_quality_for_state,
    brief_summary_for_state,
    detect_openspec_spec_context,
    normalize_spec_context,
    spec_context_candidate_refs,
    spec_context_linked_artifact_refs,
    spec_context_resolution_commands,
    spec_context_resolution_hint,
    spec_context_summary_text,
)
from task_drift import classify_drift, print_drift
from task_preflight import build_subagent_preflight_result, print_subagent_preflight
from task_prune import (
    DEFAULT_KEEP_SESSIONS,
    apply_context_prune,
    context_prune_status,
    format_prune_status,
    prepare_context_prune,
    restore_context_prune,
)
from task_text import nonempty_text_list


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="task_guard.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    workspace = subparsers.add_parser("resolve-workspace-root")
    workspace.add_argument("--cwd", default="")

    current = subparsers.add_parser("current-task")
    current.add_argument("--task", default="")
    current.add_argument("--cwd", default="")
    current.add_argument("--session-key", default="")
    current.add_argument("--json", action="store_true")
    current.add_argument("--compact", action="store_true")

    plan_dir = subparsers.add_parser("resolve-plan-dir")
    plan_dir.add_argument("--task", default="")
    plan_dir.add_argument("--cwd", default="")
    plan_dir.add_argument("--session-key", default="")

    drift = subparsers.add_parser("check-drift")
    drift.add_argument("--task", default="")
    drift.add_argument("--cwd", default="")
    drift.add_argument("--session-key", default="")
    drift.add_argument("--prompt", default="")
    drift.add_argument("--json", action="store_true")
    drift.add_argument("--compact", action="store_true")

    preflight = subparsers.add_parser("subagent-preflight")
    preflight.add_argument("--task", default="")
    preflight.add_argument("--cwd", default="")
    preflight.add_argument("--session-key", default="")
    preflight.add_argument("--host", default="generic")
    preflight.add_argument("--task-text", default="")
    preflight.add_argument("--tool-name", default="Task")
    preflight.add_argument("--json", action="store_true")
    preflight.add_argument("--text", action="store_true")
    preflight.add_argument("--compact", action="store_true")

    switch = subparsers.add_parser("check-switch-safety")
    switch.add_argument("--cwd", default="")
    switch.add_argument("--session-key", default="")
    switch.add_argument("--source-task", default="")
    switch.add_argument("--target-task", default="")
    switch.add_argument("--json", action="store_true")
    switch.add_argument("--compact", action="store_true")

    enforce = subparsers.add_parser("ensure-switch-safety")
    enforce.add_argument("--cwd", default="")
    enforce.add_argument("--session-key", default="")
    enforce.add_argument("--source-task", default="")
    enforce.add_argument("--target-task", default="")
    enforce.add_argument("--stash", action="store_true")
    enforce.add_argument("--allow-dirty", action="store_true")

    bind = subparsers.add_parser("bind-session-task")
    bind.add_argument("--cwd", default="")
    bind.add_argument("--session-key", default="")
    bind.add_argument("--task", required=True)
    bind.add_argument(
        "--role", choices=[ROLE_WRITER, ROLE_OBSERVER], default=ROLE_WRITER
    )
    bind.add_argument("--steal", action="store_true")
    bind.add_argument("--fallback", action="store_true")

    clear_session = subparsers.add_parser("clear-session-task")
    clear_session.add_argument("--cwd", default="")
    clear_session.add_argument("--session-key", default="")
    clear_session.add_argument("--fallback", action="store_true")

    clear_task = subparsers.add_parser("clear-task-sessions")
    clear_task.add_argument("--cwd", default="")
    clear_task.add_argument("--task", required=True)

    list_repos = subparsers.add_parser("list-repos")
    list_repos.add_argument("--cwd", default="")
    list_repos.add_argument("--discover", action="store_true")
    list_repos.add_argument("--json", action="store_true")

    register_repo = subparsers.add_parser("register-repo")
    register_repo.add_argument("--cwd", default="")
    register_repo.add_argument("--id", default="")
    register_repo.add_argument("path")

    set_task_repos = subparsers.add_parser("set-task-repos")
    set_task_repos.add_argument("--cwd", default="")
    set_task_repos.add_argument("--task", required=True)
    set_task_repos.add_argument("--repo", action="append", default=[])
    set_task_repos.add_argument("--primary", default="")

    repo_binding = subparsers.add_parser("task-repo-binding")
    repo_binding.add_argument("--cwd", default="")
    repo_binding.add_argument("--task", required=True)
    repo_binding.add_argument("--repo", required=True)
    repo_binding.add_argument("--json", action="store_true")

    set_repo_binding = subparsers.add_parser("set-task-repo-binding")
    set_repo_binding.add_argument("--cwd", default="")
    set_repo_binding.add_argument("--task", required=True)
    set_repo_binding.add_argument("--repo", required=True)
    set_repo_binding.add_argument(
        "--mode", choices=["shared", "worktree"], required=True
    )
    set_repo_binding.add_argument("--checkout-path", required=True)
    set_repo_binding.add_argument("--branch", default="")
    set_repo_binding.add_argument("--base-branch", default="")

    list_worktrees = subparsers.add_parser("list-worktrees")
    list_worktrees.add_argument("--cwd", default="")
    list_worktrees.add_argument("--task", default="")
    list_worktrees.add_argument("--json", action="store_true")

    set_spec_context = subparsers.add_parser("set-task-spec-context")
    set_spec_context.add_argument("--cwd", default="")
    set_spec_context.add_argument("--task", required=True)
    set_spec_context.add_argument("--provider", default="openspec")
    set_spec_context.add_argument("--ref", default="")
    set_spec_context.add_argument("--artifact", action="append", default=[])
    set_spec_context.add_argument("--summary", action="append", default=[])
    set_spec_context.add_argument("--clear", action="store_true")

    access = subparsers.add_parser("check-task-access")
    access.add_argument("--cwd", default="")
    access.add_argument("--task", required=True)
    access.add_argument("--session-key", default="")
    access.add_argument(
        "--require-role", choices=[ROLE_WRITER, ROLE_OBSERVER], default=ROLE_WRITER
    )
    access.add_argument("--fallback", action="store_true")

    record = subparsers.add_parser("record-progress")
    record.add_argument("--cwd", default="")
    record.add_argument("--task", default="")
    record.add_argument("--session-key", default="")
    record.add_argument("--fallback", action="store_true")
    record.add_argument("--source-id", required=True)
    record.add_argument("--timestamp", default="")
    record.add_argument("--status", default="complete")
    record.add_argument("--checkpoint", default="")
    record.add_argument("--action", action="append", default=[])
    record.add_argument("--file", action="append", default=[])
    record.add_argument("--note", action="append", default=[])
    record.add_argument("--task-status", default="")
    record.add_argument("--mode", default="")
    record.add_argument("--phase", default="")
    record.add_argument("--next-action", default="")
    record.add_argument("--primary-repo", default="")
    record.add_argument("--repo", action="append", default=[])
    record.add_argument("--json", action="store_true")

    prune = subparsers.add_parser("context-prune")
    prune.add_argument("--cwd", default="")
    prune.add_argument("--task", default="")
    prune.add_argument("--session-key", default="")
    prune.add_argument("--fallback", action="store_true")
    prune.add_argument("--status", action="store_true")
    prune.add_argument("--prepare", action="store_true")
    prune.add_argument("--apply", action="store_true")
    prune.add_argument("--restore", default="")
    prune.add_argument("--summary-file", default="")
    prune.add_argument("--manifest", default="")
    prune.add_argument("--keep-sessions", type=int, default=DEFAULT_KEEP_SESSIONS)
    prune.add_argument("--json", action="store_true")
    prune.add_argument("--compact", action="store_true")

    return parser.parse_args()


def safe_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def resolve_start_dir(cwd: str) -> Path:
    candidate = cwd or os.getcwd()
    try:
        return Path(candidate).expanduser().resolve()
    except OSError:
        return Path(os.getcwd()).resolve()


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def relative_path_or_empty(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())) or "."
    except ValueError:
        return ""


def workspace_contains_path(workspace_root: Path, start_dir: Path) -> bool:
    workspace_root = workspace_root.resolve()
    start_dir = start_dir.resolve()
    plan_root = workspace_root / ".planning"

    if not plan_root.is_dir():
        return False

    if start_dir == workspace_root:
        return True

    if path_is_within(start_dir, plan_root):
        return True

    if git_root_for(workspace_root) == workspace_root and path_is_within(
        start_dir, workspace_root
    ):
        return True

    for repo in read_repo_registry(plan_root):
        repo_root = registered_repo_absolute_path(workspace_root, repo)
        if path_is_within(start_dir, repo_root):
            return True

    for binding in explicit_worktree_bindings(plan_root):
        checkout_root = resolve_path_in_workspace(
            workspace_root, str(binding.get("checkout_path") or "")
        )
        if path_is_within(start_dir, checkout_root):
            return True

    start_git_root = git_root_for(start_dir)
    if start_git_root and start_git_root != workspace_root:
        relative_git_root = relative_path_or_empty(workspace_root, start_git_root)
        if (
            relative_git_root
            and relative_git_root != "."
            and len(Path(relative_git_root).parts) == 1
            and not read_repo_registry(plan_root)
            and not explicit_worktree_bindings(plan_root)
        ):
            return True

    return False


def resolve_workspace_root(cwd: str) -> Path:
    start_dir = resolve_start_dir(cwd)
    candidate = start_dir
    git_root = None

    while True:
        if (candidate / ".planning").is_dir() and workspace_contains_path(
            candidate, start_dir
        ):
            return candidate

        if (candidate / ".git").exists() and git_root is None:
            git_root = candidate

        if candidate.parent == candidate:
            break
        candidate = candidate.parent

    return git_root or start_dir


def active_delegate_ids(plan_dir: Path | None) -> list[str]:
    if plan_dir is None:
        return []
    delegates_dir = plan_dir / "delegates"
    if not delegates_dir.is_dir():
        return []

    active = []
    for entry in delegates_dir.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        status = safe_json(entry / "status.json")
        if not status:
            continue
        if str(status.get("status") or "") in {"complete", "cancelled"}:
            continue
        delegate_id = str(status.get("delegate_id") or entry.name).strip()
        if delegate_id:
            active.append(delegate_id)
    active.sort()
    return active


def task_state_by_slug(plan_root: Path, task_slug: str) -> dict:
    plan_dir = plan_root / task_slug
    if not plan_dir.is_dir():
        return {}
    state = load_task_state(plan_dir)
    state.setdefault("slug", task_slug)
    return state


def task_repo_scope(state: dict) -> list[str]:
    raw = state.get("repo_scope", []) if isinstance(state, dict) else []
    if not isinstance(raw, list):
        return []

    repo_ids = []
    seen = set()
    for item in raw:
        repo_id = normalize_repo_id(str(item or ""))
        if not repo_id or repo_id in seen:
            continue
        seen.add(repo_id)
        repo_ids.append(repo_id)
    return repo_ids


def task_primary_repo(state: dict, repo_ids: list[str] | None = None) -> str:
    primary = normalize_repo_id(str(state.get("primary_repo") or ""))
    if primary:
        return primary
    scope = repo_ids if repo_ids is not None else task_repo_scope(state)
    return scope[0] if scope else ""


def git_branch_for(path: Path) -> str:
    git_root = git_root_for(path)
    if git_root is None:
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    output = result.stdout.strip()
    return output if result.returncode == 0 else ""


def implicit_workspace_repo(workspace_root: Path) -> dict:
    git_root = git_root_for(workspace_root)
    if git_root is None or git_root != workspace_root:
        return {}
    repo_id = normalize_repo_id(workspace_root.name) or "workspace"
    return {
        "id": repo_id,
        "path": ".",
        "registration_mode": "implicit",
        "registered_at": "",
        "updated_at": "",
    }


def resolved_repos_for_task(
    plan_root: Path, workspace_root: Path, task_slug: str, state: dict | None = None
) -> list[dict]:
    task_state = (
        state if isinstance(state, dict) else task_state_by_slug(plan_root, task_slug)
    )
    repo_ids = task_repo_scope(task_state)
    repos = []

    if repo_ids:
        for repo_id in repo_ids:
            repo = repo_by_id(plan_root, repo_id)
            if repo:
                repos.append(repo)
        return repos

    implicit = implicit_workspace_repo(workspace_root)
    return [implicit] if implicit else []


def effective_task_repo_bindings(
    plan_root: Path, workspace_root: Path, task_slug: str, state: dict | None = None
) -> list[dict]:
    task_state = (
        state if isinstance(state, dict) else task_state_by_slug(plan_root, task_slug)
    )
    repos = resolved_repos_for_task(plan_root, workspace_root, task_slug, task_state)
    overrides = {
        binding["repo_id"]: binding
        for binding in read_task_repo_binding_overrides(plan_root, task_slug)
    }

    bindings = []
    for repo in repos:
        repo_path = registered_repo_absolute_path(workspace_root, repo)
        default_checkout = relative_to_workspace(workspace_root, repo_path)
        override = overrides.get(repo["id"], {})
        checkout_path = str(override.get("checkout_path") or default_checkout)
        checkout_absolute = resolve_path_in_workspace(workspace_root, checkout_path)
        branch = str(override.get("branch") or git_branch_for(checkout_absolute))
        bindings.append(
            {
                "repo_id": repo["id"],
                "repo_path": repo["path"],
                "git_root": default_checkout,
                "mode": str(override.get("mode") or "shared"),
                "checkout_path": checkout_path,
                "branch": branch,
                "base_branch": str(override.get("base_branch") or ""),
                "checkout_exists": checkout_absolute.exists(),
            }
        )

    bindings.sort(key=lambda binding: binding["repo_id"])
    return bindings


def upsert_markdown_line(
    lines: list[str], prefix: str, replacement: str, after_prefix: str = ""
) -> list[str]:
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = replacement
            return lines

    if after_prefix:
        for index, line in enumerate(lines):
            if line.startswith(after_prefix):
                lines.insert(index + 1, replacement)
                return lines

    lines.append(replacement)
    return lines


def render_repo_scope(repo_ids: list[str]) -> str:
    return ", ".join(repo_ids) if repo_ids else "(unset)"


def sync_task_repo_markdown(
    task_plan_path: Path, progress_path: Path, primary_repo: str, repo_ids: list[str]
) -> None:
    primary_text = f"`{primary_repo}`" if primary_repo else "(unset)"
    scope_text = render_repo_scope(repo_ids)
    if repo_ids:
        scope_text = ", ".join(f"`{repo_id}`" for repo_id in repo_ids)

    if task_plan_path.exists():
        lines = task_plan_path.read_text(encoding="utf-8").splitlines()
        lines = upsert_markdown_line(
            lines,
            "- Primary Repo:",
            f"- Primary Repo: {primary_text}",
            after_prefix="- Next Action:",
        )
        lines = upsert_markdown_line(
            lines,
            "- Repo Scope:",
            f"- Repo Scope: {scope_text}",
            after_prefix="- Primary Repo:",
        )
        constraint_scope = scope_text.replace("`", "") if repo_ids else "(unset)"
        lines = upsert_markdown_line(
            lines,
            "- Primary Repo Constraint:",
            f"- Primary Repo Constraint: {primary_text}",
            after_prefix="- Planning Path:",
        )
        lines = upsert_markdown_line(
            lines,
            "- Repo Scope Constraint:",
            f"- Repo Scope Constraint: {constraint_scope}",
            after_prefix="- Primary Repo Constraint:",
        )
        task_plan_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if progress_path.exists():
        lines = progress_path.read_text(encoding="utf-8").splitlines()
        lines = upsert_markdown_line(
            lines,
            "- Primary Repo:",
            f"- Primary Repo: {primary_text}",
            after_prefix="- Next Action:",
        )
        lines = upsert_markdown_line(
            lines,
            "- Repo Scope:",
            f"- Repo Scope: {scope_text}",
            after_prefix="- Primary Repo:",
        )
        progress_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def task_derived_dir(plan_dir: Path) -> Path:
    return plan_dir / ".derived"


def opencode_idle_sync_path(plan_dir: Path) -> Path:
    return task_derived_dir(plan_dir) / "opencode_idle_sync.json"


def normalize_markdown_items(values: list[str]) -> list[str]:
    items = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    return items


def format_progress_repo_scope(repo_ids: list[str]) -> str:
    return ", ".join(repo_ids) if repo_ids else "(unset)"


def quoted_markdown_path(value: str) -> str:
    if value.startswith("`") and value.endswith("`"):
        return value
    return f"`{value}`"


def ensure_progress_session_log(
    progress_path: Path, title: str, task_slug: str
) -> None:
    if progress_path.exists():
        return

    created_at = utc_now()
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.write_text(
        "\n".join(
            [
                f"# Progress Log: {title}",
                "",
                "## Snapshot",
                "",
                f"- Task Slug: `{task_slug}`",
                "- Status: `active`",
                "- Current Mode: `clarify`",
                "- Current Phase: `clarify`",
                "- Next Action: (unset)",
                "- Primary Repo: (unset)",
                "- Repo Scope: (unset)",
                f"- Last Updated: {created_at}",
                "",
                "## Session Log",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def prepend_progress_session(
    progress_path: Path,
    timestamp: str,
    status: str,
    actions: list[str],
    files_touched: list[str],
    notes: list[str],
) -> None:
    lines = progress_path.read_text(encoding="utf-8").splitlines()
    try:
        insert_at = lines.index("## Session Log") + 1
    except ValueError:
        lines.extend(["", "## Session Log"])
        insert_at = len(lines)

    while insert_at < len(lines) and lines[insert_at] == "":
        insert_at += 1

    entry_lines = [
        f"### Session: {timestamp}",
        "",
        f"- Status: {status}",
        "- Actions:",
    ]
    for action in actions:
        entry_lines.append(f"  - {action}")

    entry_lines.append("- Files touched:")
    for file_path in files_touched:
        entry_lines.append(f"  - {quoted_markdown_path(file_path)}")

    entry_lines.append("- Notes:")
    for note in notes:
        entry_lines.append(f"  - {note}")
    entry_lines.append("")

    lines[insert_at:insert_at] = entry_lines
    progress_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_progress_snapshot(
    progress_path: Path,
    task_slug: str,
    task_status: str,
    mode: str,
    phase: str,
    next_action: str,
    primary_repo: str,
    repo_scope: list[str],
    updated_at: str,
) -> None:
    lines = progress_path.read_text(encoding="utf-8").splitlines()
    lines = upsert_markdown_line(lines, "- Task Slug:", f"- Task Slug: `{task_slug}`")
    lines = upsert_markdown_line(
        lines, "- Status:", f"- Status: `{task_status or 'active'}`"
    )
    lines = upsert_markdown_line(
        lines, "- Current Mode:", f"- Current Mode: `{mode or 'unknown'}`"
    )
    lines = upsert_markdown_line(
        lines, "- Current Phase:", f"- Current Phase: `{phase or 'unknown'}`"
    )
    lines = upsert_markdown_line(
        lines, "- Next Action:", f"- Next Action: {next_action or '(unset)'}"
    )
    lines = upsert_markdown_line(
        lines,
        "- Primary Repo:",
        f"- Primary Repo: {primary_repo or '(unset)'}",
        after_prefix="- Next Action:",
    )
    lines = upsert_markdown_line(
        lines,
        "- Repo Scope:",
        f"- Repo Scope: {format_progress_repo_scope(repo_scope)}",
        after_prefix="- Primary Repo:",
    )
    lines = upsert_markdown_line(
        lines, "- Last Updated:", f"- Last Updated: {updated_at}"
    )
    progress_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def record_progress_entry(
    plan_root: Path,
    workspace_root: Path,
    task_slug: str,
    session_key: str,
    source_id: str,
    timestamp: str,
    status: str,
    checkpoint: str,
    actions: list[str],
    files_touched: list[str],
    notes: list[str],
    task_status: str,
    mode: str,
    phase: str,
    next_action: str,
    primary_repo: str,
    repo_scope: list[str],
) -> dict:
    plan_dir = plan_root / task_slug
    if not plan_dir.is_dir():
        raise SystemExit(f"Task not found: {plan_dir}")

    role = binding_role_for_task(plan_root, session_key, task_slug)
    if (
        not role
        and session_key == WORKSPACE_FALLBACK_SESSION_KEY
        and read_active_pointer(plan_root) == task_slug
        and not writer_binding_for_task(plan_root, task_slug)
    ):
        role = ROLE_WRITER
    if role != ROLE_WRITER:
        writer = writer_binding_for_task(plan_root, task_slug)
        writer_display = display_session_key(str(writer.get("session_key") or ""))
        raise SystemExit(
            f"Task `{task_slug}` is observe-only for {display_session_key(session_key)}. "
            f"Current writer: {writer_display}."
        )

    state_path = plan_dir / "state.json"
    progress_path = plan_dir / "progress.md"
    idle_sync_path = opencode_idle_sync_path(plan_dir)
    idle_sync = safe_json(idle_sync_path)
    seen_sources = idle_sync.get("sources", {}) if isinstance(idle_sync, dict) else {}
    if not isinstance(seen_sources, dict):
        seen_sources = {}
    if source_id in seen_sources:
        return {
            "ok": True,
            "task_slug": task_slug,
            "source_id": source_id,
            "deduped": True,
            "updated_at": str(seen_sources.get(source_id) or ""),
        }

    state = load_task_state(plan_dir)
    normalized_actions = normalize_markdown_items(actions)
    normalized_files = normalize_markdown_items(files_touched)
    normalized_notes = normalize_markdown_items(notes)
    resolved_timestamp = timestamp or utc_now()
    resolved_checkpoint = (
        checkpoint.strip()
        or state.get("latest_checkpoint")
        or (
            normalized_actions[0]
            if normalized_actions
            else "Recorded OpenCode idle sync progress."
        )
    )

    state["latest_checkpoint"] = resolved_checkpoint
    state["updated_at"] = resolved_timestamp
    if task_status:
        state["status"] = task_status
    if mode:
        state["mode"] = mode
    if phase:
        state["current_phase"] = phase
    if next_action:
        state["next_action"] = next_action
    if primary_repo:
        state["primary_repo"] = primary_repo
    if repo_scope:
        state["repo_scope"] = repo_scope
    write_json_file(state_path, state)

    ensure_progress_session_log(
        progress_path,
        str(state.get("title") or task_slug),
        task_slug,
    )
    update_progress_snapshot(
        progress_path,
        task_slug,
        str(state.get("status") or "active"),
        str(state.get("mode") or "unknown"),
        str(state.get("current_phase") or "unknown"),
        str(state.get("next_action") or "(unset)"),
        str(state.get("primary_repo") or ""),
        nonempty_text_list(state.get("repo_scope")),
        resolved_timestamp,
    )
    prepend_progress_session(
        progress_path,
        resolved_timestamp,
        status or "complete",
        normalized_actions or ["Recorded OpenCode idle sync progress."],
        normalized_files
        or [f".planning/{task_slug}/progress.md", f".planning/{task_slug}/state.json"],
        normalized_notes
        or ["Automated OpenCode idle sync appended this journal entry."],
    )

    sources = dict(seen_sources)
    sources[source_id] = resolved_timestamp
    retained = list(sorted(sources.items(), key=lambda item: item[1], reverse=True))[
        :200
    ]
    write_json_file(
        idle_sync_path,
        {
            "schema_version": "1.0.0",
            "task_slug": task_slug,
            "updated_at": resolved_timestamp,
            "sources": {key: value for key, value in retained},
        },
    )

    return {
        "ok": True,
        "task_slug": task_slug,
        "source_id": source_id,
        "deduped": False,
        "updated_at": resolved_timestamp,
        "checkpoint": resolved_checkpoint,
        "workspace_root": str(workspace_root),
    }


def set_task_repo_scope(
    plan_root: Path,
    workspace_root: Path,
    task_slug: str,
    repo_ids: list[str],
    primary_repo: str,
) -> dict:
    plan_dir = plan_root / task_slug
    if not plan_dir.is_dir():
        raise SystemExit(f"Task not found: {plan_dir}")

    normalized_repo_ids = []
    seen = set()
    for repo_id in repo_ids:
        normalized = normalize_repo_id(repo_id)
        if not normalized or normalized in seen:
            continue
        if not repo_by_id(plan_root, normalized):
            raise SystemExit(
                f"Repo `{normalized}` is not registered in this workspace."
            )
        seen.add(normalized)
        normalized_repo_ids.append(normalized)

    normalized_primary = normalize_repo_id(primary_repo)
    if normalized_primary and normalized_primary not in normalized_repo_ids:
        raise SystemExit("Primary repo must be part of --repo scope.")
    if not normalized_primary and normalized_repo_ids:
        normalized_primary = normalized_repo_ids[0]

    state_path = plan_dir / "state.json"
    state = load_task_state(plan_dir)
    constraints = (
        state.get("constraints", [])
        if isinstance(state.get("constraints", []), list)
        else []
    )
    constraints = [
        item
        for item in constraints
        if not str(item).startswith("Primary repo:")
        and not str(item).startswith("Repo scope:")
    ]
    constraints.append(f"Primary repo: {normalized_primary or '(unset)'}")
    constraints.append(
        f"Repo scope: {', '.join(normalized_repo_ids) if normalized_repo_ids else '(unset)'}"
    )
    state["repo_scope"] = normalized_repo_ids
    state["primary_repo"] = normalized_primary
    state["constraints"] = constraints
    state["latest_checkpoint"] = "Task repo scope updated."
    state["updated_at"] = utc_now()
    write_json_file(state_path, state)

    if normalized_repo_ids:
        filtered_bindings = [
            binding
            for binding in read_task_repo_binding_overrides(plan_root, task_slug)
            if binding["repo_id"] in normalized_repo_ids
        ]
        write_task_repo_binding_overrides(plan_root, task_slug, filtered_bindings)

    sync_task_repo_markdown(
        plan_dir / "task_plan.md",
        plan_dir / "progress.md",
        normalized_primary,
        normalized_repo_ids,
    )

    return {
        "task_slug": task_slug,
        "primary_repo": normalized_primary,
        "repo_scope": normalized_repo_ids,
        "workspace_root": str(workspace_root),
    }


def set_task_repo_binding(
    plan_root: Path,
    workspace_root: Path,
    task_slug: str,
    repo_id: str,
    mode: str,
    checkout_path: str,
    branch: str = "",
    base_branch: str = "",
) -> dict:
    task_state = task_state_by_slug(plan_root, task_slug)
    if not task_state:
        raise SystemExit(f"Task `{task_slug}` was not found.")

    normalized_repo = normalize_repo_id(repo_id)
    repo_scope = task_repo_scope(task_state)
    if repo_scope and normalized_repo not in repo_scope:
        raise SystemExit(
            f"Repo `{normalized_repo}` is not in task `{task_slug}` repo_scope."
        )

    repo = repo_by_id(plan_root, normalized_repo)
    if not repo and repo_scope:
        raise SystemExit(
            f"Repo `{normalized_repo}` is not registered in this workspace."
        )

    absolute_checkout = resolve_path_in_workspace(workspace_root, checkout_path)
    relative_checkout = relative_to_workspace(workspace_root, absolute_checkout)
    normalized_mode = "worktree" if mode == "worktree" else "shared"

    bindings = [
        binding
        for binding in read_task_repo_binding_overrides(plan_root, task_slug)
        if binding["repo_id"] != normalized_repo
    ]
    bindings.append(
        {
            "repo_id": normalized_repo,
            "mode": normalized_mode,
            "checkout_path": relative_checkout,
            "branch": branch,
            "base_branch": base_branch,
            "updated_at": utc_now(),
        }
    )
    bindings.sort(key=lambda binding: binding["repo_id"])
    write_task_repo_binding_overrides(plan_root, task_slug, bindings)

    result = {
        "task_slug": task_slug,
        "repo_id": normalized_repo,
        "mode": normalized_mode,
        "checkout_path": relative_checkout,
        "branch": branch,
        "base_branch": base_branch,
    }
    if repo:
        result["repo_path"] = repo["path"]
    return result


def set_task_spec_context(
    plan_root: Path,
    task_slug: str,
    provider: str,
    primary_ref: str,
    artifact_refs: list[str],
    summary: list[str],
    clear: bool = False,
) -> dict:
    plan_dir = plan_root / task_slug
    if not plan_dir.is_dir():
        raise SystemExit(f"Task not found: {plan_dir}")

    state_path = plan_dir / "state.json"
    state = load_task_state(plan_dir)

    if clear:
        spec_context = normalize_spec_context({})
        checkpoint = "Cleared manual spec_context override."
    else:
        normalized_provider = str(provider or "openspec").strip()
        if normalized_provider not in {"openspec", "spec-kit", "generic"}:
            raise SystemExit("--provider must be one of: openspec, spec-kit, generic")

        normalized_primary = str(primary_ref or "").strip()
        normalized_artifacts = nonempty_text_list(artifact_refs)
        if not normalized_primary:
            raise SystemExit(
                "Explicit spec context requires --ref unless --clear is used."
            )

        normalized_summary = nonempty_text_list(summary)
        if not normalized_summary:
            normalized_summary = [
                f"Manual {normalized_provider} spec_context override recorded for {normalized_primary}."
            ]

        spec_context = normalize_spec_context(
            {
                "mode": "linked",
                "provider": normalized_provider,
                "status": "linked",
                "primary_ref": normalized_primary,
                "artifact_refs": normalized_artifacts,
                "summary": normalized_summary,
            }
        )
        checkpoint = "Manual spec_context override recorded."

    state["spec_context"] = spec_context
    state["latest_checkpoint"] = checkpoint
    state["updated_at"] = utc_now()
    write_json_file(state_path, state)
    return {"task_slug": task_slug, "spec_context": spec_context}


def other_writer_tasks(
    plan_root: Path, exclude_task_slug: str = "", exclude_session_key: str = ""
) -> list[str]:
    tasks = set()
    for _, binding in iter_session_bindings(plan_root):
        if normalize_role(str(binding.get("role") or ROLE_WRITER)) != ROLE_WRITER:
            continue
        session_key = str(binding.get("session_key") or "").strip()
        if exclude_session_key and session_key == exclude_session_key:
            continue
        task_slug = str(binding.get("task_slug") or "").strip()
        if not task_slug or task_slug == exclude_task_slug:
            continue
        tasks.add(task_slug)
    return sorted(tasks)


def shared_checkout_conflicts(
    plan_root: Path, workspace_root: Path, task_slug: str, session_key: str = ""
) -> list[dict]:
    target_bindings = effective_task_repo_bindings(plan_root, workspace_root, task_slug)
    target_by_repo = {binding["repo_id"]: binding for binding in target_bindings}
    conflicts = []

    for other_task in other_writer_tasks(
        plan_root, exclude_task_slug=task_slug, exclude_session_key=session_key
    ):
        for binding in effective_task_repo_bindings(
            plan_root, workspace_root, other_task
        ):
            target = target_by_repo.get(binding["repo_id"])
            if not target:
                continue
            if target["checkout_path"] != binding["checkout_path"]:
                continue
            conflicts.append(
                {
                    "other_task": other_task,
                    "repo_id": binding["repo_id"],
                    "checkout_path": binding["checkout_path"],
                }
            )

    conflicts.sort(
        key=lambda item: (item["repo_id"], item["checkout_path"], item["other_task"])
    )
    return conflicts


def explicit_worktree_bindings(plan_root: Path) -> list[dict]:
    bindings_dir = runtime_dir(plan_root) / TASK_REPO_BINDING_DIR
    if not bindings_dir.is_dir():
        return []

    rows = []
    for entry in sorted(bindings_dir.iterdir(), key=lambda item: item.name):
        if not entry.is_file() or entry.suffix != ".json":
            continue
        task_slug = entry.stem
        for binding in read_task_repo_binding_overrides(plan_root, task_slug):
            if binding["mode"] != "worktree":
                continue
            rows.append({"task_slug": task_slug, **binding})
    return rows


def status_of(plan_dir: Path) -> str:
    return load_task_state(plan_dir).get("status", "unknown")


def auto_selectable(plan_dir: Path) -> bool:
    return status_of(plan_dir) not in {"archived", "paused", "done"}


def read_active_pointer(plan_root: Path) -> str:
    pointer = plan_root / ".active_task"
    if not pointer.exists():
        return ""
    try:
        return pointer.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def latest_task(plan_root: Path) -> Path | None:
    if not plan_root.is_dir():
        return None

    candidates = []
    for entry in plan_root.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if not auto_selectable(entry):
            continue
        candidates.append(entry)

    if not candidates:
        return None

    return max(candidates, key=lambda item: item.stat().st_mtime)


def resolve_task(cwd: str, requested_slug: str, session_key: str = "") -> dict:
    workspace_root = resolve_workspace_root(cwd)
    plan_root = workspace_root / ".planning"
    session_pin = os.environ.get("PLAN_TASK", "").strip()
    resolved_session_key = resolve_session_key(session_key)
    session_binding = read_session_binding(plan_root, resolved_session_key)
    session_binding_slug = str(session_binding.get("task_slug") or "").strip()
    active_pointer = read_active_pointer(plan_root)
    plan_dir = None
    selection_source = "none"

    def candidate_for(slug: str, allow_archived: bool) -> Path | None:
        if not slug:
            return None
        candidate = plan_root / slug
        if not candidate.is_dir():
            return None
        if not allow_archived and not auto_selectable(candidate):
            return None
        return candidate

    for slug, source, allow_archived in [
        (requested_slug, "requested_slug", True),
        (session_pin, "session_pin", True),
        (session_binding_slug, "session_binding", False),
        (active_pointer, "active_pointer", False),
    ]:
        plan_dir = candidate_for(slug, allow_archived)
        if plan_dir is not None:
            selection_source = source
            break

    if plan_dir is None:
        plan_dir = latest_task(plan_root)
        if plan_dir is not None:
            selection_source = "latest"

    state = load_task_state(plan_dir) if plan_dir is not None else {}
    delegation = state.get("delegation", {}) if isinstance(state, dict) else {}
    selected_slug = state.get("slug", "") if isinstance(state, dict) else ""
    bindings = task_bindings(plan_root, selected_slug) if selected_slug else []
    writer_binding = (
        writer_binding_for_task(plan_root, selected_slug) if selected_slug else {}
    )
    fallback_role = (
        binding_role_for_task(plan_root, WORKSPACE_FALLBACK_SESSION_KEY, selected_slug)
        if selected_slug
        else ""
    )
    binding_role = ""
    if selected_slug and resolved_session_key:
        binding_role = binding_role_for_task(
            plan_root, resolved_session_key, selected_slug
        )
    elif selected_slug and selection_source == "active_pointer" and fallback_role:
        binding_role = fallback_role
    elif selected_slug and selection_source == "active_pointer" and not writer_binding:
        binding_role = ROLE_WRITER

    observer_count = sum(1 for binding in bindings if binding["role"] == ROLE_OBSERVER)
    writer_session_key = str(writer_binding.get("session_key") or "")
    if (
        not writer_session_key
        and selected_slug
        and selection_source == "active_pointer"
    ):
        writer_session_key = WORKSPACE_FALLBACK_SESSION_KEY
    repo_scope = task_repo_scope(state)
    primary_repo = task_primary_repo(state, repo_scope)
    repo_bindings = (
        effective_task_repo_bindings(plan_root, workspace_root, selected_slug, state)
        if selected_slug
        else []
    )
    effective_spec_context = (
        detect_openspec_spec_context(workspace_root, state, repo_bindings)
        if isinstance(state, dict)
        else normalize_spec_context({})
    )
    repo_summary = summarize_repo_bindings(repo_bindings)
    resume_candidates = resumable_task_candidates(plan_root, selected_slug)

    result = {
        "found": plan_dir is not None,
        "selection_source": selection_source,
        "workspace_root": str(workspace_root),
        "plan_root": str(plan_root),
        "plan_dir": str(plan_dir) if plan_dir is not None else "",
        "requested_slug": requested_slug,
        "session_key": resolved_session_key,
        "session_binding": session_binding_slug,
        "binding_role": binding_role,
        "session_pin": session_pin,
        "active_pointer": active_pointer,
        "writer_session_key": writer_session_key,
        "writer_display": display_session_key(writer_session_key),
        "observer_count": observer_count,
        "session_count": len(bindings),
        "repo_scope": repo_scope,
        "primary_repo": primary_repo,
        "repo_bindings": repo_bindings,
        "repo_summary": repo_summary,
        "slug": state.get("slug", "") if isinstance(state, dict) else "",
        "title": state.get("title", "") if isinstance(state, dict) else "",
        "status": state.get("status", "") if isinstance(state, dict) else "",
        "mode": state.get("mode", "") if isinstance(state, dict) else "",
        "current_phase": state.get("current_phase", "")
        if isinstance(state, dict)
        else "",
        "next_action": state.get("next_action", "") if isinstance(state, dict) else "",
        "blockers": state.get("blockers", []) if isinstance(state, dict) else [],
        "active_delegates": active_delegate_ids(plan_dir),
        "verify_commands": state.get("verify_commands", [])
        if isinstance(state, dict)
        else [],
        "goal": state.get("goal", "") if isinstance(state, dict) else "",
        "non_goals": nonempty_text_list(state.get("non_goals"))
        if isinstance(state, dict)
        else [],
        "acceptance_criteria": nonempty_text_list(state.get("acceptance_criteria"))
        if isinstance(state, dict)
        else [],
        "edge_cases": nonempty_text_list(state.get("edge_cases"))
        if isinstance(state, dict)
        else [],
        "spec_context": effective_spec_context,
        "spec_candidate_refs": spec_context_candidate_refs(effective_spec_context),
        "spec_resolution_hint": spec_context_resolution_hint(
            state.get("slug", "") if isinstance(state, dict) else "",
            effective_spec_context,
        ),
        "spec_resolution_commands": spec_context_resolution_commands(
            state.get("slug", "") if isinstance(state, dict) else "",
            effective_spec_context,
        ),
        "open_questions": state.get("open_questions", [])
        if isinstance(state, dict)
        else [],
        "phases": state.get("phases", []) if isinstance(state, dict) else [],
        "resume_candidates": resume_candidates,
    }
    result["brief_missing_fields"] = brief_missing_fields_for_state(state)
    result["brief_quality"] = brief_quality_for_state(state)
    result.update(guidance_for_current_task(result))
    return result


def task_snapshot(plan_dir: Path | None, source: str) -> dict:
    if plan_dir is None or not plan_dir.is_dir():
        return {
            "found": False,
            "selection_source": source,
            "plan_dir": "",
            "slug": "",
            "title": "",
            "status": "",
            "mode": "",
            "current_phase": "",
            "next_action": "",
        }

    state = load_task_state(plan_dir)
    return {
        "found": True,
        "selection_source": source,
        "plan_dir": str(plan_dir),
        "slug": state.get("slug", plan_dir.name),
        "title": state.get("title", plan_dir.name),
        "status": state.get("status", ""),
        "mode": state.get("mode", ""),
        "current_phase": state.get("current_phase", ""),
        "next_action": state.get("next_action", ""),
    }


def latest_updated_task(plan_root: Path, exclude_slug: str = "") -> Path | None:
    if not plan_root.is_dir():
        return None

    candidates = []
    for entry in plan_root.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if exclude_slug and entry.name == exclude_slug:
            continue

        state = load_task_state(entry)
        if state.get("status") == "archived":
            continue

        state_path = entry / "state.json"
        try:
            mtime = (
                state_path.stat().st_mtime
                if state_path.exists()
                else entry.stat().st_mtime
            )
        except OSError:
            continue
        candidates.append((mtime, entry))

    if not candidates:
        return None

    return max(candidates, key=lambda item: item[0])[1]


def resumable_task_candidates(
    plan_root: Path, exclude_slug: str = "", limit: int = 3
) -> list[dict]:
    if not plan_root.is_dir():
        return []

    candidates = []
    for entry in plan_root.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue

        state = load_task_state(entry)
        slug = str(state.get("slug") or entry.name)
        if exclude_slug and slug == exclude_slug:
            continue

        status = str(state.get("status") or "")
        if status in {"archived", "done"}:
            continue

        candidates.append(
            {
                "slug": slug,
                "title": str(state.get("title") or slug),
                "status": status or "unknown",
                "mode": str(state.get("mode") or ""),
                "updated_at": str(state.get("updated_at") or ""),
            }
        )

    candidates.sort(
        key=lambda item: (item.get("updated_at") or "", item.get("slug") or ""),
        reverse=True,
    )
    return candidates[:limit]


def summarize_repo_bindings(repo_bindings: list[dict]) -> dict:
    shared = []
    worktree = []

    for binding in repo_bindings:
        item = {
            "repo_id": str(binding.get("repo_id") or ""),
            "repo_path": str(binding.get("repo_path") or ""),
            "checkout_path": str(binding.get("checkout_path") or ""),
            "branch": str(binding.get("branch") or ""),
        }
        if binding.get("mode") == "worktree":
            worktree.append(item)
        else:
            shared.append(item)

    return {
        "total": len(repo_bindings),
        "shared": shared,
        "worktree": worktree,
        "shared_repo_ids": [item["repo_id"] for item in shared],
        "worktree_repo_ids": [item["repo_id"] for item in worktree],
    }


def summarize_repo_isolation(
    plan_root: Path, workspace_root: Path, task_slug: str, session_key: str = ""
) -> dict:
    bindings = effective_task_repo_bindings(plan_root, workspace_root, task_slug)
    conflicts = shared_checkout_conflicts(
        plan_root, workspace_root, task_slug, session_key
    )
    conflict_by_repo = {}
    for item in conflicts:
        repo_entry = conflict_by_repo.setdefault(
            item["repo_id"],
            {
                "checkout_path": item["checkout_path"],
                "other_tasks": [],
            },
        )
        repo_entry["other_tasks"].append(item["other_task"])

    summary = {
        "safe_shared": [],
        "needs_worktree": [],
        "already_isolated": [],
        "recommended_commands": [],
        "has_conflicts": bool(conflicts),
    }

    for binding in bindings:
        entry = {
            "repo_id": str(binding.get("repo_id") or ""),
            "repo_path": str(binding.get("repo_path") or ""),
            "checkout_path": str(binding.get("checkout_path") or ""),
            "branch": str(binding.get("branch") or ""),
        }
        if binding.get("mode") == "worktree":
            summary["already_isolated"].append(entry)
            continue

        repo_conflict = conflict_by_repo.get(entry["repo_id"])
        if repo_conflict:
            entry["other_tasks"] = sorted(set(repo_conflict["other_tasks"]))
            entry["recommended_command"] = (
                f"sh skill/scripts/prepare-task-worktree.sh --task {task_slug} --repo {entry['repo_id']}"
            )
            summary["needs_worktree"].append(entry)
            summary["recommended_commands"].append(entry["recommended_command"])
            continue

        summary["safe_shared"].append(entry)

    return summary


def guidance_for_current_task(task: dict) -> dict:
    slug = str(task.get("slug") or "")
    repo_summary = task.get("repo_summary", {}) if isinstance(task, dict) else {}
    repo_count = int(repo_summary.get("total", 0) or 0)
    has_worktree = bool(repo_summary.get("worktree"))

    if not task.get("found"):
        candidates = task.get("resume_candidates", []) if isinstance(task, dict) else []
        if candidates:
            best = candidates[0]
            return {
                "recommended_action": "resume-task",
                "recommended_reason": "No active task is selected, and the most recent resumable task looks like the best continuation point.",
                "recommended_commands": [
                    f"sh skill/scripts/resume-task.sh {best['slug']}",
                    "sh skill/scripts/list-tasks.sh",
                ],
            }
        return {
            "recommended_action": "init-task",
            "recommended_reason": "No active or resumable task is selected, so the next step is to start a new task with a confirmed title.",
            "recommended_commands": [
                'sh skill/scripts/init-task.sh "Confirmed Task Title"',
            ],
        }

    if task.get("status") == "done":
        commands = [
            f"sh skill/scripts/archive-task.sh {slug}",
            'sh skill/scripts/init-task.sh "Next confirmed task title"',
        ]
        return {
            "recommended_action": "archive-or-open-new-task",
            "recommended_reason": "This task is already done, so the next step is usually to archive it or start a fresh task.",
            "recommended_commands": commands,
        }

    if task.get("binding_role") == ROLE_OBSERVER:
        commands = [
            f"sh skill/scripts/validate-task.sh --task {slug}",
            f"sh skill/scripts/set-active-task.sh --steal {slug}",
        ]
        if repo_count > 1 or has_worktree:
            commands.append(f"sh skill/scripts/list-worktrees.sh --task {slug}")
        return {
            "recommended_action": "observe-or-steal-writer",
            "recommended_reason": "This session is observe-only, so you can review the task safely or explicitly take the writer lease if you need to edit.",
            "recommended_commands": commands,
        }

    commands = [f"sh skill/scripts/validate-task.sh --task {slug}"]
    if repo_count > 1 or has_worktree:
        commands.append(f"sh skill/scripts/list-worktrees.sh --task {slug}")

    if task.get("mode") == "verify" or task.get("current_phase") == "verify":
        commands.append(f"sh skill/scripts/done-task.sh {slug}")
        return {
            "recommended_action": "run-verification",
            "recommended_reason": "The task is in verify mode, so the next step is to run validation and then close it out if the checks pass.",
            "recommended_commands": commands,
        }

    return {
        "recommended_action": "continue-current-task",
        "recommended_reason": "The task is active and already has a recorded next action, so the next step is to continue from that state.",
        "recommended_commands": commands,
    }


def git_root_for(workspace_root: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace_root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None

    output = result.stdout.strip()
    if result.returncode != 0 or not output:
        return None

    try:
        return Path(output).resolve()
    except OSError:
        return None


def git_status_summary(workspace_root: Path) -> dict:
    git_root = git_root_for(workspace_root)
    if git_root is None:
        return {
            "found": False,
            "root": "",
            "dirty": False,
            "staged": 0,
            "unstaged": 0,
            "untracked": 0,
            "entries": [],
        }

    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(git_root),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return {
            "found": True,
            "root": str(git_root),
            "dirty": False,
            "staged": 0,
            "unstaged": 0,
            "untracked": 0,
            "entries": [],
        }

    entries = [line for line in result.stdout.splitlines() if line.strip()]
    staged = 0
    unstaged = 0
    untracked = 0

    for entry in entries:
        if entry.startswith("??"):
            untracked += 1
            continue

        if len(entry) < 2:
            continue

        if entry[0] not in {" ", "?"}:
            staged += 1
        if entry[1] != " ":
            unstaged += 1

    return {
        "found": True,
        "root": str(git_root),
        "dirty": bool(entries),
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "entries": entries,
    }


def repo_status_for_binding(workspace_root: Path, binding: dict) -> dict:
    checkout_path = str(binding.get("checkout_path") or ".")
    checkout_absolute = resolve_path_in_workspace(workspace_root, checkout_path)
    status = git_status_summary(checkout_absolute)
    status.update(
        {
            "repo_id": str(binding.get("repo_id") or ""),
            "repo_path": str(binding.get("repo_path") or ""),
            "mode": str(binding.get("mode") or "shared"),
            "checkout_path": checkout_path,
            "branch": str(binding.get("branch") or ""),
        }
    )
    return status


def task_git_status_summary(
    plan_root: Path, workspace_root: Path, task_slug: str, state: dict | None = None
) -> dict:
    bindings = (
        effective_task_repo_bindings(plan_root, workspace_root, task_slug, state)
        if task_slug
        else []
    )

    repo_statuses = [
        repo_status_for_binding(workspace_root, binding) for binding in bindings
    ]
    if not repo_statuses:
        fallback = git_status_summary(workspace_root)
        if fallback["found"]:
            fallback.update(
                {
                    "repo_id": normalize_repo_id(workspace_root.name) or "workspace",
                    "repo_path": ".",
                    "mode": "shared",
                    "checkout_path": ".",
                    "branch": git_branch_for(workspace_root),
                }
            )
            repo_statuses = [fallback]

    dirty_entries = [repo for repo in repo_statuses if repo.get("dirty")]
    return {
        "found": any(repo.get("found") for repo in repo_statuses),
        "root": repo_statuses[0].get("root", "") if len(repo_statuses) == 1 else "",
        "dirty": bool(dirty_entries),
        "staged": sum(int(repo.get("staged") or 0) for repo in repo_statuses),
        "unstaged": sum(int(repo.get("unstaged") or 0) for repo in repo_statuses),
        "untracked": sum(int(repo.get("untracked") or 0) for repo in repo_statuses),
        "entries": [
            entry for repo in repo_statuses for entry in repo.get("entries", [])
        ],
        "repos": repo_statuses,
        "dirty_repo_ids": [
            repo.get("repo_id") or "workspace" for repo in dirty_entries
        ],
    }


def recommendation_for_switch(source_task: dict) -> tuple[str, str]:
    status = source_task.get("status", "")
    mode = source_task.get("mode", "")
    phase = source_task.get("current_phase", "")

    if status in {"done", "verifying"} or mode == "verify" or phase == "verify":
        return (
            "commit-first",
            "The current task looks verified or near-done, so committing is safer than hiding the state in a stash.",
        )

    return (
        "stash-first",
        "The current task still looks in progress, so stashing is the safest quick way to switch without mixing changes.",
    )


def stash_message(source_task: dict, target_task: dict) -> str:
    source_slug = source_task.get("slug") or "unknown-task"
    target_slug = target_task.get("slug") or "another-task"
    return f"[context-task-planning] switch from {source_slug} to {target_slug}"


def check_switch_safety(
    cwd: str, source_slug: str, target_slug: str, session_key: str = ""
) -> dict:
    workspace_root = resolve_workspace_root(cwd)
    plan_root = workspace_root / ".planning"
    active_pointer = read_active_pointer(plan_root)

    source_task = resolve_task(cwd, source_slug, session_key)
    git = task_git_status_summary(
        plan_root, workspace_root, source_task.get("slug", "")
    )
    if not source_task["found"] and git["dirty"] and active_pointer != target_slug:
        source_plan_dir = latest_updated_task(plan_root, exclude_slug=target_slug)
        source_task = task_snapshot(source_plan_dir, "recent_task")
        git = task_git_status_summary(
            plan_root, workspace_root, source_task.get("slug", "")
        )

    target_plan_dir = plan_root / target_slug if target_slug else None
    target_task = task_snapshot(target_plan_dir, "target_task")

    switching = bool(target_slug)
    if active_pointer and active_pointer == target_slug:
        switching = False
    if source_task["found"] and source_task["slug"] == target_slug:
        switching = False

    safe = (not git["found"]) or (not git["dirty"]) or (not switching)
    recommendation = "none"
    reason = ""
    if not safe:
        recommendation, reason = recommendation_for_switch(source_task)

    return {
        "workspace_root": str(workspace_root),
        "plan_root": str(plan_root),
        "active_pointer": active_pointer,
        "switching": switching,
        "safe": safe,
        "recommendation": recommendation,
        "reason": reason,
        "git": git,
        "source_task": source_task,
        "target_task": target_task,
        "stash_message": stash_message(source_task, target_task),
    }


def compact_switch_safety(result: dict) -> str:
    source_slug = result["source_task"].get("slug") or "(none)"
    target_slug = result["target_task"].get("slug") or "(none)"
    dirty = str(result["git"].get("dirty", False)).lower()
    safe = str(result.get("safe", False)).lower()
    recommendation = result.get("recommendation", "none") or "none"
    return (
        f"safe={safe} dirty={dirty} source={source_slug} target={target_slug} "
        f"recommendation={recommendation}"
    )


def print_switch_safety(result: dict, as_json: bool, compact: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if compact:
        print(compact_switch_safety(result))
        return

    git = result["git"]
    print(f"[context-task-planning] Workspace: {result['workspace_root']}")
    if not git["found"]:
        print("[context-task-planning] Switch safety: no git repository detected.")
        return

    if git.get("root"):
        print(f"[context-task-planning] Git root: {git['root']}")
    print(
        "[context-task-planning] Dirty repo checkouts: "
        f"{str(git['dirty']).lower()} "
        f"(staged={git['staged']}, unstaged={git['unstaged']}, untracked={git['untracked']})"
    )
    for repo in git.get("repos", []):
        if not repo.get("dirty"):
            continue
        print(
            "[context-task-planning] Dirty repo: "
            f"{repo.get('repo_id') or '(unknown)'} checkout={repo.get('checkout_path') or '.'} "
            f"branch={repo.get('branch') or '-'} staged={repo.get('staged', 0)} "
            f"unstaged={repo.get('unstaged', 0)} untracked={repo.get('untracked', 0)}"
        )
    print(
        f"[context-task-planning] Source task: {result['source_task'].get('slug') or '(unknown)'} "
        f"(source={result['source_task'].get('selection_source') or 'none'})"
    )
    print(
        f"[context-task-planning] Target task: {result['target_task'].get('slug') or '(none)'}"
    )
    print(
        f"[context-task-planning] Switching: {str(result['switching']).lower()} | "
        f"Safe: {str(result['safe']).lower()}"
    )
    if result["reason"]:
        print(f"[context-task-planning] Recommendation: {result['recommendation']}")
        print(f"[context-task-planning] Reason: {result['reason']}")


def run_stash(result: dict) -> None:
    git = result["git"]
    if not git["found"] or not git["dirty"]:
        return

    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                git["root"],
                "stash",
                "push",
                "-u",
                "-m",
                result["stash_message"],
            ],
            check=False,
        )
    except OSError as exc:
        raise SystemExit(f"Failed to stash worktree before switching: {exc}") from exc

    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def print_switch_warning(result: dict) -> None:
    git = result["git"]
    source_task = result["source_task"]
    target_task = result["target_task"]
    recommendation = result["recommendation"]

    print(
        "[context-task-planning] Dirty task repo checkouts detected before switching tasks.",
        file=sys.stderr,
    )
    print(
        "[context-task-planning] Repo changes: "
        f"staged={git['staged']} unstaged={git['unstaged']} untracked={git['untracked']}",
        file=sys.stderr,
    )
    dirty_repos = git.get("dirty_repo_ids", [])
    if dirty_repos:
        print(
            f"[context-task-planning] Dirty repos: {', '.join(dirty_repos)}",
            file=sys.stderr,
        )
    print(
        f"[context-task-planning] Source task: {source_task.get('slug') or '(unknown)'} "
        f"status={source_task.get('status') or '-'} mode={source_task.get('mode') or '-'} "
        f"phase={source_task.get('current_phase') or '-'}",
        file=sys.stderr,
    )
    print(
        f"[context-task-planning] Target task: {target_task.get('slug') or '(none)'}",
        file=sys.stderr,
    )
    if result["reason"]:
        print(
            f"[context-task-planning] Recommended action: {recommendation} — {result['reason']}",
            file=sys.stderr,
        )


def ensure_switch_safety(args: argparse.Namespace) -> None:
    result = check_switch_safety(
        args.cwd, args.source_task, args.target_task, args.session_key
    )

    if result["safe"] or args.allow_dirty:
        return

    if args.stash:
        run_stash(result)
        return

    print_switch_warning(result)

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(
            "[context-task-planning] Retry the switching command with `--stash` to stash all dirty task repos automatically, "
            "commit the current work manually and retry, or use `--allow-dirty` to continue anyway.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    recommendation = result["recommendation"]
    if recommendation == "commit-first":
        choices = [
            ("c", "stop here so you can commit manually (recommended)"),
            ("s", "stash current work and continue switching"),
            ("l", "leave the worktree dirty and continue switching"),
            ("x", "cancel the switch"),
        ]
    else:
        choices = [
            ("s", "stash current work and continue switching (recommended)"),
            ("c", "stop here so you can commit manually"),
            ("l", "leave the worktree dirty and continue switching"),
            ("x", "cancel the switch"),
        ]

    print(
        "[context-task-planning] Choose how to handle the current repo checkouts:",
        file=sys.stderr,
    )
    for key, label in choices:
        print(f"  [{key}] {label}", file=sys.stderr)

    while True:
        response = (
            input("[context-task-planning] Enter choice [s/c/l/x]: ").strip().lower()
        )
        if response == "s":
            run_stash(result)
            return
        if response == "l":
            return
        if response == "c":
            raise SystemExit(
                "Commit the current work manually, then rerun the switching command."
            )
        if response == "x":
            raise SystemExit("Cancelled task switch.")


def compact_current_task(task: dict) -> str:
    if not task["found"]:
        return f"task=(none) source=none action={task.get('recommended_action') or 'init-task'}"
    spec_context = normalize_spec_context(task.get("spec_context"))
    spec_suffix = ""
    if spec_context.get("provider") != "none" or spec_context.get("status") != "none":
        spec_suffix = f" spec={spec_context.get('provider') or '-'}:{spec_context.get('status') or '-'}"
    return (
        f"task={task['slug']} status={task['status'] or '-'} mode={task['mode'] or '-'} "
        f"phase={task['current_phase'] or '-'} source={task['selection_source']} "
        f"role={task.get('binding_role') or '-'} action={task.get('recommended_action') or '-'} "
        f"brief={task.get('brief_quality') or '-'}{spec_suffix}"
    )


def format_repo_binding_items(items: list[dict]) -> str:
    if not items:
        return "(none)"
    return ", ".join(
        f"{item['repo_id']} ({item['checkout_path']})"
        for item in items
        if item.get("repo_id")
    )


def print_recommended_commands(commands: list[str]) -> None:
    if not commands:
        print("[context-task-planning] Suggested commands: none")
        return

    print("[context-task-planning] Suggested commands:")
    for command in commands:
        print(f"  - {command}")


def print_resume_candidates(candidates: list[dict]) -> None:
    if not candidates:
        print("[context-task-planning] Resume candidates: none")
        return

    print("[context-task-planning] Resume candidates:")
    for item in candidates:
        print(
            "  - "
            f"{item['slug']} status={item['status']} updated={item.get('updated_at') or '-'} "
            f"title={item.get('title') or '-'}"
        )


def print_current_task(task: dict, as_json: bool, compact: bool) -> None:
    if as_json:
        print(json.dumps(task, ensure_ascii=False, indent=2))
        return

    if compact:
        print(compact_current_task(task))
        return

    print(f"[context-task-planning] Workspace: {task['workspace_root']}")
    print(f"[context-task-planning] Task root: {task['plan_root']}")
    print(
        f"[context-task-planning] Requested task: {task['requested_slug'] or '(none)'}"
    )
    print(f"[context-task-planning] Session key: {task['session_key'] or '(none)'}")
    print(
        f"[context-task-planning] Session binding: {task['session_binding'] or '(none)'}"
    )
    print(
        f"[context-task-planning] Active pointer: {task['active_pointer'] or '(none)'}"
    )
    print(f"[context-task-planning] Session pin: {task['session_pin'] or '(none)'}")
    print(f"[context-task-planning] Selected source: {task['selection_source']}")

    if not task["found"]:
        print("[context-task-planning] No active task found.")
        print(
            f"[context-task-planning] Recommended next step: {task.get('recommended_action') or 'init-task'}"
        )
        print(
            f"[context-task-planning] Why: {task.get('recommended_reason') or '(none)'}"
        )
        print_resume_candidates(task.get("resume_candidates", []))
        print_recommended_commands(task.get("recommended_commands", []))
        return

    print(f"[context-task-planning] Task: {task['slug']}")
    print(f"[context-task-planning] Title: {task['title'] or '(unknown)'}")
    print(
        "[context-task-planning] Status: "
        f"{task['status'] or '(unknown)'} | Mode: {task['mode'] or '(unknown)'} | "
        f"Phase: {task['current_phase'] or '(unknown)'}"
    )
    print(
        f"[context-task-planning] Next action: {task['next_action'] or '(none recorded)'}"
    )
    print(
        f"[context-task-planning] Brief: {task.get('brief_quality') or 'unknown'} | {brief_summary_for_state(task)}"
    )
    print(
        f"[context-task-planning] Spec context: {spec_context_summary_text(task.get('spec_context', {}))}"
    )
    spec_context = normalize_spec_context(task.get("spec_context", {}))
    if spec_context.get("primary_ref"):
        print(
            f"[context-task-planning] Primary spec ref: {spec_context.get('primary_ref')}"
        )
    candidate_refs = spec_context_candidate_refs(spec_context)
    if candidate_refs:
        print(
            "[context-task-planning] Spec candidates: " + "; ".join(candidate_refs[:4])
        )
        for index, command in enumerate(
            spec_context_resolution_commands(task.get("slug", ""), spec_context)
        ):
            prefix = "Resolve with" if index == 0 else "Or with"
            print(f"[context-task-planning] {prefix}: {command}")
    artifact_refs = spec_context_linked_artifact_refs(spec_context)
    if artifact_refs:
        print(
            "[context-task-planning] Linked artifacts: " + "; ".join(artifact_refs[:4])
        )
    brief_missing_fields = task.get("brief_missing_fields") or []
    if brief_missing_fields:
        print(
            "[context-task-planning] Brief gaps: "
            + ", ".join(str(item) for item in brief_missing_fields)
        )
    print(
        "[context-task-planning] Access: "
        f"{task.get('binding_role') or '(unbound)'} | writer={task.get('writer_display') or '(none)'} | "
        f"observers={task.get('observer_count', 0)}"
    )
    repo_scope = task.get("repo_scope") or []
    if repo_scope:
        print(
            f"[context-task-planning] Repos: primary={task.get('primary_repo') or '(none)'} | scope={', '.join(repo_scope)}"
        )
    repo_summary = task.get("repo_summary", {})
    if repo_summary.get("shared") or repo_summary.get("worktree"):
        print(
            "[context-task-planning] Repo bindings: "
            f"shared={format_repo_binding_items(repo_summary.get('shared', []))} | "
            f"worktree={format_repo_binding_items(repo_summary.get('worktree', []))}"
        )

    blockers = task["blockers"]
    if blockers:
        print(f"[context-task-planning] Blockers: {'; '.join(blockers)}")
    else:
        print("[context-task-planning] Blockers: none")

    active_delegates = task["active_delegates"]
    if active_delegates:
        print(
            f"[context-task-planning] Active delegates: {', '.join(active_delegates)}"
        )
    else:
        print("[context-task-planning] Active delegates: none")
    print(
        f"[context-task-planning] Recommended next step: {task.get('recommended_action') or 'continue-current-task'}"
    )
    print(f"[context-task-planning] Why: {task.get('recommended_reason') or '(none)'}")
    print_recommended_commands(task.get("recommended_commands", []))


def subagent_preflight_result(
    cwd: str,
    task_slug: str,
    session_key: str,
    host: str,
    task_text: str,
    tool_name: str,
) -> dict:
    task = resolve_task(cwd, task_slug, session_key)
    return build_subagent_preflight_result(task, host, task_text, tool_name)


def print_plan_dir(task: dict) -> None:
    if task.get("found") and task.get("plan_dir"):
        print(task["plan_dir"])


def list_repos_result(workspace_root: Path, plan_root: Path, discover: bool) -> dict:
    registered = read_repo_registry(plan_root)
    discovered = discover_workspace_repos(workspace_root) if discover else []
    registered_paths = {repo["path"] for repo in registered}
    discovered_only = [
        repo for repo in discovered if repo["path"] not in registered_paths
    ]
    return {
        "workspace_root": str(workspace_root),
        "registered": registered,
        "discovered": discovered_only,
    }


def print_list_repos(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(f"[context-task-planning] Workspace: {result['workspace_root']}")
    registered = result.get("registered", [])
    discovered = result.get("discovered", [])

    if registered:
        print("[context-task-planning] Registered repos:")
        for repo in registered:
            print(f"  - {repo['id']}: {repo['path']}")
    else:
        print("[context-task-planning] Registered repos: none")

    if discovered:
        print("[context-task-planning] Discoverable repos (not registered):")
        for repo in discovered:
            print(f"  - {repo['id']}: {repo['path']}")


def task_repo_binding_result(
    plan_root: Path, workspace_root: Path, task_slug: str, repo_id: str
) -> dict:
    bindings = effective_task_repo_bindings(plan_root, workspace_root, task_slug)
    wanted = normalize_repo_id(repo_id)
    for binding in bindings:
        if binding["repo_id"] == wanted:
            return {
                "workspace_root": str(workspace_root),
                "task_slug": task_slug,
                "binding": binding,
            }
    raise SystemExit(f"Repo `{wanted}` is not bound to task `{task_slug}`.")


def print_task_repo_binding(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    binding = result["binding"]
    print(f"[context-task-planning] Task: {result['task_slug']}")
    print(f"[context-task-planning] Repo: {binding['repo_id']}")
    print(
        f"[context-task-planning] Binding: mode={binding['mode']} checkout={binding['checkout_path']} branch={binding.get('branch') or '-'}"
    )


def list_worktrees_result(
    plan_root: Path, workspace_root: Path, task_slug: str = ""
) -> dict:
    rows = explicit_worktree_bindings(plan_root)
    if task_slug:
        rows = [row for row in rows if row["task_slug"] == task_slug]
    return {
        "workspace_root": str(workspace_root),
        "worktrees": rows,
    }


def print_list_worktrees(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(f"[context-task-planning] Workspace: {result['workspace_root']}")
    worktrees = sorted(
        result.get("worktrees", []),
        key=lambda row: (row["task_slug"], row["repo_id"], row["checkout_path"]),
    )
    if not worktrees:
        print("[context-task-planning] Worktrees: none")
        return

    print("[context-task-planning] Worktrees:")
    current_task = ""
    for row in worktrees:
        if row["task_slug"] != current_task:
            current_task = row["task_slug"]
            print(f"  - task={current_task}")
        print(
            "    "
            f"repo={row['repo_id']} path={row['checkout_path']} "
            f"branch={row.get('branch') or '-'}"
        )


def print_repo_isolation_summary(summary: dict) -> None:
    safe_shared = summary.get("safe_shared", [])
    needs_worktree = summary.get("needs_worktree", [])
    already_isolated = summary.get("already_isolated", [])

    print(
        "[context-task-planning] Safe shared repos: "
        f"{format_repo_binding_items(safe_shared)}"
    )

    if needs_worktree:
        print("[context-task-planning] Repos that need a worktree:")
        for item in needs_worktree:
            other_tasks = ", ".join(item.get("other_tasks", [])) or "(unknown)"
            print(
                "  - "
                f"{item['repo_id']} shares `{item['checkout_path']}` with {other_tasks}; "
                f"run `{item['recommended_command']}`"
            )
    else:
        print("[context-task-planning] Repos that need a worktree: none")

    print(
        "[context-task-planning] Already isolated repos: "
        f"{format_repo_binding_items(already_isolated)}"
    )


def render_repo_isolation_error(summary: dict) -> str:
    lines = [
        "Writer isolation required before binding this task.",
        f"[context-task-planning] Safe shared repos: {format_repo_binding_items(summary.get('safe_shared', []))}",
    ]

    needs_worktree = summary.get("needs_worktree", [])
    if needs_worktree:
        lines.append("[context-task-planning] Repos that need a worktree:")
        for item in needs_worktree:
            other_tasks = ", ".join(item.get("other_tasks", [])) or "(unknown)"
            lines.append(
                f"  - {item['repo_id']} shares `{item['checkout_path']}` with {other_tasks}; run `{item['recommended_command']}`"
            )
    else:
        lines.append("[context-task-planning] Repos that need a worktree: none")

    lines.append(
        f"[context-task-planning] Already isolated repos: {format_repo_binding_items(summary.get('already_isolated', []))}"
    )
    return "\n".join(lines)


def handle_list_repos(args: argparse.Namespace) -> None:
    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    result = list_repos_result(workspace_root, plan_root, args.discover)
    print_list_repos(result, args.json)


def handle_register_repo(args: argparse.Namespace) -> None:
    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    entry = register_workspace_repo(plan_root, workspace_root, args.path, args.id)
    print(
        f"[context-task-planning] Registered repo `{entry['id']}` at `{entry['path']}` in workspace `{workspace_root}`"
    )


def handle_set_task_repos(args: argparse.Namespace) -> None:
    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    result = set_task_repo_scope(
        plan_root, workspace_root, args.task.strip(), args.repo, args.primary
    )
    isolation = summarize_repo_isolation(plan_root, workspace_root, result["task_slug"])
    scope_text = ", ".join(result["repo_scope"]) if result["repo_scope"] else "(unset)"
    print(f"[context-task-planning] Task: {result['task_slug']}")
    print(
        f"[context-task-planning] Primary repo: {result['primary_repo'] or '(unset)'}"
    )
    print(f"[context-task-planning] Repo scope: {scope_text}")
    if isolation["has_conflicts"] or isolation.get("already_isolated"):
        print_repo_isolation_summary(isolation)


def handle_task_repo_binding(args: argparse.Namespace) -> None:
    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    result = task_repo_binding_result(
        plan_root, workspace_root, args.task.strip(), args.repo.strip()
    )
    print_task_repo_binding(result, args.json)


def handle_set_task_repo_binding(args: argparse.Namespace) -> None:
    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    result = set_task_repo_binding(
        plan_root,
        workspace_root,
        args.task.strip(),
        args.repo.strip(),
        args.mode,
        args.checkout_path,
        args.branch,
        args.base_branch,
    )
    print(
        f"[context-task-planning] Bound task `{result['task_slug']}` repo `{result['repo_id']}` to {result['mode']} checkout `{result['checkout_path']}`"
    )


def handle_set_task_spec_context(args: argparse.Namespace) -> None:
    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    result = set_task_spec_context(
        plan_root,
        args.task.strip(),
        args.provider,
        args.ref,
        args.artifact,
        args.summary,
        args.clear,
    )
    spec_context = result["spec_context"]
    print(f"[context-task-planning] Task: {result['task_slug']}")
    print(
        "[context-task-planning] Spec context: "
        + spec_context_summary_text(spec_context)
    )
    if spec_context.get("primary_ref"):
        print(
            f"[context-task-planning] Primary spec ref: {spec_context.get('primary_ref')}"
        )


def handle_list_worktrees(args: argparse.Namespace) -> None:
    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    result = list_worktrees_result(plan_root, workspace_root, args.task.strip())
    print_list_worktrees(result, args.json)


def bind_session_task(args: argparse.Namespace) -> None:
    session_key = effective_session_key(args.session_key, args.fallback)
    if not session_key:
        raise SystemExit(
            "Session binding requires PLAN_SESSION_KEY or --session-key. Use --fallback for the shared workspace default."
        )

    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    task_slug = args.task.strip()
    role = normalize_role(args.role)
    if not task_slug:
        raise SystemExit("Missing task slug for session binding.")

    plan_dir = plan_root / task_slug
    if not plan_dir.is_dir():
        raise SystemExit(f"Task not found: {plan_dir}")

    if role == ROLE_WRITER:
        isolation = summarize_repo_isolation(
            plan_root, workspace_root, task_slug, session_key
        )
        if isolation["has_conflicts"]:
            raise SystemExit(render_repo_isolation_error(isolation))

    existing_writer = writer_binding_for_task(plan_root, task_slug)
    existing_writer_key = str(existing_writer.get("session_key") or "").strip()

    if (
        role == ROLE_WRITER
        and existing_writer_key
        and existing_writer_key != session_key
        and not args.steal
    ):
        raise SystemExit(
            "Task already has a writer: "
            f"{display_session_key(existing_writer_key)}. "
            "Use --observe to join as an observer or --steal to take over the writer lease."
        )

    if (
        role == ROLE_WRITER
        and existing_writer_key
        and existing_writer_key != session_key
    ):
        demote_writer_binding(plan_root, task_slug)

    write_session_binding(plan_root, session_key, task_slug, role)


def clear_session_task(args: argparse.Namespace) -> None:
    session_key = effective_session_key(args.session_key, args.fallback)
    if not session_key:
        return

    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    clear_session_binding(plan_root, session_key)


def clear_task_sessions(args: argparse.Namespace) -> None:
    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    clear_task_session_bindings(plan_root, args.task.strip())


def check_task_access(args: argparse.Namespace) -> None:
    session_key = effective_session_key(args.session_key, args.fallback)
    if not session_key:
        raise SystemExit(
            "This command needs PLAN_SESSION_KEY or --session-key to enforce task access. Use --fallback for the shared workspace default."
        )

    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    task_slug = args.task.strip()
    role = binding_role_for_task(plan_root, session_key, task_slug)
    if (
        not role
        and session_key == WORKSPACE_FALLBACK_SESSION_KEY
        and read_active_pointer(plan_root) == task_slug
        and not writer_binding_for_task(plan_root, task_slug)
    ):
        role = ROLE_WRITER

    if not role:
        raise SystemExit(
            f"Session {display_session_key(session_key)} is not bound to task `{task_slug}`."
        )

    if args.require_role == ROLE_WRITER and role != ROLE_WRITER:
        writer = writer_binding_for_task(plan_root, task_slug)
        writer_display = display_session_key(str(writer.get("session_key") or ""))
        raise SystemExit(
            f"Task `{task_slug}` is observe-only for {display_session_key(session_key)}. "
            f"Current writer: {writer_display}. Observers may update delegate lanes but must not edit main planning files."
        )


def handle_record_progress(args: argparse.Namespace) -> None:
    session_key = effective_session_key(args.session_key, args.fallback)
    if not session_key:
        raise SystemExit(
            "record-progress requires PLAN_SESSION_KEY or --session-key. Use --fallback for the shared workspace default."
        )

    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    task_slug = args.task.strip()
    if not task_slug:
        task = resolve_task(args.cwd, "", session_key)
        if not task.get("found") or not task.get("slug"):
            raise SystemExit("Could not resolve a current task for record-progress.")
        task_slug = str(task.get("slug") or "").strip()

    result = record_progress_entry(
        plan_root,
        workspace_root,
        task_slug,
        session_key,
        args.source_id.strip(),
        args.timestamp.strip(),
        args.status.strip() or "complete",
        args.checkpoint.strip(),
        args.action,
        args.file,
        args.note,
        args.task_status.strip(),
        args.mode.strip(),
        args.phase.strip(),
        args.next_action.strip(),
        args.primary_repo.strip(),
        normalize_markdown_items(args.repo),
    )
    if args.json:
        print(json.dumps(result, indent=2))
        return

    state_text = "deduped" if result.get("deduped") else "recorded"
    print(
        f"[context-task-planning] Progress {state_text} for `{result['task_slug']}` from `{result['source_id']}`"
    )


def resolve_context_prune_task(
    args: argparse.Namespace, session_key: str = ""
) -> tuple[Path, Path, str, Path]:
    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    task = resolve_task(args.cwd, args.task, session_key)
    if not task.get("found") or not task.get("slug"):
        raise SystemExit("Could not resolve a current task for context-prune.")
    task_slug = str(task.get("slug") or "").strip()
    return workspace_root, plan_root, task_slug, plan_root / task_slug


def resolve_user_path(workspace_root: Path, value: str) -> Path | None:
    text = value.strip()
    if not text:
        return None
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        candidate = workspace_root / candidate
    return candidate.resolve()


def ensure_context_prune_writer_access(
    workspace_root: Path, task_slug: str, session_key: str
) -> None:
    if not session_key:
        raise SystemExit(
            "context-prune write actions require PLAN_SESSION_KEY or --session-key. Use --fallback for the shared workspace default."
        )
    check_task_access(
        argparse.Namespace(
            cwd=str(workspace_root),
            task=task_slug,
            session_key=session_key,
            require_role=ROLE_WRITER,
            fallback=False,
        )
    )


def print_context_prune_result(result: dict, as_json: bool, compact: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    action = result.get("action")
    if action == "prepared":
        files_value = result.get("files")
        files = files_value if isinstance(files_value, dict) else {}
        print(f"[context-task-planning] Prepared context prune for `{result.get('task_slug')}`")
        print(f"[context-task-planning] Brief: {files.get('brief')}")
        print(f"[context-task-planning] Manifest: {files.get('manifest')}")
        print(
            "[context-task-planning] Next: write the summary, then run "
            f"`sh skill/scripts/context-prune.sh --task {result.get('task_slug')} --apply --summary-file <summary.md>`"
        )
        return
    if action == "applied":
        archive_value = result.get("archive")
        archive = archive_value if isinstance(archive_value, dict) else {}
        result_value = result.get("result")
        result_meta = result_value if isinstance(result_value, dict) else {}
        print(f"[context-task-planning] Applied context prune for `{result.get('task_slug')}`")
        print(f"[context-task-planning] Archive: {archive.get('path')}")
        print(
            f"[context-task-planning] progress.md now has {result_meta.get('lines', 0)} lines and {result_meta.get('session_count', 0)} recent sessions."
        )
        return
    if action == "restored":
        print(f"[context-task-planning] Restored progress.md for `{result.get('task_slug')}`")
        print(f"[context-task-planning] Manifest: {result.get('manifest_path')}")
        print(f"[context-task-planning] Restore backup: {result.get('restore_backup')}")
        return
    print(format_prune_status(result, compact=compact))


def handle_context_prune(args: argparse.Namespace) -> None:
    actions = [
        bool(args.prepare),
        bool(args.apply),
        bool(args.restore),
        bool(args.status),
    ]
    if sum(1 for item in actions if item) > 1:
        raise SystemExit("Choose only one of --status, --prepare, --apply, or --restore.")

    session_key = effective_session_key(args.session_key, args.fallback)
    workspace_root, _plan_root, task_slug, plan_dir = resolve_context_prune_task(
        args, session_key
    )

    if args.prepare:
        result = prepare_context_prune(plan_dir, keep_sessions=args.keep_sessions)
        print_context_prune_result(result, args.json, args.compact)
        return

    if args.apply:
        ensure_context_prune_writer_access(workspace_root, task_slug, session_key)
        summary_path = resolve_user_path(workspace_root, args.summary_file)
        if summary_path is None:
            raise SystemExit("context-prune --apply requires --summary-file <path>.")
        manifest_path = resolve_user_path(workspace_root, args.manifest)
        result = apply_context_prune(plan_dir, summary_path, manifest_path)
        print_context_prune_result(result, args.json, args.compact)
        return

    if args.restore:
        ensure_context_prune_writer_access(workspace_root, task_slug, session_key)
        manifest_path = None
        if args.restore.strip().lower() != "latest":
            manifest_path = resolve_user_path(workspace_root, args.restore)
        result = restore_context_prune(plan_dir, manifest_path)
        print_context_prune_result(result, args.json, args.compact)
        return

    result = context_prune_status(plan_dir, keep_sessions=args.keep_sessions)
    print_context_prune_result(result, args.json, args.compact)


def main() -> None:
    args = parse_args()

    if args.command == "resolve-workspace-root":
        print(resolve_workspace_root(args.cwd))
        return

    if args.command == "current-task":
        task = resolve_task(args.cwd, args.task, args.session_key)
        print_current_task(task, args.json, args.compact)
        return

    if args.command == "resolve-plan-dir":
        task = resolve_task(args.cwd, args.task, args.session_key)
        print_plan_dir(task)
        return

    if args.command == "subagent-preflight":
        result = subagent_preflight_result(
            args.cwd,
            args.task,
            args.session_key,
            args.host,
            args.task_text,
            args.tool_name,
        )
        print_subagent_preflight(result, args.json, args.text, args.compact)
        return

    if args.command == "check-switch-safety":
        result = check_switch_safety(
            args.cwd, args.source_task, args.target_task, args.session_key
        )
        print_switch_safety(result, args.json, args.compact)
        return

    if args.command == "record-progress":
        handle_record_progress(args)
        return

    if args.command == "context-prune":
        handle_context_prune(args)
        return

    if args.command == "ensure-switch-safety":
        ensure_switch_safety(args)
        return

    if args.command == "bind-session-task":
        bind_session_task(args)
        return

    if args.command == "clear-session-task":
        clear_session_task(args)
        return

    if args.command == "clear-task-sessions":
        clear_task_sessions(args)
        return

    if args.command == "list-repos":
        handle_list_repos(args)
        return

    if args.command == "register-repo":
        handle_register_repo(args)
        return

    if args.command == "set-task-repos":
        handle_set_task_repos(args)
        return

    if args.command == "task-repo-binding":
        handle_task_repo_binding(args)
        return

    if args.command == "set-task-repo-binding":
        handle_set_task_repo_binding(args)
        return

    if args.command == "set-task-spec-context":
        handle_set_task_spec_context(args)
        return

    if args.command == "list-worktrees":
        handle_list_worktrees(args)
        return

    if args.command == "check-task-access":
        check_task_access(args)
        return

    prompt = args.prompt or sys.stdin.read()
    task = resolve_task(args.cwd, args.task, args.session_key)
    result = classify_drift(prompt, task)
    print_drift(result, args.json, args.compact)


if __name__ == "__main__":
    main()
