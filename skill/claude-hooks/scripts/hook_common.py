#!/usr/bin/env python3

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path


def read_hook_input():
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def skill_root() -> Path:
    return Path(__file__).resolve().parents[2]


TASK_GUARD_IMPORT_OK = False
try:
    scripts_dir = skill_root() / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from task_guard import classify_drift, resolve_task as resolve_guard_task  # type: ignore

    TASK_GUARD_IMPORT_OK = True
except ImportError:
    classify_drift = None  # type: ignore
    resolve_guard_task = None  # type: ignore


def host_skill_home(host: str = "claude") -> str:
    if host == "claude":
        plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
        if plugin_root:
            return str(Path(plugin_root) / "skill")
    if host == "codex":
        return "$HOME/.codex/skills/context-task-planning"
    if host == "opencode":
        return "$HOME/.config/opencode/skills/context-task-planning"
    if host == "trae":
        plugin_root = os.environ.get("COCO_PLUGIN_ROOT", "").strip()
        if plugin_root:
            return str(Path(plugin_root) / "skill")
        return "$HOME/.coco/skills/context-task-planning"
    return "$HOME/.claude/skills/context-task-planning"


def host_display_name(host: str = "claude") -> str:
    names = {
        "codex": "Codex",
        "opencode": "OpenCode",
        "claude": "Claude",
        "trae": "TraeCLI/Coco",
    }
    return names.get(host, "agent")


def installed_skill_command(script_name: str, host: str = "claude") -> str:
    return f'sh "{host_skill_home(host)}/scripts/{script_name}"'


def resolve_workspace_root(cwd: str | None = None) -> Path | None:
    script = skill_root() / "scripts" / "resolve-workspace-root.sh"
    try:
        result = subprocess.run(
            ["sh", str(script)],
            cwd=cwd or os.getcwd(),
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError:
        return None

    output = result.stdout.strip()
    return Path(output) if output else None


def find_named_string(value, names: set[str]) -> str:
    if isinstance(value, dict):
        for key in names:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        for nested in value.values():
            found = find_named_string(nested, names)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = find_named_string(item, names)
            if found:
                return found
    return ""


def qualify_session_key(host: str, raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    return f"{host}:{value}"


def session_key_from_payload(payload: dict, host: str = "claude") -> str:
    raw = find_named_string(
        payload,
        {
            "session_id",
            "sessionId",
            "sessionID",
            "conversation_id",
            "conversationId",
            "thread_id",
            "threadId",
            "chat_id",
            "chatId",
            "transcript_path",
            "transcriptPath",
        },
    )
    return qualify_session_key(host, raw)


def resolve_plan_dir(
    cwd: str | None = None, slug: str | None = None, session_key: str | None = None
) -> Path | None:
    script = skill_root() / "scripts" / "resolve-plan-dir.sh"
    command = ["sh", str(script)]
    if slug:
        command.append(slug)

    env = os.environ.copy()
    if session_key:
        env["PLAN_SESSION_KEY"] = session_key

    try:
        result = subprocess.run(
            command,
            cwd=cwd or os.getcwd(),
            check=True,
            text=True,
            capture_output=True,
            env=env,
        )
    except subprocess.CalledProcessError:
        return None

    output = result.stdout.strip()
    return Path(output) if output else None


def run_compact_sync(
    cwd: str | None = None, session_key: str | None = None, host: str = "claude"
) -> dict | None:
    script = skill_root() / "scripts" / "compact-sync.sh"
    command = ["sh", str(script), "--json", "--host", host]
    if session_key:
        command.extend(["--session-key", session_key])

    try:
        result = subprocess.run(
            command,
            cwd=cwd or os.getcwd(),
            check=False,
            text=True,
            capture_output=True,
        )
    except OSError:
        return None

    if result.returncode != 0:
        return None

    output = result.stdout.strip()
    if not output:
        return None

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return None


def compact_context_text(
    cwd: str | None = None, session_key: str | None = None
) -> str | None:
    script = skill_root() / "scripts" / "compact-context.sh"
    command = ["sh", str(script)]
    if session_key:
        command.extend(["--session-key", session_key])

    try:
        result = subprocess.run(
            command,
            cwd=cwd or os.getcwd(),
            check=False,
            text=True,
            capture_output=True,
        )
    except OSError:
        return None

    if result.returncode != 0:
        return None

    output = result.stdout.strip()
    return output or None


def task_tool_text(tool_input: dict) -> str:
    if not isinstance(tool_input, dict):
        return ""
    parts = []
    for key in ("description", "prompt", "command", "subagent_type"):
        value = str(tool_input.get(key, "")).strip()
        if value:
            parts.append(value)
    return " ".join(parts)


def subagent_preflight_result(
    task_text: str,
    cwd: str | None = None,
    session_key: str | None = None,
    host: str = "claude",
    tool_name: str = "Task",
    task_slug: str | None = None,
) -> dict | None:
    script = skill_root() / "scripts" / "subagent-preflight.sh"
    command = [
        "sh",
        str(script),
        "--json",
        "--host",
        host,
        "--tool-name",
        tool_name,
        "--task-text",
        task_text,
    ]
    if cwd:
        command.extend(["--cwd", cwd])
    if session_key:
        command.extend(["--session-key", session_key])
    if task_slug:
        command.extend(["--task", task_slug])

    try:
        result = subprocess.run(
            command,
            cwd=cwd or os.getcwd(),
            check=False,
            text=True,
            capture_output=True,
        )
    except OSError:
        return None

    if result.returncode != 0:
        return None

    output = result.stdout.strip()
    if not output:
        return None

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return None


def load_state(plan_dir: Path) -> dict:
    state_file = plan_dir / "state.json"
    if not state_file.exists():
        return {}

    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def workspace_has_planning(cwd: str | None = None) -> bool:
    root = resolve_workspace_root(cwd)
    return bool(root and (root / ".planning").is_dir())


def short_list(items, empty_text="none", limit=3):
    values = [str(item).strip() for item in items if str(item).strip()]
    if not values:
        return empty_text
    if len(values) <= limit:
        return "; ".join(values)
    shown = "; ".join(values[:limit])
    return f"{shown}; +{len(values) - limit} more"


def spec_summary_lines(task_meta: dict | None) -> list[str]:
    if not isinstance(task_meta, dict):
        return []

    spec_context = task_meta.get("spec_context")
    if not isinstance(spec_context, dict):
        return []

    provider = str(spec_context.get("provider") or "none")
    status = str(spec_context.get("status") or "none")
    if provider == "none" and status == "none":
        return []

    mode = str(spec_context.get("mode") or "embedded")
    lines = [f"Spec context: mode={mode} | provider={provider} | status={status}"]

    primary_ref = str(spec_context.get("primary_ref") or "").strip()
    if primary_ref:
        lines.append(f"Primary spec ref: {primary_ref}")

    candidate_refs = []
    for item in task_meta.get("spec_candidate_refs") or []:
        text = str(item).strip()
        if text and text not in candidate_refs:
            candidate_refs.append(text)
    if candidate_refs:
        lines.append(f"Spec candidates: {'; '.join(candidate_refs[:3])}")

    resolution_hint = str(task_meta.get("spec_resolution_hint") or "").strip()
    if resolution_hint:
        lines.append(f"Resolve explicitly: {resolution_hint}")

    return lines


def delegate_kind_for_text(text: str) -> str | None:
    lowered = text.lower()
    patterns = [
        (
            "review",
            ["review", "diff review", "code review", "pr review", "审查", "评审"],
        ),
        (
            "verify",
            [
                "verify",
                "validation",
                "regression",
                "failing test",
                "test failure",
                "triage",
                "验证",
                "回归",
                "测试失败",
                "失败排查",
            ],
        ),
        (
            "spike",
            [
                "spike",
                "prototype",
                "poc",
                "feasibility",
                "compare options",
                "方案对比",
                "可行性",
            ],
        ),
        (
            "discovery",
            [
                "investigate",
                "analyze",
                "map",
                "scan",
                "explore",
                "entry point",
                "dependency",
                "research",
                "调研",
                "分析",
                "找入口",
                "排查",
            ],
        ),
    ]
    for kind, keywords in patterns:
        if any(keyword in lowered for keyword in keywords):
            return kind
    return None


def default_delegate_title(kind: str) -> str:
    titles = {
        "discovery": "Repo scan",
        "spike": "Option spike",
        "verify": "Verification triage",
        "review": "Review lane",
        "catchup": "Catchup lane",
        "other": "Delegate lane",
    }
    return titles.get(kind, "Delegate lane")


def prepare_delegate_command(text: str, kind: str, host: str = "claude") -> str:
    normalized = " ".join(text.split()) or default_delegate_title(kind)
    if len(normalized) > 80:
        normalized = normalized[:77].rstrip() + "..."
    return f"{installed_skill_command('prepare-delegate.sh', host=host)} --kind {kind} {shlex.quote(normalized)}"


def delegate_hint_for_text(
    text: str, state: dict | None = None, host: str = "claude"
) -> str | None:
    kind = delegate_kind_for_text(text)
    if not kind:
        return None

    command = prepare_delegate_command(text, kind, host=host)
    base = (
        f"[context-task-planning] If this turns into a bounded `{kind}` side quest, a delegate lane may help. "
        f"Optional command: `{command}`. Keep it optional unless observe-only routing or durable lifecycle tracking makes a delegate required."
    )

    if state:
        active_delegates = state.get("delegation", {}).get("active", [])
        if active_delegates:
            return (
                base
                + f" Active delegates now: {short_list(active_delegates)}. Reuse one if it already matches the question."
            )

    return base


def task_drift_result(
    text: str, cwd: str | None = None, session_key: str | None = None
) -> dict | None:
    if (
        not TASK_GUARD_IMPORT_OK
        or not text.strip()
        or resolve_guard_task is None
        or classify_drift is None
    ):
        return None

    task = resolve_guard_task(cwd or "", "", session_key or "")
    return classify_drift(text, task)


def resolve_task_meta(
    cwd: str | None = None, session_key: str | None = None
) -> dict | None:
    if not TASK_GUARD_IMPORT_OK or resolve_guard_task is None:
        return None
    try:
        return resolve_guard_task(cwd or "", "", session_key or "")
    except Exception:
        return None


def explicit_task_context_eligible(task_meta: dict | None) -> bool:
    if not isinstance(task_meta, dict):
        return False
    if not task_meta.get("found"):
        return False
    return str(task_meta.get("selection_source") or "") in {
        "session_binding",
        "session_pin",
    }


def fallback_task_advisory(
    task_meta: dict | None, tool_name: str | None = None, host: str = "claude"
) -> str | None:
    if not isinstance(task_meta, dict) or not task_meta.get("found"):
        return None
    if explicit_task_context_eligible(task_meta):
        return None

    slug = str(task_meta.get("slug") or "").strip() or "(unknown)"
    source = str(task_meta.get("selection_source") or "")
    if source == "active_pointer":
        source_text = "workspace fallback"
    elif source == "latest":
        source_text = "latest-task fallback"
    else:
        source_text = "fallback resolution"

    lines = [
        f"[context-task-planning] {source_text.capitalize()} resolved task `{slug}`, but this {host_display_name(host)} session is not explicitly bound to it.",
        "This is a session-binding advisory, not a drift warning.",
        "Do not treat that fallback task as the current session task unless you bind or resume it explicitly.",
    ]
    if tool_name == "Task":
        lines.append(
            "If you still launch a subagent here, keep the result routing-only until task ownership is explicit."
        )
    return " ".join(lines)


def task_drift_hint(result: dict | None, tool_name: str | None = None) -> str | None:
    if not result:
        return None

    classification = result.get("classification")
    task = result.get("task") or {}
    if not task.get("found"):
        return None

    slug = task.get("slug") or "(unknown)"
    if classification == "likely-unrelated":
        matched = ", ".join(str(item) for item in result.get("matched_terms") or []) or "none"
        cues = ", ".join(str(item) for item in result.get("switch_cues") or []) or "none"
        lines = [
            f"[context-task-planning] Route evidence for the assistant: the lightweight heuristic is `likely-unrelated` for current task `{slug}`.",
            f"Switch cues: {cues}. Shared terms: {matched}.",
            "Use the conversation and current task goal to decide same-task, different-task, or unclear. If different-task or genuinely unclear, ask the user before updating planning state or launching subagents; if same-task, continue without surfacing this evidence.",
        ]
        if tool_name == "Task":
            lines.append(
                "For a native Task launch, keep the subagent scoped to the confirmed task; if the fit is wrong, return a routing mismatch instead of continuing."
            )
        return " ".join(lines)

    return None


def allow_delegate_hint(result: dict | None) -> bool:
    if not result:
        return True
    return result.get("classification") == "related"


def state_summary(
    state: dict,
    task_meta: dict | None = None,
    tool_name: str | None = None,
    include_spec: bool = False,
) -> str:
    slug = state.get("slug", "(unknown)")
    status = state.get("status", "unknown")
    mode = state.get("mode", "unknown")
    phase = state.get("current_phase", "unknown")
    next_action = state.get("next_action", "(none recorded)")
    blockers = short_list(state.get("blockers", []))
    active_delegates = short_list(
        state.get("delegation", {}).get("active", []), empty_text="none"
    )
    verify_commands = short_list(
        state.get("verify_commands", []), empty_text="none declared"
    )

    lines = [
        f"[context-task-planning] Task `{slug}` | status `{status}` | mode `{mode}` | phase `{phase}`",
        f"Next action: {next_action}",
        f"Blockers: {blockers}",
        f"Active delegates: {active_delegates}",
    ]

    role = ""
    writer_display = ""
    observer_count = 0
    repo_scope = []
    primary_repo = ""
    if isinstance(task_meta, dict):
        role = str(task_meta.get("binding_role") or "")
        writer_display = str(task_meta.get("writer_display") or "")
        observer_count = int(task_meta.get("observer_count") or 0)
        repo_scope = list(task_meta.get("repo_scope") or [])
        primary_repo = str(task_meta.get("primary_repo") or "")

    if role:
        lines.append(
            f"Access: {role} | writer={writer_display or '(none)'} | observers={observer_count}"
        )
        if role == "observer":
            lines.append(
                "Observe-only session: do not edit `task_plan.md`, `progress.md`, or `state.json`. You may still create or update delegate lanes under `delegates/<delegate-id>/`."
            )
    if repo_scope:
        lines.append(
            f"Repos: primary={primary_repo or '(none)'} | scope={', '.join(repo_scope)}"
        )
    if include_spec:
        lines.extend(spec_summary_lines(task_meta))

    if tool_name == "Bash":
        lines.append(f"Verification commands: {verify_commands}")
        if role == "observer":
            lines.append(
                "If this Bash step needs planning changes, hand them to the writer session instead of editing main planning files here."
            )
        else:
            lines.append(
                "If this Bash step changes task state, sync `progress.md` and `state.json` afterwards."
            )
    elif tool_name == "Task":
        lines.append(
            "Keep Task launches scoped to the current task. If repo ownership or task fit becomes unclear, report that back instead of switching tasks implicitly."
        )
        if role == "observer":
            lines.append(
                "Observe-only sessions should use explicit delegate lanes for side work that needs durable tracking."
            )
    else:
        lines.append(
            "Keep external or untrusted material in `findings.md`, not in Hot Context."
        )

    return "\n".join(lines)


def no_active_task_hint(cwd: str | None = None, host: str = "claude") -> str | None:
    if workspace_has_planning(cwd):
        return (
            "[context-task-planning] This workspace already has `.planning/`, but no auto-selected active task. "
            f"Run `{installed_skill_command('list-tasks.sh', host=host)}` to inspect tasks, then `resume-task.sh <slug>` or `set-active-task.sh <slug>` before major work."
        )
    return None


def looks_complex(prompt: str) -> bool:
    text = prompt.strip().lower()
    if not text:
        return False

    keywords = [
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
        "实现",
        "设计",
        "重构",
        "排查",
        "调研",
        "迁移",
        "优化",
        "新增",
        "修复",
    ]
    complexity_signals = [
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

    keyword_hit = any(word in text for word in keywords)
    signal_hit = any(signal in prompt for signal in complexity_signals)
    word_count = len(re.findall(r"\w+", prompt, flags=re.UNICODE))

    return keyword_hit and (signal_hit or word_count >= 8)


def init_task_hint(host: str = "claude") -> str:
    return (
        "[context-task-planning] This looks like multi-step work. Before implementation, initialize a task workspace with "
        f'`{installed_skill_command("init-task.sh", host=host)} "<confirmed task title>"`. If you infer the title from the request, ask the user to confirm or edit the title and slug before creating `.planning/<slug>/`. Then capture goal, non-goals, acceptance criteria, constraints, and next action in the task files.'
    )


def session_start_payload(context: str) -> str:
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        },
        ensure_ascii=False,
    )


def user_prompt_payload(context: str) -> str:
    return json.dumps({"additionalContext": context}, ensure_ascii=False)


def pre_tool_payload(context: str) -> str:
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": context,
            }
        },
        ensure_ascii=False,
    )
