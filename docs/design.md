# Design Notes

## Purpose And Scope

This document describes the architecture that is implemented in this repository
today.

`context-task-planning` is no longer just a task-folder convention. The current
system combines three layers that have to work together:

- durable task records under `.planning/<slug>/`
- runtime routing state for multi-session and multi-repo coordination
- checkout isolation through repo bindings and task-specific worktrees

The design goal is to keep the source of truth file-based and portable while
still making parallel AI coding work safe enough for daily use.

What this design optimizes for:

- recovery after context loss without host-specific history replay
- independent routing for parallel agent sessions
- explicit repo ownership in parent-directory multi-repo workspaces
- checkout-aware writer isolation instead of optimistic shared-state editing
- thin host adapters that expose the same core state instead of replacing it

What this design does not try to solve:

- built-in cross-machine coordination, conflict resolution, or distributed locking for mirrored planning state
- a GUI, MCP server, or central database
- silent automatic task switching
- silent repo or workspace inference that mutates state behind the user's back

## System Model

The system is easiest to understand as one planning tree plus one local checkout
tree:

```text
.planning/
  .active_task
  .sessions/
    <session-binding>.json
  .runtime/
    repos.json
    task_repo_bindings/
      <task-slug>.json
  <task-slug>/
    task_plan.md
    progress.md
    findings.md
    state.json
    delegates/
      <delegate-id>/
        brief.md
        result.md
        status.json

.worktrees/
  <task-slug>/
    <repo-id>/
```

The important distinction is:

- `.planning/<slug>/` stores the durable task narrative and machine-readable
  task state
- `.planning/.sessions/` stores who is currently attached to which task and in
  what role
- `.planning/.runtime/` stores workspace-level repo registration and per-task
  checkout overrides
- `.worktrees/` stores task-scoped git checkouts used to isolate overlapping
  writer tasks while keeping one task's repo work together

This separation is deliberate. Task files explain the work. Runtime metadata
routes sessions and repos to the right task. Worktrees isolate concurrent code
changes without turning `.planning/` into a second git state store. The layout
is task-first so a multi-repo task can keep its isolated checkouts together.

Inside each task, the document roles remain stable:

- `task_plan.md` holds the framing and hot context snapshot
- `progress.md` records chronological execution history
- `findings.md` keeps distilled conclusions worth re-reading later
- `state.json` is the authoritative operational snapshot for lifecycle,
  verification, repo scope, and routing metadata

## Task Resolution And Workspace Boundaries

The first architectural question is not "how do we read the task files?" It is
"which task should this session resolve to right now?"

That resolution happens in two stages.

- **Workspace root resolution** starts from the current working directory and
  walks upward.
- **Task selection** then resolves the active task inside that workspace.

Workspace resolution is intentionally conservative. An ancestor `.planning/`
directory is reused only when the current path still belongs to that workspace
through one of these relationships:

- the current path is the workspace root itself
- the current path is inside that workspace's `.planning/`
- the current path is inside a registered repo for that workspace
- the current path is inside a recorded task worktree for that workspace

There is one compatibility path for simpler setups:

- if the workspace has no explicit repo registrations or recorded worktrees yet,
  a direct child git repo may still attach back to the parent workspace

If those checks fail, the resolver falls back to the current directory or git
root instead of silently attaching to an unrelated ancestor `.planning/`.

Once the workspace is known, task selection uses this precedence:

1. explicit `--task <slug>`
2. `PLAN_TASK`
3. the session binding selected by `PLAN_SESSION_KEY`
4. `.planning/.active_task`
5. the latest auto-selectable task

Those sources are not interchangeable.

- `--task` is an explicit command-level override
- `PLAN_TASK` is a temporary shell-level override
- `PLAN_SESSION_KEY` is the normal path for host-managed parallel sessions
- `.active_task` is the compatibility fallback for the shared
  `workspace-default` actor when a host or shell does not provide session
  identity

That means `.active_task` is still useful, but it is no longer the same kind of
signal as an explicit session binding. In multi-session workflows, the real
ownership model lives in `.planning/.sessions/*.json`, while `.active_task`
remains the shared anonymous default.

That ordering is what lets the same workspace support host adapters, manual
shell usage, and backward-compatible fallback behavior at the same time.

### Resolver precedence vs host-visible binding

The resolver may still pick a task from `.active_task` or `latest`, but host
adapters should not treat every resolved task as an equally strong binding.

- `selection_source = session_binding` means the current session is explicitly
  attached to that task
- `selection_source = active_pointer` means the workspace fallback selected the
  task for an anonymous `workspace-default` actor
- `selection_source = latest` is a recovery/default guess, not a stable binding

Recommended adapter behavior:

- use `session_binding` for strong UI such as `task:<slug>` titles, native task
  cues, or write ownership indicators
- treat `active_pointer` as a weaker workspace fallback hint unless the host is
  intentionally running without per-session identity
- never present `latest` as if the session had already been explicitly bound

## Concurrency Model: Sessions, Roles, And Worktrees

The concurrency story has two separate safety rules:

- one writer owns the main planning lane for a task
- different writer tasks must not share the same repo checkout

The first rule protects planning files. The second rule protects code state.

### Session bindings and roles

Session bindings are persisted under `.planning/.sessions/*.json`. Each binding
stores:

- `session_key`
- `task_slug`
- `role`
- `updated_at`

There are two roles:

- `writer` - owns the main planning lane for that task
- `observer` - can inspect the task and work inside delegate lanes, but must not
  edit `task_plan.md`, `progress.md`, `state.json`, or `findings.md`

Important invariants:

- a task may have one writer plus additional observers
- a new writer may take over only with an explicit `--steal`
- taking over the writer lease demotes the previous writer to observer instead of
  silently allowing two writers
- lifecycle commands enforce the same access rules instead of assuming every
  attached session is allowed to mutate the task

Observers are not "inactive" sessions. They are intentionally useful for bounded
parallel work, but their safe write surface is limited to delegate lanes.

### Why worktrees are a first-class part of the design

Worktrees are not a minor implementation detail. They are the core mechanism
that makes parallel writer tasks safe in the same parent workspace.

Repo scope alone is not enough. Two tasks can both be legitimate writer tasks
and still be unsafe if they resolve to the same checkout of the same repo.

So the design tracks two different things:

- **task repo scope** - which repos a task is allowed to touch
- **task repo bindings** - which checkout that task should use for each repo

Each binding resolves to one of two modes:

- `shared` - use the repo's normal checkout in the workspace
- `worktree` - use a task-specific checkout, usually under
  `.worktrees/<task-slug>/<repo-id>/`

That means worktrees are the concurrency boundary for code changes, not just a
convenience feature. The directory layout is task-first even though the safety
check still happens at the repo binding level.

### Writer isolation rule

The system treats these cases differently:

- **safe** - two writer tasks touch different repos
- **safe** - two writer tasks touch the same repo id but through different
  checkout paths
- **unsafe** - two writer tasks resolve to the same repo checkout path

When an unsafe overlap is detected, the second task cannot bind as a writer
until a dedicated checkout exists.

Typical flow:

```text
Task A
  writer session: s1
  frontend -> shared checkout frontend/
  backend  -> shared checkout backend/

Task B
  writer session: s2
  frontend -> conflict with Task A
  resolve by creating .worktrees/task-b/frontend/
  frontend -> worktree checkout .worktrees/task-b/frontend/
```

`prepare-task-worktree.sh` is the explicit command that turns that conflict into
a safe task-scoped layout by creating the checkout and recording the task's
repo binding.

### Delegates are the observer-safe concurrency lane

Because observers may not mutate the main planning files, delegate lanes are the
sanctioned place for bounded parallel work such as:

- repository exploration
- design spikes
- verification triage
- focused review
- catch-up summaries

Each delegate keeps its own scratch state under `delegates/<delegate-id>/`.

That is why the system can support one writer plus multiple useful parallel
sessions without turning task planning into uncontrolled shared editing.

## Repo Model In Parent Workspaces

Single-repo workspaces can still work implicitly when the workspace root is
itself a git root.

Parent-directory workspaces need a more explicit model.

- **Workspace repo registry** lives in `.planning/.runtime/repos.json`
- **Task repo scope** lives in `state.json` as `repo_scope` and `primary_repo`
- **Task checkout bindings** live in
  `.planning/.runtime/task_repo_bindings/<task-slug>.json`

Auto-discovery exists only as a review aid. Registration stays explicit so the
workspace does not accidentally claim unrelated repos.

This design gives each task three levels of repo intent:

- which repos exist in the workspace
- which of those repos the task is allowed to touch
- which checkout path the task should actually use for each repo

That last level is what lets multi-session parallelism stay safe when two tasks
both need the same repo but cannot share the same checkout.

The same worktree metadata also feeds workspace resolution. Once a task has a
recorded worktree binding, entering from that `.worktrees/...` path still
resolves back to the same parent workspace and the same task state.

## Recovery And Guardrails

Recovery is a two-step process:

1. resolve the workspace and current task
2. rebuild the task snapshot from task files

After the task is selected, recovery order is:

1. `state.json`
2. the hot context at the top of `task_plan.md`
3. recent `progress.md` entries
4. unresolved delegate status files

Several guardrails reuse the same core routing model.

- **Task-focus guard** uses the resolved task to decide whether a new prompt
  looks related, unclear, or likely unrelated
- **Switch-safety guard** checks dirty git worktrees before task switching so
  code changes are not silently carried across tasks
- **Validation** checks consistency across task files, delegate state, session
  bindings, and runtime metadata

These guards are intentionally lightweight. They do not attempt to become a hard
transaction manager. Their job is to prevent the most common silent failures in
long-running agent work.

## Host Adapters And Boundaries

The canonical truth still lives in `skill/scripts/` plus the files under
`.planning/`.

Host adapters are optional layers on top of that core.

- **Claude Code plugin hooks** surface task, role, repo context, and high-signal
  route evidence on top of the shared resolver; manual settings hooks remain a fallback
- **OpenCode plugin** injects recovery and native-`Task` context, exports
  `PLAN_SESSION_KEY`, and surfaces repo and role context without becoming a second planner
- **Codex hooks** inject session-start task context, high-signal route evidence,
  and end-of-turn planning sync reminders, while still falling back to the same scripts
  and file protocol when hooks are not enabled
- **TraeCLI/Coco plugin hooks** expose the same skill and slash-command workflow
  through `coco.yaml`, inject session-start and native-`Task` context, and reuse the
  same end-of-turn planning-sync guardrails without becoming a separate planner

Adapters must not become the source of truth. They surface and route the same
file-backed state; they do not replace it.

## Tradeoffs

This architecture keeps the system local, inspectable, and portable, but it also
comes with explicit tradeoffs.

- `.active_task` remains for compatibility as the `workspace-default` fallback
  even though session bindings are the preferred model
- repo auto-discovery stays advisory because silent wrong registration is worse
  than an extra explicit step
- workspace resolution prefers conservative fallback over aggressive ancestor
  reuse
- worktree management is explicit because safe parallelism is more important than
  hiding concurrency costs
- the system optimizes for local durability and coordination, not distributed
  collaboration semantics

In practice, the design settled into its current shape because real AI coding
work exposed three constraints at once:

- one global active-task pointer was not enough for parallel sessions
- one shared parent workspace needed repo-aware boundaries
- one shared repo checkout was not enough for overlapping writer tasks

The result is still one file-backed protocol, but now with session routing,
repo-aware task scope, and worktree-aware writer isolation as first-class parts
of the architecture rather than afterthoughts.
