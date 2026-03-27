#!/usr/bin/env python3

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import task_guard


ARTIFACT_SCHEMA_VERSION = "1.0.0"
ARTIFACT_DIRNAME = ".derived"
ARTIFACT_FILENAME = "context_compact.json"
PREFER_THRESHOLDS = {
    "progress_bytes": 6 * 1024,
    "progress_lines": 120,
    "findings_bytes": 4 * 1024,
    "findings_lines": 80,
    "task_plan_bytes": 4 * 1024,
    "task_plan_lines": 140,
    "delegate_count": 2,
}
REQUIRED_THRESHOLDS = {
    "spillover_bytes": 20 * 1024,
    "spillover_lines": 500,
    "section_bytes": 10 * 1024,
    "delegate_count": 4,
}
TERMINAL_DELEGATE_STATUSES = {"complete", "cancelled"}
PAYLOAD_LIMIT_PROFILES = {
    "compact_optional": {},
    "prefer_compact": {
        "findings": {"limit": 12, "head": 8, "tail": 4},
        "decision_log": {"limit": 8, "head": 3, "tail": 5},
        "verify_commands": {"limit": 8, "head": 3, "tail": 5},
        "constraints": {"limit": 8, "head": 8, "tail": 0},
        "definition_of_done": {"limit": 6, "head": 6, "tail": 0},
    },
    "compact_first_required": {
        "findings": {"limit": 8, "head": 6, "tail": 2},
        "decision_log": {"limit": 6, "head": 2, "tail": 4},
        "verify_commands": {"limit": 5, "head": 2, "tail": 3},
        "constraints": {"limit": 6, "head": 6, "tail": 0},
        "definition_of_done": {"limit": 4, "head": 4, "tail": 0},
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="compact_context.py")
    parser.add_argument("--task", default="")
    parser.add_argument("--cwd", default="")
    parser.add_argument("--session-key", default="")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def iso_mtime(path: Path) -> str:
    try:
        timestamp = path.stat().st_mtime
    except OSError:
        return ""
    return (
        datetime.fromtimestamp(timestamp, timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def rel_path(workspace_root: Path, path: Path) -> str:
    try:
        return task_guard.relative_to_workspace(workspace_root, path)
    except SystemExit:
        return str(path)


def count_lines(text: str) -> int:
    if not text:
        return 0
    return len(text.splitlines())


def slugify_heading(text: str) -> str:
    lowered = text.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    return lowered.strip("-") or "section"


def item_ref(text: str, source_ref: str) -> dict:
    return {"text": text, "source_ref": source_ref}


def state_item_refs(items: list[str], field_name: str) -> list[dict]:
    refs = []
    for index, item in enumerate(items):
        text = str(item).strip()
        if not text:
            continue
        refs.append(item_ref(text, f"state.json#/{field_name}/{index}"))
    return refs


def is_placeholder(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and stripped.startswith("[") and stripped.endswith("]")


def extract_level2_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = None
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = lines
            current = line[3:].strip()
            lines = []
            continue
        if current is not None:
            lines.append(line)
    if current is not None:
        sections[current] = lines
    return sections


def extract_level3_sections(lines: list[str]) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    current = None
    current_lines: list[str] = []
    for line in lines:
        if line.startswith("### "):
            if current is not None:
                sections.append((current, current_lines))
            current = line[4:].strip()
            current_lines = []
            continue
        if current is not None:
            current_lines.append(line)
    if current is not None:
        sections.append((current, current_lines))
    return sections


def bullet_items(lines: list[str], nested_only: bool = False) -> list[str]:
    items = []
    for line in lines:
        raw = line.rstrip()
        stripped = raw.strip()
        if not stripped:
            continue
        if nested_only and not re.match(r"^\s{2,}-\s+", raw):
            continue
        text = ""
        if stripped.startswith("- [ ] ") or stripped.startswith("- [x] "):
            text = stripped[6:].strip()
        elif stripped.startswith("- ") or stripped.startswith("* "):
            text = stripped[2:].strip()
        if not text or is_placeholder(text):
            continue
        items.append(text)
    return items


def markdown_table_rows(lines: list[str]) -> list[list[str]]:
    rows = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells:
            continue
        if all(cell and set(cell) <= {"-", ":"} for cell in cells):
            continue
        rows.append(cells)
    return rows


def meaningful_table_rows(lines: list[str]) -> list[list[str]]:
    rows = markdown_table_rows(lines)
    if not rows:
        return []
    body = rows[1:] if len(rows) > 1 else []
    return [row for row in body if any(cell for cell in row)]


def nonempty_meaningful_lines(lines: list[str]) -> list[str]:
    items = []
    for line in lines:
        stripped = line.strip()
        if not stripped or is_placeholder(stripped):
            continue
        items.append(stripped)
    return items


def collect_delegate_section_items(result_text: str, section_name: str) -> list[str]:
    current = None
    items: list[str] = []
    for line in result_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            current = stripped[3:]
            continue
        if current != section_name:
            continue
        if stripped.startswith("- "):
            candidate = stripped[2:].strip()
            if candidate and not is_placeholder(candidate):
                items.append(candidate)
        elif stripped and not stripped.startswith("#") and not is_placeholder(stripped):
            items.append(stripped)
    return items


def source_entry(workspace_root: Path, path: Path) -> dict:
    text = read_text(path)
    return {
        "path": rel_path(workspace_root, path),
        "sha1": sha1_text(text),
        "bytes": len(text),
        "lines": count_lines(text),
        "updated_at": iso_mtime(path),
    }


def delegate_descriptors(plan_dir: Path, workspace_root: Path) -> list[dict]:
    delegates_dir = plan_dir / "delegates"
    if not delegates_dir.is_dir():
        return []

    descriptors = []
    for entry in sorted(delegates_dir.iterdir(), key=lambda item: item.name):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        status_path = entry / "status.json"
        result_path = entry / "result.md"
        status = task_guard.safe_json(status_path)
        descriptors.append(
            {
                "dir": entry,
                "delegate_id": str(status.get("delegate_id") or entry.name),
                "status": status,
                "status_path": status_path,
                "result_path": result_path,
                "result_text": read_text(result_path),
                "status_ref": rel_path(workspace_root, status_path),
                "result_ref": rel_path(workspace_root, result_path),
            }
        )
    return descriptors


def current_sources(plan_dir: Path, workspace_root: Path) -> list[dict]:
    paths = [
        plan_dir / "state.json",
        plan_dir / "task_plan.md",
        plan_dir / "findings.md",
        plan_dir / "progress.md",
    ]
    for descriptor in delegate_descriptors(plan_dir, workspace_root):
        if descriptor["status_path"].exists():
            paths.append(descriptor["status_path"])
        if descriptor["result_path"].exists():
            paths.append(descriptor["result_path"])

    entries = []
    for path in paths:
        if not path.exists():
            continue
        entries.append(source_entry(workspace_root, path))
    entries.sort(key=lambda item: item["path"])
    return entries


def source_fingerprint(entries: list[dict]) -> str:
    stable = [
        {
            "path": entry["path"],
            "sha1": entry["sha1"],
            "bytes": entry["bytes"],
            "lines": entry["lines"],
        }
        for entry in entries
    ]
    return sha1_text(json.dumps(stable, sort_keys=True))


def artifact_path_for(plan_dir: Path) -> Path:
    return plan_dir / ARTIFACT_DIRNAME / ARTIFACT_FILENAME


def read_cached_artifact(path: Path) -> dict:
    payload = task_guard.safe_json(path)
    return payload if isinstance(payload, dict) else {}


def latest_session_summary(session_lines: list[str], source_ref: str) -> list[dict]:
    sessions = extract_level3_sections(session_lines)
    if not sessions:
        return []
    _, latest_lines = sessions[-1]
    allowed_labels = {"actions", "notes"}
    current_label = ""
    items = []
    for line in latest_lines:
        stripped = line.strip()
        if stripped.startswith("- ") and stripped.endswith(":"):
            current_label = stripped[2:-1].strip().lower()
            continue
        if current_label not in allowed_labels:
            continue
        if not re.match(r"^\s{2,}-\s+", line.rstrip()):
            continue
        text = line.strip()[2:].strip()
        if text and not is_placeholder(text):
            items.append(text)
    return [item_ref(text, source_ref) for text in items[:6]]


def payload_profile_name(required_reasons: list[str], prefer_reasons: list[str]) -> str:
    if required_reasons:
        return "compact_first_required"
    if prefer_reasons:
        return "prefer_compact"
    return "compact_optional"


def compact_window(
    items: list[dict], limit: int, head: int, tail: int
) -> tuple[list[dict], int]:
    if limit <= 0 or len(items) <= limit:
        return list(items), 0

    head = max(0, min(head, limit))
    tail = max(0, min(tail, limit - head))
    if head + tail > limit:
        tail = max(0, limit - head)

    kept = list(items[:head])
    if tail:
        tail_items = list(items[-tail:])
        seen = {id(item) for item in kept}
        for item in tail_items:
            if id(item) in seen:
                continue
            kept.append(item)
    return kept[:limit], max(0, len(items) - len(kept[:limit]))


def apply_list_limit(
    payload: dict,
    section_name: str,
    items: list[dict],
    rule: dict,
    source_ref: str,
    reason: str,
) -> list[dict]:
    kept, omitted_count = compact_window(
        items,
        int(rule.get("limit", 0) or 0),
        int(rule.get("head", 0) or 0),
        int(rule.get("tail", 0) or 0),
    )
    if omitted_count <= 0:
        return kept

    payload.setdefault("omitted", {})[f"{section_name}_overflow"] = {
        "count": omitted_count,
        "included": len(kept),
        "source_ref": source_ref,
        "reason": reason,
    }
    return kept


def apply_payload_limits(payload: dict, profile_name: str) -> None:
    rules = PAYLOAD_LIMIT_PROFILES.get(profile_name, {})
    if not rules:
        return

    distilled = payload.get("distilled", {})
    task = payload.get("task", {})

    if "findings" in rules:
        distilled["findings"] = apply_list_limit(
            payload,
            "findings",
            list(distilled.get("findings", [])),
            rules["findings"],
            "findings.md#distilled-findings",
            "Keep the compact view focused on the highest-signal findings and preserve the remainder by source reference.",
        )

    if "decision_log" in rules:
        distilled["decision_log"] = apply_list_limit(
            payload,
            "decision_log",
            list(distilled.get("decision_log", [])),
            rules["decision_log"],
            "task_plan.md#decision-log",
            "Keep the compact view focused on a small set of representative decision log entries.",
        )

    if "verify_commands" in rules:
        task["verify_commands"] = apply_list_limit(
            payload,
            "verify_commands",
            list(task.get("verify_commands", [])),
            rules["verify_commands"],
            "state.json#/verify_commands",
            "Keep the compact view focused on a short verification slice and preserve the full command matrix by source reference.",
        )

    if "constraints" in rules:
        distilled["constraints"] = apply_list_limit(
            payload,
            "constraints",
            list(distilled.get("constraints", [])),
            rules["constraints"],
            "state.json#/constraints",
            "Keep the compact view focused on the highest-signal constraints and preserve the full list by source reference.",
        )

    if "definition_of_done" in rules:
        distilled["definition_of_done"] = apply_list_limit(
            payload,
            "definition_of_done",
            list(distilled.get("definition_of_done", [])),
            rules["definition_of_done"],
            "task_plan.md#definition-of-done",
            "Keep the compact view focused on the most actionable done criteria and preserve the full list by source reference.",
        )


def decision_log_entries(lines: list[str], source_ref: str) -> list[dict]:
    rows = meaningful_table_rows(lines)
    entries = []
    for row in rows:
        if len(row) < 2:
            continue
        decision = row[0].strip()
        rationale = row[1].strip()
        if not decision or not rationale:
            continue
        entries.append(
            {
                "decision": decision,
                "rationale": rationale,
                "source_ref": source_ref,
            }
        )
    return entries


def checkpoint_entries(lines: list[str], source_ref: str) -> list[dict]:
    rows = meaningful_table_rows(lines)
    entries = []
    for row in rows[-3:]:
        if len(row) < 3:
            continue
        entries.append(
            {
                "timestamp": row[0].strip(),
                "checkpoint": row[1].strip(),
                "next_action": row[2].strip(),
                "source_ref": source_ref,
            }
        )
    return entries


def verification_entries(lines: list[str], source_ref: str) -> list[dict]:
    rows = meaningful_table_rows(lines)
    entries = []
    for row in rows[-3:]:
        if len(row) < 4:
            continue
        entries.append(
            {
                "timestamp": row[0].strip(),
                "command": row[1].strip(),
                "result": row[2].strip(),
                "notes": row[3].strip(),
                "source_ref": source_ref,
            }
        )
    return entries


def delegate_compact_entries(descriptors: list[dict]) -> tuple[list[dict], int]:
    entries = []
    closed_count = 0
    for descriptor in descriptors:
        status = descriptor["status"]
        delegate_status = str(status.get("status") or "")
        promoted = list(status.get("promoted_findings") or [])
        include = delegate_status not in TERMINAL_DELEGATE_STATUSES or not promoted
        if not include:
            closed_count += 1
            continue
        summary = str(status.get("summary") or "").strip()
        recommended = collect_delegate_section_items(
            descriptor["result_text"], "Recommended Promotion"
        )[:3]
        risks = collect_delegate_section_items(descriptor["result_text"], "Open Risks")[
            :3
        ]
        entries.append(
            {
                "delegate_id": descriptor["delegate_id"],
                "kind": str(status.get("kind") or "other"),
                "status": delegate_status or "unknown",
                "summary": item_ref(summary, descriptor["status_ref"])
                if summary
                else None,
                "recommended_promotion": [
                    item_ref(text, f"{descriptor['result_ref']}#recommended-promotion")
                    for text in recommended
                ],
                "open_risks": [
                    item_ref(text, f"{descriptor['result_ref']}#open-risks")
                    for text in risks
                ],
                "source_refs": [descriptor["status_ref"], descriptor["result_ref"]],
            }
        )
    return entries, closed_count


def build_payload(task: dict) -> dict:
    workspace_root = Path(task["workspace_root"])
    plan_dir = Path(task["plan_dir"])
    state_path = plan_dir / "state.json"
    task_plan_path = plan_dir / "task_plan.md"
    findings_path = plan_dir / "findings.md"
    progress_path = plan_dir / "progress.md"
    artifact_path = artifact_path_for(plan_dir)

    state = task_guard.load_task_state(plan_dir)
    task_plan_text = read_text(task_plan_path)
    findings_text = read_text(findings_path)
    progress_text = read_text(progress_path)
    state_text = read_text(state_path)

    task_plan_sections = extract_level2_sections(task_plan_text)
    findings_sections = extract_level2_sections(findings_text)
    progress_sections = extract_level2_sections(progress_text)

    delegates = delegate_descriptors(plan_dir, workspace_root)
    active_delegate_entries, closed_delegate_count = delegate_compact_entries(delegates)
    unresolved_delegate_count = len(active_delegate_entries)

    raw_notes_lines = findings_sections.get("Raw Notes", [])
    external_inputs_lines = findings_sections.get("External Inputs", [])
    session_log_lines = progress_sections.get("Session Log", [])

    raw_notes_items = bullet_items(raw_notes_lines)
    external_inputs_items = bullet_items(external_inputs_lines)
    session_sections = extract_level3_sections(session_log_lines)
    older_session_count = max(0, len(session_sections) - 1)

    source_entries = current_sources(plan_dir, workspace_root)
    fingerprint = source_fingerprint(source_entries)

    task_plan_bytes = len(task_plan_text)
    findings_bytes = len(findings_text)
    progress_bytes = len(progress_text)
    state_bytes = len(state_text)
    delegate_bytes = sum(
        len(read_text(descriptor["status_path"])) + len(descriptor["result_text"])
        for descriptor in delegates
    )

    task_plan_lines = count_lines(task_plan_text)
    findings_lines = count_lines(findings_text)
    progress_lines = count_lines(progress_text)
    state_lines = count_lines(state_text)
    delegate_lines = sum(
        count_lines(read_text(descriptor["status_path"]))
        + count_lines(descriptor["result_text"])
        for descriptor in delegates
    )

    spillover_bytes = task_plan_bytes + findings_bytes + progress_bytes + delegate_bytes
    spillover_lines = task_plan_lines + findings_lines + progress_lines + delegate_lines

    prefer_reasons = []
    if progress_bytes >= PREFER_THRESHOLDS["progress_bytes"]:
        prefer_reasons.append(
            f"progress.md is {progress_bytes} bytes (>= {PREFER_THRESHOLDS['progress_bytes']})"
        )
    if progress_lines >= PREFER_THRESHOLDS["progress_lines"]:
        prefer_reasons.append(
            f"progress.md is {progress_lines} lines (>= {PREFER_THRESHOLDS['progress_lines']})"
        )
    if findings_bytes >= PREFER_THRESHOLDS["findings_bytes"]:
        prefer_reasons.append(
            f"findings.md is {findings_bytes} bytes (>= {PREFER_THRESHOLDS['findings_bytes']})"
        )
    if findings_lines >= PREFER_THRESHOLDS["findings_lines"]:
        prefer_reasons.append(
            f"findings.md is {findings_lines} lines (>= {PREFER_THRESHOLDS['findings_lines']})"
        )
    if task_plan_bytes >= PREFER_THRESHOLDS["task_plan_bytes"]:
        prefer_reasons.append(
            f"task_plan.md is {task_plan_bytes} bytes (>= {PREFER_THRESHOLDS['task_plan_bytes']})"
        )
    if task_plan_lines >= PREFER_THRESHOLDS["task_plan_lines"]:
        prefer_reasons.append(
            f"task_plan.md is {task_plan_lines} lines (>= {PREFER_THRESHOLDS['task_plan_lines']})"
        )
    if unresolved_delegate_count >= PREFER_THRESHOLDS["delegate_count"]:
        prefer_reasons.append(
            f"unresolved delegates = {unresolved_delegate_count} (>= {PREFER_THRESHOLDS['delegate_count']})"
        )
    if raw_notes_items:
        prefer_reasons.append(
            "Raw Notes contains material that should stay out of repeated reads"
        )
    if external_inputs_items:
        prefer_reasons.append(
            "External Inputs contains material that should stay out of repeated reads"
        )

    required_reasons = []
    if spillover_bytes >= REQUIRED_THRESHOLDS["spillover_bytes"]:
        required_reasons.append(
            f"spillover bytes = {spillover_bytes} (>= {REQUIRED_THRESHOLDS['spillover_bytes']})"
        )
    if spillover_lines >= REQUIRED_THRESHOLDS["spillover_lines"]:
        required_reasons.append(
            f"spillover lines = {spillover_lines} (>= {REQUIRED_THRESHOLDS['spillover_lines']})"
        )
    if (
        max(task_plan_bytes, findings_bytes, progress_bytes)
        >= REQUIRED_THRESHOLDS["section_bytes"]
    ):
        required_reasons.append(
            f"at least one markdown section is >= {REQUIRED_THRESHOLDS['section_bytes']} bytes"
        )
    if unresolved_delegate_count >= REQUIRED_THRESHOLDS["delegate_count"]:
        required_reasons.append(
            f"unresolved delegates = {unresolved_delegate_count} (>= {REQUIRED_THRESHOLDS['delegate_count']})"
        )

    tracked_paths = [entry["path"] for entry in source_entries]
    profile_name = payload_profile_name(required_reasons, prefer_reasons)

    payload = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "task_slug": str(state.get("slug") or plan_dir.name),
        "generated_at": task_guard.utc_now(),
        "artifact": {
            "path": rel_path(workspace_root, artifact_path),
            "persisted": False,
            "status": "generated-current",
        },
        "freshness": {
            "source_fingerprint": fingerprint,
            "tracked_paths": tracked_paths,
        },
        "read_policy": {
            "payload_profile": profile_name,
            "should_prefer_compact": bool(prefer_reasons or required_reasons),
            "compact_first_required": bool(required_reasons),
            "prefer_reasons": prefer_reasons,
            "compact_first_reasons": required_reasons,
            "metrics": {
                "state_bytes": state_bytes,
                "state_lines": state_lines,
                "task_plan_bytes": task_plan_bytes,
                "task_plan_lines": task_plan_lines,
                "findings_bytes": findings_bytes,
                "findings_lines": findings_lines,
                "progress_bytes": progress_bytes,
                "progress_lines": progress_lines,
                "delegate_bytes": delegate_bytes,
                "delegate_lines": delegate_lines,
                "spillover_bytes": spillover_bytes,
                "spillover_lines": spillover_lines,
                "unresolved_delegate_count": unresolved_delegate_count,
                "raw_notes_count": len(raw_notes_items),
                "external_inputs_count": len(external_inputs_items),
            },
            "thresholds": {
                "prefer_compact": PREFER_THRESHOLDS,
                "compact_first_required": REQUIRED_THRESHOLDS,
            },
        },
        "task": {
            "title": str(state.get("title") or plan_dir.name),
            "status": str(state.get("status") or "unknown"),
            "mode": str(state.get("mode") or "unknown"),
            "current_phase": str(state.get("current_phase") or "unknown"),
            "goal": str(state.get("goal") or ""),
            "next_action": str(state.get("next_action") or ""),
            "blockers": state_item_refs(list(state.get("blockers") or []), "blockers"),
            "verify_commands": state_item_refs(
                list(state.get("verify_commands") or []), "verify_commands"
            ),
            "latest_checkpoint": str(state.get("latest_checkpoint") or ""),
            "repo_scope": list(state.get("repo_scope") or []),
            "primary_repo": str(state.get("primary_repo") or ""),
        },
        "distilled": {
            "non_goals": state_item_refs(
                list(state.get("non_goals") or []), "non_goals"
            ),
            "constraints": state_item_refs(
                list(state.get("constraints") or []), "constraints"
            ),
            "open_questions": state_item_refs(
                list(state.get("open_questions") or []), "open_questions"
            ),
            "definition_of_done": [
                item_ref(text, "task_plan.md#definition-of-done")
                for text in bullet_items(
                    task_plan_sections.get("Definition of Done", [])
                )
            ],
            "decision_log": decision_log_entries(
                task_plan_sections.get("Decision Log", []), "task_plan.md#decision-log"
            ),
            "findings": [
                item_ref(text, "findings.md#distilled-findings")
                for text in bullet_items(
                    findings_sections.get("Distilled Findings", [])
                )
            ]
            + [
                item_ref(text, "findings.md#decisions-to-promote")
                for text in bullet_items(
                    findings_sections.get("Decisions To Promote", [])
                )
            ]
            + [
                item_ref(text, "findings.md#delegate-findings")
                for text in bullet_items(findings_sections.get("Delegate Findings", []))
            ],
            "latest_session": latest_session_summary(
                session_log_lines, "progress.md#session-log"
            ),
            "recent_checkpoints": checkpoint_entries(
                progress_sections.get("Checkpoints", []), "progress.md#checkpoints"
            ),
            "recent_verification": verification_entries(
                progress_sections.get("Verification Log", []),
                "progress.md#verification-log",
            ),
            "handoff_notes": [
                item_ref(text, "progress.md#handoff-notes")
                for text in bullet_items(progress_sections.get("Handoff Notes", []))
            ],
            "active_delegates": active_delegate_entries,
        },
        "omitted": {
            "raw_notes": {
                "count": len(raw_notes_items),
                "source_ref": "findings.md#raw-notes",
                "reason": "Keep temporary notes out of repeated recovery reads.",
            },
            "external_inputs": {
                "count": len(external_inputs_items),
                "source_ref": "findings.md#external-inputs",
                "reason": "Keep untrusted material out of repeated recovery reads.",
            },
            "older_sessions": {
                "count": older_session_count,
                "source_ref": "progress.md#session-log",
                "reason": "Prefer the latest session plus checkpoints for recovery.",
            },
            "closed_delegates": {
                "count": closed_delegate_count,
                "source_ref": rel_path(workspace_root, plan_dir / "delegates"),
                "reason": "Closed delegate lanes stay available in their own history.",
            },
        },
    }

    apply_payload_limits(payload, profile_name)

    compact_size = len(json.dumps(payload, ensure_ascii=False, indent=2))
    total_source_bytes = state_bytes + spillover_bytes
    reduction_ratio = 0.0
    if total_source_bytes > 0:
        reduction_ratio = round(1 - (compact_size / total_source_bytes), 3)
    payload["compression_estimate"] = {
        "compact_bytes": compact_size,
        "source_bytes": total_source_bytes,
        "estimated_reduction_ratio": reduction_ratio,
    }
    return payload


def persist_payload(payload: dict, plan_dir: Path) -> dict:
    artifact_path = artifact_path_for(plan_dir)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    payload = copy.deepcopy(payload)
    payload["artifact"]["persisted"] = True
    payload["artifact"]["status"] = "persisted-fresh"
    artifact_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def freshness_state(task: dict) -> tuple[Path, dict, dict, bool]:
    plan_dir = Path(task["plan_dir"])
    artifact_path = artifact_path_for(plan_dir)
    cached = read_cached_artifact(artifact_path) if artifact_path.exists() else {}
    current = build_payload(task)
    cached_fingerprint = str(
        cached.get("freshness", {}).get("source_fingerprint") or ""
    )
    current_fingerprint = str(
        current.get("freshness", {}).get("source_fingerprint") or ""
    )
    return (
        artifact_path,
        cached,
        current,
        bool(cached and cached_fingerprint == current_fingerprint),
    )


def render_text(payload: dict) -> str:
    task = payload.get("task", {})
    lines = [
        f"Task `{payload.get('task_slug')}` | status `{task.get('status')}` | mode `{task.get('mode')}` | phase `{task.get('current_phase')}`",
        f"Goal: {task.get('goal') or '(none recorded)'}",
        f"Next action: {task.get('next_action') or '(none recorded)'}",
    ]

    read_policy = payload.get("read_policy", {})
    if read_policy.get("compact_first_required"):
        lines.append("Compact policy: required first")
    elif read_policy.get("should_prefer_compact"):
        lines.append("Compact policy: preferred")
    else:
        lines.append("Compact policy: optional")

    reasons = list(read_policy.get("compact_first_reasons") or []) or list(
        read_policy.get("prefer_reasons") or []
    )
    if reasons:
        lines.append(f"Why: {reasons[0]}")

    blockers = [
        item.get("text") for item in task.get("blockers", []) if item.get("text")
    ]
    lines.append(f"Blockers: {'; '.join(blockers) if blockers else 'none'}")

    findings = payload.get("distilled", {}).get("findings", [])
    if findings:
        lines.append("Findings:")
        for item in findings[:5]:
            lines.append(f"- {item.get('text')}")

    latest_session = payload.get("distilled", {}).get("latest_session", [])
    if latest_session:
        lines.append("Latest session:")
        for item in latest_session[:4]:
            lines.append(f"- {item.get('text')}")

    checkpoints = payload.get("distilled", {}).get("recent_checkpoints", [])
    if checkpoints:
        lines.append("Recent checkpoints:")
        for item in checkpoints:
            lines.append(
                f"- {item.get('timestamp')}: {item.get('checkpoint')} -> {item.get('next_action')}"
            )

    delegates = payload.get("distilled", {}).get("active_delegates", [])
    if delegates:
        lines.append("Active delegates:")
        for item in delegates[:4]:
            summary = item.get("summary") or {}
            summary_text = summary.get("text") if isinstance(summary, dict) else ""
            suffix = f" | {summary_text}" if summary_text else ""
            lines.append(
                f"- {item.get('delegate_id')} ({item.get('kind')}, {item.get('status')}){suffix}"
            )

    omitted = payload.get("omitted", {})
    omitted_parts = []
    for key in ("raw_notes", "external_inputs", "older_sessions", "closed_delegates"):
        count = int(omitted.get(key, {}).get("count", 0) or 0)
        if count:
            omitted_parts.append(f"{key}={count}")
    if omitted_parts:
        lines.append("Omitted: " + ", ".join(omitted_parts))

    compression = payload.get("compression_estimate", {})
    if compression:
        lines.append(
            "Compression estimate: "
            f"{compression.get('compact_bytes', 0)} bytes vs {compression.get('source_bytes', 0)} bytes "
            f"(~{int(round(float(compression.get('estimated_reduction_ratio', 0)) * 100))}% smaller)"
        )

    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    task = task_guard.resolve_task(args.cwd, args.task, args.session_key)
    if not task.get("found"):
        raise SystemExit("[context-task-planning] No task found for compact context.")

    artifact_path, cached, current, is_fresh = freshness_state(task)

    if args.check:
        if not artifact_path.exists():
            print(
                f"missing artifact: {rel_path(Path(task['workspace_root']), artifact_path)}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        if not is_fresh:
            print(
                f"stale artifact: {rel_path(Path(task['workspace_root']), artifact_path)}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        print(
            f"fresh artifact: {rel_path(Path(task['workspace_root']), artifact_path)}",
            file=sys.stderr,
        )
        return

    if args.refresh:
        payload = persist_payload(current, Path(task["plan_dir"]))
    elif is_fresh:
        payload = copy.deepcopy(cached)
        payload.setdefault("artifact", {})
        payload["artifact"]["persisted"] = True
        payload["artifact"]["status"] = "fresh-cache"
    else:
        payload = current
        payload["artifact"]["persisted"] = False
        payload["artifact"]["status"] = "ephemeral-current"

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(render_text(payload))


if __name__ == "__main__":
    main()
