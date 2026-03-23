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

### Fast path

#### Step 1: Install the skill

```bash
npx skills add excitedhaha/context-task-planning -g
```

Choose `context-task-planning` and the agent(s) you use when prompted.

#### Step 2: Copy one real task prompt

Start with something big enough to need recovery:

```text
Refactor the auth flow across backend and frontend. This will take multiple steps, may get interrupted, and should be verified before you wrap up.
```

Good first tasks are:

- a medium refactor
- a bug that crosses files or repos
- a task that will likely take more than one session

Skip these for your first run:

- tiny edits
- one-shot shell commands
- work you can finish from memory in one short turn

For work like this, the agent should usually pick the skill automatically. Only mention `context-task-planning` explicitly if your host does not auto-invoke it reliably.

#### Step 3: Check that the task showed up

You should see one of these:

- `Claude Code` - `task:<slug>` in the status line
- `OpenCode` - `task:<slug> | ...` in the session title
- `Codex` - `sh skill/scripts/current-task.sh --compact` prints the active task

If that cue is missing, use:

- `docs/claude.md`
- `docs/opencode.md`
- `docs/codex.md`

#### Step 4: Simulate one recovery

In the same repo, ask:

```text
I lost context on this task. Recover the active task from local planning files and continue from the recorded next action.
```

If the agent can continue from `.planning/<slug>/` without you re-teaching the whole task, the workflow is working.

#### Step 5: Stop learning there

You do not need the advanced layers yet. For your first few uses, ignore:

- session bindings
- repo registration
- worktree isolation
- delegate lanes
- JSON schemas

### You are done when

- the agent creates or resumes a task under `.planning/<slug>/`
- the current task becomes visible in your host or shell
- the agent can recover from the task files after an interruption
- the task records real verification before it is called done

### Common first-time mistakes

- using it on work that is too small
- reading `.planning/` before trying a real task
- trying to learn scripts before seeing one successful recovery
- treating the files as the product instead of as the recovery layer

## Track 2: Growing into daily use

### Goal

Make long-running, interruption-prone, multi-task work feel controlled instead of fragile.

You can stop after any level. Each level adds one capability for one new pain point.

Most users grow in this order:

- one session, one task, with the task visible
- deliberate task switching
- a second session for a second task or for observer-only help
- a worktree when two writer tasks need the same repo
- explicit repo registration only when one task truly spans several repos

For each level below, first try the copyable prompt with the agent. Drop to the shell fallback only when your host does not handle that workflow cleanly enough on its own.

### Level 1: Make the base loop boring

When to learn this:

- you already had one success case
- you want a repeatable default workflow instead of a one-off demo

What to do:

- start or resume tasks through normal conversation
- keep the current task visible in your host or shell
- let the agent keep the current task, next action, and verification state current
- treat `verify` as part of the contract, not as optional cleanup

Try saying:

```text
This task will take multiple steps and may span more than one session. Keep the task state current as you work, and verify before you wrap up.
```

If task visibility is not showing yet, say:

```text
Help me make the current task visible in this host. Tell me what cue I should expect, and if setup is missing, point me to the right host-specific doc.
```

Host-specific setup lives in:

- `docs/claude.md`
- `docs/opencode.md`
- `docs/codex.md`

You can ignore until later:

- session bindings
- repo scopes
- worktrees
- delegate lanes

### Level 2: Switch tasks deliberately

When to learn this:

- a new ask appears mid-stream
- you carry local code changes while trying to switch tasks

What to do:

- treat the routing choice explicitly: continue the current task, switch to an existing task, or create a new task
- use `check-task-drift.sh` when the match is uncertain
- expect the dirty-worktree guard to stop unsafe task switches unless you choose `--stash` or `--allow-dirty`

Try saying:

```text
Before you mix this new ask into the active task, check whether it still fits. If it does not, tell me whether we should continue the current task, switch tasks, or create a new one.
```

Useful command:

```bash
sh skill/scripts/check-task-drift.sh --prompt "Also investigate the billing webhook regression" --json
```

You can ignore until later:

- if you normally work on one task at a time, this can stay lightweight

### Level 3: Open a second session for parallel work

When to learn this:

- you want to keep your current task moving while you open another window, tab, or terminal
- you want quick parallel help without losing your place in the first session

What to do:

- open a second session instead of interrupting the first one
- if the second session is about a different problem, tell the agent it is a separate task right away
- if the second session is only helping on the current task, keep it `observer`-only by default
- use the simple rule: new task -> new session; same task but read-only help -> observer session

The most common pattern is:

- one main session doing the real implementation
- one extra session either for a separate task or for read-only help on the same task

Try saying in the new session for a different task:

```text
Keep my auth refactor in the other session. In this new session, start a separate task to investigate the billing webhook regression.
```

Try saying in the new session for read-only help on the same task:

```text
Use this new session only to help with `feature-auth`. Bind it as an observer, and do not edit the main planning files from here.
```

If you are using shell fallback for a different task:

```bash
export PLAN_SESSION_KEY=manual:billing-bug
sh skill/scripts/init-task.sh "Investigate billing webhook regression"
```

If you are using shell fallback for an observer session on the same task:

```bash
export PLAN_SESSION_KEY=manual:feature-auth-review
sh skill/scripts/set-active-task.sh --observe feature-auth
```

You can ignore until later:

- if you only use one session at a time, `.planning/.active_task` remains enough

### Level 4: If the second session also needs to edit code, add a worktree

When to learn this:

- you already opened a second session, and now that second session also needs to write code
- both tasks touch the same repo, so two writer sessions would otherwise share one checkout

What to do:

- keep the first writer task where it is
- before the second writer starts editing, ask the agent to prepare a separate worktree for that task
- keep using observer-only sessions for read-only help; use a worktree only when the second session also needs to write code

The trigger is simple:

- second session + same repo + code changes = use a worktree

Common example:

- one session is still working on `feature-auth`
- a second session now needs to fix a billing bug in the same `frontend` repo

Try saying in the second writer session:

```text
Another task is already editing `frontend` in a different session. Before you change code here, create a separate worktree for this task so the two sessions do not share one checkout.
```

If you are using shell fallback for the new writer task:

```bash
sh skill/scripts/prepare-task-worktree.sh --task frontend-billing-cleanup --repo frontend
```

That checkout lands under `.worktrees/frontend-billing-cleanup/frontend/` by
default, so one task's isolated repo work stays together.

You can ignore until later:

- if your tasks run serially or touch different repos, shared checkouts are still fine

### Level 5: If one task truly spans several repos, move up to a parent workspace

When to learn this:

- one task now needs changes in more than one repo, such as `frontend/` and `backend/`
- you no longer want to manage that work as separate repo-local tasks

What to do:

- open the agent from the parent folder that contains the repos
- keep one shared `.planning/` for the whole task at that parent level
- register the repos once, then scope the task to the repos it may touch

This is the next step after the single-repo story. You only need it when the same task itself crosses repo boundaries.

The trigger is simple:

- one task + two or more repos = use a parent workspace

Common example:

- one session is fixing a signup flow
- the same task needs UI changes in `frontend` and API changes in `backend`

Try saying:

```text
This is one task across `frontend` and `backend`. Start it from the parent workspace, keep one shared planning task for both repos, and scope the task to those repos before you edit anything.
```

If you are using shell fallback from the parent workspace:

```bash
sh skill/scripts/list-repos.sh --discover
sh skill/scripts/register-repo.sh --id frontend frontend
sh skill/scripts/register-repo.sh --id backend backend
sh skill/scripts/init-task.sh --repo frontend --repo backend --primary frontend "Cross-repo auth flow"
```

You can ignore until later:

- single-repo workspaces do not need this ceremony

### Level 6: Use delegates and verification to close cleanly

When to learn this:

- you need a bounded side quest such as repo scanning, risk review, or verification triage
- you want later sessions to tell the difference between `implemented`, `verified`, and `blocked`

What to do:

- use delegate lanes for bounded discovery, review, and verification work
- keep the main task focused and promote only distilled findings back
- record what done means, which checks ran, and what is still blocked

Try saying:

```text
Keep the main task focused. If you need a bounded repo scan, risk review, or verification pass, open a delegate lane and promote only the distilled findings back.
```

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
sh skill/scripts/prepare-task-worktree.sh --task feature-auth --repo frontend
sh skill/scripts/register-repo.sh --id frontend frontend
sh skill/scripts/prepare-delegate.sh --kind discovery "Map auth entry points"
```

By default that worktree lives at `.worktrees/feature-auth/frontend/`.

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
