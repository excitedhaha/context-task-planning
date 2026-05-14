#!/usr/bin/env python3
"""
Tests for session_binding module.
"""

import json
import os
from pathlib import Path

import pytest

from session_binding import (
    clear_session_binding,
    clear_task_session_bindings,
    demote_writer_binding,
    display_session_key,
    effective_session_key,
    iter_session_bindings,
    normalize_role,
    read_session_binding,
    resolve_session_key,
    session_binding_name,
    session_binding_path,
    session_key_candidates,
    session_registry_dir,
    task_bindings,
    utc_now,
    write_session_binding,
    writer_binding_for_task,
)
from constants import ROLE_OBSERVER, ROLE_WRITER, WORKSPACE_FALLBACK_SESSION_KEY


class TestUtcNow:
    """Tests for utc_now function."""

    def test_returns_iso_format(self):
        """Test that utc_now returns ISO format string."""
        result = utc_now()
        assert "T" in result
        assert result.endswith("Z")

    def test_no_microseconds(self):
        """Test that microseconds are stripped."""
        result = utc_now()
        # ISO format with microseconds would have 6 digits after seconds
        assert "." not in result.split("T")[1].split("Z")[0]


class TestResolveSessionKey:
    """Tests for resolve_session_key function."""

    def test_returns_explicit_key(self):
        """Test that explicit key is returned."""
        result = resolve_session_key("my-session")
        assert result == "my-session"

    def test_returns_stripped_key(self):
        """Test that key is stripped."""
        result = resolve_session_key("  my-session  ")
        assert result == "my-session"

    def test_returns_empty_for_no_key(self):
        """Test that empty string is returned when no key."""
        result = resolve_session_key("")
        assert result == ""

    def test_uses_environment_variable(self, monkeypatch):
        """Test that environment variable is used as fallback."""
        monkeypatch.setenv("PLAN_SESSION_KEY", "env-session")
        result = resolve_session_key("")
        assert result == "env-session"

    def test_explicit_takes_precedence(self, monkeypatch):
        """Test that explicit key takes precedence over env."""
        monkeypatch.setenv("PLAN_SESSION_KEY", "env-session")
        result = resolve_session_key("explicit-session")
        assert result == "explicit-session"


class TestEffectiveSessionKey:
    """Tests for effective_session_key function."""

    def test_returns_resolved_key(self):
        """Test that resolved key is returned."""
        result = effective_session_key("my-session")
        assert result == "my-session"

    def test_returns_fallback_when_enabled(self):
        """Test that fallback is used when enabled."""
        result = effective_session_key("", fallback=True)
        assert result == WORKSPACE_FALLBACK_SESSION_KEY

    def test_no_fallback_when_disabled(self):
        """Test that empty is returned when fallback disabled."""
        result = effective_session_key("", fallback=False)
        assert result == ""


class TestNormalizeRole:
    """Tests for normalize_role function."""

    def test_writer_role(self):
        """Test writer role normalization."""
        assert normalize_role("writer") == ROLE_WRITER
        assert normalize_role("any-value") == ROLE_WRITER

    def test_observer_role(self):
        """Test observer role normalization."""
        assert normalize_role("observer") == ROLE_OBSERVER

    def test_case_sensitive(self):
        """Test that role comparison is case-sensitive."""
        assert normalize_role("OBSERVER") == ROLE_WRITER
        assert normalize_role("Observer") == ROLE_WRITER


class TestDisplaySessionKey:
    """Tests for display_session_key function."""

    def test_empty_key(self):
        """Test empty key display."""
        assert display_session_key("") == "(none)"

    def test_fallback_key(self):
        """Test fallback key display."""
        assert display_session_key(WORKSPACE_FALLBACK_SESSION_KEY) == "workspace-default"

    def test_regular_key(self):
        """Test regular key display."""
        assert display_session_key("my-session") == "my-session"


class TestSessionBindingName:
    """Tests for session_binding_name function."""

    def test_includes_cleaned_key(self):
        """Test that cleaned key is included."""
        result = session_binding_name("my-session")
        assert result.startswith("my-session-")
        assert result.endswith(".json")

    def test_sanitizes_special_chars(self):
        """Test that special characters are sanitized."""
        result = session_binding_name("my session/key:value")
        assert " " not in result
        assert "/" not in result
        assert ":" not in result

    def test_includes_hash(self):
        """Test that hash is included."""
        result = session_binding_name("test")
        parts = result.replace(".json", "").split("-")
        # Last part should be a 12-char hash
        assert len(parts[-1]) == 12

    def test_empty_key_uses_default(self):
        """Test that empty key uses 'session' default."""
        result = session_binding_name("")
        assert result.startswith("session-")


class TestSessionRegistryDir:
    """Tests for session_registry_dir function."""

    def test_returns_sessions_dir(self, tmp_path):
        """Test that sessions directory is returned."""
        plan_root = tmp_path / ".planning"
        result = session_registry_dir(plan_root)
        assert result.name == ".sessions"
        assert result.parent == plan_root


class TestSessionBindingPath:
    """Tests for session_binding_path function."""

    def test_returns_path_for_valid_key(self, tmp_path):
        """Test that path is returned for valid key."""
        plan_root = tmp_path / ".planning"
        result = session_binding_path(plan_root, "my-session")
        assert result is not None
        assert result.suffix == ".json"

    def test_returns_none_for_empty_key(self, tmp_path):
        """Test that None is returned for empty key."""
        plan_root = tmp_path / ".planning"
        result = session_binding_path(plan_root, "")
        assert result is None


class TestSessionKeyCandidates:
    """Tests for legacy-compatible session key lookup."""

    def test_returns_exact_key_first(self):
        assert session_key_candidates("trae:session-1") == [
            "trae:session-1",
            "traecli:session-1",
        ]

    def test_returns_legacy_alias_for_traecli(self):
        assert session_key_candidates("traecli:session-1") == [
            "traecli:session-1",
            "trae:session-1",
        ]

    def test_returns_only_exact_key_for_other_hosts(self):
        assert session_key_candidates("opencode:session-1") == ["opencode:session-1"]


class TestWriteAndReadSessionBinding:
    """Tests for write_session_binding and read_session_binding functions."""

    def test_write_and_read_roundtrip(self, tmp_path):
        """Test write and read roundtrip."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        write_session_binding(plan_root, "test-session", "my-task")
        result = read_session_binding(plan_root, "test-session")

        assert result["session_key"] == "test-session"
        assert result["task_slug"] == "my-task"
        assert result["role"] == ROLE_WRITER

    def test_write_with_observer_role(self, tmp_path):
        """Test writing with observer role."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        write_session_binding(plan_root, "test-session", "my-task", ROLE_OBSERVER)
        result = read_session_binding(plan_root, "test-session")

        assert result["role"] == ROLE_OBSERVER

    def test_read_nonexistent_binding(self, tmp_path):
        """Test reading nonexistent binding."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        result = read_session_binding(plan_root, "nonexistent")
        assert result == {}

    def test_clear_session_binding(self, tmp_path):
        """Test clearing session binding."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        write_session_binding(plan_root, "test-session", "my-task")
        assert clear_session_binding(plan_root, "test-session") is True
        assert read_session_binding(plan_root, "test-session") == {}

    def test_clear_nonexistent_binding(self, tmp_path):
        """Test clearing nonexistent binding."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        assert clear_session_binding(plan_root, "nonexistent") is False

    def test_reads_legacy_traecli_binding_via_trae_key(self, tmp_path):
        """Test that current Trae host can read older TraeCLI bindings."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        write_session_binding(plan_root, "traecli:session-1", "my-task", ROLE_OBSERVER)

        result = read_session_binding(plan_root, "trae:session-1")

        assert result["session_key"] == "traecli:session-1"
        assert result["task_slug"] == "my-task"
        assert result["role"] == ROLE_OBSERVER

    def test_clears_legacy_traecli_binding_via_trae_key(self, tmp_path):
        """Test that clear_session_binding removes compatible legacy aliases."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        write_session_binding(plan_root, "traecli:session-1", "my-task")

        assert clear_session_binding(plan_root, "trae:session-1") is True
        assert read_session_binding(plan_root, "traecli:session-1") == {}


class TestTaskBindings:
    """Tests for task_bindings function."""

    def test_returns_bindings_for_task(self, tmp_path):
        """Test that bindings for a task are returned."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        write_session_binding(plan_root, "session-1", "task-a")
        write_session_binding(plan_root, "session-2", "task-a")
        write_session_binding(plan_root, "session-3", "task-b")

        bindings = task_bindings(plan_root, "task-a")
        assert len(bindings) == 2

    def test_returns_empty_for_no_bindings(self, tmp_path):
        """Test that empty list is returned when no bindings."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        bindings = task_bindings(plan_root, "nonexistent-task")
        assert bindings == []


class TestWriterBindingForTask:
    """Tests for writer_binding_for_task function."""

    def test_returns_writer_binding(self, tmp_path):
        """Test that writer binding is returned."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        write_session_binding(plan_root, "session-1", "task-a", ROLE_WRITER)
        write_session_binding(plan_root, "session-2", "task-a", ROLE_OBSERVER)

        result = writer_binding_for_task(plan_root, "task-a")
        assert result["session_key"] == "session-1"
        assert result["role"] == ROLE_WRITER

    def test_returns_empty_when_no_writer(self, tmp_path):
        """Test that empty dict is returned when no writer."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        write_session_binding(plan_root, "session-1", "task-a", ROLE_OBSERVER)

        result = writer_binding_for_task(plan_root, "task-a")
        assert result == {}


class TestDemoteWriterBinding:
    """Tests for demote_writer_binding function."""

    def test_demotes_to_observer(self, tmp_path):
        """Test that writer is demoted to observer."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        write_session_binding(plan_root, "session-1", "task-a", ROLE_WRITER)
        demoted = demote_writer_binding(plan_root, "task-a")

        assert demoted == "session-1"
        result = read_session_binding(plan_root, "session-1")
        assert result["role"] == ROLE_OBSERVER

    def test_returns_empty_when_no_writer(self, tmp_path):
        """Test that empty string is returned when no writer."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        result = demote_writer_binding(plan_root, "task-without-writer")
        assert result == ""


class TestClearTaskSessionBindings:
    """Tests for clear_task_session_bindings function."""

    def test_clears_all_bindings_for_task(self, tmp_path):
        """Test that all bindings for a task are cleared."""
        plan_root = tmp_path / ".planning"
        plan_root.mkdir(parents=True)

        write_session_binding(plan_root, "session-1", "task-a")
        write_session_binding(plan_root, "session-2", "task-a")
        write_session_binding(plan_root, "session-3", "task-b")

        cleared = clear_task_session_bindings(plan_root, "task-a")

        assert len(cleared) == 2
        assert "session-1" in cleared
        assert "session-2" in cleared
        assert task_bindings(plan_root, "task-a") == []
        assert len(task_bindings(plan_root, "task-b")) == 1
