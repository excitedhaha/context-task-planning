#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
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

DELEGATE_KIND_PATTERNS = [
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

DELEGATE_RECOMMEND_SESSION_CUES = [
    "resume later",
    "pick up later",
    "later session",
    "follow up later",
    "后续继续",
    "之后继续",
    "跨会话",
]

DELEGATE_RECOMMEND_ARTIFACT_CUES = [
    "write up",
    "report",
    "summary",
    "matrix",
    "research notes",
    "record findings",
    "整理结论",
    "输出报告",
    "记录结果",
]

DELEGATE_RECOMMEND_MULTI_CUES = [
    "multiple repos",
    "across repos",
    "each repo",
    "for every repo",
    "parallel",
    "多个仓库",
    "多个子问题",
    "逐个仓库",
]

DELEGATE_REQUIRED_LIFECYCLE_CUES = [
    "durable lifecycle",
    "lifecycle state",
    "track lifecycle",
    "resume and promote",
    "blocked then resume",
    "持久生命周期",
    "跟踪生命周期",
    "恢复并提升",
]

DELEGATE_REQUIRED_CLOSEOUT_CUES = [
    "before done",
    "before archive",
    "block done",
    "block archive",
    "gate closeout",
    "完成前",
    "归档前",
    "阻塞 done",
]

DELEGATE_REQUIRED_CONTEXT_CUES = [
    "survive context loss",
    "after context loss",
    "promote later",
    "review later before promote",
    "上下文丢失后",
    "之后再提升",
    "稍后再评审",
]

SPECIAL_TOKEN_RE = re.compile(
    r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+"
    r"|[A-Za-z0-9_.-]+\.(?:sh|py|md|json|yaml|yml|toml|txt)"
    r"|\.[A-Za-z0-9_.-]+"
    r"|[A-Za-z0-9_.-]*-[A-Za-z0-9_.-]+"
)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
SESSION_KEY_ENV = "PLAN_SESSION_KEY"
SESSION_DIR_NAME = ".sessions"
RUNTIME_DIR_NAME = ".runtime"
REPO_REGISTRY_FILE = "repos.json"
TASK_REPO_BINDING_DIR = "task_repo_bindings"
WORKTREE_ROOT_NAME = ".worktrees"
ROLE_WRITER = "writer"
ROLE_OBSERVER = "observer"
WORKSPACE_FALLBACK_SESSION_KEY = "workspace:default"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="task_guard.py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    workspace = subparsers.add_parser("resolve-workspace-root")
    workspace.add_argument("--cwd", default="")

    current = subparsers.add_parser("current-task")
    current.add_argument("--task", default="")
    current.add_argument("--cwd", default="")
    current.add_argument("--session-key", default="")
    current.add_argument("--json", action="store_true")
    current.add_argument("--compact", action="store_true")

    plan_dir = subparsers.add_parser("resolve-plan-dir")
    plan_dir.add_argument("--task", default="")
    plan_dir.add_argument("--cwd", default="")
    plan_dir.add_argument("--session-key", default="")

    drift = subparsers.add_parser("check-drift")
    drift.add_argument("--task", default="")
    drift.add_argument("--cwd", default="")
    drift.add_argument("--session-key", default="")
    drift.add_argument("--prompt", default="")
    drift.add_argument("--json", action="store_true")
    drift.add_argument("--compact", action="store_true")

    preflight = subparsers.add_parser("subagent-preflight")
    preflight.add_argument("--task", default="")
    preflight.add_argument("--cwd", default="")
    preflight.add_argument("--session-key", default="")
    preflight.add_argument("--host", default="generic")
    preflight.add_argument("--task-text", default="")
    preflight.add_argument("--tool-name", default="Task")
    preflight.add_argument("--json", action="store_true")
    preflight.add_argument("--text", action="store_true")
    preflight.add_argument("--compact", action="store_true")

    switch = subparsers.add_parser("check-switch-safety")
    switch.add_argument("--cwd", default="")
    switch.add_argument("--session-key", default="")
    switch.add_argument("--source-task", default="")
    switch.add_argument("--target-task", default="")
    switch.add_argument("--json", action="store_true")
    switch.add_argument("--compact", action="store_true")

    enforce = subparsers.add_parser("ensure-switch-safety")
    enforce.add_argument("--cwd", default="")
    enforce.add_argument("--session-key", default="")
    enforce.add_argument("--source-task", default="")
    enforce.add_argument("--target-task", default="")
    enforce.add_argument("--stash", action="store_true")
    enforce.add_argument("--allow-dirty", action="store_true")

    bind = subparsers.add_parser("bind-session-task")
    bind.add_argument("--cwd", default="")
    bind.add_argument("--session-key", default="")
    bind.add_argument("--task", required=True)
    bind.add_argument(
        "--role", choices=[ROLE_WRITER, ROLE_OBSERVER], default=ROLE_WRITER
    )
    bind.add_argument("--steal", action="store_true")
    bind.add_argument("--fallback", action="store_true")

    clear_session = subparsers.add_parser("clear-session-task")
    clear_session.add_argument("--cwd", default="")
    clear_session.add_argument("--session-key", default="")
    clear_session.add_argument("--fallback", action="store_true")

    clear_task = subparsers.add_parser("clear-task-sessions")
    clear_task.add_argument("--cwd", default="")
    clear_task.add_argument("--task", required=True)

    list_repos = subparsers.add_parser("list-repos")
    list_repos.add_argument("--cwd", default="")
    list_repos.add_argument("--discover", action="store_true")
    list_repos.add_argument("--json", action="store_true")

    register_repo = subparsers.add_parser("register-repo")
    register_repo.add_argument("--cwd", default="")
    register_repo.add_argument("--id", default="")
    register_repo.add_argument("path")

    set_task_repos = subparsers.add_parser("set-task-repos")
    set_task_repos.add_argument("--cwd", default="")
    set_task_repos.add_argument("--task", required=True)
    set_task_repos.add_argument("--repo", action="append", default=[])
    set_task_repos.add_argument("--primary", default="")

    repo_binding = subparsers.add_parser("task-repo-binding")
    repo_binding.add_argument("--cwd", default="")
    repo_binding.add_argument("--task", required=True)
    repo_binding.add_argument("--repo", required=True)
    repo_binding.add_argument("--json", action="store_true")

    set_repo_binding = subparsers.add_parser("set-task-repo-binding")
    set_repo_binding.add_argument("--cwd", default="")
    set_repo_binding.add_argument("--task", required=True)
    set_repo_binding.add_argument("--repo", required=True)
    set_repo_binding.add_argument(
        "--mode", choices=["shared", "worktree"], required=True
    )
    set_repo_binding.add_argument("--checkout-path", required=True)
    set_repo_binding.add_argument("--branch", default="")
    set_repo_binding.add_argument("--base-branch", default="")

    list_worktrees = subparsers.add_parser("list-worktrees")
    list_worktrees.add_argument("--cwd", default="")
    list_worktrees.add_argument("--task", default="")
    list_worktrees.add_argument("--json", action="store_true")

    access = subparsers.add_parser("check-task-access")
    access.add_argument("--cwd", default="")
    access.add_argument("--task", required=True)
    access.add_argument("--session-key", default="")
    access.add_argument(
        "--require-role", choices=[ROLE_WRITER, ROLE_OBSERVER], default=ROLE_WRITER
    )
    access.add_argument("--fallback", action="store_true")

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


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def relative_path_or_empty(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())) or "."
    except ValueError:
        return ""


def workspace_contains_path(workspace_root: Path, start_dir: Path) -> bool:
    workspace_root = workspace_root.resolve()
    start_dir = start_dir.resolve()
    plan_root = workspace_root / ".planning"

    if not plan_root.is_dir():
        return False

    if start_dir == workspace_root:
        return True

    if path_is_within(start_dir, plan_root):
        return True

    if git_root_for(workspace_root) == workspace_root and path_is_within(
        start_dir, workspace_root
    ):
        return True

    for repo in read_repo_registry(plan_root):
        repo_root = registered_repo_absolute_path(workspace_root, repo)
        if path_is_within(start_dir, repo_root):
            return True

    for binding in explicit_worktree_bindings(plan_root):
        checkout_root = resolve_path_in_workspace(
            workspace_root, str(binding.get("checkout_path") or "")
        )
        if path_is_within(start_dir, checkout_root):
            return True

    start_git_root = git_root_for(start_dir)
    if start_git_root and start_git_root != workspace_root:
        relative_git_root = relative_path_or_empty(workspace_root, start_git_root)
        if (
            relative_git_root
            and relative_git_root != "."
            and len(Path(relative_git_root).parts) == 1
            and not read_repo_registry(plan_root)
            and not explicit_worktree_bindings(plan_root)
        ):
            return True

    return False


def resolve_workspace_root(cwd: str) -> Path:
    start_dir = resolve_start_dir(cwd)
    candidate = start_dir
    git_root = None

    while True:
        if (candidate / ".planning").is_dir() and workspace_contains_path(
            candidate, start_dir
        ):
            return candidate

        if (candidate / ".git").exists() and git_root is None:
            git_root = candidate

        if candidate.parent == candidate:
            break
        candidate = candidate.parent

    return git_root or start_dir


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def resolve_session_key(explicit: str = "") -> str:
    for candidate in (explicit.strip(), os.environ.get(SESSION_KEY_ENV, "").strip()):
        if candidate:
            return candidate
    return ""


def effective_session_key(explicit: str = "", fallback: bool = False) -> str:
    session_key = resolve_session_key(explicit)
    if session_key:
        return session_key
    if fallback:
        return WORKSPACE_FALLBACK_SESSION_KEY
    return ""


def normalize_role(value: str) -> str:
    return ROLE_OBSERVER if value == ROLE_OBSERVER else ROLE_WRITER


def display_session_key(session_key: str) -> str:
    if not session_key:
        return "(none)"
    if session_key == WORKSPACE_FALLBACK_SESSION_KEY:
        return "workspace-default"
    return session_key


def session_registry_dir(plan_root: Path) -> Path:
    return plan_root / SESSION_DIR_NAME


def session_binding_name(session_key: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", session_key).strip("-.") or "session"
    digest = hashlib.sha1(session_key.encode("utf-8")).hexdigest()[:12]
    return f"{cleaned[:48]}-{digest}.json"


def session_binding_path(plan_root: Path, session_key: str) -> Path | None:
    key = resolve_session_key(session_key)
    if not key:
        return None
    return session_registry_dir(plan_root) / session_binding_name(key)


def iter_session_bindings(plan_root: Path) -> list[tuple[Path, dict]]:
    registry = session_registry_dir(plan_root)
    if not registry.is_dir():
        return []

    bindings = []
    for entry in registry.iterdir():
        if not entry.is_file() or entry.suffix != ".json":
            continue
        bindings.append((entry, safe_json(entry)))
    return bindings


def read_session_binding(plan_root: Path, session_key: str) -> dict:
    key = resolve_session_key(session_key)
    if not key:
        return {}

    path = session_binding_path(plan_root, key)
    if path is None:
        return {}

    binding = safe_json(path)
    if not binding:
        return {}
    if binding.get("session_key") and binding.get("session_key") != key:
        return {}
    binding.setdefault("session_key", key)
    binding["role"] = normalize_role(str(binding.get("role") or ROLE_WRITER))
    binding.setdefault("path", str(path))
    return binding


def write_session_binding(
    plan_root: Path, session_key: str, task_slug: str, role: str = ROLE_WRITER
) -> None:
    key = resolve_session_key(session_key)
    if not key or not task_slug:
        return

    path = session_binding_path(plan_root, key)
    if path is None:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0.0",
        "session_key": key,
        "task_slug": task_slug,
        "role": normalize_role(role),
        "updated_at": utc_now(),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def clear_session_binding(plan_root: Path, session_key: str) -> bool:
    path = session_binding_path(plan_root, session_key)
    if path is None or not path.exists():
        return False
    path.unlink()
    return True


def clear_task_session_bindings(plan_root: Path, task_slug: str) -> list[str]:
    cleared = []
    for path, binding in iter_session_bindings(plan_root):
        if binding.get("task_slug") != task_slug:
            continue
        session_key = str(binding.get("session_key") or "").strip()
        try:
            path.unlink()
            if session_key:
                cleared.append(session_key)
        except OSError:
            continue
    return cleared


def task_bindings(plan_root: Path, task_slug: str) -> list[dict]:
    bindings = []
    for path, binding in iter_session_bindings(plan_root):
        if str(binding.get("task_slug") or "").strip() != task_slug:
            continue
        session_key = str(binding.get("session_key") or "").strip()
        if not session_key:
            continue
        bindings.append(
            {
                "path": str(path),
                "session_key": session_key,
                "task_slug": task_slug,
                "role": normalize_role(str(binding.get("role") or ROLE_WRITER)),
                "updated_at": str(binding.get("updated_at") or ""),
            }
        )
    bindings.sort(
        key=lambda item: (
            item["role"] != ROLE_WRITER,
            item["updated_at"],
            item["session_key"],
        )
    )
    return bindings


def writer_binding_for_task(plan_root: Path, task_slug: str) -> dict:
    for binding in task_bindings(plan_root, task_slug):
        if binding["role"] == ROLE_WRITER:
            return binding
    return {}


def binding_role_for_task(plan_root: Path, session_key: str, task_slug: str) -> str:
    binding = read_session_binding(plan_root, session_key)
    if str(binding.get("task_slug") or "").strip() != task_slug:
        return ""
    return normalize_role(str(binding.get("role") or ROLE_WRITER))


def demote_writer_binding(plan_root: Path, task_slug: str) -> str:
    writer = writer_binding_for_task(plan_root, task_slug)
    session_key = str(writer.get("session_key") or "").strip()
    if not session_key:
        return ""
    write_session_binding(plan_root, session_key, task_slug, ROLE_OBSERVER)
    return session_key


def runtime_dir(plan_root: Path) -> Path:
    return plan_root / RUNTIME_DIR_NAME


def repo_registry_path(plan_root: Path) -> Path:
    return runtime_dir(plan_root) / REPO_REGISTRY_FILE


def task_repo_binding_path(plan_root: Path, task_slug: str) -> Path:
    return runtime_dir(plan_root) / TASK_REPO_BINDING_DIR / f"{task_slug}.json"


def normalize_repo_id(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = re.sub(r"-+", "-", lowered).strip("-")
    return lowered


def write_json_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def relative_to_workspace(workspace_root: Path, absolute_path: Path) -> str:
    try:
        return str(absolute_path.resolve().relative_to(workspace_root.resolve())) or "."
    except ValueError as exc:
        raise SystemExit(
            f"Path `{absolute_path}` must live under workspace `{workspace_root}`."
        ) from exc


def resolve_path_in_workspace(workspace_root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = workspace_root / candidate
    try:
        return candidate.resolve()
    except OSError as exc:
        raise SystemExit(f"Could not resolve path `{raw_path}`: {exc}") from exc


def read_repo_registry(plan_root: Path) -> list[dict]:
    payload = safe_json(repo_registry_path(plan_root))
    repos = payload.get("repos", []) if isinstance(payload, dict) else []
    if not isinstance(repos, list):
        return []

    normalized = []
    seen = set()
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        repo_id = normalize_repo_id(str(repo.get("id") or ""))
        repo_path = str(repo.get("path") or "").strip()
        if not repo_id or not repo_path or repo_id in seen:
            continue
        seen.add(repo_id)
        normalized.append(
            {
                "id": repo_id,
                "path": repo_path,
                "registration_mode": str(repo.get("registration_mode") or "manual"),
                "registered_at": str(repo.get("registered_at") or ""),
                "updated_at": str(repo.get("updated_at") or ""),
            }
        )
    return normalized


def write_repo_registry(plan_root: Path, repos: list[dict]) -> None:
    payload = {
        "schema_version": "1.0.0",
        "repos": repos,
        "updated_at": utc_now(),
    }
    write_json_file(repo_registry_path(plan_root), payload)


def repo_by_id(plan_root: Path, repo_id: str) -> dict:
    wanted = normalize_repo_id(repo_id)
    for repo in read_repo_registry(plan_root):
        if repo["id"] == wanted:
            return repo
    return {}


def registered_repo_absolute_path(workspace_root: Path, repo: dict) -> Path:
    repo_path = str(repo.get("path") or "").strip() or "."
    return resolve_path_in_workspace(workspace_root, repo_path)


def discover_workspace_repos(workspace_root: Path) -> list[dict]:
    candidates = [workspace_root]
    for entry in sorted(workspace_root.iterdir(), key=lambda item: item.name):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if entry.name in {"node_modules", "vendor", WORKTREE_ROOT_NAME}:
            continue
        candidates.append(entry)

    discovered = []
    seen_paths = set()
    for candidate in candidates:
        git_root = git_root_for(candidate)
        if git_root is None:
            continue
        rel_path = relative_to_workspace(workspace_root, git_root)
        if rel_path in seen_paths:
            continue
        seen_paths.add(rel_path)
        repo_id = normalize_repo_id(
            git_root.name if rel_path != "." else workspace_root.name
        )
        discovered.append(
            {
                "id": repo_id or "workspace",
                "path": rel_path,
            }
        )

    discovered.sort(key=lambda repo: (repo["path"] != ".", repo["path"], repo["id"]))
    return discovered


def register_workspace_repo(
    plan_root: Path, workspace_root: Path, raw_path: str, requested_id: str = ""
) -> dict:
    resolved_path = resolve_path_in_workspace(workspace_root, raw_path)
    git_root = git_root_for(resolved_path)
    if git_root is None:
        raise SystemExit(f"Path `{raw_path}` is not inside a git repository.")

    repo_path = relative_to_workspace(workspace_root, git_root)
    repo_id = normalize_repo_id(requested_id or git_root.name or repo_path)
    if not repo_id:
        raise SystemExit("Could not derive a repo id. Pass --id explicitly.")

    repos = read_repo_registry(plan_root)
    for repo in repos:
        if repo["id"] == repo_id and repo["path"] != repo_path:
            raise SystemExit(
                f"Repo id `{repo_id}` is already registered for `{repo['path']}`."
            )
        if repo["path"] == repo_path and repo["id"] != repo_id:
            raise SystemExit(
                f"Repo path `{repo_path}` is already registered as `{repo['id']}`."
            )

    timestamp = utc_now()
    entry = {
        "id": repo_id,
        "path": repo_path,
        "registration_mode": "manual",
        "registered_at": timestamp,
        "updated_at": timestamp,
    }

    updated = False
    for index, repo in enumerate(repos):
        if repo["id"] == repo_id:
            entry["registered_at"] = repo.get("registered_at") or timestamp
            repos[index] = entry
            updated = True
            break

    if not updated:
        repos.append(entry)
        repos.sort(key=lambda repo: repo["id"])

    write_repo_registry(plan_root, repos)
    return entry


def read_task_repo_binding_overrides(plan_root: Path, task_slug: str) -> list[dict]:
    payload = safe_json(task_repo_binding_path(plan_root, task_slug))
    bindings = payload.get("bindings", []) if isinstance(payload, dict) else []
    if not isinstance(bindings, list):
        return []

    normalized = []
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        repo_id = normalize_repo_id(str(binding.get("repo_id") or ""))
        checkout_path = str(binding.get("checkout_path") or "").strip()
        mode = str(binding.get("mode") or "shared").strip() or "shared"
        if not repo_id or not checkout_path:
            continue
        normalized.append(
            {
                "repo_id": repo_id,
                "mode": "worktree" if mode == "worktree" else "shared",
                "checkout_path": checkout_path,
                "branch": str(binding.get("branch") or "").strip(),
                "base_branch": str(binding.get("base_branch") or "").strip(),
                "updated_at": str(binding.get("updated_at") or "").strip(),
            }
        )
    return normalized


def write_task_repo_binding_overrides(
    plan_root: Path, task_slug: str, bindings: list[dict]
) -> None:
    payload = {
        "schema_version": "1.0.0",
        "task_slug": task_slug,
        "bindings": bindings,
        "updated_at": utc_now(),
    }
    write_json_file(task_repo_binding_path(plan_root, task_slug), payload)


def load_task_state(plan_dir: Path) -> dict:
    state = safe_json(plan_dir / "state.json")
    if state:
        return state
    return {"slug": plan_dir.name, "title": plan_dir.name}


def active_delegate_ids(plan_dir: Path | None) -> list[str]:
    if plan_dir is None:
        return []
    delegates_dir = plan_dir / "delegates"
    if not delegates_dir.is_dir():
        return []

    active = []
    for entry in delegates_dir.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        status = safe_json(entry / "status.json")
        if not status:
            continue
        if str(status.get("status") or "") in {"complete", "cancelled"}:
            continue
        delegate_id = str(status.get("delegate_id") or entry.name).strip()
        if delegate_id:
            active.append(delegate_id)
    active.sort()
    return active


def task_state_by_slug(plan_root: Path, task_slug: str) -> dict:
    plan_dir = plan_root / task_slug
    if not plan_dir.is_dir():
        return {}
    state = load_task_state(plan_dir)
    state.setdefault("slug", task_slug)
    return state


def task_repo_scope(state: dict) -> list[str]:
    raw = state.get("repo_scope", []) if isinstance(state, dict) else []
    if not isinstance(raw, list):
        return []

    repo_ids = []
    seen = set()
    for item in raw:
        repo_id = normalize_repo_id(str(item or ""))
        if not repo_id or repo_id in seen:
            continue
        seen.add(repo_id)
        repo_ids.append(repo_id)
    return repo_ids


def task_primary_repo(state: dict, repo_ids: list[str] | None = None) -> str:
    primary = normalize_repo_id(str(state.get("primary_repo") or ""))
    if primary:
        return primary
    scope = repo_ids if repo_ids is not None else task_repo_scope(state)
    return scope[0] if scope else ""


def git_branch_for(path: Path) -> str:
    git_root = git_root_for(path)
    if git_root is None:
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    output = result.stdout.strip()
    return output if result.returncode == 0 else ""


def implicit_workspace_repo(workspace_root: Path) -> dict:
    git_root = git_root_for(workspace_root)
    if git_root is None or git_root != workspace_root:
        return {}
    repo_id = normalize_repo_id(workspace_root.name) or "workspace"
    return {
        "id": repo_id,
        "path": ".",
        "registration_mode": "implicit",
        "registered_at": "",
        "updated_at": "",
    }


def resolved_repos_for_task(
    plan_root: Path, workspace_root: Path, task_slug: str, state: dict | None = None
) -> list[dict]:
    task_state = (
        state if isinstance(state, dict) else task_state_by_slug(plan_root, task_slug)
    )
    repo_ids = task_repo_scope(task_state)
    repos = []

    if repo_ids:
        for repo_id in repo_ids:
            repo = repo_by_id(plan_root, repo_id)
            if repo:
                repos.append(repo)
        return repos

    implicit = implicit_workspace_repo(workspace_root)
    return [implicit] if implicit else []


def effective_task_repo_bindings(
    plan_root: Path, workspace_root: Path, task_slug: str, state: dict | None = None
) -> list[dict]:
    task_state = (
        state if isinstance(state, dict) else task_state_by_slug(plan_root, task_slug)
    )
    repos = resolved_repos_for_task(plan_root, workspace_root, task_slug, task_state)
    overrides = {
        binding["repo_id"]: binding
        for binding in read_task_repo_binding_overrides(plan_root, task_slug)
    }

    bindings = []
    for repo in repos:
        repo_path = registered_repo_absolute_path(workspace_root, repo)
        default_checkout = relative_to_workspace(workspace_root, repo_path)
        override = overrides.get(repo["id"], {})
        checkout_path = str(override.get("checkout_path") or default_checkout)
        checkout_absolute = resolve_path_in_workspace(workspace_root, checkout_path)
        branch = str(override.get("branch") or git_branch_for(checkout_absolute))
        bindings.append(
            {
                "repo_id": repo["id"],
                "repo_path": repo["path"],
                "git_root": default_checkout,
                "mode": str(override.get("mode") or "shared"),
                "checkout_path": checkout_path,
                "branch": branch,
                "base_branch": str(override.get("base_branch") or ""),
                "checkout_exists": checkout_absolute.exists(),
            }
        )

    bindings.sort(key=lambda binding: binding["repo_id"])
    return bindings


def upsert_markdown_line(
    lines: list[str], prefix: str, replacement: str, after_prefix: str = ""
) -> list[str]:
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = replacement
            return lines

    if after_prefix:
        for index, line in enumerate(lines):
            if line.startswith(after_prefix):
                lines.insert(index + 1, replacement)
                return lines

    lines.append(replacement)
    return lines


def render_repo_scope(repo_ids: list[str]) -> str:
    return ", ".join(repo_ids) if repo_ids else "(unset)"


def sync_task_repo_markdown(
    task_plan_path: Path, progress_path: Path, primary_repo: str, repo_ids: list[str]
) -> None:
    primary_text = f"`{primary_repo}`" if primary_repo else "(unset)"
    scope_text = render_repo_scope(repo_ids)
    if repo_ids:
        scope_text = ", ".join(f"`{repo_id}`" for repo_id in repo_ids)

    if task_plan_path.exists():
        lines = task_plan_path.read_text(encoding="utf-8").splitlines()
        lines = upsert_markdown_line(
            lines,
            "- Primary Repo:",
            f"- Primary Repo: {primary_text}",
            after_prefix="- Next Action:",
        )
        lines = upsert_markdown_line(
            lines,
            "- Repo Scope:",
            f"- Repo Scope: {scope_text}",
            after_prefix="- Primary Repo:",
        )
        constraint_scope = scope_text.replace("`", "") if repo_ids else "(unset)"
        lines = upsert_markdown_line(
            lines,
            "- Primary Repo Constraint:",
            f"- Primary Repo Constraint: {primary_text}",
            after_prefix="- Planning Path:",
        )
        lines = upsert_markdown_line(
            lines,
            "- Repo Scope Constraint:",
            f"- Repo Scope Constraint: {constraint_scope}",
            after_prefix="- Primary Repo Constraint:",
        )
        task_plan_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if progress_path.exists():
        lines = progress_path.read_text(encoding="utf-8").splitlines()
        lines = upsert_markdown_line(
            lines,
            "- Primary Repo:",
            f"- Primary Repo: {primary_text}",
            after_prefix="- Next Action:",
        )
        lines = upsert_markdown_line(
            lines,
            "- Repo Scope:",
            f"- Repo Scope: {scope_text}",
            after_prefix="- Primary Repo:",
        )
        progress_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_task_repo_scope(
    plan_root: Path,
    workspace_root: Path,
    task_slug: str,
    repo_ids: list[str],
    primary_repo: str,
) -> dict:
    plan_dir = plan_root / task_slug
    if not plan_dir.is_dir():
        raise SystemExit(f"Task not found: {plan_dir}")

    normalized_repo_ids = []
    seen = set()
    for repo_id in repo_ids:
        normalized = normalize_repo_id(repo_id)
        if not normalized or normalized in seen:
            continue
        if not repo_by_id(plan_root, normalized):
            raise SystemExit(
                f"Repo `{normalized}` is not registered in this workspace."
            )
        seen.add(normalized)
        normalized_repo_ids.append(normalized)

    normalized_primary = normalize_repo_id(primary_repo)
    if normalized_primary and normalized_primary not in normalized_repo_ids:
        raise SystemExit("Primary repo must be part of --repo scope.")
    if not normalized_primary and normalized_repo_ids:
        normalized_primary = normalized_repo_ids[0]

    state_path = plan_dir / "state.json"
    state = load_task_state(plan_dir)
    constraints = (
        state.get("constraints", [])
        if isinstance(state.get("constraints", []), list)
        else []
    )
    constraints = [
        item
        for item in constraints
        if not str(item).startswith("Primary repo:")
        and not str(item).startswith("Repo scope:")
    ]
    constraints.append(f"Primary repo: {normalized_primary or '(unset)'}")
    constraints.append(
        f"Repo scope: {', '.join(normalized_repo_ids) if normalized_repo_ids else '(unset)'}"
    )
    state["repo_scope"] = normalized_repo_ids
    state["primary_repo"] = normalized_primary
    state["constraints"] = constraints
    state["latest_checkpoint"] = "Task repo scope updated."
    state["updated_at"] = utc_now()
    write_json_file(state_path, state)

    if normalized_repo_ids:
        filtered_bindings = [
            binding
            for binding in read_task_repo_binding_overrides(plan_root, task_slug)
            if binding["repo_id"] in normalized_repo_ids
        ]
        write_task_repo_binding_overrides(plan_root, task_slug, filtered_bindings)

    sync_task_repo_markdown(
        plan_dir / "task_plan.md",
        plan_dir / "progress.md",
        normalized_primary,
        normalized_repo_ids,
    )

    return {
        "task_slug": task_slug,
        "primary_repo": normalized_primary,
        "repo_scope": normalized_repo_ids,
        "workspace_root": str(workspace_root),
    }


def set_task_repo_binding(
    plan_root: Path,
    workspace_root: Path,
    task_slug: str,
    repo_id: str,
    mode: str,
    checkout_path: str,
    branch: str = "",
    base_branch: str = "",
) -> dict:
    task_state = task_state_by_slug(plan_root, task_slug)
    if not task_state:
        raise SystemExit(f"Task `{task_slug}` was not found.")

    normalized_repo = normalize_repo_id(repo_id)
    repo_scope = task_repo_scope(task_state)
    if repo_scope and normalized_repo not in repo_scope:
        raise SystemExit(
            f"Repo `{normalized_repo}` is not in task `{task_slug}` repo_scope."
        )

    repo = repo_by_id(plan_root, normalized_repo)
    if not repo and repo_scope:
        raise SystemExit(
            f"Repo `{normalized_repo}` is not registered in this workspace."
        )

    absolute_checkout = resolve_path_in_workspace(workspace_root, checkout_path)
    relative_checkout = relative_to_workspace(workspace_root, absolute_checkout)
    normalized_mode = "worktree" if mode == "worktree" else "shared"

    bindings = [
        binding
        for binding in read_task_repo_binding_overrides(plan_root, task_slug)
        if binding["repo_id"] != normalized_repo
    ]
    bindings.append(
        {
            "repo_id": normalized_repo,
            "mode": normalized_mode,
            "checkout_path": relative_checkout,
            "branch": branch,
            "base_branch": base_branch,
            "updated_at": utc_now(),
        }
    )
    bindings.sort(key=lambda binding: binding["repo_id"])
    write_task_repo_binding_overrides(plan_root, task_slug, bindings)

    result = {
        "task_slug": task_slug,
        "repo_id": normalized_repo,
        "mode": normalized_mode,
        "checkout_path": relative_checkout,
        "branch": branch,
        "base_branch": base_branch,
    }
    if repo:
        result["repo_path"] = repo["path"]
    return result


def other_writer_tasks(
    plan_root: Path, exclude_task_slug: str = "", exclude_session_key: str = ""
) -> list[str]:
    tasks = set()
    for _, binding in iter_session_bindings(plan_root):
        if normalize_role(str(binding.get("role") or ROLE_WRITER)) != ROLE_WRITER:
            continue
        session_key = str(binding.get("session_key") or "").strip()
        if exclude_session_key and session_key == exclude_session_key:
            continue
        task_slug = str(binding.get("task_slug") or "").strip()
        if not task_slug or task_slug == exclude_task_slug:
            continue
        tasks.add(task_slug)
    return sorted(tasks)


def shared_checkout_conflicts(
    plan_root: Path, workspace_root: Path, task_slug: str, session_key: str = ""
) -> list[dict]:
    target_bindings = effective_task_repo_bindings(plan_root, workspace_root, task_slug)
    target_by_repo = {binding["repo_id"]: binding for binding in target_bindings}
    conflicts = []

    for other_task in other_writer_tasks(
        plan_root, exclude_task_slug=task_slug, exclude_session_key=session_key
    ):
        for binding in effective_task_repo_bindings(
            plan_root, workspace_root, other_task
        ):
            target = target_by_repo.get(binding["repo_id"])
            if not target:
                continue
            if target["checkout_path"] != binding["checkout_path"]:
                continue
            conflicts.append(
                {
                    "other_task": other_task,
                    "repo_id": binding["repo_id"],
                    "checkout_path": binding["checkout_path"],
                }
            )

    conflicts.sort(
        key=lambda item: (item["repo_id"], item["checkout_path"], item["other_task"])
    )
    return conflicts


def explicit_worktree_bindings(plan_root: Path) -> list[dict]:
    bindings_dir = runtime_dir(plan_root) / TASK_REPO_BINDING_DIR
    if not bindings_dir.is_dir():
        return []

    rows = []
    for entry in sorted(bindings_dir.iterdir(), key=lambda item: item.name):
        if not entry.is_file() or entry.suffix != ".json":
            continue
        task_slug = entry.stem
        for binding in read_task_repo_binding_overrides(plan_root, task_slug):
            if binding["mode"] != "worktree":
                continue
            rows.append({"task_slug": task_slug, **binding})
    return rows


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


def resolve_task(cwd: str, requested_slug: str, session_key: str = "") -> dict:
    workspace_root = resolve_workspace_root(cwd)
    plan_root = workspace_root / ".planning"
    session_pin = os.environ.get("PLAN_TASK", "").strip()
    resolved_session_key = resolve_session_key(session_key)
    session_binding = read_session_binding(plan_root, resolved_session_key)
    session_binding_slug = str(session_binding.get("task_slug") or "").strip()
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
        (session_binding_slug, "session_binding", False),
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
    selected_slug = state.get("slug", "") if isinstance(state, dict) else ""
    bindings = task_bindings(plan_root, selected_slug) if selected_slug else []
    writer_binding = (
        writer_binding_for_task(plan_root, selected_slug) if selected_slug else {}
    )
    fallback_role = (
        binding_role_for_task(plan_root, WORKSPACE_FALLBACK_SESSION_KEY, selected_slug)
        if selected_slug
        else ""
    )
    binding_role = ""
    if selected_slug and resolved_session_key:
        binding_role = binding_role_for_task(
            plan_root, resolved_session_key, selected_slug
        )
    elif selected_slug and selection_source == "active_pointer" and fallback_role:
        binding_role = fallback_role
    elif selected_slug and selection_source == "active_pointer" and not writer_binding:
        binding_role = ROLE_WRITER

    observer_count = sum(1 for binding in bindings if binding["role"] == ROLE_OBSERVER)
    writer_session_key = str(writer_binding.get("session_key") or "")
    if (
        not writer_session_key
        and selected_slug
        and selection_source == "active_pointer"
    ):
        writer_session_key = WORKSPACE_FALLBACK_SESSION_KEY
    repo_scope = task_repo_scope(state)
    primary_repo = task_primary_repo(state, repo_scope)
    repo_bindings = (
        effective_task_repo_bindings(plan_root, workspace_root, selected_slug, state)
        if selected_slug
        else []
    )
    repo_summary = summarize_repo_bindings(repo_bindings)
    resume_candidates = resumable_task_candidates(plan_root, selected_slug)

    result = {
        "found": plan_dir is not None,
        "selection_source": selection_source,
        "workspace_root": str(workspace_root),
        "plan_root": str(plan_root),
        "plan_dir": str(plan_dir) if plan_dir is not None else "",
        "requested_slug": requested_slug,
        "session_key": resolved_session_key,
        "session_binding": session_binding_slug,
        "binding_role": binding_role,
        "session_pin": session_pin,
        "active_pointer": active_pointer,
        "writer_session_key": writer_session_key,
        "writer_display": display_session_key(writer_session_key),
        "observer_count": observer_count,
        "session_count": len(bindings),
        "repo_scope": repo_scope,
        "primary_repo": primary_repo,
        "repo_bindings": repo_bindings,
        "repo_summary": repo_summary,
        "slug": state.get("slug", "") if isinstance(state, dict) else "",
        "title": state.get("title", "") if isinstance(state, dict) else "",
        "status": state.get("status", "") if isinstance(state, dict) else "",
        "mode": state.get("mode", "") if isinstance(state, dict) else "",
        "current_phase": state.get("current_phase", "")
        if isinstance(state, dict)
        else "",
        "next_action": state.get("next_action", "") if isinstance(state, dict) else "",
        "blockers": state.get("blockers", []) if isinstance(state, dict) else [],
        "active_delegates": active_delegate_ids(plan_dir),
        "verify_commands": state.get("verify_commands", [])
        if isinstance(state, dict)
        else [],
        "goal": state.get("goal", "") if isinstance(state, dict) else "",
        "open_questions": state.get("open_questions", [])
        if isinstance(state, dict)
        else [],
        "phases": state.get("phases", []) if isinstance(state, dict) else [],
        "resume_candidates": resume_candidates,
    }
    result.update(guidance_for_current_task(result))
    return result


def task_snapshot(plan_dir: Path | None, source: str) -> dict:
    if plan_dir is None or not plan_dir.is_dir():
        return {
            "found": False,
            "selection_source": source,
            "plan_dir": "",
            "slug": "",
            "title": "",
            "status": "",
            "mode": "",
            "current_phase": "",
            "next_action": "",
        }

    state = load_task_state(plan_dir)
    return {
        "found": True,
        "selection_source": source,
        "plan_dir": str(plan_dir),
        "slug": state.get("slug", plan_dir.name),
        "title": state.get("title", plan_dir.name),
        "status": state.get("status", ""),
        "mode": state.get("mode", ""),
        "current_phase": state.get("current_phase", ""),
        "next_action": state.get("next_action", ""),
    }


def latest_updated_task(plan_root: Path, exclude_slug: str = "") -> Path | None:
    if not plan_root.is_dir():
        return None

    candidates = []
    for entry in plan_root.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if exclude_slug and entry.name == exclude_slug:
            continue

        state = load_task_state(entry)
        if state.get("status") == "archived":
            continue

        state_path = entry / "state.json"
        try:
            mtime = (
                state_path.stat().st_mtime
                if state_path.exists()
                else entry.stat().st_mtime
            )
        except OSError:
            continue
        candidates.append((mtime, entry))

    if not candidates:
        return None

    return max(candidates, key=lambda item: item[0])[1]


def resumable_task_candidates(
    plan_root: Path, exclude_slug: str = "", limit: int = 3
) -> list[dict]:
    if not plan_root.is_dir():
        return []

    candidates = []
    for entry in plan_root.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue

        state = load_task_state(entry)
        slug = str(state.get("slug") or entry.name)
        if exclude_slug and slug == exclude_slug:
            continue

        status = str(state.get("status") or "")
        if status in {"archived", "done"}:
            continue

        candidates.append(
            {
                "slug": slug,
                "title": str(state.get("title") or slug),
                "status": status or "unknown",
                "mode": str(state.get("mode") or ""),
                "updated_at": str(state.get("updated_at") or ""),
            }
        )

    candidates.sort(
        key=lambda item: (item.get("updated_at") or "", item.get("slug") or ""),
        reverse=True,
    )
    return candidates[:limit]


def summarize_repo_bindings(repo_bindings: list[dict]) -> dict:
    shared = []
    worktree = []

    for binding in repo_bindings:
        item = {
            "repo_id": str(binding.get("repo_id") or ""),
            "repo_path": str(binding.get("repo_path") or ""),
            "checkout_path": str(binding.get("checkout_path") or ""),
            "branch": str(binding.get("branch") or ""),
        }
        if binding.get("mode") == "worktree":
            worktree.append(item)
        else:
            shared.append(item)

    return {
        "total": len(repo_bindings),
        "shared": shared,
        "worktree": worktree,
        "shared_repo_ids": [item["repo_id"] for item in shared],
        "worktree_repo_ids": [item["repo_id"] for item in worktree],
    }


def summarize_repo_isolation(
    plan_root: Path, workspace_root: Path, task_slug: str, session_key: str = ""
) -> dict:
    bindings = effective_task_repo_bindings(plan_root, workspace_root, task_slug)
    conflicts = shared_checkout_conflicts(
        plan_root, workspace_root, task_slug, session_key
    )
    conflict_by_repo = {}
    for item in conflicts:
        repo_entry = conflict_by_repo.setdefault(
            item["repo_id"],
            {
                "checkout_path": item["checkout_path"],
                "other_tasks": [],
            },
        )
        repo_entry["other_tasks"].append(item["other_task"])

    summary = {
        "safe_shared": [],
        "needs_worktree": [],
        "already_isolated": [],
        "recommended_commands": [],
        "has_conflicts": bool(conflicts),
    }

    for binding in bindings:
        entry = {
            "repo_id": str(binding.get("repo_id") or ""),
            "repo_path": str(binding.get("repo_path") or ""),
            "checkout_path": str(binding.get("checkout_path") or ""),
            "branch": str(binding.get("branch") or ""),
        }
        if binding.get("mode") == "worktree":
            summary["already_isolated"].append(entry)
            continue

        repo_conflict = conflict_by_repo.get(entry["repo_id"])
        if repo_conflict:
            entry["other_tasks"] = sorted(set(repo_conflict["other_tasks"]))
            entry["recommended_command"] = (
                f"sh skill/scripts/prepare-task-worktree.sh --task {task_slug} --repo {entry['repo_id']}"
            )
            summary["needs_worktree"].append(entry)
            summary["recommended_commands"].append(entry["recommended_command"])
            continue

        summary["safe_shared"].append(entry)

    return summary


def guidance_for_current_task(task: dict) -> dict:
    slug = str(task.get("slug") or "")
    repo_summary = task.get("repo_summary", {}) if isinstance(task, dict) else {}
    repo_count = int(repo_summary.get("total", 0) or 0)
    has_worktree = bool(repo_summary.get("worktree"))

    if not task.get("found"):
        candidates = task.get("resume_candidates", []) if isinstance(task, dict) else []
        if candidates:
            best = candidates[0]
            return {
                "recommended_action": "resume-task",
                "recommended_reason": "No active task is selected, and the most recent resumable task looks like the best continuation point.",
                "recommended_commands": [
                    f"sh skill/scripts/resume-task.sh {best['slug']}",
                    "sh skill/scripts/list-tasks.sh",
                ],
            }
        return {
            "recommended_action": "init-task",
            "recommended_reason": "No active or resumable task is selected, so the next step is to start a new task.",
            "recommended_commands": [
                'sh skill/scripts/init-task.sh "Task Title"',
            ],
        }

    if task.get("status") == "done":
        commands = [
            f"sh skill/scripts/archive-task.sh {slug}",
            'sh skill/scripts/init-task.sh "Next task title"',
        ]
        return {
            "recommended_action": "archive-or-open-new-task",
            "recommended_reason": "This task is already done, so the next step is usually to archive it or start a fresh task.",
            "recommended_commands": commands,
        }

    if task.get("binding_role") == ROLE_OBSERVER:
        commands = [
            f"sh skill/scripts/validate-task.sh --task {slug}",
            f"sh skill/scripts/set-active-task.sh --steal {slug}",
        ]
        if repo_count > 1 or has_worktree:
            commands.append(f"sh skill/scripts/list-worktrees.sh --task {slug}")
        return {
            "recommended_action": "observe-or-steal-writer",
            "recommended_reason": "This session is observe-only, so you can review the task safely or explicitly take the writer lease if you need to edit.",
            "recommended_commands": commands,
        }

    commands = [f"sh skill/scripts/validate-task.sh --task {slug}"]
    if repo_count > 1 or has_worktree:
        commands.append(f"sh skill/scripts/list-worktrees.sh --task {slug}")

    if task.get("mode") == "verify" or task.get("current_phase") == "verify":
        commands.append(f"sh skill/scripts/done-task.sh {slug}")
        return {
            "recommended_action": "run-verification",
            "recommended_reason": "The task is in verify mode, so the next step is to run validation and then close it out if the checks pass.",
            "recommended_commands": commands,
        }

    return {
        "recommended_action": "continue-current-task",
        "recommended_reason": "The task is active and already has a recorded next action, so the next step is to continue from that state.",
        "recommended_commands": commands,
    }


def git_root_for(workspace_root: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace_root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None

    output = result.stdout.strip()
    if result.returncode != 0 or not output:
        return None

    try:
        return Path(output).resolve()
    except OSError:
        return None


def git_status_summary(workspace_root: Path) -> dict:
    git_root = git_root_for(workspace_root)
    if git_root is None:
        return {
            "found": False,
            "root": "",
            "dirty": False,
            "staged": 0,
            "unstaged": 0,
            "untracked": 0,
            "entries": [],
        }

    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(git_root),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return {
            "found": True,
            "root": str(git_root),
            "dirty": False,
            "staged": 0,
            "unstaged": 0,
            "untracked": 0,
            "entries": [],
        }

    entries = [line for line in result.stdout.splitlines() if line.strip()]
    staged = 0
    unstaged = 0
    untracked = 0

    for entry in entries:
        if entry.startswith("??"):
            untracked += 1
            continue

        if len(entry) < 2:
            continue

        if entry[0] not in {" ", "?"}:
            staged += 1
        if entry[1] != " ":
            unstaged += 1

    return {
        "found": True,
        "root": str(git_root),
        "dirty": bool(entries),
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "entries": entries,
    }


def repo_status_for_binding(workspace_root: Path, binding: dict) -> dict:
    checkout_path = str(binding.get("checkout_path") or ".")
    checkout_absolute = resolve_path_in_workspace(workspace_root, checkout_path)
    status = git_status_summary(checkout_absolute)
    status.update(
        {
            "repo_id": str(binding.get("repo_id") or ""),
            "repo_path": str(binding.get("repo_path") or ""),
            "mode": str(binding.get("mode") or "shared"),
            "checkout_path": checkout_path,
            "branch": str(binding.get("branch") or ""),
        }
    )
    return status


def task_git_status_summary(
    plan_root: Path, workspace_root: Path, task_slug: str, state: dict | None = None
) -> dict:
    bindings = (
        effective_task_repo_bindings(plan_root, workspace_root, task_slug, state)
        if task_slug
        else []
    )

    repo_statuses = [
        repo_status_for_binding(workspace_root, binding) for binding in bindings
    ]
    if not repo_statuses:
        fallback = git_status_summary(workspace_root)
        if fallback["found"]:
            fallback.update(
                {
                    "repo_id": normalize_repo_id(workspace_root.name) or "workspace",
                    "repo_path": ".",
                    "mode": "shared",
                    "checkout_path": ".",
                    "branch": git_branch_for(workspace_root),
                }
            )
            repo_statuses = [fallback]

    dirty_entries = [repo for repo in repo_statuses if repo.get("dirty")]
    return {
        "found": any(repo.get("found") for repo in repo_statuses),
        "root": repo_statuses[0].get("root", "") if len(repo_statuses) == 1 else "",
        "dirty": bool(dirty_entries),
        "staged": sum(int(repo.get("staged") or 0) for repo in repo_statuses),
        "unstaged": sum(int(repo.get("unstaged") or 0) for repo in repo_statuses),
        "untracked": sum(int(repo.get("untracked") or 0) for repo in repo_statuses),
        "entries": [
            entry for repo in repo_statuses for entry in repo.get("entries", [])
        ],
        "repos": repo_statuses,
        "dirty_repo_ids": [
            repo.get("repo_id") or "workspace" for repo in dirty_entries
        ],
    }


def recommendation_for_switch(source_task: dict) -> tuple[str, str]:
    status = source_task.get("status", "")
    mode = source_task.get("mode", "")
    phase = source_task.get("current_phase", "")

    if status in {"done", "verifying"} or mode == "verify" or phase == "verify":
        return (
            "commit-first",
            "The current task looks verified or near-done, so committing is safer than hiding the state in a stash.",
        )

    return (
        "stash-first",
        "The current task still looks in progress, so stashing is the safest quick way to switch without mixing changes.",
    )


def stash_message(source_task: dict, target_task: dict) -> str:
    source_slug = source_task.get("slug") or "unknown-task"
    target_slug = target_task.get("slug") or "another-task"
    return f"[context-task-planning] switch from {source_slug} to {target_slug}"


def check_switch_safety(
    cwd: str, source_slug: str, target_slug: str, session_key: str = ""
) -> dict:
    workspace_root = resolve_workspace_root(cwd)
    plan_root = workspace_root / ".planning"
    active_pointer = read_active_pointer(plan_root)

    source_task = resolve_task(cwd, source_slug, session_key)
    git = task_git_status_summary(
        plan_root, workspace_root, source_task.get("slug", "")
    )
    if not source_task["found"] and git["dirty"] and active_pointer != target_slug:
        source_plan_dir = latest_updated_task(plan_root, exclude_slug=target_slug)
        source_task = task_snapshot(source_plan_dir, "recent_task")
        git = task_git_status_summary(
            plan_root, workspace_root, source_task.get("slug", "")
        )

    target_plan_dir = plan_root / target_slug if target_slug else None
    target_task = task_snapshot(target_plan_dir, "target_task")

    switching = bool(target_slug)
    if active_pointer and active_pointer == target_slug:
        switching = False
    if source_task["found"] and source_task["slug"] == target_slug:
        switching = False

    safe = (not git["found"]) or (not git["dirty"]) or (not switching)
    recommendation = "none"
    reason = ""
    if not safe:
        recommendation, reason = recommendation_for_switch(source_task)

    return {
        "workspace_root": str(workspace_root),
        "plan_root": str(plan_root),
        "active_pointer": active_pointer,
        "switching": switching,
        "safe": safe,
        "recommendation": recommendation,
        "reason": reason,
        "git": git,
        "source_task": source_task,
        "target_task": target_task,
        "stash_message": stash_message(source_task, target_task),
    }


def compact_switch_safety(result: dict) -> str:
    source_slug = result["source_task"].get("slug") or "(none)"
    target_slug = result["target_task"].get("slug") or "(none)"
    dirty = str(result["git"].get("dirty", False)).lower()
    safe = str(result.get("safe", False)).lower()
    recommendation = result.get("recommendation", "none") or "none"
    return (
        f"safe={safe} dirty={dirty} source={source_slug} target={target_slug} "
        f"recommendation={recommendation}"
    )


def print_switch_safety(result: dict, as_json: bool, compact: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if compact:
        print(compact_switch_safety(result))
        return

    git = result["git"]
    print(f"[context-task-planning] Workspace: {result['workspace_root']}")
    if not git["found"]:
        print("[context-task-planning] Switch safety: no git repository detected.")
        return

    if git.get("root"):
        print(f"[context-task-planning] Git root: {git['root']}")
    print(
        "[context-task-planning] Dirty repo checkouts: "
        f"{str(git['dirty']).lower()} "
        f"(staged={git['staged']}, unstaged={git['unstaged']}, untracked={git['untracked']})"
    )
    for repo in git.get("repos", []):
        if not repo.get("dirty"):
            continue
        print(
            "[context-task-planning] Dirty repo: "
            f"{repo.get('repo_id') or '(unknown)'} checkout={repo.get('checkout_path') or '.'} "
            f"branch={repo.get('branch') or '-'} staged={repo.get('staged', 0)} "
            f"unstaged={repo.get('unstaged', 0)} untracked={repo.get('untracked', 0)}"
        )
    print(
        f"[context-task-planning] Source task: {result['source_task'].get('slug') or '(unknown)'} "
        f"(source={result['source_task'].get('selection_source') or 'none'})"
    )
    print(
        f"[context-task-planning] Target task: {result['target_task'].get('slug') or '(none)'}"
    )
    print(
        f"[context-task-planning] Switching: {str(result['switching']).lower()} | "
        f"Safe: {str(result['safe']).lower()}"
    )
    if result["reason"]:
        print(f"[context-task-planning] Recommendation: {result['recommendation']}")
        print(f"[context-task-planning] Reason: {result['reason']}")


def run_stash(result: dict) -> None:
    git = result["git"]
    if not git["found"] or not git["dirty"]:
        return

    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                git["root"],
                "stash",
                "push",
                "-u",
                "-m",
                result["stash_message"],
            ],
            check=False,
        )
    except OSError as exc:
        raise SystemExit(f"Failed to stash worktree before switching: {exc}") from exc

    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def print_switch_warning(result: dict) -> None:
    git = result["git"]
    source_task = result["source_task"]
    target_task = result["target_task"]
    recommendation = result["recommendation"]

    print(
        "[context-task-planning] Dirty task repo checkouts detected before switching tasks.",
        file=sys.stderr,
    )
    print(
        "[context-task-planning] Repo changes: "
        f"staged={git['staged']} unstaged={git['unstaged']} untracked={git['untracked']}",
        file=sys.stderr,
    )
    dirty_repos = git.get("dirty_repo_ids", [])
    if dirty_repos:
        print(
            f"[context-task-planning] Dirty repos: {', '.join(dirty_repos)}",
            file=sys.stderr,
        )
    print(
        f"[context-task-planning] Source task: {source_task.get('slug') or '(unknown)'} "
        f"status={source_task.get('status') or '-'} mode={source_task.get('mode') or '-'} "
        f"phase={source_task.get('current_phase') or '-'}",
        file=sys.stderr,
    )
    print(
        f"[context-task-planning] Target task: {target_task.get('slug') or '(none)'}",
        file=sys.stderr,
    )
    if result["reason"]:
        print(
            f"[context-task-planning] Recommended action: {recommendation} — {result['reason']}",
            file=sys.stderr,
        )


def ensure_switch_safety(args: argparse.Namespace) -> None:
    result = check_switch_safety(
        args.cwd, args.source_task, args.target_task, args.session_key
    )

    if result["safe"] or args.allow_dirty:
        return

    if args.stash:
        run_stash(result)
        return

    print_switch_warning(result)

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(
            "[context-task-planning] Retry the switching command with `--stash` to stash all dirty task repos automatically, "
            "commit the current work manually and retry, or use `--allow-dirty` to continue anyway.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    recommendation = result["recommendation"]
    if recommendation == "commit-first":
        choices = [
            ("c", "stop here so you can commit manually (recommended)"),
            ("s", "stash current work and continue switching"),
            ("l", "leave the worktree dirty and continue switching"),
            ("x", "cancel the switch"),
        ]
    else:
        choices = [
            ("s", "stash current work and continue switching (recommended)"),
            ("c", "stop here so you can commit manually"),
            ("l", "leave the worktree dirty and continue switching"),
            ("x", "cancel the switch"),
        ]

    print(
        "[context-task-planning] Choose how to handle the current repo checkouts:",
        file=sys.stderr,
    )
    for key, label in choices:
        print(f"  [{key}] {label}", file=sys.stderr)

    while True:
        response = (
            input("[context-task-planning] Enter choice [s/c/l/x]: ").strip().lower()
        )
        if response == "s":
            run_stash(result)
            return
        if response == "l":
            return
        if response == "c":
            raise SystemExit(
                "Commit the current work manually, then rerun the switching command."
            )
        if response == "x":
            raise SystemExit("Cancelled task switch.")


def compact_current_task(task: dict) -> str:
    if not task["found"]:
        return f"task=(none) source=none action={task.get('recommended_action') or 'init-task'}"
    return (
        f"task={task['slug']} status={task['status'] or '-'} mode={task['mode'] or '-'} "
        f"phase={task['current_phase'] or '-'} source={task['selection_source']} "
        f"role={task.get('binding_role') or '-'} action={task.get('recommended_action') or '-'}"
    )


def format_repo_binding_items(items: list[dict]) -> str:
    if not items:
        return "(none)"
    return ", ".join(
        f"{item['repo_id']} ({item['checkout_path']})"
        for item in items
        if item.get("repo_id")
    )


def print_recommended_commands(commands: list[str]) -> None:
    if not commands:
        print("[context-task-planning] Suggested commands: none")
        return

    print("[context-task-planning] Suggested commands:")
    for command in commands:
        print(f"  - {command}")


def print_resume_candidates(candidates: list[dict]) -> None:
    if not candidates:
        print("[context-task-planning] Resume candidates: none")
        return

    print("[context-task-planning] Resume candidates:")
    for item in candidates:
        print(
            "  - "
            f"{item['slug']} status={item['status']} updated={item.get('updated_at') or '-'} "
            f"title={item.get('title') or '-'}"
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
    print(f"[context-task-planning] Session key: {task['session_key'] or '(none)'}")
    print(
        f"[context-task-planning] Session binding: {task['session_binding'] or '(none)'}"
    )
    print(
        f"[context-task-planning] Active pointer: {task['active_pointer'] or '(none)'}"
    )
    print(f"[context-task-planning] Session pin: {task['session_pin'] or '(none)'}")
    print(f"[context-task-planning] Selected source: {task['selection_source']}")

    if not task["found"]:
        print("[context-task-planning] No active task found.")
        print(
            f"[context-task-planning] Recommended next step: {task.get('recommended_action') or 'init-task'}"
        )
        print(
            f"[context-task-planning] Why: {task.get('recommended_reason') or '(none)'}"
        )
        print_resume_candidates(task.get("resume_candidates", []))
        print_recommended_commands(task.get("recommended_commands", []))
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
    print(
        "[context-task-planning] Access: "
        f"{task.get('binding_role') or '(unbound)'} | writer={task.get('writer_display') or '(none)'} | "
        f"observers={task.get('observer_count', 0)}"
    )
    repo_scope = task.get("repo_scope") or []
    if repo_scope:
        print(
            f"[context-task-planning] Repos: primary={task.get('primary_repo') or '(none)'} | scope={', '.join(repo_scope)}"
        )
    repo_summary = task.get("repo_summary", {})
    if repo_summary.get("shared") or repo_summary.get("worktree"):
        print(
            "[context-task-planning] Repo bindings: "
            f"shared={format_repo_binding_items(repo_summary.get('shared', []))} | "
            f"worktree={format_repo_binding_items(repo_summary.get('worktree', []))}"
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
    print(
        f"[context-task-planning] Recommended next step: {task.get('recommended_action') or 'continue-current-task'}"
    )
    print(f"[context-task-planning] Why: {task.get('recommended_reason') or '(none)'}")
    print_recommended_commands(task.get("recommended_commands", []))


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


def text_matches_any(text: str, patterns: list[str]) -> bool:
    lowered = " ".join(text.lower().split())
    return any(pattern in lowered for pattern in patterns)


def delegate_kind_for_text(text: str) -> str | None:
    lowered = text.lower()
    for kind, patterns in DELEGATE_KIND_PATTERNS:
        if any(pattern in lowered for pattern in patterns):
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


def prepare_delegate_command(text: str, kind: str) -> str:
    normalized = " ".join(text.split()) or default_delegate_title(kind)
    if len(normalized) > 80:
        normalized = normalized[:77].rstrip() + "..."
    script_path = Path(__file__).resolve().with_name("prepare-delegate.sh")
    return f"sh {shlex.quote(str(script_path))} --kind {kind} {shlex.quote(normalized)}"


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


def unique_strings(values: list[str]) -> list[str]:
    seen = set()
    ordered = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


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
    primary_repo = str(task.get("primary_repo") or "") or (
        repos[0]["id"] if repos else ""
    )
    repo_scope = repo_scope_for_payload(task, repos)
    lines = [
        f"[context-task-planning] Current task: {task.get('slug') or '(none)'} | role: {role} | routing: {routing.get('classification') or '-'}",
        "Treat this subagent request as part of the current task only. Do not silently broaden scope.",
        f"Primary repo: {primary_repo or '(none)'}",
        f"Repo scope: {', '.join(repo_scope) if repo_scope else '(none)'}",
        "Repo/worktree bindings:",
    ]
    for repo in repos:
        lines.append(
            f"- {repo['id']}: {repo['binding_mode']} at {repo['checkout_path']}"
        )
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


def subagent_preflight_result(
    cwd: str,
    task_slug: str,
    session_key: str,
    host: str,
    task_text: str,
    tool_name: str,
) -> dict:
    task = resolve_task(cwd, task_slug, session_key)
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
        decision_reason = "task fit looks likely unrelated"
        operator_message = (
            f"[context-task-planning] This Task request looks likely unrelated to the current task `{task.get('slug') or '(none)'}`. "
            "Confirm whether to continue the current task, switch tasks, or initialize a new task before launching a subagent."
        )
    elif classification == "unclear":
        decision_reason = "task fit is unclear"
        operator_message = (
            f"[context-task-planning] Task fit is unclear for `{task.get('slug') or '(none)'}`. "
            "Confirm whether this still belongs to the current task before launching a subagent."
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
            or "task-related request with meaningful repo context and a bounded side-work pattern"
        )
        prompt_prefix = prompt_prefix_for_preflight(task, routing, repos, delegate)
    else:
        decision = "payload_only"
        decision_reason = "task-related request with meaningful repo/worktree context"
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


def print_plan_dir(task: dict) -> None:
    if task.get("found") and task.get("plan_dir"):
        print(task["plan_dir"])


def list_repos_result(workspace_root: Path, plan_root: Path, discover: bool) -> dict:
    registered = read_repo_registry(plan_root)
    discovered = discover_workspace_repos(workspace_root) if discover else []
    registered_paths = {repo["path"] for repo in registered}
    discovered_only = [
        repo for repo in discovered if repo["path"] not in registered_paths
    ]
    return {
        "workspace_root": str(workspace_root),
        "registered": registered,
        "discovered": discovered_only,
    }


def print_list_repos(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(f"[context-task-planning] Workspace: {result['workspace_root']}")
    registered = result.get("registered", [])
    discovered = result.get("discovered", [])

    if registered:
        print("[context-task-planning] Registered repos:")
        for repo in registered:
            print(f"  - {repo['id']}: {repo['path']}")
    else:
        print("[context-task-planning] Registered repos: none")

    if discovered:
        print("[context-task-planning] Discoverable repos (not registered):")
        for repo in discovered:
            print(f"  - {repo['id']}: {repo['path']}")


def task_repo_binding_result(
    plan_root: Path, workspace_root: Path, task_slug: str, repo_id: str
) -> dict:
    bindings = effective_task_repo_bindings(plan_root, workspace_root, task_slug)
    wanted = normalize_repo_id(repo_id)
    for binding in bindings:
        if binding["repo_id"] == wanted:
            return {
                "workspace_root": str(workspace_root),
                "task_slug": task_slug,
                "binding": binding,
            }
    raise SystemExit(f"Repo `{wanted}` is not bound to task `{task_slug}`.")


def print_task_repo_binding(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    binding = result["binding"]
    print(f"[context-task-planning] Task: {result['task_slug']}")
    print(f"[context-task-planning] Repo: {binding['repo_id']}")
    print(
        f"[context-task-planning] Binding: mode={binding['mode']} checkout={binding['checkout_path']} branch={binding.get('branch') or '-'}"
    )


def list_worktrees_result(
    plan_root: Path, workspace_root: Path, task_slug: str = ""
) -> dict:
    rows = explicit_worktree_bindings(plan_root)
    if task_slug:
        rows = [row for row in rows if row["task_slug"] == task_slug]
    return {
        "workspace_root": str(workspace_root),
        "worktrees": rows,
    }


def print_list_worktrees(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(f"[context-task-planning] Workspace: {result['workspace_root']}")
    worktrees = sorted(
        result.get("worktrees", []),
        key=lambda row: (row["task_slug"], row["repo_id"], row["checkout_path"]),
    )
    if not worktrees:
        print("[context-task-planning] Worktrees: none")
        return

    print("[context-task-planning] Worktrees:")
    current_task = ""
    for row in worktrees:
        if row["task_slug"] != current_task:
            current_task = row["task_slug"]
            print(f"  - task={current_task}")
        print(
            "    "
            f"repo={row['repo_id']} path={row['checkout_path']} "
            f"branch={row.get('branch') or '-'}"
        )


def print_repo_isolation_summary(summary: dict) -> None:
    safe_shared = summary.get("safe_shared", [])
    needs_worktree = summary.get("needs_worktree", [])
    already_isolated = summary.get("already_isolated", [])

    print(
        "[context-task-planning] Safe shared repos: "
        f"{format_repo_binding_items(safe_shared)}"
    )

    if needs_worktree:
        print("[context-task-planning] Repos that need a worktree:")
        for item in needs_worktree:
            other_tasks = ", ".join(item.get("other_tasks", [])) or "(unknown)"
            print(
                "  - "
                f"{item['repo_id']} shares `{item['checkout_path']}` with {other_tasks}; "
                f"run `{item['recommended_command']}`"
            )
    else:
        print("[context-task-planning] Repos that need a worktree: none")

    print(
        "[context-task-planning] Already isolated repos: "
        f"{format_repo_binding_items(already_isolated)}"
    )


def render_repo_isolation_error(summary: dict) -> str:
    lines = [
        "Writer isolation required before binding this task.",
        f"[context-task-planning] Safe shared repos: {format_repo_binding_items(summary.get('safe_shared', []))}",
    ]

    needs_worktree = summary.get("needs_worktree", [])
    if needs_worktree:
        lines.append("[context-task-planning] Repos that need a worktree:")
        for item in needs_worktree:
            other_tasks = ", ".join(item.get("other_tasks", [])) or "(unknown)"
            lines.append(
                f"  - {item['repo_id']} shares `{item['checkout_path']}` with {other_tasks}; run `{item['recommended_command']}`"
            )
    else:
        lines.append("[context-task-planning] Repos that need a worktree: none")

    lines.append(
        f"[context-task-planning] Already isolated repos: {format_repo_binding_items(summary.get('already_isolated', []))}"
    )
    return "\n".join(lines)


def handle_list_repos(args: argparse.Namespace) -> None:
    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    result = list_repos_result(workspace_root, plan_root, args.discover)
    print_list_repos(result, args.json)


def handle_register_repo(args: argparse.Namespace) -> None:
    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    entry = register_workspace_repo(plan_root, workspace_root, args.path, args.id)
    print(
        f"[context-task-planning] Registered repo `{entry['id']}` at `{entry['path']}` in workspace `{workspace_root}`"
    )


def handle_set_task_repos(args: argparse.Namespace) -> None:
    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    result = set_task_repo_scope(
        plan_root, workspace_root, args.task.strip(), args.repo, args.primary
    )
    isolation = summarize_repo_isolation(plan_root, workspace_root, result["task_slug"])
    scope_text = ", ".join(result["repo_scope"]) if result["repo_scope"] else "(unset)"
    print(f"[context-task-planning] Task: {result['task_slug']}")
    print(
        f"[context-task-planning] Primary repo: {result['primary_repo'] or '(unset)'}"
    )
    print(f"[context-task-planning] Repo scope: {scope_text}")
    if isolation["has_conflicts"] or isolation.get("already_isolated"):
        print_repo_isolation_summary(isolation)


def handle_task_repo_binding(args: argparse.Namespace) -> None:
    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    result = task_repo_binding_result(
        plan_root, workspace_root, args.task.strip(), args.repo.strip()
    )
    print_task_repo_binding(result, args.json)


def handle_set_task_repo_binding(args: argparse.Namespace) -> None:
    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    result = set_task_repo_binding(
        plan_root,
        workspace_root,
        args.task.strip(),
        args.repo.strip(),
        args.mode,
        args.checkout_path,
        args.branch,
        args.base_branch,
    )
    print(
        f"[context-task-planning] Bound task `{result['task_slug']}` repo `{result['repo_id']}` to {result['mode']} checkout `{result['checkout_path']}`"
    )


def handle_list_worktrees(args: argparse.Namespace) -> None:
    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    result = list_worktrees_result(plan_root, workspace_root, args.task.strip())
    print_list_worktrees(result, args.json)


def bind_session_task(args: argparse.Namespace) -> None:
    session_key = effective_session_key(args.session_key, args.fallback)
    if not session_key:
        raise SystemExit(
            "Session binding requires PLAN_SESSION_KEY or --session-key. Use --fallback for the shared workspace default."
        )

    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    task_slug = args.task.strip()
    role = normalize_role(args.role)
    if not task_slug:
        raise SystemExit("Missing task slug for session binding.")

    plan_dir = plan_root / task_slug
    if not plan_dir.is_dir():
        raise SystemExit(f"Task not found: {plan_dir}")

    if role == ROLE_WRITER:
        isolation = summarize_repo_isolation(
            plan_root, workspace_root, task_slug, session_key
        )
        if isolation["has_conflicts"]:
            raise SystemExit(render_repo_isolation_error(isolation))

    existing_writer = writer_binding_for_task(plan_root, task_slug)
    existing_writer_key = str(existing_writer.get("session_key") or "").strip()

    if (
        role == ROLE_WRITER
        and existing_writer_key
        and existing_writer_key != session_key
        and not args.steal
    ):
        raise SystemExit(
            "Task already has a writer: "
            f"{display_session_key(existing_writer_key)}. "
            "Use --observe to join as an observer or --steal to take over the writer lease."
        )

    if (
        role == ROLE_WRITER
        and existing_writer_key
        and existing_writer_key != session_key
    ):
        demote_writer_binding(plan_root, task_slug)

    write_session_binding(plan_root, session_key, task_slug, role)


def clear_session_task(args: argparse.Namespace) -> None:
    session_key = effective_session_key(args.session_key, args.fallback)
    if not session_key:
        return

    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    clear_session_binding(plan_root, session_key)


def clear_task_sessions(args: argparse.Namespace) -> None:
    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    clear_task_session_bindings(plan_root, args.task.strip())


def check_task_access(args: argparse.Namespace) -> None:
    session_key = effective_session_key(args.session_key, args.fallback)
    if not session_key:
        raise SystemExit(
            "This command needs PLAN_SESSION_KEY or --session-key to enforce task access. Use --fallback for the shared workspace default."
        )

    workspace_root = resolve_workspace_root(args.cwd)
    plan_root = workspace_root / ".planning"
    task_slug = args.task.strip()
    role = binding_role_for_task(plan_root, session_key, task_slug)
    if (
        not role
        and session_key == WORKSPACE_FALLBACK_SESSION_KEY
        and read_active_pointer(plan_root) == task_slug
        and not writer_binding_for_task(plan_root, task_slug)
    ):
        role = ROLE_WRITER

    if not role:
        raise SystemExit(
            f"Session {display_session_key(session_key)} is not bound to task `{task_slug}`."
        )

    if args.require_role == ROLE_WRITER and role != ROLE_WRITER:
        writer = writer_binding_for_task(plan_root, task_slug)
        writer_display = display_session_key(str(writer.get("session_key") or ""))
        raise SystemExit(
            f"Task `{task_slug}` is observe-only for {display_session_key(session_key)}. "
            f"Current writer: {writer_display}. Observers may update delegate lanes but must not edit main planning files."
        )


def main() -> None:
    args = parse_args()

    if args.command == "resolve-workspace-root":
        print(resolve_workspace_root(args.cwd))
        return

    if args.command == "current-task":
        task = resolve_task(args.cwd, args.task, args.session_key)
        print_current_task(task, args.json, args.compact)
        return

    if args.command == "resolve-plan-dir":
        task = resolve_task(args.cwd, args.task, args.session_key)
        print_plan_dir(task)
        return

    if args.command == "subagent-preflight":
        result = subagent_preflight_result(
            args.cwd,
            args.task,
            args.session_key,
            args.host,
            args.task_text,
            args.tool_name,
        )
        print_subagent_preflight(result, args.json, args.text, args.compact)
        return

    if args.command == "check-switch-safety":
        result = check_switch_safety(
            args.cwd, args.source_task, args.target_task, args.session_key
        )
        print_switch_safety(result, args.json, args.compact)
        return

    if args.command == "ensure-switch-safety":
        ensure_switch_safety(args)
        return

    if args.command == "bind-session-task":
        bind_session_task(args)
        return

    if args.command == "clear-session-task":
        clear_session_task(args)
        return

    if args.command == "clear-task-sessions":
        clear_task_sessions(args)
        return

    if args.command == "list-repos":
        handle_list_repos(args)
        return

    if args.command == "register-repo":
        handle_register_repo(args)
        return

    if args.command == "set-task-repos":
        handle_set_task_repos(args)
        return

    if args.command == "task-repo-binding":
        handle_task_repo_binding(args)
        return

    if args.command == "set-task-repo-binding":
        handle_set_task_repo_binding(args)
        return

    if args.command == "list-worktrees":
        handle_list_worktrees(args)
        return

    if args.command == "check-task-access":
        check_task_access(args)
        return

    prompt = args.prompt or sys.stdin.read()
    task = resolve_task(args.cwd, args.task, args.session_key)
    result = classify_drift(prompt, task)
    print_drift(result, args.json, args.compact)


if __name__ == "__main__":
    main()
