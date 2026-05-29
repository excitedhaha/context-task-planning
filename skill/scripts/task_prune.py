#!/usr/bin/env python3

import json
import re
import shutil
from hashlib import sha256
from pathlib import Path

from file_lock import file_lock, lock_path_for
from file_utils import atomic_write_json, atomic_write_text
from session_binding import utc_now


PROGRESS_WARN_LINES = 500
PROGRESS_WARN_BYTES = 64 * 1024
PROGRESS_RECOMMEND_LINES = 2000
PROGRESS_RECOMMEND_BYTES = 128 * 1024
PROGRESS_RECOMMEND_SESSIONS = 100
PROGRESS_STRONG_LINES = 5000
PROGRESS_STRONG_BYTES = 256 * 1024
PROGRESS_READ_GUARD_LINES = 10000
PROGRESS_READ_GUARD_BYTES = 512 * 1024

DEFAULT_KEEP_SESSIONS = 60
MANIFEST_SCHEMA_VERSION = "1.0.0"

NOISE_PATTERNS = (
    re.compile(r"Handled the latest OpenCode task turn", re.IGNORECASE),
    re.compile(r"^\s*- Tools:\s*", re.IGNORECASE),
    re.compile(r"^\s*- (?:Ran )?.*\.planning/[^\s`]+/(?:progress\.md|state\.json)"),
    re.compile(r"\*\*(?:Considering|Analyzing|Planning|Updating|Inspecting|Fixing)\b"),
)


def as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def task_derived_dir(plan_dir: Path) -> Path:
    return plan_dir / ".derived"


def prune_root(plan_dir: Path) -> Path:
    return task_derived_dir(plan_dir) / "prune"


def progress_path_for(plan_dir: Path) -> Path:
    return plan_dir / "progress.md"


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_sha256(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def path_stats(path: Path) -> dict:
    try:
        stat = path.stat()
    except OSError:
        return {
            "exists": False,
            "bytes": 0,
            "mtime_ns": 0,
            "sha256": "",
        }
    return {
        "exists": True,
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": file_sha256(path),
    }


def read_stable_text_with_stats(path: Path) -> tuple[str, dict]:
    try:
        before = path.stat()
    except OSError as exc:
        raise SystemExit(f"Could not stat {path}: {exc}")
    text = path.read_text(encoding="utf-8")
    try:
        after = path.stat()
    except OSError as exc:
        raise SystemExit(f"Could not stat {path}: {exc}")
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise SystemExit(
            "progress.md changed while preparing context-prune. Re-run --prepare."
        )
    return text, {
        "exists": True,
        "bytes": after.st_size,
        "mtime_ns": after.st_mtime_ns,
        "sha256": text_sha256(text),
    }


def progress_session_log_bounds(lines: list[str]) -> tuple[int, int, int]:
    heading = -1
    for index, line in enumerate(lines):
        if line.startswith("## Session Log"):
            heading = index
            break
    if heading < 0:
        return -1, -1, -1

    body_start = heading + 1
    end = len(lines)
    for index in range(body_start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return heading, body_start, end


def progress_session_blocks(lines: list[str]) -> list[tuple[int, int]]:
    _heading, body_start, body_end = progress_session_log_bounds(lines)
    if body_start < 0:
        return []

    starts = [
        index
        for index in range(body_start, body_end)
        if lines[index].startswith("### Session:")
    ]
    blocks: list[tuple[int, int]] = []
    for offset, start in enumerate(starts):
        end = starts[offset + 1] if offset + 1 < len(starts) else body_end
        blocks.append((start, end))
    return blocks


def remove_level2_section(lines: list[str], heading: str) -> list[str]:
    start = -1
    for index, line in enumerate(lines):
        if line.strip() == heading:
            start = index
            break
    if start < 0:
        return lines

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    while start > 0 and lines[start - 1] == "":
        start -= 1
    return lines[:start] + lines[end:]


def progress_metrics(progress_path: Path) -> dict:
    stats = path_stats(progress_path)
    if not stats["exists"]:
        return {
            **stats,
            "lines": 0,
            "session_count": 0,
            "noise_line_count": 0,
            "noise_ratio": 0.0,
            "session_log_found": False,
        }

    lines = progress_path.read_text(encoding="utf-8").splitlines()
    blocks = progress_session_blocks(lines)
    noise_line_count = sum(
        1 for line in lines if any(pattern.search(line) for pattern in NOISE_PATTERNS)
    )
    line_count = len(lines)
    return {
        **stats,
        "lines": line_count,
        "session_count": len(blocks),
        "noise_line_count": noise_line_count,
        "noise_ratio": round(noise_line_count / line_count, 3) if line_count else 0.0,
        "session_log_found": bool(blocks),
    }


def prune_risk_for_metrics(metrics: dict) -> tuple[str, list[str]]:
    reasons: list[str] = []
    line_count = int(metrics.get("lines") or 0)
    byte_count = int(metrics.get("bytes") or 0)
    session_count = int(metrics.get("session_count") or 0)

    if line_count >= PROGRESS_READ_GUARD_LINES:
        reasons.append(
            f"progress.md is {line_count} lines (>= {PROGRESS_READ_GUARD_LINES})"
        )
    if byte_count >= PROGRESS_READ_GUARD_BYTES:
        reasons.append(
            f"progress.md is {byte_count} bytes (>= {PROGRESS_READ_GUARD_BYTES})"
        )
    if reasons:
        return "read_guard", reasons

    if line_count >= PROGRESS_STRONG_LINES:
        reasons.append(
            f"progress.md is {line_count} lines (>= {PROGRESS_STRONG_LINES})"
        )
    if byte_count >= PROGRESS_STRONG_BYTES:
        reasons.append(
            f"progress.md is {byte_count} bytes (>= {PROGRESS_STRONG_BYTES})"
        )
    if reasons:
        return "strongly_recommend", reasons

    if line_count >= PROGRESS_RECOMMEND_LINES:
        reasons.append(
            f"progress.md is {line_count} lines (>= {PROGRESS_RECOMMEND_LINES})"
        )
    if byte_count >= PROGRESS_RECOMMEND_BYTES:
        reasons.append(
            f"progress.md is {byte_count} bytes (>= {PROGRESS_RECOMMEND_BYTES})"
        )
    if session_count >= PROGRESS_RECOMMEND_SESSIONS:
        reasons.append(
            f"progress.md has {session_count} sessions (>= {PROGRESS_RECOMMEND_SESSIONS})"
        )
    if reasons:
        return "recommend_prune", reasons

    if line_count >= PROGRESS_WARN_LINES:
        reasons.append(f"progress.md is {line_count} lines (>= {PROGRESS_WARN_LINES})")
    if byte_count >= PROGRESS_WARN_BYTES:
        reasons.append(
            f"progress.md is {byte_count} bytes (>= {PROGRESS_WARN_BYTES})"
        )
    if reasons:
        return "warn", reasons

    return "ok", []


def context_prune_status(plan_dir: Path, keep_sessions: int = DEFAULT_KEEP_SESSIONS) -> dict:
    plan_dir = Path(plan_dir)
    task_slug = plan_dir.name
    progress_path = progress_path_for(plan_dir)
    metrics = progress_metrics(progress_path)
    risk, reasons = prune_risk_for_metrics(metrics)
    session_count = int(metrics.get("session_count") or 0)
    prunable_sessions = max(0, session_count - max(0, keep_sessions))

    return {
        "ok": True,
        "task_slug": task_slug,
        "plan_dir": str(plan_dir),
        "progress_path": str(progress_path),
        "risk": risk,
        "reasons": reasons,
        "metrics": metrics,
        "keep_sessions": keep_sessions,
        "prunable_sessions": prunable_sessions,
        "recommended_action": "prepare_prune" if prunable_sessions else "none",
        "recommended_command": (
            f"sh skill/scripts/context-prune.sh --task {task_slug} --prepare"
            if prunable_sessions
            else ""
        ),
    }


def safe_run_id(timestamp: str) -> str:
    text = timestamp.replace("-", "").replace(":", "")
    text = text.replace(".", "").replace("+0000", "Z").replace("+00:00", "Z")
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "prune"


def context_prune_hint(status: dict) -> str:
    risk = str(status.get("risk") or "ok")
    if risk not in {"recommend_prune", "strongly_recommend", "read_guard"}:
        return ""
    task_slug = str(status.get("task_slug") or "")
    metrics = as_dict(status.get("metrics"))
    line_count = int(metrics.get("lines") or 0)
    session_count = int(metrics.get("session_count") or 0)
    command = str(status.get("recommended_command") or "").strip()
    command_text = f" Run `{command}` to prepare a model-reviewed prune." if command else ""
    return (
        f"[context-task-planning] Task `{task_slug}` has a large `progress.md` "
        f"({line_count} lines, {session_count} sessions; risk={risk}).{command_text} "
        "Do not read the full progress log unless the archived history is needed."
    )


def build_prune_brief(
    plan_dir: Path,
    status: dict,
    keep_sessions: int,
    pruned_start_line: int,
    pruned_end_line: int,
) -> str:
    task_slug = plan_dir.name
    metrics = as_dict(status.get("metrics"))
    prunable_sessions = int(status.get("prunable_sessions") or 0)
    return "\n".join(
        [
            f"# Context Prune Brief: {task_slug}",
            "",
            "Summarize the older `progress.md` session history so the coordinator can prune the source file without losing recoverable task context.",
            "",
            "## Source",
            "",
            f"- Progress file: `.planning/{task_slug}/progress.md`",
            f"- Total lines: {metrics.get('lines', 0)}",
            f"- Total sessions: {metrics.get('session_count', 0)}",
            f"- Keep newest sessions: {keep_sessions}",
            f"- Summarize older sessions: {prunable_sessions}",
            f"- Suggested source range: lines {pruned_start_line}-{pruned_end_line}",
            "",
            "## Preserve In Summary",
            "",
            "- User decisions and explicit scope changes",
            "- Verification commands and failures",
            "- Blockers, unresolved risks, rollback notes, commits, branches, PRs, or deployment notes",
            "- Durable implementation milestones not already captured by `task_plan.md`, `findings.md`, checkpoints, or handoff notes",
            "",
            "## Safe To Omit",
            "",
            "- Repeated planning-file self-sync entries",
            "- Tool-only notes with no durable outcome",
            "- Failed patch/read attempts that were immediately corrected and left no lasting decision",
            "- Model reasoning prose such as `Considering...` / `Analyzing...` notes",
            "",
            "## Required Output",
            "",
            "Write a concise markdown summary file with these headings:",
            "",
            "- `### Timeline Summary`",
            "- `### Preserved Decisions`",
            "- `### Preserved Verification`",
            "- `### Preserved Risks And Blockers`",
            "- `### Omitted Noise`",
            "",
            "Then apply with:",
            "",
            f"`sh skill/scripts/context-prune.sh --task {task_slug} --apply --summary-file <summary.md>`",
            "",
        ]
    )


def prepare_context_prune(plan_dir: Path, keep_sessions: int = DEFAULT_KEEP_SESSIONS) -> dict:
    plan_dir = Path(plan_dir)
    progress_path = progress_path_for(plan_dir)
    if not progress_path.exists():
        raise SystemExit(f"Missing progress.md: {progress_path}")

    lock_path = lock_path_for(progress_path, plan_dir.parent)
    with file_lock(lock_path):
        original_text, source_stats = read_stable_text_with_stats(progress_path)
    lines = original_text.splitlines()
    blocks = progress_session_blocks(lines)
    if not blocks:
        raise SystemExit("progress.md has no recognizable Session Log entries to prune")

    keep_sessions = max(1, keep_sessions)
    prunable_sessions = max(0, len(blocks) - keep_sessions)
    if prunable_sessions <= 0:
        raise SystemExit(
            f"Nothing to prune: progress.md has {len(blocks)} sessions and keep_sessions={keep_sessions}"
        )

    pruned_start, pruned_end = blocks[keep_sessions][0], blocks[-1][1]
    status = context_prune_status(plan_dir, keep_sessions=keep_sessions)
    created_at = utc_now()
    run_id = safe_run_id(created_at)
    root = prune_root(plan_dir)
    run_dir = root / run_id
    suffix = 2
    while run_dir.exists():
        run_dir = root / f"{run_id}-{suffix}"
        suffix += 1
    run_id = run_dir.name
    run_dir.mkdir(parents=True, exist_ok=False)

    brief_path = run_dir / "brief.md"
    manifest_path = run_dir / "manifest.json"
    summary_path = run_dir / "summary.md"
    archive_path = run_dir / "progress.original.md"
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "operation": "context-prune",
        "status": "prepared",
        "task_slug": plan_dir.name,
        "created_at": created_at,
        "updated_at": created_at,
        "run_id": run_id,
        "plan_dir": str(plan_dir),
        "progress_path": str(progress_path),
        "keep_sessions": keep_sessions,
        "source": {
            **source_stats,
            "lines": len(lines),
            "session_count": len(blocks),
        },
        "pruned_range": {
            "start_line": pruned_start + 1,
            "end_line": pruned_end,
            "session_count": prunable_sessions,
        },
        "files": {
            "brief": str(brief_path),
            "summary_expected": str(summary_path),
            "archive": str(archive_path),
            "manifest": str(manifest_path),
        },
    }
    atomic_write_text(
        brief_path,
        build_prune_brief(
            plan_dir,
            status,
            keep_sessions,
            pruned_start + 1,
            pruned_end,
        ),
    )
    atomic_write_json(manifest_path, manifest)
    return {"ok": True, "action": "prepared", **manifest}


def latest_manifest_path(plan_dir: Path) -> Path | None:
    root = prune_root(plan_dir)
    if not root.is_dir():
        return None
    candidates = [path for path in root.glob("*/manifest.json") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime_ns)


def load_manifest(plan_dir: Path, manifest_path: Path | None = None) -> tuple[Path, dict]:
    resolved = manifest_path or latest_manifest_path(plan_dir)
    if resolved is None:
        raise SystemExit("No context-prune manifest found. Run --prepare first.")
    try:
        manifest = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not read context-prune manifest: {resolved}: {exc}")
    if not isinstance(manifest, dict) or manifest.get("operation") != "context-prune":
        raise SystemExit(f"Invalid context-prune manifest: {resolved}")
    validate_manifest_for_plan_dir(plan_dir, resolved, manifest)
    return resolved, manifest


def validate_manifest_for_plan_dir(
    plan_dir: Path, manifest_path: Path, manifest: dict
) -> None:
    plan_dir = plan_dir.resolve()
    manifest_path = manifest_path.resolve()
    expected_root = prune_root(plan_dir).resolve()
    if not path_is_within(manifest_path, expected_root):
        raise SystemExit(
            f"context-prune manifest must be under the current task prune directory: {expected_root}"
        )
    if manifest_path.name != "manifest.json":
        raise SystemExit("context-prune manifest path must end with manifest.json")

    run_id = str(manifest.get("run_id") or "").strip()
    if run_id and manifest_path.parent.name != run_id:
        raise SystemExit("context-prune manifest run_id does not match its directory")
    if str(manifest.get("task_slug") or "") != plan_dir.name:
        raise SystemExit("context-prune manifest does not belong to the current task")

    manifest_plan_dir = str(manifest.get("plan_dir") or "").strip()
    if manifest_plan_dir and Path(manifest_plan_dir).resolve() != plan_dir:
        raise SystemExit("context-prune manifest plan_dir does not match the current task")

    manifest_progress = str(manifest.get("progress_path") or "").strip()
    if manifest_progress and Path(manifest_progress).resolve() != progress_path_for(plan_dir).resolve():
        raise SystemExit("context-prune manifest progress_path does not match the current task")

    files = as_dict(manifest.get("files"))
    for key in ("brief", "summary_expected", "archive", "manifest"):
        value = str(files.get(key) or "").strip()
        if value and not path_is_within(Path(value), manifest_path.parent):
            raise SystemExit(
                f"context-prune manifest file `{key}` must stay inside its prune run directory"
            )


def assert_source_unchanged(progress_path: Path, manifest: dict) -> None:
    source = as_dict(manifest.get("source"))
    expected_sha = str(source.get("sha256") or "")
    expected_mtime = int(source.get("mtime_ns") or 0)
    expected_bytes = int(source.get("bytes") or 0)
    current = path_stats(progress_path)
    if (
        current.get("sha256") != expected_sha
        or int(current.get("mtime_ns") or 0) != expected_mtime
        or int(current.get("bytes") or 0) != expected_bytes
    ):
        raise SystemExit(
            "progress.md changed since context-prune --prepare. Re-run --prepare before applying."
        )


def normalize_summary_text(summary_path: Path) -> str:
    if not summary_path.exists():
        raise SystemExit(f"Summary file not found: {summary_path}")
    text = summary_path.read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit(f"Summary file is empty: {summary_path}")
    return text


def build_pruned_progress(
    lines: list[str],
    keep_sessions: int,
    summary_text: str,
    archive_display_path: str,
    manifest: dict,
    applied_at: str,
) -> str:
    heading, body_start, body_end = progress_session_log_bounds(lines)
    if heading < 0:
        raise SystemExit("progress.md is missing `## Session Log`")
    blocks = progress_session_blocks(lines)
    if len(blocks) <= keep_sessions:
        raise SystemExit(
            f"Nothing to prune: progress.md has {len(blocks)} sessions and keep_sessions={keep_sessions}"
        )

    new_lines = lines[: heading + 1]
    new_lines.append("")
    for start, end in blocks[:keep_sessions]:
        block = lines[start:end]
        while block and block[-1] == "":
            block = block[:-1]
        new_lines.extend(block)
        new_lines.append("")

    source = as_dict(manifest.get("source"))
    pruned_range = as_dict(manifest.get("pruned_range"))
    summary_lines = [
        "## Pruned History Summary",
        "",
        f"- Pruned At: `{applied_at}`",
        f"- Source Archive: `{archive_display_path}`",
        f"- Original SHA256: `{source.get('sha256', '')}`",
        f"- Original Sessions: {source.get('session_count', 0)}",
        f"- Pruned Sessions: {pruned_range.get('session_count', 0)}",
        f"- Kept Recent Sessions: {keep_sessions}",
        "",
    ]
    summary_lines.extend(summary_text.splitlines())
    summary_lines.append("")

    post_sections = remove_level2_section(lines[body_end:], "## Pruned History Summary")
    while post_sections and post_sections[0] == "":
        post_sections = post_sections[1:]
    new_lines.extend(summary_lines)
    new_lines.extend(post_sections)
    return "\n".join(new_lines).rstrip() + "\n"


def apply_context_prune(
    plan_dir: Path,
    summary_path: Path,
    manifest_path: Path | None = None,
) -> dict:
    plan_dir = Path(plan_dir)
    progress_path = progress_path_for(plan_dir)
    resolved_manifest_path, manifest = load_manifest(plan_dir, manifest_path)
    keep_sessions = int(manifest.get("keep_sessions") or DEFAULT_KEEP_SESSIONS)
    summary_text = normalize_summary_text(summary_path)
    files = as_dict(manifest.get("files"))
    archive_path = Path(str(files.get("archive") or ""))
    if not archive_path:
        raise SystemExit("context-prune manifest is missing archive path")

    lock_path = lock_path_for(progress_path, plan_dir.parent)
    with file_lock(lock_path):
        assert_source_unchanged(progress_path, manifest)
        original_text = progress_path.read_text(encoding="utf-8")
        lines = original_text.splitlines()
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        if archive_path.exists():
            raise SystemExit(f"Archive already exists: {archive_path}")
        atomic_write_text(archive_path, original_text)
        applied_at = utc_now()
        archive_display_path = f".planning/{plan_dir.name}/.derived/prune/{manifest.get('run_id')}/progress.original.md"
        pruned_text = build_pruned_progress(
            lines,
            keep_sessions,
            summary_text,
            archive_display_path,
            manifest,
            applied_at,
        )
        atomic_write_text(progress_path, pruned_text)

        manifest["status"] = "applied"
        manifest["updated_at"] = applied_at
        manifest["applied_at"] = applied_at
        manifest["summary_file"] = str(summary_path)
        manifest["archive"] = {
            **path_stats(archive_path),
            "path": str(archive_path),
        }
        manifest["result"] = {
            **path_stats(progress_path),
            "lines": len(pruned_text.splitlines()),
            "session_count": len(progress_session_blocks(pruned_text.splitlines())),
        }
        atomic_write_json(resolved_manifest_path, manifest)
    return {"ok": True, "action": "applied", "manifest_path": str(resolved_manifest_path), **manifest}


def restore_context_prune(plan_dir: Path, manifest_path: Path | None = None) -> dict:
    plan_dir = Path(plan_dir)
    progress_path = progress_path_for(plan_dir)
    resolved_manifest_path, manifest = load_manifest(plan_dir, manifest_path)
    archive = as_dict(manifest.get("archive"))
    files = as_dict(manifest.get("files"))
    archive_path = Path(str(archive.get("path") or files.get("archive") or ""))
    if not archive_path.exists():
        raise SystemExit(f"Archive not found: {archive_path}")

    lock_path = lock_path_for(progress_path, plan_dir.parent)
    with file_lock(lock_path):
        restored_at = utc_now()
        archive_text = archive_path.read_text(encoding="utf-8")
        backup_path = resolved_manifest_path.parent / f"progress.before-restore.{safe_run_id(restored_at)}.md"
        if progress_path.exists():
            shutil.copyfile(progress_path, backup_path)
        atomic_write_text(progress_path, archive_text)
        manifest["status"] = "restored"
        manifest["updated_at"] = restored_at
        manifest["restored_at"] = restored_at
        manifest["restore_backup"] = str(backup_path)
        atomic_write_json(resolved_manifest_path, manifest)
    return {"ok": True, "action": "restored", "manifest_path": str(resolved_manifest_path), **manifest}


def format_prune_status(status: dict, compact: bool = False) -> str:
    metrics = as_dict(status.get("metrics"))
    if compact:
        return (
            f"prune={status.get('risk')} lines={metrics.get('lines', 0)} "
            f"bytes={metrics.get('bytes', 0)} sessions={metrics.get('session_count', 0)} "
            f"prunable={status.get('prunable_sessions', 0)}"
        )
    lines = [
        f"[context-task-planning] Context prune status for `{status.get('task_slug')}`: {status.get('risk')}",
        f"[context-task-planning] progress.md: {metrics.get('lines', 0)} lines, {metrics.get('bytes', 0)} bytes, {metrics.get('session_count', 0)} sessions",
        f"[context-task-planning] Noise estimate: {metrics.get('noise_line_count', 0)} lines ({metrics.get('noise_ratio', 0.0)})",
        f"[context-task-planning] Prunable sessions with keep_sessions={status.get('keep_sessions')}: {status.get('prunable_sessions')}",
    ]
    for reason in status.get("reasons") or []:
        lines.append(f"[context-task-planning] Reason: {reason}")
    command = str(status.get("recommended_command") or "").strip()
    if command:
        lines.append(f"[context-task-planning] Suggested command: {command}")
    return "\n".join(lines)
