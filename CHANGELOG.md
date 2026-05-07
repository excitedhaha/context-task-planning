# Changelog

All notable changes to this project are documented here.

## [Unreleased]

## [0.7.1] - 2026-05-07

### Fixed
- Fixed Codex plugin hooks.json to use plugin directory path instead of skills directory path.

## [0.7.0] - 2026-05-06

### Added
- Added `.codex-plugin/` directory with `plugin.json` and `hooks.json` for complete Codex plugin support.
- Added `smoke-test-codex-plugin.sh` to validate Codex plugin structure and configuration.

### Changed
- Codex install is now a single plugin command (`codex plugin install`) instead of two-step skill + hook package install.
- Updated all docs (`README.md`, `docs/codex.md`, `docs/sharing.md`, `skill/SKILL.md`, `skill/reference.md`, `skill/codex-hooks/README.md`) to recommend Codex plugin install.
- Extended `check-version.sh` to validate `.codex-plugin/plugin.json` version.

### Removed
- Removed standalone `hooks/context-task-planning/` hook package (replaced by bundled plugin hooks).
- Removed `skill/codex-hooks/config.example.toml` manual fallback (no longer needed with plugin install).
- Removed `skill/scripts/smoke-test-codex-hook-package.sh` (replaced by plugin smoke test).

## [0.6.0] - 2026-05-03

### Added
- Published `context-task-planning-opencode` npm package for native `opencode plugin context-task-planning-opencode --global` install.
- Added `resolveSkillRoot()` to OpenCode plugin: dynamically discovers skill scripts at env override, legacy symlink, global OpenCode, project-local, or ancestor directory locations (previously hardcoded `../`).
- Added `autoInstallCommands()` to OpenCode plugin: npm package auto-installs slash commands to `~/.config/opencode/commands/` on first load using `{{SKILL_SCRIPTS_DIR}}` template resolution.
- Added `PLUGIN_VERSION` constant to `task-focus-guard.js` for runtime version identification.
- Added graceful degradation when skill scripts are not found: all hook handlers become no-ops, and a toast with install instructions is shown on first session creation.
- Added OpenCode plugin and npm package smoke tests to CI release workflow.
- Added npm publish step to CI release workflow using OIDC trusted publishers (no NPM_TOKEN needed).
- Added `--force` and `--uninstall` flags to `install-opencode-plugin.sh` and `install-opencode-commands.sh`.
- Added `--force` flag passthrough to `install-macos.sh`.
- Extended `check-version.sh` to validate OpenCode plugin `PLUGIN_VERSION` and command file existence.

### Changed
- OpenCode install is now two steps (`npx skills add` + `opencode plugin`) instead of three (symlink scripts are deprecated).
- Updated all docs (`README.md`, `docs/opencode.md`, `docs/onboarding.md`, `docs/sharing.md`, `skill/SKILL.md`, `skill/reference.md`) to recommend `opencode plugin` and mark symlink scripts as legacy.

## [0.5.0] - 2026-05-03

### Changed
- Migrated Claude Code subagent context injection from `PreToolUse` additionalContext to `SubagentStart` additionalContext, so task context appears at the start of the subagent conversation rather than next to the tool call result.
- Simplified `PreToolUse` on Task to only handle `delegate_required` gating; context injection is now handled by `SubagentStart`.
- Replaced `delegate_hint_for_text` with `delegate_hint_from_preflight` across all hosts, using the preflight result's `delegate.kind` and `delegate.command` as the single source of truth instead of duplicating the keyword classification logic from `task_guard.py`.
- Cleaned up unused `delegate_hint_for_text` imports from `user_prompt_submit.py` across Claude, Trae, and Codex hooks.

### Added
- Added `SubagentStart` hook to Claude Code hooks.json with `subagent_start.py` that injects task state and prompt prefix into newly spawned subagents.
- Added `pre_tool_ask_payload` for Claude Code `PreToolUse` responses that use `permissionDecision: "ask"` to surface confirmation dialogs.
- Added `delegate_required` blocking in Claude Code `PreToolUse`: when preflight returns `delegate_required`, the user must confirm before the Task/Agent tool proceeds.
- Added delegate command hint to OpenCode's `payload_plus_delegate_recommended` path, so users can copy the `prepare-delegate.sh` command directly.
- Added `context-aware-worker.toml` Codex custom agent definition that guides subagents to run `subagent-preflight.sh` before starting work.
- Documented Codex custom agent approach in `docs/codex.md`.

### Removed
- Removed duplicate `delegate_kind_for_text`, `prepare_delegate_command`, and `default_delegate_title` from `hook_common.py` — the authoritative implementations remain in `task_guard.py`.

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
