# OpenCode Notes

This page only covers OpenCode-specific setup and behavior. Use `README.md` for the first success case and `docs/onboarding.md` for the shared workflow.

OpenCode support in this project has two thin host-specific layers over the same shell-first runtime:

- an OpenCode plugin for visibility, toasts, session binding, and native-`Task` preflight
- bundled slash commands for common task workflows such as init, inspect, list, validate, and drift-check

If you only want the shortest path: install the skill, run the plugin and command helpers once, restart OpenCode, then smoke-test `/task-current` and `/task-list`.

## Install

Recommended install:

```bash
npx skills add excitedhaha/context-task-planning -g
```

Choose `context-task-planning` and the OpenCode agent when prompted.

Local fallback while developing from a clone:

```bash
sh skill/scripts/install-macos.sh
```

A global install makes the skill available under:

```text
~/.config/opencode/skills/context-task-planning
```

The OpenCode-specific extras install into separate locations:

- plugin: `~/.config/opencode/plugins/`
- slash commands: `~/.config/opencode/commands/`

## What OpenCode adds

The OpenCode plugin is a thin UI layer over the same file-backed task state. Once enabled, it can:

- prefix the session title as `task:<slug> | ...`
- expose bundled slash commands for common task entry points
- show toasts for drift, stale planning, and task-binding/bootstrap events
- warn when tracked work happens but `.planning/<slug>/` looks stale
- export `PLAN_SESSION_KEY` so task-aware shell commands bind to the current OpenCode session
- call the shared `subagent-preflight` helper before native `Task` launches and prepend the canonical repo/worktree prefix when the request still fits the current task
- surface linked spec context such as auto-detected OpenSpec refs in the injected task summary and native-`Task` preflight payload when available, including a short candidate hint when the runtime refuses to guess
- carry repo context for parent-workspace multi-repo tasks
- stay quiet in repositories that do not already use `.planning/`

## Enable the OpenCode plugin and commands

If you installed from a local clone with:

```bash
sh skill/scripts/install-macos.sh
```

the OpenCode plugin and bundled slash commands are installed automatically by default, so you can usually skip straight to restarting OpenCode and running the smoke test below.

If you installed through `npx skills add`, run the bundled helpers once because OpenCode loads skills, plugins, and commands from different directories:

```bash
sh ~/.config/opencode/skills/context-task-planning/scripts/install-opencode-plugin.sh
sh ~/.config/opencode/skills/context-task-planning/scripts/install-opencode-commands.sh
```

You can also run the helper from a local clone:

```bash
sh skill/scripts/install-opencode-plugin.sh
sh skill/scripts/install-opencode-commands.sh
```

Then restart OpenCode so it picks up new plugins and slash commands.

If you want the skill symlink but not the runtime plugin or slash commands from the local installer, use:

```bash
sh skill/scripts/install-macos.sh --skip-opencode-plugin
sh skill/scripts/install-macos.sh --skip-opencode-commands
```

## What you should notice

After the plugin and commands are enabled and OpenCode is restarted, you should see:

- the session title prefixed as `task:<slug> | ...`
- bundled slash commands such as `/task-init` appearing in the OpenCode command menu
- a warning toast when a prompt looks like likely task drift
- a warning toast when tracked work has happened but planning files look stale
- the first task-creation shell command in a fresh OpenCode session now bootstraps a real session binding instead of falling back to the shared workspace pointer
- if a fresh or fallback-resolved session directly edits one task's `.planning/<slug>/state.json|task_plan.md|progress.md|findings.md`, OpenCode now auto-bootstraps a binding for that task instead of silently staying on the old fallback task; it tries writer first and falls back to observer with a warning when repo isolation blocks writer ownership
- the same task still resolving when OpenCode starts inside a registered repo path or recorded worktree under a parent workspace
- in some repos, the injected task summary can also mention one linked spec ref, or a few candidate refs when the runtime refuses to guess
- treat that spec line as scoping help, not as extra setup; only use the manual override path if the work really needs one authoritative ref

Sample illustration:

![OpenCode title and toast sample](assets/opencode-title-toast-sample.svg)

This is a sample illustration of the expected title/toast fallback, not a live screenshot from your machine.

## Bundled slash commands

Current bundled commands:

- `/task-init <task title>` - run `sh ~/.config/opencode/skills/context-task-planning/scripts/init-task.sh "<task title>"` and report the created task
- `/task-current` - run `sh ~/.config/opencode/skills/context-task-planning/scripts/current-task.sh` and summarize the active task plus next action
- `/task-list` - run `sh ~/.config/opencode/skills/context-task-planning/scripts/list-tasks.sh` and summarize the available tasks in the workspace
- `/task-validate` - run `sh ~/.config/opencode/skills/context-task-planning/scripts/validate-task.sh` and summarize whether the current task state is valid
- `/task-drift <new request>` - run `sh ~/.config/opencode/skills/context-task-planning/scripts/check-task-drift.sh --prompt "<new request>" --json` and summarize whether the new ask still fits the current task
- `/task-done [slug]` - run `sh ~/.config/opencode/skills/context-task-planning/scripts/done-task.sh [slug]` and mark the current or named task done when verification and safety checks pass

The command files are installed into:

```text
~/.config/opencode/commands/task-current.md
~/.config/opencode/commands/task-done.md
~/.config/opencode/commands/task-init.md
~/.config/opencode/commands/task-list.md
~/.config/opencode/commands/task-drift.md
~/.config/opencode/commands/task-validate.md
```

These commands stay thin on purpose: the underlying shell scripts remain the source of truth for task resolution, initialization, dirty-worktree safety, and session binding behavior.

## Quick validation and troubleshooting

Fastest smoke test after install:

- run `/task-current` to confirm OpenCode can resolve the current task
- run `/task-list` to confirm the workspace task list is available
- run `/task-validate` to confirm the validation path responds without auto-fixing warnings

If the commands do not appear right away:

- make sure the command files exist under `~/.config/opencode/commands/`
- restart OpenCode after running the install helper
- rerun `sh ~/.config/opencode/skills/context-task-planning/scripts/install-opencode-commands.sh` if the command symlinks are missing
- rerun `sh ~/.config/opencode/skills/context-task-planning/scripts/install-opencode-plugin.sh` if the title/toast behavior is missing but slash commands are present
- if the slash commands work but the task title never updates, verify that the plugin loaded and that you restarted OpenCode after installation

## Plugin lifecycle

The OpenCode plugin is event-driven. It is not a file watcher, background sync daemon, or guaranteed writeback layer for `.planning/` files.

Current handlers in `skill/opencode-plugin/task-focus-guard.js` run at these moments:

- `chat.message` - after a user message is assembled; cache prompt text, classify drift, and try to sync the visible task title
- `experimental.chat.system.transform` - right before the model receives system context; inject current-task, drift, and freshness reminders
- `experimental.session.compacting` - right before OpenCode compacts a session; run the shared compact-sync helper, then feed compact recovery context into the compaction prompt and cache one resume-time recovery injection for the next turn
- `tool.execute.before` - before a tool runs; today this mainly prefixes native `Task` launches with routing and delegate guidance
- `shell.env` - before shell execution; inject `PLAN_SESSION_KEY` so shell commands resolve the correct per-session task binding
- `tool.execute.after` - after a tool finishes; refresh visible task cues and freshness counters, then show a stale-planning toast when needed; freshness tracking normalizes namespaced tool names such as `functions.bash`, inspects `multi_tool_use.parallel` payloads for nested tracked work like `functions.apply_patch`, and uses `state.json` / `progress.md` as the sync-critical freshness baseline before falling back to the broader planning set
- `tool.execute.after` also watches for direct writes to one task's main planning files; when a session is still running on fallback resolution, that planning write now bootstraps the matching session binding so later compact sync and writer reminders target the task the agent is actually editing
- `event` - on host events such as `session.created`, `session.updated`, `session.compacted`, and `tui.session.select`; sync session titles for already-bound tasks, cache message and diff metadata from `message.updated` / `message.part.updated` / `session.diff`, run a deterministic writer-only journal sync on `session.idle`, and fall back to the same deduped journal sync on later visible events such as `session.updated`, `session.status`, `message.updated`, or `session.diff` when the host never emits `session.idle` for that completed turn

Typical message flow:

1. select or create a session -> `event`
2. send a user message -> `chat.message`
3. build model system context -> `experimental.chat.system.transform`
4. execute tools -> `tool.execute.before` / `shell.env` / `tool.execute.after`

## Why task files do not always auto-sync

The plugin can make session state visible and inject reminders, and it now has one narrow automatic writeback path for writer sessions after a completed turn with real work, using `session.idle` when available and a deduped visible-event fallback when the host skips that event. It still does not act as a general planner or rewrite every task file on every turn.

In practice this means:

- session-title sync can be host-driven and deterministic once the session binding is correct
- `state.json` and `progress.md` can now receive a deterministic append-only journal update after a writer session finishes a turn with real tool/patch/diff activity
- compact-time recovery is now two-stage: OpenCode injects compact recovery context into the compaction prompt itself, then injects the same compact recovery context once on the first post-compaction turn so the model does not rely only on the compressed transcript summary
- `task_plan.md` and `findings.md` are still agent-driven; the plugin does not try to infer or rewrite Hot Context, decisions, or findings from transcript history
- the shared `sh skill/scripts/compact-sync.sh` helper is now wired to OpenCode on a best-effort basis when event payloads visibly mention compact/compression; writer sessions may repair warning-level drift and refresh the derived compact artifact, while observer sessions stay derived-only
- writer-session reminders should explicitly say to sync `progress.md` and `state.json` whenever a turn materially changes progress, blockers, or `next_action`

## Idle journal sync

The automatic journal sync path is intentionally narrow:

- it only runs for the writer session bound to the current task
- it only runs when the cached assistant turn shows real tool, patch, or diff activity
- it prefers `session.idle`, but if OpenCode skips that event for a finished turn it can fall back on the next visible session event that still carries the same completed assistant state
- it records one deduped source id per assistant message under `.planning/<slug>/.derived/opencode_idle_sync.json`
- it updates `state.json.updated_at` and `state.json.latest_checkpoint`
- it refreshes the `## Snapshot` block in `progress.md`
- it prepends one append-only `## Session Log` entry with actions, files touched, and compact notes derived from the latest turn

This keeps the plugin advisory for planning content while still giving OpenCode a minimal, deterministic writeback layer for the most common "I changed code but forgot to sync progress" case.

## Compact recovery

OpenCode compaction used to be much easier to drift after than Claude because the plugin only noticed some compact-looking events and refreshed the derived artifact on a best-effort basis.

The recovery path is now stricter:

- `experimental.session.compacting` runs the shared compact sync before compaction and appends the derived compact context to the compaction prompt
- the plugin now recognizes real `session.compacted` events directly instead of relying only on loose `compact` keyword matches
- after compaction, the next `experimental.chat.system.transform` injects one resume-time recovery prompt that tells the model to treat the compact artifact as the current hot context
- after that first resume injection, OpenCode now keeps a narrower persistent reminder on subsequent turns until the session actually reads the current task's `state.json` and `progress.md`; `task_plan.md` stays a conditional follow-up when Hot Context or decisions matter

This still is not a hard tool-enforced file read, but it closes the main gap that let OpenCode resume from an over-compressed transcript without rehydrating the task context.

## Task preflight

The plugin's `tool.execute.before` hook now calls the same shell-first helper as Claude:

```bash
sh skill/scripts/subagent-preflight.sh \
  --cwd "$PWD" \
  --host opencode \
  --tool-name Task \
  --task-text "Investigate the auth entry points across repos" \
  --json
```

OpenCode keeps freshness reminders separate from the preflight decision:

- `payload_only` or `payload_plus_delegate_recommended` - prepend the canonical task and repo/worktree prefix to the outbound `Task` prompt
- `routing_only` - prepend routing confirmation only
- `delegate_required` - prepend delegate-required guidance instead of treating the native `Task` launch as sufficient

When `current-task` resolves a linked OpenSpec context, that same preflight prefix now includes the spec context summary plus the primary linked ref so the native `Task` launch stays scoped to the right external artifact. If the runtime stops at `status=ambiguous`, the prefix now carries the candidate refs plus an explicit manual-override hint instead of pretending one candidate is authoritative. Treat that as routing help first; exploratory work can usually continue without resolving candidates up front.

The plugin still keeps title and toast behavior unchanged in this first pass.

## Current limits

- the plugin SDK exposes hooks, session title updates, and TUI toasts, but not a dedicated custom sidebar or status bar widget API
- the plugin is still not a second planner; its automatic writeback stays limited to deterministic `state.json` / `progress.md` journal sync, preferring `session.idle` and falling back to later visible events only after file evidence for the completed turn arrives
- compact sync is heuristic, but the plugin now also uses the dedicated `experimental.session.compacting` hook when OpenCode exposes it and still falls back to compact/compression signals on visible session events otherwise
- if you do not see a dedicated sidebar widget, that is expected today

## Manual fallback

Useful commands when you want direct control:

- `sh skill/scripts/init-task.sh "Implement auth flow"`
- `sh skill/scripts/current-task.sh --compact`
- `sh skill/scripts/compact-sync.sh`
- `sh skill/scripts/check-task-drift.sh --prompt "Also investigate the billing webhook regression" --json`
- `sh skill/scripts/subagent-preflight.sh --cwd "$PWD" --host opencode --tool-name Task --task-text "Investigate auth entry points" --text`
- `sh skill/scripts/validate-task.sh`
- `sh skill/scripts/set-task-spec-context.sh --task <slug> --ref <spec-ref>`

Use `set-task-spec-context.sh` only when the work really needs one authoritative spec ref. If OpenCode only shows a few candidate refs during exploration, you can usually keep going without recording a manual override yet.

For the shared progression from first success to multi-session and multi-repo usage, go back to `docs/onboarding.md`. For the deeper architecture behind OpenCode's task resolution and repo/worktree behavior, use `docs/design.md`.
