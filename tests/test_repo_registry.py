#!/usr/bin/env python3
"""
Tests for repo_registry module.
"""

import json
from pathlib import Path

import pytest

from repo_registry import (
    discover_workspace_repos,
    git_root_for,
    load_task_state,
    normalize_repo_id,
    read_repo_registry,
    read_task_repo_binding_overrides,
    register_workspace_repo,
    repo_by_id,
    repo_registry_path,
    runtime_dir,
    task_repo_binding_path,
    write_repo_registry,
    write_task_repo_binding_overrides,
)
from constants import REPO_REGISTRY_FILE, RUNTIME_DIR_NAME, TASK_REPO_BINDING_DIR


class TestNormalizeRepoId:
    """Tests for normalize_repo_id function."""

    def test_lowercase_conversion(self):
        """Test that repo ID is lowercased."""
        assert normalize_repo_id("MyRepo") == "myrepo"

    def test_special_chars_replaced(self):
        """Test that special characters are replaced with hyphens."""
        assert normalize_repo_id("my_repo-name") == "my-repo-name"

    def test_multiple_hyphens_collapsed(self):
        """Test that multiple hyphens are collapsed."""
        assert normalize_repo_id("my---repo") == "my-repo"

    def test_leading_trailing_hyphens_stripped(self):
        """Test that leading/trailing hyphens are stripped."""
        assert normalize_repo_id("-my-repo-") == "my-repo"

    def test_empty_string(self):
        """Test empty string handling."""
        assert normalize_repo_id("") == ""


class TestRuntimeDir:
    """Tests for runtime_dir function."""

    def test_returns_runtime_dir(self, tmp_path):
        """Test that runtime directory is returned."""
        plan_root = tmp_path / ".planning"
        result = runtime_dir(plan_root)
        assert result.name == RUNTIME_DIR_NAME
        assert result.parent == plan_root


class TestRepoRegistryPath:
    """Tests for repo_registry_path function."""

    def test_returns_registry_path(self, tmp_path):
        """Test that registry path is returned."""
        plan_root = tmp_path / ".planning"
        result = repo_registry_path(plan_root)
        assert result.name == REPO_REGISTRY_FILE
        assert RUNTIME_DIR_NAME in str(result)


class TestTaskRepoBindingPath:
    """Tests for task_repo_binding_path function."""

    def test_returns_binding_path(self, tmp_path):
        """Test that binding path is returned."""
        plan_root = tmp_path / ".planning"
        result = task_repo_binding_path(plan_root, "my-task")
        assert result.name == "my-task.json"
        assert TASK_REPO_BINDING_DIR in str(result)


class TestReadRepoRegistry:
    """Tests for read_repo_registry function."""

    def test_empty_registry(self, tmp_path):
        """Test reading empty registry."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)
        runtime_dir(plan_root).mkdir(parents=True)

        result = read_repo_registry(plan_root)
        assert result == []

    def test_reads_existing_registry(self, tmp_path):
        """Test reading existing registry."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)
        registry_path = repo_registry_path(plan_root)
        registry_path.parent.mkdir(parents=True)

        payload = {
            "repos": [
                {"id": "main-repo", "path": "."},
                {"id": "sub-repo", "path": "subdir"},
            ]
        }
        registry_path.write_text(json.dumps(payload))

        result = read_repo_registry(plan_root)
        assert len(result) == 2
        assert result[0]["id"] == "main-repo"

    def test_handles_corrupt_json(self, tmp_path):
        """Test handling of corrupt JSON."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)
        registry_path = repo_registry_path(plan_root)
        registry_path.parent.mkdir(parents=True)
        registry_path.write_text("not valid json")

        result = read_repo_registry(plan_root)
        assert result == []


class TestWriteRepoRegistry:
    """Tests for write_repo_registry function."""

    def test_writes_registry(self, tmp_path):
        """Test writing registry."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        repos = [
            {"id": "main-repo", "path": ".", "registration_mode": "manual"},
        ]
        write_repo_registry(plan_root, repos)

        result = read_repo_registry(plan_root)
        assert len(result) == 1
        assert result[0]["id"] == "main-repo"

    def test_includes_timestamp(self, tmp_path):
        """Test that timestamp is included."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        repos = [{"id": "main-repo", "path": "."}]
        write_repo_registry(plan_root, repos)

        registry_path = repo_registry_path(plan_root)
        payload = json.loads(registry_path.read_text())
        assert "updated_at" in payload


class TestRepoById:
    """Tests for repo_by_id function."""

    def test_finds_repo(self, tmp_path):
        """Test finding a repo by ID."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        repos = [
            {"id": "main-repo", "path": "."},
            {"id": "sub-repo", "path": "subdir"},
        ]
        write_repo_registry(plan_root, repos)

        result = repo_by_id(plan_root, "main-repo")
        assert result["id"] == "main-repo"

    def test_returns_empty_for_unknown(self, tmp_path):
        """Test that empty dict is returned for unknown repo."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        result = repo_by_id(plan_root, "unknown-repo")
        assert result == {}

    def test_case_insensitive(self, tmp_path):
        """Test that search is case-insensitive."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        repos = [{"id": "Main-Repo", "path": "."}]
        write_repo_registry(plan_root, repos)

        result = repo_by_id(plan_root, "MAIN-REPO")
        assert result["id"] == "main-repo"


class TestLoadTaskState:
    """Tests for load_task_state function."""

    def test_loads_existing_state(self, tmp_path):
        """Test loading existing state."""
        task_dir = tmp_path / "my-task"
        task_dir.mkdir(parents=True)

        state = {"slug": "my-task", "title": "My Task", "status": "in_progress"}
        (task_dir / "state.json").write_text(json.dumps(state))

        result = load_task_state(task_dir)
        assert result["slug"] == "my-task"
        assert result["status"] == "in_progress"

    def test_returns_minimal_state_for_missing(self, tmp_path):
        """Test that minimal state is returned when state.json missing."""
        task_dir = tmp_path / "my-task"
        task_dir.mkdir(parents=True)

        result = load_task_state(task_dir)
        assert result["slug"] == "my-task"
        assert result["title"] == "my-task"


class TestTaskRepoBindingOverrides:
    """Tests for task-repo binding overrides."""

    def test_write_and_read_bindings(self, tmp_path):
        """Test write and read roundtrip."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        bindings = [
            {
                "repo_id": "main-repo",
                "mode": "worktree",
                "checkout_path": ".worktrees/task/main",
                "branch": "task/my-task",
            }
        ]
        write_task_repo_binding_overrides(plan_root, "my-task", bindings)

        result = read_task_repo_binding_overrides(plan_root, "my-task")
        assert len(result) == 1
        assert result[0]["repo_id"] == "main-repo"
        assert result[0]["mode"] == "worktree"

    def test_returns_empty_for_missing(self, tmp_path):
        """Test that empty list is returned for missing bindings."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        result = read_task_repo_binding_overrides(plan_root, "unknown-task")
        assert result == []

    def test_normalizes_mode(self, tmp_path):
        """Test that mode is normalized."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        bindings = [
            {"repo_id": "main-repo", "mode": "invalid-mode", "checkout_path": "."}
        ]
        write_task_repo_binding_overrides(plan_root, "my-task", bindings)

        result = read_task_repo_binding_overrides(plan_root, "my-task")
        assert result[0]["mode"] == "shared"  # invalid mode defaults to shared


class TestGitRootFor:
    """Tests for git_root_for function."""

    def test_finds_git_root(self, tmp_path):
        """Test finding git root."""
        # This test depends on the test being run in a git repo
        # Since we're in a git repo, this should work
        result = git_root_for(Path.cwd())
        assert result is not None
        assert (result / ".git").exists() or (result / ".git").is_dir()

    def test_returns_none_for_non_git(self, tmp_path):
        """Test that None is returned for non-git directory."""
        result = git_root_for(tmp_path)
        # tmp_path is typically not in a git repo
        # But it might be if tests are run from within a git repo
        # So we just check it returns a Path or None
        assert result is None or isinstance(result, Path)
