#!/usr/bin/env python3
"""
Repository registry management for context-task-planning.

Handles:
- Repository registration and discovery
- Task-repo binding overrides
- Path resolution within workspace
"""

import json
import re
import subprocess
from pathlib import Path

from constants import (
    REPO_REGISTRY_FILE,
    RUNTIME_DIR_NAME,
    TASK_REPO_BINDING_DIR,
    WORKTREE_ROOT_NAME,
)
from file_utils import atomic_write_json
from file_lock import file_lock, lock_path_for
from session_binding import safe_json, utc_now


def runtime_dir(plan_root: Path) -> Path:
    """Get the runtime directory path."""
    return plan_root / RUNTIME_DIR_NAME


def repo_registry_path(plan_root: Path) -> Path:
    """Get the repository registry file path."""
    return runtime_dir(plan_root) / REPO_REGISTRY_FILE


def task_repo_binding_path(plan_root: Path, task_slug: str) -> Path:
    """Get the task-repo binding file path."""
    return runtime_dir(plan_root) / TASK_REPO_BINDING_DIR / f"{task_slug}.json"


def normalize_repo_id(value: str) -> str:
    """Normalize a repository ID to lowercase kebab-case."""
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = re.sub(r"-+", "-", lowered).strip("-")
    return lowered


def write_json_file(path: Path, payload: dict) -> None:
    """Write JSON file atomically."""
    atomic_write_json(path, payload, indent=2)


def relative_to_workspace(workspace_root: Path, absolute_path: Path) -> str:
    """Get relative path from workspace root."""
    try:
        return str(absolute_path.resolve().relative_to(workspace_root.resolve())) or "."
    except ValueError as exc:
        raise SystemExit(
            f"Path `{absolute_path}` must live under workspace `{workspace_root}`."
        ) from exc


def resolve_path_in_workspace(workspace_root: Path, raw_path: str) -> Path:
    """Resolve a path within the workspace."""
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = workspace_root / candidate
    try:
        return candidate.resolve()
    except OSError as exc:
        raise SystemExit(f"Could not resolve path `{raw_path}`: {exc}") from exc


def git_root_for(workspace_root: Path) -> Path | None:
    """Get the git root for a directory, or None if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace_root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def read_repo_registry(plan_root: Path) -> list[dict]:
    """Read the repository registry."""
    payload = safe_json(repo_registry_path(plan_root))
    repos = payload.get("repos", []) if isinstance(payload, dict) else []
    if not isinstance(repos, list):
        return []

    normalized = []
    seen = set()
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        repo_id = normalize_repo_id(str(repo.get("id") or ""))
        repo_path = str(repo.get("path") or "").strip()
        if not repo_id or not repo_path or repo_id in seen:
            continue
        seen.add(repo_id)
        normalized.append(
            {
                "id": repo_id,
                "path": repo_path,
                "registration_mode": str(repo.get("registration_mode") or "manual"),
                "registered_at": str(repo.get("registered_at") or ""),
                "updated_at": str(repo.get("updated_at") or ""),
            }
        )
    return normalized


def write_repo_registry(plan_root: Path, repos: list[dict]) -> None:
    """Write the repository registry with concurrent safety."""
    payload = {
        "schema_version": "1.0.0",
        "repos": repos,
        "updated_at": utc_now(),
    }

    # Use file lock for concurrent safety
    registry_path = repo_registry_path(plan_root)
    lock_file = lock_path_for(registry_path, plan_root)
    with file_lock(lock_file):
        write_json_file(registry_path, payload)


def repo_by_id(plan_root: Path, repo_id: str) -> dict:
    """Get a repository by ID."""
    wanted = normalize_repo_id(repo_id)
    for repo in read_repo_registry(plan_root):
        if repo["id"] == wanted:
            return repo
    return {}


def registered_repo_absolute_path(workspace_root: Path, repo: dict) -> Path:
    """Get the absolute path for a registered repository."""
    repo_path = str(repo.get("path") or "").strip() or "."
    return resolve_path_in_workspace(workspace_root, repo_path)


def discover_workspace_repos(workspace_root: Path) -> list[dict]:
    """Discover git repositories in the workspace."""
    candidates = [workspace_root]
    for entry in sorted(workspace_root.iterdir(), key=lambda item: item.name):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if entry.name in {"node_modules", "vendor", WORKTREE_ROOT_NAME}:
            continue
        candidates.append(entry)

    discovered = []
    seen_paths = set()
    for candidate in candidates:
        git_root = git_root_for(candidate)
        if git_root is None:
            continue
        rel_path = relative_to_workspace(workspace_root, git_root)
        if rel_path in seen_paths:
            continue
        seen_paths.add(rel_path)
        repo_id = normalize_repo_id(
            git_root.name if rel_path != "." else workspace_root.name
        )
        discovered.append(
            {
                "id": repo_id or "workspace",
                "path": rel_path,
            }
        )

    discovered.sort(key=lambda repo: (repo["path"] != ".", repo["path"], repo["id"]))
    return discovered


def register_workspace_repo(
    plan_root: Path, workspace_root: Path, raw_path: str, requested_id: str = ""
) -> dict:
    """Register a repository in the workspace."""
    resolved_path = resolve_path_in_workspace(workspace_root, raw_path)
    git_root = git_root_for(resolved_path)
    if git_root is None:
        raise SystemExit(f"Path `{raw_path}` is not inside a git repository.")

    repo_path = relative_to_workspace(workspace_root, git_root)
    repo_id = normalize_repo_id(requested_id or git_root.name or repo_path)
    if not repo_id:
        raise SystemExit("Could not derive a repo id. Pass --id explicitly.")

    repos = read_repo_registry(plan_root)
    for repo in repos:
        if repo["id"] == repo_id and repo["path"] != repo_path:
            raise SystemExit(
                f"Repo id `{repo_id}` is already registered for `{repo['path']}`."
            )
        if repo["path"] == repo_path and repo["id"] != repo_id:
            raise SystemExit(
                f"Repo path `{repo_path}` is already registered as `{repo['id']}`."
            )

    timestamp = utc_now()
    entry = {
        "id": repo_id,
        "path": repo_path,
        "registration_mode": "manual",
        "registered_at": timestamp,
        "updated_at": timestamp,
    }

    updated = False
    for index, repo in enumerate(repos):
        if repo["id"] == repo_id:
            entry["registered_at"] = repo.get("registered_at") or timestamp
            repos[index] = entry
            updated = True
            break

    if not updated:
        repos.append(entry)
        repos.sort(key=lambda repo: repo["id"])

    write_repo_registry(plan_root, repos)
    return entry


def read_task_repo_binding_overrides(plan_root: Path, task_slug: str) -> list[dict]:
    """Read task-repo binding overrides."""
    payload = safe_json(task_repo_binding_path(plan_root, task_slug))
    bindings = payload.get("bindings", []) if isinstance(payload, dict) else []
    if not isinstance(bindings, list):
        return []

    normalized = []
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        repo_id = normalize_repo_id(str(binding.get("repo_id") or ""))
        checkout_path = str(binding.get("checkout_path") or "").strip()
        mode = str(binding.get("mode") or "shared").strip() or "shared"
        if not repo_id or not checkout_path:
            continue
        normalized.append(
            {
                "repo_id": repo_id,
                "mode": "worktree" if mode == "worktree" else "shared",
                "checkout_path": checkout_path,
                "branch": str(binding.get("branch") or "").strip(),
                "base_branch": str(binding.get("base_branch") or "").strip(),
                "updated_at": str(binding.get("updated_at") or "").strip(),
            }
        )
    return normalized


def write_task_repo_binding_overrides(
    plan_root: Path, task_slug: str, bindings: list[dict]
) -> None:
    """Write task-repo binding overrides with concurrent safety."""
    payload = {
        "schema_version": "1.0.0",
        "task_slug": task_slug,
        "bindings": bindings,
        "updated_at": utc_now(),
    }

    # Use file lock for concurrent safety
    binding_path = task_repo_binding_path(plan_root, task_slug)
    lock_file = lock_path_for(binding_path, plan_root)
    with file_lock(lock_file):
        write_json_file(binding_path, payload)


def load_task_state(plan_dir: Path) -> dict:
    """Load task state from state.json, with fallback to minimal state."""
    state = safe_json(plan_dir / "state.json")
    if state:
        return state
    return {"slug": plan_dir.name, "title": plan_dir.name}
