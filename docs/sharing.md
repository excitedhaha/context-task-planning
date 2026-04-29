# Sharing Notes

This repository is meant to be shared as a context engineering skill while keeping real task state local.

## What teammates are getting

- task-scoped workspaces under `.planning/<slug>/`
- durable recovery after context loss or agent switching
- delegate lanes for sub-agents, review, verify, and discovery side quests
- verification-aware task closure instead of "done means I think it is done"

## What should be shared

- `README.md`
- `docs/`
- `.claude-plugin/`
- `skill/`
- `LICENSE`

## What should stay local

- `.planning/`
- local `.claude/`, `.codex/`, or `.opencode/` project settings
- generated Python cache files

Those paths are ignored by `.gitignore` on purpose.

## Recommended install for a teammate

For Claude Code, prefer the plugin path because it packages the skills and lifecycle hooks together:

```bash
claude plugin marketplace add excitedhaha/context-task-planning
claude plugin install context-task-planning@context-task-planning
```

For OpenCode, Codex, or standalone skill installs:

```bash
npx skills add excitedhaha/context-task-planning -g
```

Notes:

1. The Claude plugin exposes the main skill under `skill/`, the bundled task-entry skills under `skills/`, and the plugin hooks under `skill/claude-hooks/hooks.json`.
2. With `npx skills add`, choose `context-task-planning` and any task-entry skills your teammate wants when prompted.
3. If they want to preview before installing, they can run `npx skills add excitedhaha/context-task-planning -l`.
4. If they use Claude Code without the plugin and want hook automation, merge `skill/claude-hooks/settings.example.json` into either `~/.claude/settings.json` or `.claude/settings.local.json`. Do not enable both plugin hooks and manual hook entries at the same time.
5. If they use Codex and want hook automation, prefer the packaged hook install:

   ```bash
   npx codex-marketplace add excitedhaha/context-task-planning/hooks/context-task-planning --hook --global
   ```

   Use `--project` from a repository for a trusted project-local install. Team bootstrap scripts can append `--yes` after reviewing the hook package. If GitHub rejects the marketplace request with a rate-limit or `403`, set `GITHUB_TOKEN` and retry. If the hook-package installer is unavailable, merge `skill/codex-hooks/config.example.toml` manually into `~/.codex/config.toml` or a trusted project `.codex/config.toml`.

6. If they already use `planning-with-files`, disable its hooks or old skill link first to avoid duplicate planning prompts.

## Local fallback for contributors

If someone wants to inspect or develop the repository locally first:

```bash
git clone https://github.com/excitedhaha/context-task-planning.git
cd context-task-planning
claude --plugin-dir .
```

For symlink-based standalone testing instead:

```bash
sh skill/scripts/install-macos.sh
```

## How teammates should use it

- Preferred: give the agent a real multi-step task in normal language; it should usually pick `context-task-planning` automatically, create or resume a task, keep `.planning/` current, and record verification as the work progresses
- Ask for delegate lanes when there is a bounded subproblem such as review, discovery, or verify triage
- Use scripts when you want explicit control, debugging, or a fallback when a host does not auto-invoke the skill
- If a teammate asks "how do I start", give them the GitHub install command first and one of the example prompts below second

Example prompts you can hand to a teammate:

```text
Implement this feature across the relevant backend and frontend paths. This will take multiple steps, may get interrupted, and should be verified before you wrap up.
```

```text
I lost context. Recover the active task from .planning/ and continue from the recorded next_action.
```

```text
Review the risky parts of this migration. Keep the main task focused, and if you need a bounded side investigation, promote only the distilled findings.
```

## Recommended publish checklist

Before pushing to GitHub:

1. Run:

```bash
for f in skill/scripts/*.sh; do sh -n "$f"; done
sh skill/scripts/check-version.sh
sh skill/scripts/extract-release-notes.sh "$(cat VERSION)" >/dev/null
python3 -m py_compile skill/claude-hooks/scripts/*.py skill/codex-hooks/scripts/*.py
python3 -m py_compile hooks/context-task-planning/scripts/*.py
sh skill/scripts/smoke-test-claude-plugin.sh
sh skill/scripts/smoke-test-codex-hook-package.sh
npx skills add . -l
sh skill/scripts/validate-task.sh || true
```

2. Confirm `.planning/` is not staged.
3. Confirm `VERSION`, `skill/SKILL.md` `metadata.version`, `.claude-plugin/plugin.json` `version`, and `CHANGELOG.md` describe the same release.
4. Confirm local absolute paths only appear in private planning state, not in shareable docs.
5. Confirm README and docs lead with context engineering, delegate lanes, and agent-first usage rather than a script-only workflow.
6. Confirm install commands point at `excitedhaha/context-task-planning`.
7. Confirm hook docs still match `skill/claude-hooks/hooks.json`, `skill/claude-hooks/settings.example.json`, `skill/codex-hooks/config.example.toml`, and `hooks/context-task-planning/hooks.json`.
8. Do not create tags or GitHub releases manually unless explicitly requested; `.github/workflows/release.yml` handles `v$(cat VERSION)` after the change lands on `main`.

## Notes on `.planning/`

The repository itself can have a local `.planning/` directory while you are building the skill. That state is intentionally not part of the shared artifact you commit or publish from this repo.

That is separate from mirroring `.planning/` in your own environment across machines; the skill simply does not provide built-in coordination or conflict resolution for that mirrored state.

If you want to publish an example planning task, create a scrubbed example under `docs/` instead of committing a real local workspace.
