# Changelog

All notable changes to this project are documented here.

## [Unreleased]

## [0.4.3] - 2026-05-03

### Removed
- Removed context compression feature designed for 4K-8K token models, now obsolete for modern 256K-1M token models. Deleted compact_context.py (1103 lines), compact_sync.py (196 lines), and related hooks/scripts, simplifying 15+ integration points.

### Changed
- Refactored task_guard.py (2000+ lines) into modular components: constants.py, file_lock.py, file_utils.py, repo_registry.py, and session_binding.py for better maintainability and testability.
- Fixed POSIX sh compatibility in prepare-task-worktree.sh by removing non-portable flock file descriptor syntax, relying on Python-level fcntl.flock() instead.

### Added
- Added unit tests for core modules (constants, file_lock, file_utils, repo_registry, session_binding) with 100+ test cases.
- Added pyproject.toml for pytest configuration.

## [0.4.2] - 2026-04-30

### Changed
- Updated `task-init` contracts across TraeCLI/Coco, OpenCode, and bundled task-entry skills so inferred task creation now previews both the candidate title and candidate slug before confirmation.
- Standardized `task-init` guidance to pass explicit `--title` and `--slug` values into `init-task.sh`, while keeping slug recomputation and normalization rules aligned with `slugify.sh`.
- Refreshed README and host-specific onboarding/docs so task creation consistently documents title/slug confirmation instead of title-only confirmation.

### Added
- Added smoke-test coverage to catch regressions in `task-init` contract text and to verify custom slug overrides preserve the user-facing title while normalizing the planning directory slug.

## [0.4.1] - 2026-04-29

### Changed
- Reduced task-drift false positives by treating `unclear` as non-conclusive route evidence and leaving normal user turns quiet.
- Changed host hooks to inject route evidence only for high-signal `likely-unrelated` prompts, while preserving session-start recovery and native-`Task` preflight context.
- Removed OpenCode drift toasts so the main LLM can decide whether to ask the user from conversation context.

## [0.4.0] - 2026-04-29

### Added
- Added TraeCLI/Coco plugin support with `coco.yaml`, bundled slash commands, a Trae-visible main skill entry, and lifecycle hooks under `skill/trae-hooks/`.
- Added `smoke-test-trae-plugin.sh` to validate Trae/Coco plugin paths, command files, hook scripts, and plugin-root command guidance.
- Added TraeCLI/Coco setup and troubleshooting documentation.

### Changed
- Extended the supported-host positioning from Claude Code, OpenCode, and Codex to include TraeCLI/Coco while keeping `skill/scripts/` as the shared runtime.
- Claude plugin skill paths now list the bundled task-entry skills explicitly so the Trae-visible main skill entry does not create a duplicate Claude skill.

## [0.3.0] - 2026-04-29

### Added
- Added Claude Code plugin packaging with `.claude-plugin/plugin.json` and a self-hosted marketplace catalog.
- Added plugin-scoped Claude lifecycle hooks under `skill/claude-hooks/hooks.json`.
- Added `smoke-test-claude-plugin.sh` to validate plugin metadata, hook paths, and plugin-root command guidance.
- Added `AGENTS.md` as the shared project instruction file and linked `CLAUDE.md` to it.
- Added version metadata, changelog, release-note extraction, version checks, and a GitHub Action for automatic tags and releases.

### Changed
- Recommended Claude Code installation now uses the plugin and marketplace path, while standalone skill installation remains available for fallback and other hosts.
- Claude task-entry skills now prefer plugin-bundled core scripts and fall back to standalone skill or repo-local paths.
- Claude hook guidance now uses plugin-root-aware command paths when running from a plugin install.

### Docs
- Updated Claude, onboarding, sharing, design, and adapter docs for the plugin distribution model and release discipline.
