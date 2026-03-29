# Context Task Planning

Keep complex coding tasks recoverable, visible, and isolated across Claude Code, OpenCode, and Codex.

`context-task-planning` gives a coding agent a task-scoped workspace on disk so it can:

- resume after context loss, model switches, or agent switches
- keep the current task visible
- avoid silently mixing unrelated work into the same lane
- record real verification before calling the task done

Most users should talk to the agent, not manage planning files or shell scripts by hand.

For larger tasks, the agent should capture a lightweight brief before deep implementation: goal, non-goals, acceptance criteria, constraints, and verification expectations.

You do not need to choose a spec mode up front. If the repo has no established spec artifacts, the agent keeps that brief in `.planning/<slug>/`. If the repo already has an external spec workflow, the runtime can reuse those refs instead of re-creating them under `.planning/`.

## When to use it

Use it when the work is:

- multi-step or long-running
- likely to be interrupted and resumed later
- large enough that one chat session is not a safe source of truth
- likely to spawn bounded side quests such as repo scans, reviews, or verification passes

Skip it for tiny one-shot edits that do not need recovery.

## Quickstart

### 1. Install the skill

Recommended install:

```bash
npx skills add excitedhaha/context-task-planning -g
```

Choose `context-task-planning` and the agent(s) you want when prompted.

For preview or local contributor install paths, see `docs/sharing.md`.

### 2. Give the agent one real task

```text
Refactor the auth flow across backend and frontend. This will take multiple steps, may get interrupted, and should be verified before you wrap up.
```

For multi-step or recovery-sensitive work, the agent should usually pick this skill automatically. If your host does not auto-invoke it reliably, mention `context-task-planning` explicitly.

### 3. Check that the task became visible

- `Claude Code` - look for `task:<slug>` in the status line
- `OpenCode` - look for `task:<slug> | ...` in the session title plus task/drift toasts
- `Codex` - run `sh skill/scripts/current-task.sh` for the full summary and recommended next step, or `sh skill/scripts/current-task.sh --compact` for a prompt-friendly cue

In some repos, that summary may also mention a linked spec ref or a short candidate hint. Treat that as scoping help, not as extra setup you need to do before normal work.

### 4. Simulate one recovery

```text
I lost context on this task. Recover the active task from local planning files and continue from the recorded next action.
```

If the agent can continue from `.planning/<slug>/` without you re-teaching the whole task, the workflow is working.

When the task has grown enough that replaying multiple markdown files feels noisy, a compact recovery view is available. See `docs/onboarding.md` for when to use it.

### 5. If this worked, choose only the next doc you need

- `docs/onboarding.md` - the full user journey, from first success to multi-session, multi-repo, worktree, delegate, and verification workflows
- `docs/claude.md` - Claude-specific setup and cues
- `docs/opencode.md` - OpenCode-specific plugin behavior and limits
- `docs/codex.md` - Codex-specific shell-first workflow
- `docs/design.md` - the deeper architecture
- `docs/spec-aware-task-runtime.md` - spec-aware design notes, mainly for contributors or deeper implementation questions

If you only wanted one successful first run, you can stop here.

If you keep using the skill, the next section is the short map of what to learn next.

## If you keep using it

Start with just these three things:

- one durable task
- visible task state
- recovery plus verification

Add the deeper layers only when you need them:

- task switching - drift checks plus dirty-worktree guardrails
- parallel sessions - `writer` and `observer` bindings
- parent workspaces - explicit repo registration plus task repo scope
- overlapping writer tasks - task-specific worktrees
- bounded side quests - delegate lanes

`docs/onboarding.md` walks through those layers in order and explains when each one is worth learning.

The shared shell entry points now map cleanly to those basics:

- `sh skill/scripts/current-task.sh` - human-readable summary of the resolved task plus the recommended next step
- `sh skill/scripts/current-task.sh --compact` - short status for prompts, tmux, or status bars
- `sh skill/scripts/compact-context.sh` - compact recovery view for larger tasks; see `docs/onboarding.md`
- `sh skill/scripts/validate-task.sh --fix-warnings` - repair warning-level snapshot drift after manual edits or long-running work

## What stays on disk

Usually all you need to care about is:

```text
.planning/<slug>/
  task_plan.md
  findings.md
  progress.md
  state.json
```

Advanced workflows may also add derived recovery artifacts, session bindings,
repo metadata, and task-scoped `.worktrees/`, but they stay local and
inspectable. `docs/onboarding.md` covers when those extra layers are worth
learning.

## Limitations

- the portable contract is file-based, so host-specific UI differs
- no cross-machine sync
- no host-specific session-history catchup layer
- the optional adapters are reminders and visibility aids, not a hard transaction system
