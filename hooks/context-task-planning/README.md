# Context Task Planning Codex Hooks

This is a Codex hook package for `context-task-planning`.

Use it when you want the Codex lifecycle hooks without hand-merging the
example TOML into `~/.codex/config.toml`.

## Install

Install the skill first:

```bash
npx skills add excitedhaha/context-task-planning -g
```

Then install the hook package:

```bash
npx codex-marketplace add excitedhaha/context-task-planning/hooks/context-task-planning --hook --global
```

For unattended team bootstrap scripts, add `--yes` after you have reviewed the
hook package:

```bash
npx codex-marketplace add excitedhaha/context-task-planning/hooks/context-task-planning --hook --global --yes
```

For a single repository instead of your whole Codex profile, use `--project`
from that repository:

```bash
npx codex-marketplace add excitedhaha/context-task-planning/hooks/context-task-planning --hook --project
```

The hook package installer writes the appropriate `hooks.json` entry and
enables `features.codex_hooks = true` for the selected scope.

This package intentionally uses Codex's config-layer `hooks.json` surface
instead of plugin-local hooks. Keep the hook runtime explicit and reviewable:
Codex hooks execute local commands.

If GitHub rejects the marketplace request with a rate-limit or `403`, set
`GITHUB_TOKEN` and retry.

## Runtime

The package contains only a thin dispatcher. At runtime it delegates to the
installed skill under one of the standard Codex skill locations, so hook logic
stays in one source of truth:

- project skill: `<repo>/.codex/skills/context-task-planning`
- global skill: `${CODEX_HOME:-$HOME/.codex}/skills/context-task-planning`
- fallback global skill: `$HOME/.agents/skills/context-task-planning`

If the skill cannot be found, the hook reports a non-blocking Codex warning
instead of failing the turn.

## Verify From A Checkout

```bash
sh skill/scripts/smoke-test-codex-hook-package.sh
```

The smoke test validates the hook package JSON, the dispatcher, the delegated
Python hooks, global hook lookup, and project-local `.codex/hooks/` lookup
without writing to your real Codex config.
