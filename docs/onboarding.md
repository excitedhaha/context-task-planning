# Onboarding

Use this guide if you want a more directed path than the main `README.md`.

It has two tracks:

- `First-time users` - get to a real success case in a few minutes
- `Heavy AI coding users` - fold the skill into a daily multi-task workflow without turning it into overhead

## Start here

You do not need to learn the full file protocol up front.

For the first few sessions, only learn these ideas:

- `task` - the current unit of work
- `next action` - what the agent should do next
- `recover` - resume from `.planning/` after context loss
- `verify` - record real checks before calling the task done

Everything else can wait.

## Track 1: First-time users

### Goal

Reach one clear aha moment: you can leave a long coding task, come back later, and continue without re-explaining everything.

### 3-minute path

#### Step 1: Install the skill

Install the skill:

```bash
npx skills add excitedhaha/context-task-planning -g
```

Do not start by learning scripts. If you want in-host task visibility after your first success case, follow the host notes later:

- `Claude Code` - `docs/claude.md`
- `OpenCode` - `docs/opencode.md`
- `Codex` - `docs/codex.md`

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

If you do not yet see a host cue, enable it through the host notes listed in Step 1.

This matters because visible task state is what makes silent task mixing harder.

#### Step 4: Simulate a recovery

In the same repo, ask:

```text
I lost context on this task. Recover the active task from local planning files and continue from the recorded next action.
```

If the agent can continue from `.planning/<slug>/` without you re-teaching the whole task, the workflow is working.

#### Step 5: Stop learning there

For your first few uses, ignore these concepts unless you hit a real need:

- delegate lanes
- session-scoped task binding
- manual task switching
- archive semantics
- JSON schemas

### What first-time users care about most

- `Will this save me time?`
- `Can I resume tomorrow without replaying the whole task?`
- `Will it keep the agent from drifting into another problem?`
- `Do I need to manage files by hand?`

The intended answers are:

- yes, if the task is big enough
- yes, that is a core goal
- often yes, especially when host cues are enabled
- no, not in the normal path

### Common first-time mistakes

- using it on work that is too small
- reading `.planning/` before trying a real prompt
- trying to learn every script before seeing one successful recovery
- assuming the files are the product, instead of the support system

## Track 2: Heavy AI coding users

### Goal

Make long-running, interruption-prone, multi-task work feel controlled instead of fragile.

### When this skill starts paying off

Use it as part of your default workflow when you regularly do things like:

- run multiple coding threads in one repository
- switch between Claude Code, OpenCode, and Codex
- hand work to subagents or isolated review/research passes
- pick up unfinished work after sleep, meetings, or context clears
- need a durable record of what is done, blocked, or still unverified

### Recommended heavy-user path

#### Level 1: Standardize your opening prompt

Use one consistent ask for large work:

```text
Refactor the auth flow across backend and frontend. This will take multiple steps, may get interrupted, and I want the work kept organized as you go. Verify before you wrap up.
```

This reduces ambiguity and makes agent behavior more repeatable.

For work like this, the agent should usually pick the skill automatically. If it does not in your setup, add `context-task-planning` explicitly as a fallback.

#### Level 2: Treat task visibility as required, not optional

If you cannot see the current task, you are more likely to mix work.

- `Claude Code` - use the status line
- `OpenCode` - use the title prefix and toasts
- `Codex` - put `sh skill/scripts/current-task.sh --compact` in your shell or tmux workflow

#### Level 3: Use task switching deliberately

When a new ask appears mid-stream, treat it as a routing decision:

- continue the current task
- switch to an existing task
- create a new task

If the match is uncertain, use:

```bash
sh skill/scripts/check-task-drift.sh --prompt "Also investigate the billing webhook regression" --json
```

The goal is not perfect classification. The goal is to stop silent task mixing.

#### Level 4: Use delegate lanes only for bounded side quests

Good uses:

- repo scanning
- risk review
- test triage
- option comparison

Bad uses:

- concurrent edits to the main planning files
- broad, open-ended implementation work
- risky release or migration actions

If you are about to ask a subagent a narrow question, that is the right time to create a delegate lane.

#### Level 5: Make verification part of the contract

Do not let a task end at "the agent says it is done".

Make sure the task records:

- what done means
- which checks were run
- what failed or remains blocked

This is especially useful when a later session needs to tell the difference between `implemented`, `verified`, and `probably fine`.

### What heavy users should learn next

- `PLAN_SESSION_KEY` plus `set-active-task.sh` / `resume-task.sh` when multiple terminals or sessions need independent current tasks
- explicit `register-repo.sh` / `set-task-repos.sh` when one parent workspace contains several git repos
- `validate-task.sh` when task files may have drifted
- delegate lane lifecycle for repeated subagent use
- pause / resume / done / archive commands when task history starts to matter

When you adopt the parent-workspace multi-repo pattern, keep the shared `.planning/` at that parent level. After repos are registered, entering from `frontend/`, `backend/`, or a recorded `.worktrees/...` checkout still resolves back to the same workspace; unrelated ancestor `.planning/` directories should not steal that resolution.

### What heavy users still should not optimize too early

- full manual editing of every planning file
- custom workflow rules before the base loop feels natural
- overusing delegates for every small question
- turning the system into a ceremony layer for trivial tasks

## Real workflow examples

### Example: First-time success case

1. Start a cross-file refactor.
2. Let the agent create the task.
3. Interrupt the session.
4. Ask the agent to recover.
5. Confirm it continues from the saved next action.

If that works, you have already learned the most important part.

### Example: Heavy-user daily loop

1. Start or resume one main task.
2. Keep the active task visible.
3. Check drift before mixing a new complex ask into the same lane.
4. Use delegate lanes for bounded exploration or review.
5. Record verification before done.

## If the system feels too heavy

Use this minimum viable workflow:

1. start one task
2. keep the task visible
3. recover from `.planning/` after interruption
4. verify before done

Ignore everything else until you feel the pain that those extra controls are meant to solve.
