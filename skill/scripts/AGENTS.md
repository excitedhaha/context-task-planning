# AGENTS.md

## Scope
- This directory is the shared runtime core for `context-task-planning`.
- Shell wrappers are the public entry points; Python modules hold reusable decisions and persistence helpers.
- Keep host-specific behavior out of this directory unless it is only formatting an existing shared result.

## Module Boundaries
- `task_guard.py`: CLI facade and command handlers. Keep argument parsing, command orchestration, and user-facing output here; move reusable logic into focused modules.
- `task_text.py`: prompt complexity, term extraction, text matching, and delegate command text helpers.
- `spec_context.py`: spec context normalization, linked-provider detection, brief quality, candidate refs, and spec display helpers.
- `task_drift.py`: route-evidence classification and drift output formatting.
- `task_preflight.py`: native `Task` preflight decisions, repo payload formatting, delegate escalation, and preflight output formatting.
- `session_binding.py`: session key resolution, writer/observer bindings, binding migration compatibility, and session persistence.
- `repo_registry.py`: workspace repo registry, task repo binding overrides, repo discovery, and workspace-relative path helpers.
- `file_utils.py` and `file_lock.py`: atomic writes and concurrency primitives. Reuse them for new writes instead of open-coded file replacement.
- `constants.py`: shared literals and regexes used by multiple modules. Avoid scattering duplicate keyword lists in adapters.

## Development Rules
- Preserve shell command names, flags, exit behavior, and JSON field names unless the user explicitly asks for a breaking change.
- Do not duplicate drift, preflight, delegate, spec, session, repo, or worktree heuristics in host adapters; expose or reuse a shared function instead.
- Prefer moving pure logic into `task_text.py`, `spec_context.py`, `task_drift.py`, or `task_preflight.py` before adding more code to `task_guard.py`.
- Keep dependency direction simple: low-level helpers and constants first, then text/spec/drift/preflight modules, then `task_guard.py` as the facade.
- Avoid circular imports. If a helper would introduce a cycle, move it to the lowest module that can own it cleanly.
- Use `write_json_file`, `atomic_write_json`, or existing locked write helpers for runtime state changes.
- Keep generated or local runtime state out of commits: `.planning/`, `.worktrees/`, hook caches, and `__pycache__/` are not source files.

## Tests And Verification
- Add or update pytest coverage when changing reusable Python decisions, especially `resolve_task`, drift classification, spec context detection, preflight decisions, and session/repo binding behavior.
- For Python changes, run `python3 -m py_compile skill/scripts/*.py skill/claude-hooks/scripts/*.py skill/codex-hooks/scripts/*.py skill/trae-hooks/scripts/*.py`.
- For shell wrapper changes, run `for f in skill/scripts/*.sh; do sh -n "$f"; done`.
- For behavior that affects CLI guidance, repo/worktree routing, or host adapters, run the matching smoke tests under `skill/scripts/`.
- If the environment has `PLAN_SESSION_KEY` set, clear it for tests that assume no active session, for example `PLAN_SESSION_KEY= uvx --with pytest pytest`.
