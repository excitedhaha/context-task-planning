#!/usr/bin/env python3

import json

from constants import (
    DELEGATE_RECOMMEND_ARTIFACT_CUES,
    DELEGATE_RECOMMEND_MULTI_CUES,
    DELEGATE_RECOMMEND_SESSION_CUES,
    DELEGATE_REQUIRED_CLOSEOUT_CUES,
    DELEGATE_REQUIRED_CONTEXT_CUES,
    DELEGATE_REQUIRED_LIFECYCLE_CUES,
    ROLE_OBSERVER,
    ROLE_WRITER,
)
from spec_context import (
    normalize_spec_context,
    spec_context_candidate_refs,
    spec_context_linked_artifact_refs,
    spec_context_resolution_hint,
    spec_context_summary_text,
)
from task_drift import classify_drift
from task_text import (
    delegate_kind_for_text,
    nonempty_text_list,
    prepare_delegate_command,
    text_matches_any,
    unique_strings,
)


def repo_entries_for_task(task: dict) -> list[dict]:
    entries = []
    for binding in task.get("repo_bindings", []):
        repo_id = str(binding.get("repo_id") or "").strip()
        if not repo_id:
            continue
        binding_mode = "worktree" if binding.get("mode") == "worktree" else "shared"
        repo_path = str(binding.get("repo_path") or ".")
        checkout_path = str(binding.get("checkout_path") or repo_path or ".")
        entries.append(
            {
                "id": repo_id,
                "path": repo_path,
                "binding_mode": binding_mode,
                "checkout_path": checkout_path,
                "branch": str(binding.get("branch") or ""),
                "base_branch": str(binding.get("base_branch") or ""),
                "write_policy": "prefer_isolated"
                if binding_mode == "worktree"
                else "allowed",
            }
        )
    return entries


def repo_scope_for_payload(task: dict, repos: list[dict]) -> list[str]:
    scope = [
        str(repo_id).strip()
        for repo_id in task.get("repo_scope", [])
        if str(repo_id).strip()
    ]
    if scope:
        return scope
    return [repo["id"] for repo in repos if repo.get("id")]


def repo_summary_text(repos: list[dict]) -> str:
    if not repos:
        return ""
    return "; ".join(
        f"{repo['id']} {repo['binding_mode']} at {repo['checkout_path']}"
        for repo in repos
        if repo.get("id")
    )


def preflight_binding_role(task: dict) -> str:
    role = str(task.get("binding_role") or "").strip()
    if role in {ROLE_WRITER, ROLE_OBSERVER}:
        return role
    return ROLE_WRITER if task.get("found") else ""


def delegate_analysis_for_text(text: str, task: dict) -> dict:
    normalized = " ".join(text.lower().split())
    kind = delegate_kind_for_text(normalized) or ""
    recommended_reasons = []
    required_reasons = []

    if kind:
        recommended_reasons.append(f"bounded {kind} work")
    if text_matches_any(normalized, DELEGATE_RECOMMEND_SESSION_CUES):
        recommended_reasons.append("work may outlive the current session")
    if text_matches_any(normalized, DELEGATE_RECOMMEND_ARTIFACT_CUES):
        recommended_reasons.append("durable artifacts would help")
    if text_matches_any(normalized, DELEGATE_RECOMMEND_MULTI_CUES):
        recommended_reasons.append(
            "multiple sibling side quests may need explicit tracking"
        )

    if task.get("binding_role") == ROLE_OBSERVER:
        required_reasons.append("current session is observe-only")
    if text_matches_any(normalized, DELEGATE_REQUIRED_CLOSEOUT_CUES):
        required_reasons.append("side work must block done or archive")
    if text_matches_any(normalized, DELEGATE_REQUIRED_LIFECYCLE_CUES):
        required_reasons.append("side work needs durable lifecycle states")
    if text_matches_any(normalized, DELEGATE_REQUIRED_CONTEXT_CUES):
        required_reasons.append("side work must survive context loss before promotion")

    required_reasons = unique_strings(required_reasons)
    recommended_reasons = unique_strings(recommended_reasons)
    command_kind = kind or ("other" if required_reasons or recommended_reasons else "")
    return {
        "kind": command_kind,
        "recommended": bool(recommended_reasons) and not required_reasons,
        "required": bool(required_reasons),
        "recommended_reasons": recommended_reasons,
        "required_reasons": required_reasons,
        "reason": "; ".join(required_reasons or recommended_reasons),
        "command": prepare_delegate_command(text, command_kind) if command_kind else "",
    }


def prompt_prefix_for_preflight(
    task: dict, routing: dict, repos: list[dict], delegate: dict
) -> str:
    role = preflight_binding_role(task) or "unbound"
    classification = str(routing.get("classification") or "")
    primary_repo = str(task.get("primary_repo") or "") or (
        repos[0]["id"] if repos else ""
    )
    repo_scope = repo_scope_for_payload(task, repos)
    lines = [
        f"[context-task-planning] Current task: {task.get('slug') or '(none)'} | role: {role} | routing: {routing.get('classification') or '-'}",
        f"Primary repo: {primary_repo or '(none)'}",
        f"Repo scope: {', '.join(repo_scope) if repo_scope else '(none)'}",
        "Repo/worktree bindings:",
    ]
    if classification == "unclear":
        lines.insert(
            1,
            "Heuristic task fit is unclear. Use the surrounding conversation and current task goal to decide whether this subagent request belongs here; if not, report a routing mismatch instead of continuing.",
        )
    else:
        lines.insert(
            1,
            "Treat this subagent request as part of the current task only. Do not silently broaden scope.",
        )
    for repo in repos:
        lines.append(
            f"- {repo['id']}: {repo['binding_mode']} at {repo['checkout_path']}"
        )
    spec_context = normalize_spec_context(task.get("spec_context"))
    if spec_context.get("provider") != "none" or spec_context.get("status") != "none":
        lines.append(f"Spec context: {spec_context_summary_text(spec_context)}")
        if spec_context.get("primary_ref"):
            lines.append(f"Primary spec ref: {spec_context.get('primary_ref')}")
        candidate_refs = spec_context_candidate_refs(spec_context)
        if candidate_refs:
            lines.append("Spec candidates: " + "; ".join(candidate_refs[:3]))
            hint = spec_context_resolution_hint(task.get("slug", ""), spec_context)
            if hint:
                lines.append(f"Resolve explicitly: {hint}")
            lines.append(
                "If this subagent needs an authoritative spec ref, resolve one explicitly first. "
                "Exploratory work may reference these as non-authoritative candidates."
            )
        artifact_refs = spec_context_linked_artifact_refs(spec_context)
        if artifact_refs:
            lines.append("Linked spec refs: " + "; ".join(artifact_refs[:3]))
    lines.append(
        "If repo ownership or task fit becomes unclear, report that back instead of switching tasks implicitly."
    )
    if delegate.get("recommended") and delegate.get("kind"):
        lines.append(
            f"Delegate recommended: this looks like bounded {delegate['kind']} work and may benefit from a durable lane."
        )
        if delegate.get("command"):
            lines.append(f"Optional command: {delegate['command']}")
    return "\n".join(lines)


def build_subagent_preflight_result(
    task: dict,
    host: str,
    task_text: str,
    tool_name: str,
) -> dict:
    routing = classify_drift(task_text, task)
    repos = repo_entries_for_task(task)
    repo_scope = repo_scope_for_payload(task, repos)
    primary_repo = str(task.get("primary_repo") or "") or (
        repos[0]["id"] if repos else ""
    )
    delegate = delegate_analysis_for_text(task_text, task)
    binding_role = preflight_binding_role(task)
    normalized_host = (
        host if host in {"claude", "opencode", "codex", "generic"} else "generic"
    )
    normalized_tool = tool_name or "Task"

    decision = "routing_only"
    decision_reason = ""
    operator_message = ""
    prompt_prefix = ""
    classification = routing.get("classification") or ""

    if normalized_tool != "Task":
        decision_reason = "P0 preflight only injects payloads for native Task launches"
        operator_message = "[context-task-planning] Native subagent preflight is only active for `Task` launches in P0."
    elif classification == "empty-prompt":
        decision_reason = "empty task text"
        operator_message = "[context-task-planning] Task text is empty, so no canonical repo/worktree payload will be injected."
    elif classification == "no-active-task":
        decision_reason = "no active task"
        operator_message = "[context-task-planning] No active task is resolved, so there is no current task payload to inject before launching a subagent."
    elif classification == "likely-unrelated":
        decision_reason = "route heuristic is likely-unrelated"
        operator_message = (
            f"[context-task-planning] Route evidence for this Task request: the lightweight heuristic is `likely-unrelated` for current task `{task.get('slug') or '(none)'}`. "
            "Use the surrounding conversation and task goal to decide whether to continue the current task, switch tasks, or initialize a new task before launching a subagent."
        )
    elif not repos:
        decision_reason = "no meaningful repo/worktree context exists"
        operator_message = "[context-task-planning] The current task does not expose meaningful repo/worktree bindings yet, so there is no canonical payload to inject."
    elif delegate.get("required"):
        decision = "delegate_required"
        decision_reason = delegate.get("reason") or "delegate is required"
        operator_message = "[context-task-planning] Delegate required: do not treat this side work as a free-form native subagent task under the current session."
        if delegate.get("command"):
            operator_message += (
                f" Create or reuse a delegate lane first: {delegate['command']}"
            )
    elif delegate.get("recommended"):
        decision = "payload_plus_delegate_recommended"
        decision_reason = (
            delegate.get("reason")
            or (
                "heuristic-unclear request with meaningful repo context and a bounded side-work pattern"
                if classification == "unclear"
                else "task-related request with meaningful repo context and a bounded side-work pattern"
            )
        )
        prompt_prefix = prompt_prefix_for_preflight(task, routing, repos, delegate)
    else:
        decision = "payload_only"
        decision_reason = (
            "heuristic-unclear request with meaningful repo/worktree context for LLM route judgment"
            if classification == "unclear"
            else "task-related request with meaningful repo/worktree context"
        )
        prompt_prefix = prompt_prefix_for_preflight(task, routing, repos, delegate)

    return {
        "found": bool(task.get("found")),
        "host": normalized_host,
        "tool_name": normalized_tool,
        "decision": decision,
        "decision_reason": decision_reason,
        "routing": {
            "classification": classification,
            "recommendation": routing.get("recommendation") or "",
        },
        "task": {
            "slug": str(task.get("slug") or ""),
            "status": str(task.get("status") or ""),
            "mode": str(task.get("mode") or ""),
            "current_phase": str(task.get("current_phase") or ""),
            "spec_context": normalize_spec_context(task.get("spec_context")),
            "spec_candidate_refs": nonempty_text_list(task.get("spec_candidate_refs")),
            "spec_resolution_hint": str(task.get("spec_resolution_hint") or ""),
            "spec_resolution_commands": nonempty_text_list(
                task.get("spec_resolution_commands")
            ),
            "binding_role": binding_role,
            "writer_display": str(task.get("writer_display") or ""),
            "observer_count": int(task.get("observer_count") or 0),
        },
        "repo_context": {
            "primary_repo": primary_repo,
            "repo_scope": repo_scope,
            "repo_summary": repo_summary_text(repos),
            "repos": repos,
        },
        "delegate": {
            "kind": str(delegate.get("kind") or ""),
            "recommended": bool(delegate.get("recommended")),
            "required": bool(delegate.get("required")),
            "reason": str(delegate.get("reason") or ""),
            "command": str(delegate.get("command") or ""),
        },
        "prompt_prefix": prompt_prefix,
        "operator_message": operator_message,
    }


def subagent_preflight_text(result: dict) -> str:
    sections = []
    prompt_prefix = str(result.get("prompt_prefix") or "").strip()
    operator_message = str(result.get("operator_message") or "").strip()
    if prompt_prefix:
        sections.append(prompt_prefix)
    if operator_message:
        sections.append(operator_message)
    return "\n\n".join(section for section in sections if section)


def compact_subagent_preflight(result: dict) -> str:
    task = result.get("task", {})
    delegate = result.get("delegate", {})
    if delegate.get("required"):
        delegate_state = "required"
    elif delegate.get("recommended"):
        delegate_state = "recommended"
    else:
        delegate_state = "none"
    return (
        f"decision={result.get('decision') or 'routing_only'} "
        f"task={task.get('slug') or '(none)'} "
        f"routing={result.get('routing', {}).get('classification') or '-'} "
        f"delegate={delegate_state}"
    )


def print_subagent_preflight(
    result: dict, as_json: bool, as_text: bool, compact: bool
) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if compact:
        print(compact_subagent_preflight(result))
        return

    if as_text:
        text = subagent_preflight_text(result)
        if text:
            print(text)
        return

    print(
        "[context-task-planning] Subagent preflight: "
        f"decision={result.get('decision') or 'routing_only'} "
        f"host={result.get('host') or 'generic'} tool={result.get('tool_name') or 'Task'}"
    )
    print(
        f"[context-task-planning] Reason: {result.get('decision_reason') or '(none)'}"
    )
    routing = result.get("routing", {})
    print(
        "[context-task-planning] Routing: "
        f"{routing.get('classification') or '-'} -> {routing.get('recommendation') or '-'}"
    )
    task = result.get("task", {})
    print(
        "[context-task-planning] Task: "
        f"{task.get('slug') or '(none)'} role={task.get('binding_role') or '-'}"
    )
    repo_context = result.get("repo_context", {})
    print(
        "[context-task-planning] Repo context: "
        f"primary={repo_context.get('primary_repo') or '(none)'} "
        f"scope={', '.join(repo_context.get('repo_scope') or []) or '(none)'}"
    )
    text = subagent_preflight_text(result)
    if text:
        print(text)
