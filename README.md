# Context Task Planning

Keep complex coding tasks recoverable, visible, and isolated across Claude Code, OpenCode, Codex, and TraeCLI/Coco.

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

### 1. Install for your host

Claude Code recommended install:

```bash
claude plugin marketplace add excitedhaha/context-task-planning
claude plugin install context-task-planning@context-task-planning
```

Then run `/reload-plugins` or restart Claude Code. The plugin bundles the main skill, the `task-*` entry skills, and Claude lifecycle hooks.

Skill-only install for OpenCode, Codex, or Claude Code users who prefer standalone skills:

```bash
npx skills add excitedhaha/context-task-planning -g
```

Choose `context-task-planning` and the agent(s) you want when prompted. Claude Code standalone-skill users can also choose the bundled thin task-entry skills: `task-init`, `task-current`, `task-list`, `task-validate`, `task-drift`, and `task-done`.

If you mainly use OpenCode, you can also enable a small bundled slash-command surface for common task flows. The OpenCode-specific install and smoke-test steps live in `docs/opencode.md`.

TraeCLI/Coco recommended install:

```bash
coco plugin install --type=github excitedhaha/context-task-planning --name context-task-planning
```

Restart TraeCLI/Coco after installation. The plugin exposes the main skill, bundled `/context-task-planning:task-*` slash commands, and lifecycle hooks declared in `coco.yaml`.

If you use Codex and want lifecycle hooks, install the hook package after the skill:

```bash
npx codex-marketplace add excitedhaha/context-task-planning/hooks/context-task-planning --hook --global
```

For preview or local contributor install paths, see `docs/sharing.md`.

### 2. Give the agent one real task

```text
Refactor the auth flow across backend and frontend. This will take multiple steps, may get interrupted, and should be verified before you wrap up.
```

For multi-step or recovery-sensitive work, the agent should usually pick this skill automatically. If your host does not auto-invoke it reliably, mention `context-task-planning` explicitly.

If the prompt does not name the task explicitly, the agent should suggest a concise task title and slug first, then wait for your confirmation before creating `.planning/<slug>/`.

### 3. Check that the task became visible

- `Claude Code` - plugin hooks should inject task context and reminders automatically; plugin task-entry skills appear namespaced, such as `/context-task-planning:task-current` and `/context-task-planning:task-list`
- `OpenCode` - look for `task:<slug> | ...` in the session title, route evidence on high-signal scope switches, and operational toasts for stale planning or binding events; if you also enabled the OpenCode command helpers, bundled slash commands such as `/task-current` or `/task-list` should appear too
- `Codex` - if `codex features list` includes `codex_hooks`, install the optional hook package for session-start task context, high-signal route evidence, and end-of-turn planning sync, or run `sh skill/scripts/current-task.sh` for the full summary and recommended next step
- `TraeCLI/Coco` - plugin hooks inject task context and planning-sync reminders; bundled slash commands appear namespaced, such as `/context-task-planning:task-current` and `/context-task-planning:task-list`

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
- `docs/opencode.md` - OpenCode-specific install steps, slash commands, plugin behavior, and troubleshooting
- `docs/codex.md` - Codex-specific hooks and shell-first workflow
- `docs/trae.md` - TraeCLI/Coco plugin install, slash commands, hooks, and troubleshooting
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

Claude Code users also get thin skill-style entry points for the same high-frequency flows. In plugin installs they are namespaced as `/context-task-planning:<name>`; in standalone skill installs they appear as `/task-*`:

- `task-init <task title>` - create a tracked task from a confirmed title
- `task-current` - inspect the current task and next action
- `task-list` - list existing tasks in the workspace
- `task-validate` - validate the current task without auto-fixing warnings
- `task-drift <new request>` - check whether a new ask still fits the current task
- `task-done [slug]` - mark the current or named task done after verification

OpenCode users also get a small slash-command surface for the same high-frequency flows:

- `/task-init <task title>` - create a tracked task from a confirmed title
- `/task-current` - inspect the current task and next action
- `/task-list` - list existing tasks in the workspace
- `/task-validate` - validate the current task without auto-fixing warnings
- `/task-drift <new request>` - check whether a new ask still fits the current task
- `/task-done [slug]` - mark the current or named task done after verification

See `docs/opencode.md` for OpenCode-specific install details, troubleshooting, and smoke tests.

TraeCLI/Coco users get equivalent plugin-bundled slash commands under the plugin namespace:

- `/context-task-planning:task-init <task title>` - create a tracked task from a confirmed title
- `/context-task-planning:task-current` - inspect the current task and next action
- `/context-task-planning:task-list` - list existing tasks in the workspace
- `/context-task-planning:task-validate` - validate the current task without auto-fixing warnings
- `/context-task-planning:task-drift <new request>` - check whether a new ask still fits the current task
- `/context-task-planning:task-done [slug]` - mark the current or named task done after verification

See `docs/trae.md` for TraeCLI/Coco-specific install details, hooks, and smoke tests.

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
- no built-in cross-machine coordination; `.planning/` can be mirrored across machines, but session bindings and local checkout/worktree state remain machine-local
- no host-specific session-history catchup layer
- the optional adapters are reminders and visibility aids, not a hard transaction system
