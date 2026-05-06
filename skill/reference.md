# Reference

## Context engineering layers

This skill treats context engineering as three coordinated layers:

1. `Persistence` - durable files hold the state that a live context window will lose
2. `Isolation` - each task gets its own planning workspace
3. `Delegation` - independent subproblems can be handled in their own scratch lanes

## Principles

### Clarify before build

Capture goals, non-goals, acceptance criteria, constraints, and open questions before implementation.

### Markdown for humans, JSON for tools

Use markdown for explanation and review. Use `state.json` for stable machine-readable state.

### Single writer, multiple readers

The coordinator owns main planning files. Delegates do not. A task may have one writer session plus additional observer sessions.

### Distill before promote

External inputs become conclusions only after distillation. Keep raw or untrusted inputs out of repeated reads.

### Verify explicitly

Task completion should include real verification commands and recorded results.

### Archive instead of overwrite

Finished tasks are preserved as history. New work gets a new slug.

## Delegate-friendly work

Good delegate candidates:

- repository scanning
- implementation option comparison
- test failure triage
- code review or diff review
- long-session catchup summaries

Minimal delegate loop:

1. create a lane with `prepare-delegate.sh` or `create-delegate.sh`
2. switch the lane to `running` with `start-delegate.sh`
3. let the isolated worker answer the bounded question in `result.md`
4. if the lane stalls, use `block-delegate.sh`; if it is no longer needed, use `cancel-delegate.sh`
5. close the lane with `complete-delegate.sh`
6. merge durable conclusions with `promote-delegate.sh`

Use delegate lanes proactively for discovery, review, and verify subproblems instead of mixing those side quests into the coordinator's main context.

## Subagent preflight

Use `subagent-preflight.sh` when a host or wrapper is about to launch a native subagent and needs one shared routing and repo/worktree decision:

```bash
sh skill/scripts/subagent-preflight.sh \
  --cwd "$PWD" \
  --host claude \
  --tool-name Task \
  --task-text "Investigate auth entry points" \
  --json
```

The shared decisions are:

- `routing_only` - do not inject canonical repo/worktree payload; show routing confirmation only
- `payload_only` - inject the canonical prompt prefix for a related native `Task` launch
- `payload_plus_delegate_recommended` - inject the canonical prompt prefix and add non-blocking delegate guidance
- `delegate_required` - do not treat the native subagent launch as sufficient; create or reuse a delegate lane first

The shell wrapper calls `task_guard.py subagent-preflight`, so task resolution, drift classification, repo scope, and worktree bindings stay in one place.

When the active task carries linked spec context, the preflight text prefix includes the same spec summary. If that spec context is `status=ambiguous`, the preflight JSON now also exposes `task.spec_candidate_refs`, `task.spec_resolution_hint`, and `task.spec_resolution_commands`, and the text prefix tells the subagent to resolve one candidate explicitly before treating it as authoritative unless the work is exploratory only.

## Validation

Run `validate-task.sh` whenever you suspect drift between `state.json`, markdown snapshots, and delegate status files.

- hard failures should cover missing files, invalid JSON, or active delegate mismatches
- softer warnings can cover stale `progress.md` snapshots or other recoverable drift
- `validate-task.sh --fix-warnings` should only repair warning-level snapshot drift, not hard failures or operational truth in `state.json`

## Task focus guard

Use `current-task.sh` when you need the resolved task plus the next recommended action.

For the deeper architecture behind session bindings, repo scope, and worktree isolation, see `docs/design.md`.

Resolution order is: explicit `--task`, `PLAN_TASK`, the session binding selected by `PLAN_SESSION_KEY`, `.planning/.active_task`, then the latest auto-selectable task.

Treat those sources differently in UI: `session_binding` is the strong per-session signal, `.planning/.active_task` is the shared `workspace-default` fallback, and `latest` is only a recovery/default guess.

The default human-readable output should answer:

- what task is currently selected
- whether this session is writer or observer
- which repos are shared versus isolated worktrees
- whether the runtime is using embedded brief context or an auto-detected linked provider such as OpenSpec
- what command the operator should run next

The JSON output keeps the existing task fields and appends recommendation metadata such as `repo_summary`, `recommended_action`, `recommended_reason`, `recommended_commands`, and `resume_candidates`. It also surfaces brief-oriented fields such as `acceptance_criteria`, `edge_cases`, `spec_context`, `brief_quality`, and `brief_missing_fields` for adapters. When a repo exposes a clear OpenSpec candidate, `spec_context` carries the linked provider metadata and stable refs without writing back to OpenSpec files. When detection lands in `status=ambiguous`, the resolved task JSON also exposes `spec_candidate_refs`, `spec_resolution_hint`, and `spec_resolution_commands` so hosts can surface a thin manual override UX without inventing provider-specific logic.

`set-active-task.sh` accepts `--observe` for read-only bindings and `--steal` when a new session intentionally takes over the writer lease.

Use `check-task-drift.sh` when you want lightweight route evidence for whether a new request still fits the active task. The result is heuristic input for the main LLM, not a final semantic drift decision.

Use `check-switch-safety.sh --target-task <slug> --json` when you are about to switch tasks in a git repository and want to know whether the current worktree should be stashed or committed first.

`init-task.sh`, `resume-task.sh`, and `set-active-task.sh` now enforce that guard automatically. In a dirty git worktree they will prompt to stash, stop so you can commit manually, continue dirty, or cancel. Use `--stash` to auto-stash or `--allow-dirty` to bypass the guard deliberately. When `PLAN_SESSION_KEY` is present, those commands update the current session binding instead of treating `.planning/.active_task` as the only live pointer; without a session key, they operate on the shared `workspace-default` fallback.

Observer sessions may still create or update delegate lanes under `delegates/<delegate-id>/`, but they must leave `task_plan.md`, `progress.md`, `state.json`, and `findings.md` to the writer.

For parent workspaces that contain multiple repos, register repos explicitly with `register-repo.sh`, attach them to tasks with `set-task-repos.sh`, and only use auto-discovery as a review aid before you confirm the registrations.

Parent-workspace resolution is path-aware: unrelated ancestor `.planning/` roots should not capture the current session.

If two writer tasks need the same repo concurrently, prepare a dedicated
checkout for the overlapping repo with
`prepare-task-worktree.sh --task <slug> --repo <repo-id>`. By default that
creates `.worktrees/<task-slug>/<repo-id>/`. Use `--path` only when you
intentionally need a nonstandard checkout location.

`set-task-repos.sh` and writer-bind failures should also tell you which repos are:

- safe to keep shared
- already isolated in a task worktree
- blocked until you run `prepare-task-worktree.sh`

On hosts without runtime adapters, treat `likely-unrelated` as a prompt to confirm routing before you edit `.planning/`. Treat `unclear` as non-conclusive evidence and decide from the conversation plus task goal.

Linked provider refs from `spec_context` also feed `check-task-drift.sh` and `subagent-preflight.sh`, so prompts that mention the chosen OpenSpec change or spec artifact continue to route as part of the current task.

If OpenSpec detection lands in `status=ambiguous`, `current-task` shows the candidate refs plus an explicit `set-task-spec-context.sh` hint. Use `sh skill/scripts/set-task-spec-context.sh --task <slug> --ref <spec-ref>` to record the manual override in `.planning/<slug>/state.json` without editing provider files. Add `--artifact <ref>` when you want the linked artifact refs to stay explicit, or `--clear` to return to the default embedded fallback.

For OpenCode specifically, prefer `opencode plugin context-task-planning-opencode --global` after installing the skill; the npm plugin auto-installs slash commands on first load. The legacy symlink-based `install-opencode-plugin.sh` and `install-opencode-commands.sh` scripts still work but are deprecated. The plugin is designed to stay quiet in repositories that do not already use `.planning/`.

For Claude Code specifically, prefer the plugin declared by `.claude-plugin/plugin.json`. It bundles the main skill, task-entry skills, and `skill/claude-hooks/hooks.json` so users do not hand-merge hook settings. The legacy `skill/claude-hooks/settings.example.json` remains the standalone fallback and also carries the optional native `statusLine` configuration.

For Codex specifically, prefer the plugin declared by `.codex-plugin/plugin.json`. It bundles the main skill, task-entry skills, and hooks so users get everything with one install command. The hooks use `SessionStart`, `UserPromptSubmit`, `PostToolUse`, and `Stop` to re-inject task context in long threads and ask Codex to continue once when a mutating turn is about to finish without planning sync evidence. They do not provide a native status cue or mutate native subagent prompts.

For TraeCLI/Coco specifically, prefer the plugin root with `coco.yaml`, `commands/`, `skills/`, and `skill/trae-hooks/`. It exposes plugin-bundled slash commands, a Trae-visible main skill entry, prompt/tool hooks, and a `Stop` planning-sync guard while still delegating all durable state and routing decisions to `skill/scripts/`.

Claude Code also supports bundled thin task-entry skills for the same high-frequency flows. Those skills should stay thin wrappers over the shared shell scripts rather than becoming a second workflow implementation.

OpenCode also supports bundled slash commands; these are auto-installed by the npm plugin on first load, or installed manually through `install-opencode-commands.sh` (legacy). Those commands should stay thin wrappers over the shared shell scripts rather than becoming a second workflow implementation.

TraeCLI/Coco slash commands live under root `commands/` and should follow the same thin-wrapper rule.

P0 classifications are:

- `related`
- `unclear`
- `likely-unrelated`
- `no-active-task`

Poor delegate candidates:

- concurrent writes to main planning files
- risky shared-state operations
- destructive release or migration steps

## Recovery checklist

If context feels stale, answer these in order:

1. Which task is active?
2. What mode is it in?
3. What is the next action?
4. What is blocked?
5. What proves the task is done?

Those answers should be available from the task folder without relying on session history.

## Status semantics

- `active` - the task is open for ongoing work and may be the current target for one or more sessions
- `paused` - the task is intentionally parked; keep the next action intact
- `blocked` - the task cannot advance until blockers are resolved
- `verifying` - the task is in an explicit validation pass
- `done` - the task has cleared its completion bar but is not yet archived
- `archived` - the task is historical and should not be auto-selected
