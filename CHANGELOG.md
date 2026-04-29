# Changelog

All notable changes to this project are documented here.

## [Unreleased]

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
