#!/usr/bin/env python3

import json

from constants import ROLE_OBSERVER
from repo_registry import write_repo_registry
from session_binding import write_session_binding
from spec_context import (
    detect_openspec_spec_context,
    spec_context_resolution_commands,
)
from task_drift import classify_drift
from task_guard import resolve_task, subagent_preflight_result


def write_task(workspace, slug="runtime", **overrides):
    plan_root = workspace / ".planning"
    plan_root.mkdir(parents=True, exist_ok=True)
    task_dir = plan_root / slug
    task_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "slug": slug,
        "title": "Runtime cleanup",
        "status": "active",
        "mode": "implement",
        "current_phase": "implementation",
        "goal": "Refactor runtime task guard behavior",
        "next_action": "Continue refactor",
        "blockers": [],
        "non_goals": ["Do not change CLI contracts"],
        "acceptance_criteria": ["Existing smoke tests keep passing"],
        "edge_cases": [],
        "open_questions": [],
        "phases": [],
    }
    state.update(overrides)
    (task_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n")
    return task_dir


def test_resolve_task_prefers_session_binding(temp_workspace):
    write_task(temp_workspace, "fallback-task")
    write_task(temp_workspace, "bound-task", title="Bound task")
    plan_root = temp_workspace / ".planning"
    (plan_root / ".active_task").write_text("fallback-task\n")
    write_session_binding(plan_root, "test:session", "bound-task", ROLE_OBSERVER)

    task = resolve_task(str(temp_workspace), "", "test:session")

    assert task["found"] is True
    assert task["slug"] == "bound-task"
    assert task["selection_source"] == "session_binding"
    assert task["binding_role"] == ROLE_OBSERVER


def test_classify_drift_uses_task_and_spec_terms():
    task = {
        "found": True,
        "slug": "runtime-cleanup",
        "title": "Runtime cleanup",
        "goal": "Refactor task guard runtime",
        "current_phase": "implementation",
        "next_action": "Move drift logic",
        "blockers": [],
        "non_goals": [],
        "acceptance_criteria": [],
        "edge_cases": [],
        "open_questions": [],
        "phases": [],
        "spec_context": {
            "mode": "linked",
            "provider": "openspec",
            "status": "linked",
            "primary_ref": "openspec/changes/runtime-cleanup",
            "artifact_refs": ["openspec/changes/runtime-cleanup/proposal.md"],
            "summary": [],
        },
    }

    assert classify_drift("continue", task)["classification"] == "related"
    assert (
        classify_drift("Review openspec/changes/runtime-cleanup/proposal.md", task)[
            "classification"
        ]
        == "related"
    )
    assert (
        classify_drift("Start a new task for billing webhooks", task)[
            "classification"
        ]
        == "likely-unrelated"
    )


def test_subagent_preflight_injects_repo_payload_and_delegate_hint(temp_workspace):
    (temp_workspace / "app").mkdir()
    write_task(
        temp_workspace,
        "runtime",
        repo_scope=["app"],
        primary_repo="app",
    )
    plan_root = temp_workspace / ".planning"
    write_repo_registry(
        plan_root,
        [
            {
                "id": "app",
                "path": "app",
                "registration_mode": "manual",
                "registered_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            }
        ],
    )

    result = subagent_preflight_result(
        str(temp_workspace),
        "runtime",
        "",
        "codex",
        "Review runtime cleanup implementation",
        "Task",
    )

    assert result["decision"] == "payload_plus_delegate_recommended"
    assert result["routing"]["classification"] == "related"
    assert result["repo_context"]["primary_repo"] == "app"
    assert result["delegate"]["kind"] == "review"
    assert "Delegate recommended" in result["prompt_prefix"]
    assert "- app: shared at app" in result["prompt_prefix"]


def test_openspec_ambiguous_context_exposes_resolution_commands(temp_workspace):
    for change in ["add-cache", "remove-cache"]:
        change_dir = temp_workspace / "openspec" / "changes" / change
        change_dir.mkdir(parents=True)
        (change_dir / "proposal.md").write_text(f"# {change}\n")
    state = {
        "slug": "runtime",
        "title": "Runtime cleanup",
        "goal": "Investigate runtime behavior",
    }

    spec_context = detect_openspec_spec_context(temp_workspace, state, [])

    assert spec_context["status"] == "ambiguous"
    assert len(spec_context["artifact_refs"]) == 2
    commands = spec_context_resolution_commands("runtime", spec_context)
    assert commands
    assert commands[0].startswith(
        "sh skill/scripts/set-task-spec-context.sh --task runtime --ref "
    )
