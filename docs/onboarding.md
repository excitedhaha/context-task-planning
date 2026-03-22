# Onboarding

Use this guide if you want the full user journey after `README.md`.

You do not need to learn the full file protocol up front. Start with `Track 1` until you get one successful recovery. Move to `Track 2` only when your daily workflow actually needs more control.

## The journey at a glance

- get one real success case
- keep the current task visible
- switch tasks deliberately instead of mixing them
- separate parallel sessions with `writer` and `observer` roles
- span multiple repos from one parent workspace
- isolate overlapping writer work with task-specific worktrees
- close work with delegate lanes and real verification

## Track 1: First-time users

### Goal

Reach one clear aha moment: you can leave a long coding task, come back later, and continue without re-explaining everything.

### 5-minute path

#### Step 1: Install the skill

```bash
npx skills add excitedhaha/context-task-planning -g
```

Choose `context-task-planning` and the agent(s) you use when prompted.

If you want host-specific setup after your first success case, use:

- `docs/claude.md`
- `docs/opencode.md`
- `docs/codex.md`

#### Step 2: Give the agent one task that is large enough to matter

Good first example:

```text
Refactor the auth flow across backend and frontend. This will take multiple steps, may get interrupted, and should be verified before you wrap up.
```

For work like this, the agent should usually pick the skill automatically. Only mention `context-task-planning` explicitly if your host does not auto-invoke it reliably.

Pick something real:

- a medium refactor
- a bug that spans backend and frontend
- a task that will likely take more than one session

Bad first examples:

- rename one variable
- change one sentence in a file
- quick one-shot shell commands

#### Step 3: Check that the task became visible

Depending on your setup, you should see one of these:

- `Claude Code` - `task:<slug>` in the status line
- `OpenCode` - `task:<slug> | ...` in the session title
- `Codex` - `sh skill/scripts/current-task.sh --compact` prints the active task

This matters because visible task state is what makes silent task mixing harder.

#### Step 4: Simulate one recovery

In the same repo, ask:

```text
I lost context on this task. Recover the active task from local planning files and continue from the recorded next action.
```

If the agent can continue from `.planning/<slug>/` without you re-teaching the whole task, the workflow is working.

#### Step 5: Stop learning there

For your first few uses, ignore these until you hit a real need:

- session bindings
- repo registration
- worktree isolation
- delegate lanes
- JSON schemas

### What success looks like

- the agent creates or resumes a task under `.planning/<slug>/`
- the current task becomes visible in your host or shell
- the agent can recover from the task files after an interruption
- the task records real verification before it is called done

### Common first-time mistakes

- using it on work that is too small
- reading `.planning/` before trying a real prompt
- trying to learn every script before seeing one successful recovery
- assuming the files are the product, instead of the support system

## Track 2: Growing into daily use

### Goal

Make long-running, interruption-prone, multi-task work feel controlled instead of fragile.

You can stop after any level. Each level adds one capability for one new pain point.

### Level 1: Make the base loop boring

When to learn this:

- you already had one success case
- you want a repeatable default workflow instead of a one-off demo

What to do:

- start or resume tasks through normal conversation
- let the agent keep the current task, next action, and verification state current
- treat `verify` as part of the contract, not as optional cleanup

You can ignore until later:

- session bindings
- repo scopes
- worktrees
- delegate lanes

### Level 2: Keep the current task visible

When to learn this:

- you switch contexts often and lose track of the active task
- you want drift to feel obvious instead of silent

What to do:

- `Claude Code` - use the status line
- `OpenCode` - use the title prefix and toasts
- `Codex` - put `sh skill/scripts/current-task.sh --compact` in your shell prompt, tmux status line, or a quick manual check

Read the host notes only for the setup differences:

- `docs/claude.md`
- `docs/opencode.md`
- `docs/codex.md`

You can ignore until later:

- manual editing of planning files
- deeper architecture details from `docs/design.md`

### Level 3: Switch tasks deliberately

When to learn this:

- a new ask appears mid-stream
- you carry local code changes while trying to switch tasks

What to do:

- treat the routing choice explicitly: continue the current task, switch to an existing task, or create a new task
- use `check-task-drift.sh` when the match is uncertain
- expect the dirty-worktree guard to stop unsafe task switches unless you choose `--stash` or `--allow-dirty`

Useful command:

```bash
sh skill/scripts/check-task-drift.sh --prompt "Also investigate the billing webhook regression" --json
```

You can ignore until later:

- if you normally work on one task at a time, this can stay lightweight

### Level 4: Separate parallel sessions

When to learn this:

- you keep multiple terminals, multiple agents, or multiple host sessions open at once
- one session should keep working while another only observes or reviews

What to do:

- give each session its own binding
- keep one `writer` for the main planning lane
- use extra `observer` sessions for read-only task context plus delegate-lane work

Manual shell fallback:

```bash
export PLAN_SESSION_KEY=manual:feature-auth
sh skill/scripts/set-active-task.sh feature-auth
sh skill/scripts/set-active-task.sh --observe feature-auth
```

You can ignore until later:

- if you only use one session at a time, `.planning/.active_task` remains enough

### Level 5: Use a parent workspace with multiple repos

When to learn this:

- one task spans repos such as `frontend/` and `backend/`
- you open the agent from a parent directory instead of a single repo root

What to do:

- keep one shared `.planning/` at the parent workspace level
- explicitly register repos before binding them to a task
- record the task's repo scope so the same task resolves from the parent, a registered repo path, or a recorded worktree path

Typical setup:

```bash
sh skill/scripts/list-repos.sh --discover
sh skill/scripts/register-repo.sh --id frontend frontend
sh skill/scripts/register-repo.sh --id backend backend
sh skill/scripts/init-task.sh --repo frontend --repo backend --primary frontend "Cross-repo auth flow"
```

You can ignore until later:

- single-repo workspaces do not need this ceremony

### Level 6: Isolate overlapping writer tasks with worktrees

When to learn this:

- two active writer tasks both need the same repo
- repo scope alone is not enough to keep code changes safe

What to do:

- keep repo scope as the answer to "which repos may this task touch?"
- use worktree bindings as the answer to "which checkout will this task actually edit?"
- prepare a task-specific worktree before two writer tasks touch the same repo checkout

Typical setup:

```bash
sh skill/scripts/prepare-task-worktree.sh --task frontend-billing-cleanup --repo frontend
```

You can ignore until later:

- if your tasks run serially or touch different repos, shared checkouts are still fine

### Level 7: Use delegates and verification to close cleanly

When to learn this:

- you need a bounded side quest such as repo scanning, risk review, or verification triage
- you want later sessions to tell the difference between `implemented`, `verified`, and `blocked`

What to do:

- use delegate lanes for bounded discovery, review, and verification work
- keep the main task focused and promote only distilled findings back
- record what done means, which checks ran, and what is still blocked

Useful commands:

```bash
sh skill/scripts/prepare-delegate.sh --kind discovery "Map auth entry points"
sh skill/scripts/validate-task.sh
```

Do not use delegates for:

- broad open-ended implementation
- concurrent edits to the main planning files
- risky release or migration actions

## Manual fallback and scripts

You do not need this section for the normal path. Use it when auto-invoke does not fire, you want explicit control, or you are debugging the workflow.

Start with the smallest useful commands:

```bash
sh skill/scripts/current-task.sh --compact
sh skill/scripts/check-task-drift.sh --prompt "Also investigate the billing webhook regression" --json
sh skill/scripts/validate-task.sh
```

Add the deeper commands only when the workflow actually needs them:

```bash
sh skill/scripts/init-task.sh "Implement auth flow"
sh skill/scripts/set-active-task.sh --observe feature-auth
sh skill/scripts/register-repo.sh --id frontend frontend
sh skill/scripts/prepare-task-worktree.sh --task feature-auth --repo frontend
sh skill/scripts/prepare-delegate.sh --kind discovery "Map auth entry points"
```

If you want the full command contract instead of the progressive usage guide, use `skill/reference.md`.

## Which doc to read next

- `README.md` - the concise entry point and quickstart
- `docs/claude.md` - Claude-specific setup and visible cues
- `docs/opencode.md` - OpenCode-specific plugin behavior and limitations
- `docs/codex.md` - Codex-specific shell-first workflow
- `docs/design.md` - why session bindings, repo scopes, and worktrees exist
- `skill/reference.md` - command reference once you want explicit control

## If the system feels too heavy

Use this minimum viable workflow:

1. start one task
2. keep the task visible
3. recover from `.planning/` after interruption
4. verify before done

Ignore everything else until you feel the pain that the deeper layers are meant to solve.
