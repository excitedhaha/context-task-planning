#!/usr/bin/env python3

import json

from constants import SWITCH_CUES
from spec_context import normalize_spec_context
from task_text import extract_terms, looks_complex, looks_like_followup


def task_signature_terms(task: dict) -> set[str]:
    spec_context = normalize_spec_context(task.get("spec_context"))
    parts = [
        task.get("slug", ""),
        task.get("title", ""),
        task.get("goal", ""),
        task.get("current_phase", ""),
        task.get("next_action", ""),
    ]
    parts.extend(task.get("blockers", []))
    parts.extend(task.get("non_goals", []))
    parts.extend(task.get("acceptance_criteria", []))
    parts.extend(task.get("edge_cases", []))
    parts.extend(task.get("open_questions", []))
    parts.append(spec_context.get("primary_ref", ""))
    parts.extend(spec_context.get("artifact_refs", []))
    parts.extend(spec_context.get("summary", []))
    for phase in task.get("phases", []):
        if not isinstance(phase, dict):
            continue
        parts.append(phase.get("id", ""))
        parts.append(phase.get("title", ""))
    return extract_terms("\n".join(str(part) for part in parts if part))


def switch_cues(prompt: str) -> list[str]:
    lowered = prompt.lower()
    hits = []
    for cue in SWITCH_CUES:
        if cue in lowered:
            hits.append(cue)
    return hits


def recommendation_for(classification: str) -> str:
    if classification == "related":
        return "continue-current-task"
    if classification == "likely-unrelated":
        return "ask-continue-switch-or-new-task"
    if classification == "no-active-task":
        return "resume-or-init-task"
    if classification == "empty-prompt":
        return "ignore"
    return "confirm-before-mixing-work"


def classify_drift(prompt: str, task: dict) -> dict:
    prompt = prompt.strip()
    if not prompt:
        classification = "empty-prompt"
        return {
            "classification": classification,
            "recommendation": recommendation_for(classification),
            "matched_terms": [],
            "switch_cues": [],
            "complex_prompt": False,
            "followup_prompt": False,
            "task": task,
        }

    if not task["found"]:
        classification = "no-active-task"
        return {
            "classification": classification,
            "recommendation": recommendation_for(classification),
            "matched_terms": [],
            "switch_cues": switch_cues(prompt),
            "complex_prompt": looks_complex(prompt),
            "followup_prompt": looks_like_followup(prompt),
            "task": task,
        }

    followup = looks_like_followup(prompt)
    complex_prompt = looks_complex(prompt)
    prompt_terms = extract_terms(prompt)
    signature_terms = task_signature_terms(task)
    matched_terms = sorted(prompt_terms & signature_terms)
    cue_hits = switch_cues(prompt)
    strong_match = any(
        "/" in term or "." in term or "-" in term or len(term) >= 8
        for term in matched_terms
    )

    if followup:
        classification = "related"
    elif strong_match or len(matched_terms) >= 2:
        classification = "related"
    elif cue_hits and len(matched_terms) <= 1:
        classification = "likely-unrelated"
    elif len(matched_terms) == 1 and not complex_prompt:
        classification = "related"
    else:
        classification = "unclear"

    return {
        "classification": classification,
        "recommendation": recommendation_for(classification),
        "matched_terms": matched_terms,
        "switch_cues": cue_hits,
        "complex_prompt": complex_prompt,
        "followup_prompt": followup,
        "task": task,
    }


def compact_drift(result: dict) -> str:
    task = result["task"]
    slug = task.get("slug") or "(none)"
    source = task.get("selection_source") or "none"
    matched = (
        ",".join(result["matched_terms"][:3]) if result["matched_terms"] else "none"
    )
    return (
        f"classification={result['classification']} task={slug} "
        f"source={source} matched={matched}"
    )


def print_drift(result: dict, as_json: bool, compact: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if compact:
        print(compact_drift(result))
        return

    task = result["task"]
    print(f"[context-task-planning] Drift check: {result['classification']}")
    print(f"[context-task-planning] Recommendation: {result['recommendation']}")
    if task.get("found"):
        print(
            f"[context-task-planning] Task: {task['slug']} "
            f"(source={task['selection_source']})"
        )
    else:
        print("[context-task-planning] Task: (none)")

    matched_terms = result["matched_terms"]
    if matched_terms:
        print(f"[context-task-planning] Shared terms: {', '.join(matched_terms)}")
    else:
        print("[context-task-planning] Shared terms: none")

    if result["switch_cues"]:
        print(
            f"[context-task-planning] Switch cues: {', '.join(result['switch_cues'])}"
        )
    else:
        print("[context-task-planning] Switch cues: none")

    print(
        "[context-task-planning] Prompt flags: "
        f"complex={str(result['complex_prompt']).lower()} "
        f"followup={str(result['followup_prompt']).lower()}"
    )
