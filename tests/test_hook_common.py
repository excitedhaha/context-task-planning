#!/usr/bin/env python3

import sys
from pathlib import Path


HOOK_SCRIPTS = Path(__file__).resolve().parents[1] / "skill" / "claude-hooks" / "scripts"
if str(HOOK_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(HOOK_SCRIPTS))

from hook_common import (  # noqa: E402
    concise_subagent_preflight_context,
    subagent_preflight_should_inject_concise,
)


def test_concise_subagent_preflight_omits_single_repo_noise():
    preflight = {
        "found": True,
        "decision": "routing_only",
        "routing": {"classification": "related"},
        "task": {"slug": "runtime-cleanup", "binding_role": "writer"},
        "repo_context": {"repos": [], "repo_scope": []},
    }

    text = concise_subagent_preflight_context(preflight)

    assert subagent_preflight_should_inject_concise(preflight)
    assert "Current task: runtime-cleanup" in text
    assert "Keep this subagent scoped to the current task" in text
    assert "Repo/worktree bindings" not in text
    assert "Delegate recommended" not in text
    assert "Next action" not in text


def test_concise_subagent_preflight_adds_multirepo_and_spec_context():
    preflight = {
        "found": True,
        "decision": "payload_plus_delegate_recommended",
        "routing": {"classification": "unclear"},
        "task": {
            "slug": "runtime-multi-repo",
            "binding_role": "writer",
            "spec_context": {
                "mode": "linked",
                "provider": "openspec",
                "status": "ambiguous",
                "primary_ref": "",
                "artifact_refs": ["openspec/changes/runtime-a"],
            },
            "spec_candidate_refs": [
                "openspec/changes/runtime-a",
                "openspec/changes/runtime-b",
            ],
            "spec_resolution_hint": "sh skill/scripts/set-task-spec-context.sh --task runtime-multi-repo --ref <chosen-spec-ref>",
        },
        "repo_context": {
            "primary_repo": "app",
            "repo_scope": ["app", "api"],
            "repos": [
                {"id": "app", "binding_mode": "shared", "checkout_path": "app"},
                {"id": "api", "binding_mode": "worktree", "checkout_path": ".worktrees/api"},
            ],
        },
    }

    text = concise_subagent_preflight_context(preflight)

    assert subagent_preflight_should_inject_concise(preflight)
    assert "Task fit is unclear" in text
    assert "Repo scope: app, api" in text
    assert "- api: worktree at .worktrees/api" in text
    assert "Spec context: mode=linked | provider=openspec | status=ambiguous" in text
    assert "Spec candidates: openspec/changes/runtime-a; openspec/changes/runtime-b" in text
    assert "Resolve explicitly:" in text


def test_unrelated_preflight_does_not_use_concise_injection():
    preflight = {
        "found": True,
        "decision": "routing_only",
        "routing": {"classification": "likely-unrelated"},
        "task": {"slug": "runtime-cleanup", "binding_role": "writer"},
    }

    assert not subagent_preflight_should_inject_concise(preflight)
