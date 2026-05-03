#!/usr/bin/env python3
"""
Test configuration and fixtures for context-task-planning tests.
"""

import json
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory with .planning structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        plan_root = workspace / ".planning"
        plan_root.mkdir(parents=True)

        # Create runtime directory
        runtime_dir = plan_root / ".runtime"
        runtime_dir.mkdir(parents=True)

        # Create sessions directory
        sessions_dir = plan_root / ".sessions"
        sessions_dir.mkdir(parents=True)

        yield workspace


@pytest.fixture
def temp_task(temp_workspace):
    """Create a temporary task directory with basic state."""
    task_slug = "test-task"
    task_dir = temp_workspace / ".planning" / task_slug
    task_dir.mkdir(parents=True)

    # Create basic state.json
    state = {
        "slug": task_slug,
        "title": "Test Task",
        "status": "in_progress",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }
    (task_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n")

    # Create basic plan.md
    (task_dir / "plan.md").write_text("# Test Task\n\nThis is a test task.\n")

    yield {
        "workspace": temp_workspace,
        "task_slug": task_slug,
        "task_dir": task_dir,
        "state": state,
    }
