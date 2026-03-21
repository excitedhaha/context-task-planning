# Context Task Planning

Keep complex coding tasks recoverable, isolated, and visible across Claude Code, OpenCode, and Codex.

`context-task-planning` gives a coding agent a task-scoped workspace on disk so it can:

- resume after context loss, model switches, or agent switches
- keep the current task visible
- avoid silently mixing unrelated work into the same lane
- record real verification before calling the task done

Most users should talk to the agent, not manage planning files or shell scripts by hand.

## When to use it

Use it when the work is:

- multi-step or long-running
- likely to be interrupted and resumed later
- large enough that one chat session is not a safe source of truth
- likely to spawn bounded side quests such as repo scans, reviews, or verification passes

Skip it for tiny one-shot edits that do not need recovery.

## What a good first run looks like

After setup, the normal path should feel like this:

1. You give the agent a complex task in normal language.
2. The agent creates or resumes `.planning/<slug>/`.
3. The current task becomes visible in your host or shell.
4. If you lose context, the agent recovers from local task files.
5. Before wrapping up, the agent records real verification results.

## Quickstart

### 1. Install the skill

Recommended install:

```bash
npx skills add excitedhaha/context-task-planning -g
```

Choose `context-task-planning` and the agent(s) you want when prompted.

If you want to preview what will be installed first:

```bash
npx skills add excitedhaha/context-task-planning -l
```

If you are developing from a local clone instead:

```bash
git clone https://github.com/excitedhaha/context-task-planning.git
cd context-task-planning
sh skill/scripts/install-macos.sh
```

That local installer also enables the bundled OpenCode plugin by default. If you only want the skill symlinks, use:

```bash
sh skill/scripts/install-macos.sh --skip-opencode-plugin
```

### 2. Start your first task in plain language

```text
Refactor the auth flow across backend and frontend. This will take multiple steps, may get interrupted, and should be verified before you wrap up.
```

If you lose context later:

```text
I lost context on this task. Recover the active task from local planning files and continue from the recorded next action.
```

For multi-step or recovery-sensitive work, the agent should usually pick this skill automatically. If your host does not auto-invoke it reliably, mention `context-task-planning` explicitly.

### 3. Sanity-check that it worked

- `Claude Code` - restart Claude Code and look for `task:<slug>` in the native status line
- `OpenCode` - restart OpenCode, send one message, and look for `task:<slug> | ...` in the session title plus task/drift toasts
- `Codex` - run `sh skill/scripts/current-task.sh --compact` and expect the current task slug in the output

If you want a guided path after setup, see `docs/onboarding.md`.

If you want in-host task visibility cues, jump to `Host cues` below for the quick overview and links to the host-specific setup docs.

## Daily workflow

### Normal path

- Start or resume a task through normal conversation.
- Let the agent keep the current task, next action, and verification state up to date.
- If the session is interrupted, recover from `.planning/`.
- Finish only after real verification is recorded.

### What gets created

Each task lives under `.planning/<slug>/`:

```text
.planning/
  .active_task
  feature-auth/
    task_plan.md
    findings.md
    progress.md
    state.json
    delegates/
      repo-scan/
        brief.md
        result.md
        status.json
```

You usually do not need to edit these files manually, but they stay readable when you want to inspect or recover a task.

## Host cues

Once enabled, the current task should be visible without opening `.planning/` manually:

- `Claude Code` - native status line task cue plus drift reminders
- `OpenCode` - session title prefix, task/drift toasts, and stale-planning nudges
- `Codex` - shell or tmux visibility through `current-task.sh --compact`, plus confirm-before-switch guidance
- `Any shell or tmux` - `sh skill/scripts/current-task.sh --compact` prints a one-line task summary for prompts, status bars, or scripts

Sample illustrations:

![Claude Code status line sample](docs/assets/claude-statusline-sample.svg)

![OpenCode title and toast sample](docs/assets/opencode-title-toast-sample.svg)

These are sample illustrations, not live screenshots.

Setup details by host:

- `Claude Code` - `docs/claude.md`
- `OpenCode` - `docs/opencode.md`
- `Codex` - `docs/codex.md`

## Advanced controls

Use these when you want explicit control, debugging, or automation.

### Useful commands

```bash
sh skill/scripts/init-task.sh "Implement auth flow"
sh skill/scripts/current-task.sh --compact
sh skill/scripts/check-task-drift.sh --prompt "Also investigate the billing webhook regression" --json
sh skill/scripts/check-switch-safety.sh --target-task feature-auth --json
sh skill/scripts/list-repos.sh --discover
sh skill/scripts/register-repo.sh --id frontend frontend
sh skill/scripts/set-task-repos.sh feature-auth --repo frontend --primary frontend
sh skill/scripts/prepare-task-worktree.sh --task feature-auth --repo frontend
sh skill/scripts/prepare-delegate.sh --kind discovery "Map auth entry points"
sh skill/scripts/validate-task.sh
sh skill/scripts/list-tasks.sh
```

In git repositories, `init-task.sh`, `resume-task.sh`, and `set-active-task.sh` now warn before switching tasks with a dirty worktree. Use `--stash` to stash automatically or `--allow-dirty` only when you intentionally want to carry local changes across tasks.

### Multiple active sessions

Each Claude/OpenCode/Codex session can keep its own current task. Host adapters can provide a stable session key automatically; the manual shell fallback is:

```bash
export PLAN_SESSION_KEY=manual:feature-auth
sh skill/scripts/set-active-task.sh feature-auth
```

Use `PLAN_TASK` only as a one-off manual override inside the current shell. `.planning/.active_task` remains the workspace fallback when no session binding exists.

If several sessions point at the same task, only one should be the writer. Use `sh skill/scripts/set-active-task.sh --observe <slug>` for extra read-only sessions; observers may still work inside `delegates/<delegate-id>/` lanes.

### Parent workspace with multiple repos

If you open the agent from a parent directory that contains several git repos, keep one shared `.planning/` in that parent directory and register repos explicitly before binding them to tasks:

```bash
sh skill/scripts/list-repos.sh --discover
sh skill/scripts/register-repo.sh --id frontend frontend
sh skill/scripts/register-repo.sh --id backend backend
sh skill/scripts/init-task.sh --repo frontend --repo backend --primary frontend "Cross-repo auth flow"
```

Use `list-repos.sh --discover` only to review candidate repos; the actual registration step stays explicit. Once that parent workspace owns `.planning/`, running from the parent directory itself, a registered repo path such as `frontend/`, or a recorded `.worktrees/<repo>/<task>/` checkout still resolves back to the same shared task state. Unrelated ancestor `.planning/` directories are ignored unless the current path actually belongs to that older workspace.

If two writer tasks need the same repo at once, prepare a dedicated checkout for the overlapping repo instead of reusing the shared checkout:

```bash
sh skill/scripts/prepare-task-worktree.sh --task cross-repo-auth-flow --repo frontend
```

### Delegate lanes

Use delegate lanes for bounded subproblems such as:

- repository exploration
- option comparison
- test failure triage
- focused review

Promote only distilled findings back to the main task.

For more examples and full command coverage, see:

- `docs/onboarding.md`
- `skill/examples.md`
- `skill/reference.md`

## What this skill optimizes for

- `Recoverability` - task state survives context loss
- `Isolation` - each task gets its own workspace
- `Visibility` - the current task stays visible in the host or shell
- `Verification` - done means checked, not just discussed

For the deeper implementation model, see `docs/design.md`.

## Limitations

- the portable contract is file-based, so host-specific UI differs
- no cross-machine sync
- no host-specific session-history catchup layer
- the optional adapters are reminders and visibility aids, not a hard transaction system

## Agent-specific notes

- `docs/claude.md`
- `docs/codex.md`
- `docs/onboarding.md`
- `docs/opencode.md`
- `docs/sharing.md`

## Repository layout

```text
context-task-planning/
  docs/
  skill/
    SKILL.md
    claude-hooks/
    reference.md
    examples.md
    templates/
    schemas/
    scripts/
```

## Sharing and publishing

- the reusable artifact is the repository itself: `README.md`, `docs/`, `skill/`, and `LICENSE`
- real task state under `.planning/` is intentionally local and ignored by Git
- if a teammate already uses `planning-with-files`, disable its hooks or old skill link before enabling this skill's Claude hooks
- `npx skills add` is the preferred install path for teammates; local scripts remain the fallback for contributors
- before publishing changes, run the checklist in `docs/sharing.md`

## Status

`v0.2.0` includes:

- repository-local `.planning/`
- slug-based task isolation
- pure-file recovery
- task state schema
- delegate lanes for bounded side quests
- agent-first usage with script escape hatches
- shared task focus guard primitives for visibility and drift checks
- optional Claude Code hooks/status line and OpenCode plugin adapter

It still does not include host-specific session catchup or cross-machine sync.

## Inspirations

- `planning-with-files`
- `devis`
- `multi-manus-planning`
- `plan-cascade`
