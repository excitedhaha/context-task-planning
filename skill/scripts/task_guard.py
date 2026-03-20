#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
from pathlib import Path


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "around",
    "as",
    "at",
    "be",
    "before",
    "by",
    "current",
    "for",
    "from",
    "help",
    "into",
    "keep",
    "make",
    "mode",
    "next",
    "not",
    "phase",
    "plan",
    "planning",
    "project",
    "resume",
    "skill",
    "state",
    "status",
    "step",
    "steps",
    "task",
    "tasks",
    "that",
    "the",
    "then",
    "this",
    "use",
    "using",
    "with",
    "work",
    "workflow",
    "上下文",
    "一个",
    "一些",
    "不是",
    "任务",
    "当前",
    "工作",
    "然后",
    "继续",
    "问题",
}

FOLLOWUP_PHRASES = [
    "continue",
    "keep going",
    "go on",
    "same task",
    "follow up",
    "use the same task",
    "继续",
    "接着",
    "继续做",
    "按上面的改",
    "刚才那个",
    "同一个任务",
]

SWITCH_CUES = [
    "another task",
    "different task",
    "new task",
    "separately",
    "instead",
    "unrelated",
    "另外",
    "另一个",
    "顺便",
    "单独",
    "新任务",
    "换个",
]

COMPLEX_KEYWORDS = [
    "implement",
    "build",
    "create",
    "add",
    "refactor",
    "debug",
    "investigate",
    "migrate",
    "design",
    "plan",
    "optimize",
    "fix",
    "audit",
    "wire",
    "document",
    "实现",
    "设计",
    "重构",
    "排查",
    "调研",
    "迁移",
    "优化",
    "新增",
    "修复",
    "补充",
]

COMPLEX_SIGNALS = [
    "\n",
    "1.",
    "2.",
    "- ",
    "需要",
    "并且",
    "同时",
    "方案",
    "步骤",
]

SPECIAL_TOKEN_RE = re.compile(
    r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+"
    r"|[A-Za-z0-9_.-]+\.(?:sh|py|md|json|yaml|yml|toml|txt)"
    r"|\.[A-Za-z0-9_.-]+"
    r"|[A-Za-z0-9_.-]*-[A-Za-z0-9_.-]+"
)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]{2,}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="task_guard.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    current = subparsers.add_parser("current-task")
    current.add_argument("--task", default="")
    current.add_argument("--cwd", default="")
    current.add_argument("--json", action="store_true")
    current.add_argument("--compact", action="store_true")

    drift = subparsers.add_parser("check-drift")
    drift.add_argument("--task", default="")
    drift.add_argument("--cwd", default="")
    drift.add_argument("--prompt", default="")
    drift.add_argument("--json", action="store_true")
    drift.add_argument("--compact", action="store_true")

    return parser.parse_args()


def safe_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def resolve_start_dir(cwd: str) -> Path:
    candidate = cwd or os.getcwd()
    try:
        return Path(candidate).expanduser().resolve()
    except OSError:
        return Path(os.getcwd()).resolve()


def resolve_workspace_root(cwd: str) -> Path:
    start_dir = resolve_start_dir(cwd)
    candidate = start_dir
    git_root = None

    while True:
        if (candidate / ".planning").is_dir():
            return candidate

        if (candidate / ".git").exists() and git_root is None:
            git_root = candidate

        if candidate.parent == candidate:
            break
        candidate = candidate.parent

    return git_root or start_dir


def load_task_state(plan_dir: Path) -> dict:
    state = safe_json(plan_dir / "state.json")
    if state:
        return state
    return {"slug": plan_dir.name, "title": plan_dir.name}


def status_of(plan_dir: Path) -> str:
    return load_task_state(plan_dir).get("status", "unknown")


def auto_selectable(plan_dir: Path) -> bool:
    return status_of(plan_dir) not in {"archived", "paused", "done"}


def read_active_pointer(plan_root: Path) -> str:
    pointer = plan_root / ".active_task"
    if not pointer.exists():
        return ""
    try:
        return pointer.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def latest_task(plan_root: Path) -> Path | None:
    if not plan_root.is_dir():
        return None

    candidates = []
    for entry in plan_root.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if not auto_selectable(entry):
            continue
        candidates.append(entry)

    if not candidates:
        return None

    return max(candidates, key=lambda item: item.stat().st_mtime)


def resolve_task(cwd: str, requested_slug: str) -> dict:
    workspace_root = resolve_workspace_root(cwd)
    plan_root = workspace_root / ".planning"
    session_pin = os.environ.get("PLAN_TASK", "").strip()
    active_pointer = read_active_pointer(plan_root)
    plan_dir = None
    selection_source = "none"

    def candidate_for(slug: str, allow_archived: bool) -> Path | None:
        if not slug:
            return None
        candidate = plan_root / slug
        if not candidate.is_dir():
            return None
        if not allow_archived and not auto_selectable(candidate):
            return None
        return candidate

    for slug, source, allow_archived in [
        (requested_slug, "requested_slug", True),
        (session_pin, "session_pin", True),
        (active_pointer, "active_pointer", False),
    ]:
        plan_dir = candidate_for(slug, allow_archived)
        if plan_dir is not None:
            selection_source = source
            break

    if plan_dir is None:
        plan_dir = latest_task(plan_root)
        if plan_dir is not None:
            selection_source = "latest"

    state = load_task_state(plan_dir) if plan_dir is not None else {}
    delegation = state.get("delegation", {}) if isinstance(state, dict) else {}

    return {
        "found": plan_dir is not None,
        "selection_source": selection_source,
        "workspace_root": str(workspace_root),
        "plan_root": str(plan_root),
        "plan_dir": str(plan_dir) if plan_dir is not None else "",
        "requested_slug": requested_slug,
        "session_pin": session_pin,
        "active_pointer": active_pointer,
        "slug": state.get("slug", "") if isinstance(state, dict) else "",
        "title": state.get("title", "") if isinstance(state, dict) else "",
        "status": state.get("status", "") if isinstance(state, dict) else "",
        "mode": state.get("mode", "") if isinstance(state, dict) else "",
        "current_phase": state.get("current_phase", "")
        if isinstance(state, dict)
        else "",
        "next_action": state.get("next_action", "") if isinstance(state, dict) else "",
        "blockers": state.get("blockers", []) if isinstance(state, dict) else [],
        "active_delegates": delegation.get("active", [])
        if isinstance(delegation, dict)
        else [],
        "verify_commands": state.get("verify_commands", [])
        if isinstance(state, dict)
        else [],
        "goal": state.get("goal", "") if isinstance(state, dict) else "",
        "open_questions": state.get("open_questions", [])
        if isinstance(state, dict)
        else [],
        "phases": state.get("phases", []) if isinstance(state, dict) else [],
    }


def compact_current_task(task: dict) -> str:
    if not task["found"]:
        return "task=(none) source=none"
    return (
        f"task={task['slug']} status={task['status'] or '-'} mode={task['mode'] or '-'} "
        f"phase={task['current_phase'] or '-'} source={task['selection_source']}"
    )


def print_current_task(task: dict, as_json: bool, compact: bool) -> None:
    if as_json:
        print(json.dumps(task, ensure_ascii=False, indent=2))
        return

    if compact:
        print(compact_current_task(task))
        return

    print(f"[context-task-planning] Workspace: {task['workspace_root']}")
    print(f"[context-task-planning] Task root: {task['plan_root']}")
    print(
        f"[context-task-planning] Requested task: {task['requested_slug'] or '(none)'}"
    )
    print(
        f"[context-task-planning] Active pointer: {task['active_pointer'] or '(none)'}"
    )
    print(f"[context-task-planning] Session pin: {task['session_pin'] or '(none)'}")
    print(f"[context-task-planning] Selected source: {task['selection_source']}")

    if not task["found"]:
        print("[context-task-planning] No active task found.")
        return

    print(f"[context-task-planning] Task: {task['slug']}")
    print(f"[context-task-planning] Title: {task['title'] or '(unknown)'}")
    print(
        "[context-task-planning] Status: "
        f"{task['status'] or '(unknown)'} | Mode: {task['mode'] or '(unknown)'} | "
        f"Phase: {task['current_phase'] or '(unknown)'}"
    )
    print(
        f"[context-task-planning] Next action: {task['next_action'] or '(none recorded)'}"
    )

    blockers = task["blockers"]
    if blockers:
        print(f"[context-task-planning] Blockers: {'; '.join(blockers)}")
    else:
        print("[context-task-planning] Blockers: none")

    active_delegates = task["active_delegates"]
    if active_delegates:
        print(
            f"[context-task-planning] Active delegates: {', '.join(active_delegates)}"
        )
    else:
        print("[context-task-planning] Active delegates: none")


def looks_complex(prompt: str) -> bool:
    text = prompt.strip().lower()
    if not text:
        return False
    keyword_hit = any(word in text for word in COMPLEX_KEYWORDS)
    signal_hit = any(signal in prompt for signal in COMPLEX_SIGNALS)
    word_count = len(re.findall(r"\w+", prompt, flags=re.UNICODE))
    return keyword_hit and (signal_hit or word_count >= 8)


def looks_like_followup(prompt: str) -> bool:
    text = " ".join(prompt.lower().split())
    if text in {"continue", "继续", "go on", "接着", "按上面的改", "刚才那个"}:
        return True
    if len(re.findall(r"\w+", prompt, flags=re.UNICODE)) <= 3 and any(
        cue in text for cue in {"continue", "继续", "接着", "那个", "same"}
    ):
        return True
    return any(phrase in text for phrase in FOLLOWUP_PHRASES)


def expand_special_token(token: str) -> set[str]:
    cleaned = token.strip("`'\"()[]{}<>")
    values = {cleaned}
    if "/" in cleaned:
        values.add(cleaned.split("/")[-1])
    if "." in cleaned:
        values.add(cleaned.rsplit(".", 1)[0])
    for part in re.split(r"[/_.-]+", cleaned):
        if len(part) >= 2:
            values.add(part)
    return values


def normalize_term(term: str) -> str:
    return term.strip().lower()


def extract_terms(text: str) -> set[str]:
    terms = set()
    lowered = text.lower()

    for token in SPECIAL_TOKEN_RE.findall(text):
        for expanded in expand_special_token(normalize_term(token)):
            if expanded and expanded not in STOPWORDS and not expanded.isdigit():
                terms.add(expanded)

    for token in WORD_RE.findall(lowered):
        normalized = normalize_term(token)
        if normalized not in STOPWORDS and not normalized.isdigit():
            terms.add(normalized)

    for token in CHINESE_RE.findall(text):
        normalized = normalize_term(token)
        if normalized not in STOPWORDS:
            terms.add(normalized)

    return terms


def task_signature_terms(task: dict) -> set[str]:
    parts = [
        task.get("slug", ""),
        task.get("title", ""),
        task.get("goal", ""),
        task.get("current_phase", ""),
        task.get("next_action", ""),
    ]
    parts.extend(task.get("blockers", []))
    parts.extend(task.get("open_questions", []))
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


def main() -> None:
    args = parse_args()

    if args.command == "current-task":
        task = resolve_task(args.cwd, args.task)
        print_current_task(task, args.json, args.compact)
        return

    prompt = args.prompt or sys.stdin.read()
    task = resolve_task(args.cwd, args.task)
    result = classify_drift(prompt, task)
    print_drift(result, args.json, args.compact)


if __name__ == "__main__":
    main()
