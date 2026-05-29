#!/usr/bin/env python3

import pytest

from task_prune import (
    apply_context_prune,
    context_prune_status,
    prepare_context_prune,
    progress_session_blocks,
    restore_context_prune,
)


def write_progress(task_dir, session_count=8):
    lines = [
        "# Progress Log: Test",
        "",
        "## Snapshot",
        "",
        "- Task Slug: `test-task`",
        "- Status: `active`",
        "- Current Mode: `execute`",
        "- Current Phase: `execute`",
        "- Next Action: Continue",
        "- Last Updated: 2024-01-01T00:00:00Z",
        "",
        "## Session Log",
        "",
    ]
    for index in reversed(range(session_count)):
        lines.extend(
            [
                f"### Session: 2024-01-01T00:{index:02d}:00Z",
                "",
                "- Status: complete",
                "- Actions:",
                f"  - Completed durable step {index}",
                "- Files touched:",
                "  - `src/example.py`",
                "- Notes:",
                "  - Preserved useful note",
                "",
            ]
        )
    lines.extend(
        [
            "## Checkpoints",
            "",
            "| Timestamp | Checkpoint | Next Action |",
            "|-----------|------------|-------------|",
            "| 2024-01-01T00:00:00Z | important checkpoint | continue |",
            "",
            "## Verification Log",
            "",
            "| Timestamp | Command | Result | Notes |",
            "|-----------|---------|--------|-------|",
            "| 2024-01-01T00:00:00Z | `pytest` | pass | ok |",
            "",
            "## Handoff Notes",
            "",
            "- Continue from latest checkpoint.",
        ]
    )
    (task_dir / "progress.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_context_prune_status_recommends_large_session_log(temp_workspace):
    task_dir = temp_workspace / ".planning" / "test-task"
    task_dir.mkdir(parents=True)
    write_progress(task_dir, session_count=120)

    status = context_prune_status(task_dir, keep_sessions=60)

    assert status["risk"] == "recommend_prune"
    assert status["metrics"]["session_count"] == 120
    assert status["prunable_sessions"] == 60


def test_prepare_and_apply_context_prune_archives_old_progress(temp_workspace):
    task_dir = temp_workspace / ".planning" / "test-task"
    task_dir.mkdir(parents=True)
    write_progress(task_dir, session_count=8)
    summary_path = task_dir / ".derived" / "summary.md"
    summary_path.parent.mkdir(parents=True)
    summary_path.write_text(
        "### Timeline Summary\n\n- Older sessions completed setup and verification.\n",
        encoding="utf-8",
    )

    prepared = prepare_context_prune(task_dir, keep_sessions=3)
    applied = apply_context_prune(
        task_dir,
        summary_path,
        manifest_path=task_dir / ".derived" / "prune" / prepared["run_id"] / "manifest.json",
    )
    progress = (task_dir / "progress.md").read_text(encoding="utf-8")

    assert applied["status"] == "applied"
    assert "## Pruned History Summary" in progress
    assert "Older sessions completed setup and verification." in progress
    assert "important checkpoint" in progress
    assert len(progress_session_blocks(progress.splitlines())) == 3
    assert "Completed durable step 7" in progress
    assert "Completed durable step 6" in progress
    assert "Completed durable step 5" in progress
    assert "Completed durable step 4" not in progress
    assert (task_dir / ".derived" / "prune" / prepared["run_id"] / "progress.original.md").exists()


def test_apply_context_prune_rejects_changed_progress(temp_workspace):
    task_dir = temp_workspace / ".planning" / "test-task"
    task_dir.mkdir(parents=True)
    write_progress(task_dir, session_count=5)
    summary_path = task_dir / "summary.md"
    summary_path.write_text("### Timeline Summary\n\n- Summary.\n", encoding="utf-8")

    prepared = prepare_context_prune(task_dir, keep_sessions=2)
    with (task_dir / "progress.md").open("a", encoding="utf-8") as fh:
        fh.write("\n<!-- concurrent update -->\n")

    with pytest.raises(SystemExit, match="changed since context-prune --prepare"):
        apply_context_prune(
            task_dir,
            summary_path,
            manifest_path=task_dir / ".derived" / "prune" / prepared["run_id"] / "manifest.json",
        )


def test_apply_context_prune_rejects_manifest_from_other_task(temp_workspace):
    task_dir = temp_workspace / ".planning" / "test-task"
    other_dir = temp_workspace / ".planning" / "other-task"
    task_dir.mkdir(parents=True)
    other_dir.mkdir(parents=True)
    write_progress(task_dir, session_count=5)
    write_progress(other_dir, session_count=5)
    summary_path = task_dir / "summary.md"
    summary_path.write_text("### Timeline Summary\n\n- Summary.\n", encoding="utf-8")

    prepared = prepare_context_prune(other_dir, keep_sessions=2)
    manifest_path = other_dir / ".derived" / "prune" / prepared["run_id"] / "manifest.json"

    with pytest.raises(SystemExit, match="current task prune directory"):
        apply_context_prune(task_dir, summary_path, manifest_path=manifest_path)


def test_restore_context_prune_restores_archived_progress(temp_workspace):
    task_dir = temp_workspace / ".planning" / "test-task"
    task_dir.mkdir(parents=True)
    write_progress(task_dir, session_count=6)
    original = (task_dir / "progress.md").read_text(encoding="utf-8")
    summary_path = task_dir / "summary.md"
    summary_path.write_text("### Timeline Summary\n\n- Summary.\n", encoding="utf-8")

    prepared = prepare_context_prune(task_dir, keep_sessions=2)
    manifest_path = task_dir / ".derived" / "prune" / prepared["run_id"] / "manifest.json"
    apply_context_prune(task_dir, summary_path, manifest_path=manifest_path)
    restore_context_prune(task_dir, manifest_path=manifest_path)

    assert (task_dir / "progress.md").read_text(encoding="utf-8") == original
