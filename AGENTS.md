# AGENTS.md

## Project
- `context-task-planning` is a shell-first, file-backed skill for long-running AI coding tasks.
- Shared truth lives in `skill/scripts/` and local task state under `.planning/<slug>/`.
- Keep routing, drift, repo, and worktree logic in the shared core, mainly `skill/scripts/task_guard.py` and `skill/scripts/*.sh`.
- Host integrations in `skill/claude-hooks/` and `skill/opencode-plugin/` are thin adapters, not alternate sources of truth.

## Key Files
- `README.md`: positioning and quickstart
- `VERSION`, `CHANGELOG.md`: release source of truth and release notes
- `.claude-plugin/plugin.json`: Claude Code plugin manifest
- `.github/workflows/release.yml`: automatic tag and GitHub Release workflow
- `docs/onboarding.md`: user workflow
- `docs/design.md`: architecture and invariants
- `skill/reference.md`: command contract
- `docs/claude.md`, `docs/opencode.md`, `docs/codex.md`: host-specific notes

## Working Rules
- Prefer minimal changes and preserve the shell-first workflow.
- If behavior changes, update the matching docs in the same change.
- Do not duplicate shared logic in host-specific adapters.
- Do not commit local state under `.planning/`, `.worktrees/`, `.claude/`, `.codex/`, or `.opencode/` unless explicitly asked.

## Release Discipline
- Treat user-visible, install/distribution, workflow, hook, script, or doc behavior changes as release-bearing changes.
- Maintain version metadata and release notes in the same change when release files exist: keep `VERSION`, `skill/SKILL.md` `metadata.version`, and `.claude-plugin/plugin.json` `version` in sync.
- Maintain `CHANGELOG.md` using an `Unreleased` section plus dated version sections; GitHub release notes should be derived from the released version section.
- Do not create tags or GitHub releases manually unless explicitly requested. The GitHub Action owns automatic tag and release creation after the version/changelog change lands.

## Verify
- Doc-only changes: reread the touched markdown and keep it concise.
- Script changes: `for f in skill/scripts/*.sh; do sh -n "$f"; done`
- Claude hook changes: `python3 -m py_compile skill/claude-hooks/scripts/*.py`
- Workflow changes: run the relevant smoke test plus `sh skill/scripts/validate-task.sh`
