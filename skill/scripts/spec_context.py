#!/usr/bin/env python3

import shlex
from pathlib import Path

from constants import SPEC_CONTEXT_MODES, SPEC_CONTEXT_PROVIDERS, SPEC_CONTEXT_STATUSES
from repo_registry import normalize_repo_id, relative_to_workspace, resolve_path_in_workspace
from task_text import extract_terms, nonempty_text_list


def normalize_spec_context(raw: object) -> dict:
    payload = raw if isinstance(raw, dict) else {}

    mode = str(payload.get("mode") or "embedded").strip()
    if mode not in SPEC_CONTEXT_MODES:
        mode = "embedded"

    provider = str(payload.get("provider") or "none").strip()
    if provider not in SPEC_CONTEXT_PROVIDERS:
        provider = "none"

    status = str(payload.get("status") or "none").strip()
    if status not in SPEC_CONTEXT_STATUSES:
        status = "none"

    return {
        "mode": mode,
        "provider": provider,
        "status": status,
        "primary_ref": str(payload.get("primary_ref") or "").strip(),
        "artifact_refs": nonempty_text_list(payload.get("artifact_refs")),
        "summary": nonempty_text_list(payload.get("summary")),
    }


def spec_context_has_explicit_link(spec_context: dict) -> bool:
    normalized = normalize_spec_context(spec_context)
    return bool(
        normalized.get("primary_ref")
        or normalized.get("artifact_refs")
        or normalized.get("provider") != "none"
        or normalized.get("status") != "none"
        or normalized.get("mode") in {"linked", "none"}
    )


def repo_bindings_for_detection(
    workspace_root: Path, repo_bindings: list[dict] | None
) -> list[dict]:
    bindings = []
    seen = set()
    for binding in repo_bindings or []:
        checkout_path = (
            str(binding.get("checkout_path") or binding.get("repo_path") or ".").strip()
            or "."
        )
        checkout_absolute = resolve_path_in_workspace(workspace_root, checkout_path)
        key = str(checkout_absolute)
        if key in seen or not checkout_absolute.exists():
            continue
        seen.add(key)
        bindings.append(
            {
                "repo_id": str(binding.get("repo_id") or "").strip(),
                "checkout_path": checkout_path,
                "checkout_absolute": checkout_absolute,
            }
        )

    if bindings:
        return bindings

    return [
        {
            "repo_id": normalize_repo_id(workspace_root.name) or "workspace",
            "checkout_path": ".",
            "checkout_absolute": workspace_root.resolve(),
        }
    ]


def task_terms_for_provider_detection(state: dict) -> set[str]:
    parts = [
        state.get("slug", ""),
        state.get("title", ""),
        state.get("goal", ""),
        state.get("next_action", ""),
    ]
    parts.extend(nonempty_text_list(state.get("non_goals")))
    parts.extend(nonempty_text_list(state.get("acceptance_criteria")))
    parts.extend(nonempty_text_list(state.get("edge_cases")))
    parts.extend(nonempty_text_list(state.get("open_questions")))
    return extract_terms("\n".join(str(part) for part in parts if part))


def exact_match_tokens_for_provider_detection(state: dict) -> list[str]:
    candidates = []
    for value in [state.get("slug", ""), state.get("title", "")]:
        token = normalize_repo_id(str(value or ""))
        if token:
            candidates.append(token)
    return nonempty_text_list(candidates)


def openspec_ref_text(
    workspace_root: Path,
    binding: dict,
    artifact_path: Path,
    repo_binding_count: int,
) -> str:
    relative_path = relative_to_workspace(workspace_root, artifact_path)
    repo_id = str(binding.get("repo_id") or "").strip()
    if repo_binding_count > 1 and repo_id:
        return f"{repo_id}:{relative_path}"
    return relative_path


def openspec_artifact_refs(
    workspace_root: Path,
    binding: dict,
    candidate_dir: Path,
    repo_binding_count: int,
    limit: int = 4,
) -> list[str]:
    priority_files = []
    for name in ["proposal.md", "design.md", "tasks.md", "spec.md", "readme.md"]:
        candidate = candidate_dir / name
        if candidate.is_file():
            priority_files.append(candidate)

    markdown_files = list(priority_files)
    for entry in sorted(candidate_dir.rglob("*.md")):
        if entry in markdown_files:
            continue
        markdown_files.append(entry)
        if len(markdown_files) >= limit:
            break

    return [
        openspec_ref_text(workspace_root, binding, path, repo_binding_count)
        for path in markdown_files[:limit]
    ]


def openspec_change_candidates(
    workspace_root: Path,
    binding: dict,
    openspec_root: Path,
    repo_binding_count: int,
) -> list[dict]:
    changes_dir = openspec_root / "changes"
    if not changes_dir.is_dir():
        return []

    candidates = []
    for entry in sorted(changes_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        candidates.append(
            {
                "kind": "change",
                "name": entry.name,
                "primary_ref": openspec_ref_text(
                    workspace_root, binding, entry, repo_binding_count
                ),
                "artifact_refs": openspec_artifact_refs(
                    workspace_root, binding, entry, repo_binding_count
                ),
            }
        )
    return candidates


def openspec_spec_candidates(
    workspace_root: Path,
    binding: dict,
    openspec_root: Path,
    repo_binding_count: int,
) -> list[dict]:
    specs_dir = openspec_root / "specs"
    if not specs_dir.is_dir():
        return []

    directories = []
    seen = set()
    for entry in sorted(specs_dir.rglob("spec.md")):
        if not entry.is_file():
            continue
        candidate_dir = entry.parent
        key = str(candidate_dir)
        if key in seen:
            continue
        seen.add(key)
        directories.append(candidate_dir)

    candidates = []
    for entry in directories:
        name = relative_to_workspace(workspace_root, entry).split("/")[-1]
        candidates.append(
            {
                "kind": "spec",
                "name": name,
                "primary_ref": openspec_ref_text(
                    workspace_root, binding, entry, repo_binding_count
                ),
                "artifact_refs": openspec_artifact_refs(
                    workspace_root, binding, entry, repo_binding_count
                ),
            }
        )
    return candidates


def scored_openspec_candidates(state: dict, candidates: list[dict]) -> list[dict]:
    task_terms = task_terms_for_provider_detection(state)
    exact_tokens = exact_match_tokens_for_provider_detection(state)
    scored = []
    for candidate in candidates:
        haystack = "\n".join(
            [
                candidate.get("kind", ""),
                candidate.get("name", ""),
                candidate.get("primary_ref", ""),
            ]
            + list(candidate.get("artifact_refs") or [])
        )
        candidate_terms = extract_terms(haystack)
        primary_ref = str(candidate.get("primary_ref") or "").lower()
        exact_match = any(token and token in primary_ref for token in exact_tokens)
        scored.append(
            {
                **candidate,
                "score": len(task_terms & candidate_terms),
                "exact_match": exact_match,
            }
        )

    scored.sort(
        key=lambda item: (
            1 if item.get("exact_match") else 0,
            int(item.get("score") or 0),
            1 if item.get("kind") == "change" else 0,
            item.get("primary_ref") or "",
        ),
        reverse=True,
    )
    return scored


def choose_openspec_candidate(scored_candidates: list[dict]) -> dict | None:
    if not scored_candidates:
        return None
    if len(scored_candidates) == 1:
        return scored_candidates[0]

    top = scored_candidates[0]
    second = scored_candidates[1]
    if top.get("exact_match") and not second.get("exact_match"):
        return top
    if int(top.get("score") or 0) >= 2 and int(top.get("score") or 0) > int(
        second.get("score") or 0
    ):
        return top
    return None


def detect_openspec_spec_context(
    workspace_root: Path, state: dict, repo_bindings: list[dict]
) -> dict:
    normalized = normalize_spec_context(state.get("spec_context"))
    if spec_context_has_explicit_link(normalized):
        return normalized

    detection_bindings = repo_bindings_for_detection(workspace_root, repo_bindings)
    repo_binding_count = len(detection_bindings)
    detected_roots = []
    candidates = []
    for binding in detection_bindings:
        openspec_root = binding["checkout_absolute"] / "openspec"
        if not openspec_root.is_dir():
            continue
        detected_roots.append(
            openspec_ref_text(
                workspace_root, binding, openspec_root, repo_binding_count
            )
        )
        candidates.extend(
            openspec_change_candidates(
                workspace_root, binding, openspec_root, repo_binding_count
            )
        )
        candidates.extend(
            openspec_spec_candidates(
                workspace_root, binding, openspec_root, repo_binding_count
            )
        )

    if not detected_roots:
        return normalized

    scored_candidates = scored_openspec_candidates(state, candidates)
    chosen = choose_openspec_candidate(scored_candidates)
    if chosen is not None:
        summary = [
            f"Auto-linked to the clearest OpenSpec {chosen.get('kind') or 'artifact'} candidate under {detected_roots[0]}."
        ]
        return {
            "mode": "linked",
            "provider": "openspec",
            "status": "linked",
            "primary_ref": str(chosen.get("primary_ref") or ""),
            "artifact_refs": nonempty_text_list(chosen.get("artifact_refs") or []),
            "summary": summary,
        }

    if scored_candidates:
        summary = [
            f"Detected OpenSpec under {detected_roots[0]} but found multiple plausible artifact candidates.",
            "Record a manual link or narrow the task wording before treating one candidate as authoritative.",
        ]
        return {
            "mode": "linked",
            "provider": "openspec",
            "status": "ambiguous",
            "primary_ref": "",
            "artifact_refs": [
                str(item.get("primary_ref") or "") for item in scored_candidates[:4]
            ],
            "summary": summary,
        }

    return {
        "mode": "linked",
        "provider": "openspec",
        "status": "detected",
        "primary_ref": detected_roots[0],
        "artifact_refs": [],
        "summary": [
            f"Detected OpenSpec under {detected_roots[0]} but no clear change or spec artifact was found for this task."
        ],
    }


def brief_missing_fields_for_state(state: dict) -> list[str]:
    if not isinstance(state, dict):
        return [
            "goal",
            "non_goals",
            "acceptance_criteria",
            "constraints",
            "verify_commands",
        ]

    missing = []
    if not str(state.get("goal") or "").strip():
        missing.append("goal")
    if not nonempty_text_list(state.get("non_goals")):
        missing.append("non_goals")
    if not nonempty_text_list(state.get("acceptance_criteria")):
        missing.append("acceptance_criteria")
    if not nonempty_text_list(state.get("constraints")):
        missing.append("constraints")
    if not nonempty_text_list(state.get("verify_commands")):
        missing.append("verify_commands")
    return missing


def brief_quality_for_state(state: dict) -> str:
    missing = brief_missing_fields_for_state(state)
    if not missing:
        return "ready"
    if "goal" in missing:
        return "missing-goal"
    if missing == ["acceptance_criteria"]:
        return "needs-acceptance"
    return "needs-clarification"


def brief_summary_for_state(state: dict) -> str:
    acceptance_count = len(nonempty_text_list(state.get("acceptance_criteria")))
    edge_case_count = len(nonempty_text_list(state.get("edge_cases")))

    if acceptance_count == 0:
        summary = "acceptance missing"
    elif acceptance_count == 1:
        summary = "1 acceptance criterion recorded"
    else:
        summary = f"{acceptance_count} acceptance criteria recorded"

    if edge_case_count == 1:
        summary += "; 1 edge case recorded"
    elif edge_case_count > 1:
        summary += f"; {edge_case_count} edge cases recorded"

    return summary


def spec_context_summary_text(spec_context: dict) -> str:
    normalized = normalize_spec_context(spec_context)
    return (
        f"mode=`{normalized['mode']}` | provider=`{normalized['provider']}` | "
        f"status=`{normalized['status']}`"
    )


def spec_context_candidate_refs(spec_context: dict) -> list[str]:
    normalized = normalize_spec_context(spec_context)
    if normalized.get("status") != "ambiguous":
        return []
    return nonempty_text_list(normalized.get("artifact_refs"))


def spec_context_linked_artifact_refs(spec_context: dict) -> list[str]:
    normalized = normalize_spec_context(spec_context)
    if normalized.get("status") == "ambiguous":
        return []
    return nonempty_text_list(normalized.get("artifact_refs"))


def spec_context_resolution_hint(task_slug: str, spec_context: dict) -> str:
    candidate_refs = spec_context_candidate_refs(spec_context)
    if not task_slug or not candidate_refs:
        return ""
    return (
        "sh skill/scripts/set-task-spec-context.sh --task "
        f"{shlex.quote(task_slug)} --ref <chosen-spec-ref>"
    )


def spec_context_resolution_commands(
    task_slug: str, spec_context: dict, limit: int = 2
) -> list[str]:
    if not task_slug:
        return []

    commands = []
    for ref in spec_context_candidate_refs(spec_context)[:limit]:
        commands.append(
            "sh skill/scripts/set-task-spec-context.sh --task "
            f"{shlex.quote(task_slug)} --ref {shlex.quote(ref)}"
        )
    return commands
