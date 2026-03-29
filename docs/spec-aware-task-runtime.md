# Spec-Aware Task Runtime

## Goal

Absorb the useful parts of spec coding without turning
`context-task-planning` into another full spec framework.

The intended result is:

- keep `agent-first` as the default user experience
- provide a lightweight task brief when a repo has no spec framework yet
- reuse existing spec artifacts when a repo already has a framework such as
  OpenSpec
- keep `.planning/` focused on execution state, recovery, routing, and
  verification instead of making it a second repo-level source of truth

## Non-goals

- do not clone the OpenSpec lifecycle of proposal, delta specs, archive, and
  merge
- do not require users to run new shell commands before normal work can start
- do not make host adapters a second planner or a hidden writeback layer
- do not auto-create or auto-edit external spec framework artifacts in the
  first pass
- do not force tiny one-shot tasks through a heavyweight spec ritual

## Why This Shape

Spec coding and `context-task-planning` solve different layers of the same
problem.

- spec frameworks are strongest at agreeing on intent before code exists
- this project is strongest at keeping long-running AI execution recoverable,
  visible, isolated, and verifiable

That means the right move is not replacement. The right move is to make the
task runtime spec-aware.

The practical product position becomes:

- `what should we build?` -> external spec framework when one exists, otherwise
  a lightweight embedded task brief
- `how do we keep the work safe across long sessions?` ->
  `context-task-planning`

## Principles

### Agent-first, shell-fallback

Most users should still talk to the agent. Scripts remain the fallback and the
shared core contract, not the recommended primary UX.

### One runtime, multiple context sources

The runtime should work the same way whether task intent comes from:

- embedded task brief fields inside `.planning/<slug>/`
- linked external artifacts such as `openspec/changes/...`

### Embedded when absent, linked when present

If a repo has no established spec framework, the task should still gain a
minimal spec-quality brief. If a repo already has one, the runtime should link
to it instead of re-creating its structure under `.planning/`.

### Verification should track acceptance, not just commands

The current verify model is valuable, but spec-aware behavior should tie
verification back to acceptance criteria and definition of done wherever
possible.

### Keep shared truth in the shared core

Detection, linking, drift terms, and preflight payloads should stay in the
shared shell/Python core, mainly `task_guard.py` plus the existing task files.
Host adapters should surface the same truth, not invent their own version.

## Operating Modes

### Mode A: Embedded Brief

Use this when the repo does not expose a recognized spec framework.

The task itself carries a lightweight spec-quality brief inside the existing
files.

Required planning fields become:

- `goal`
- `non_goals`
- `acceptance_criteria`
- `constraints`
- `open_questions`
- `definition_of_done`
- `verify_commands`

Optional but useful fields:

- `edge_cases`
- `assumptions`
- `change_surface`

This mode should feel like a stronger version of the existing `clarify` phase,
not like a separate framework install.

### Mode B: Linked Spec Context

Use this when the repo already has a spec framework or spec artifacts that are
already treated as authoritative by the team.

In this mode:

- external artifacts remain the intent source of truth
- `.planning/<slug>/` stores execution state and the link to those artifacts
- recovery, drift checks, and subagent preflight read the external context but
  do not own it

The first provider should be OpenSpec because its repo layout is stable and easy
to identify. Later providers can be added once their artifact patterns are
validated in real projects.

## Data Model

### State fields

Extend `state.json` with a minimal spec-aware contract.

```json
{
  "goal": "Ship dark mode for the settings page.",
  "non_goals": [
    "Do not redesign unrelated pages."
  ],
  "acceptance_criteria": [
    "Users can switch between light and dark mode from settings.",
    "The selected theme persists across reloads.",
    "System preference is used only as the initial default."
  ],
  "constraints": [
    "Reuse the existing design system tokens.",
    "Do not add a new state library."
  ],
  "open_questions": [],
  "edge_cases": [
    "First load when no preference is stored.",
    "Theme switch while another tab is open."
  ],
  "spec_context": {
    "mode": "embedded",
    "provider": "none",
    "status": "none",
    "primary_ref": "",
    "artifact_refs": [],
    "summary": []
  }
}
```

Recommended semantics:

- `acceptance_criteria` is the minimum useful spec addition
- `edge_cases` stays optional in P0, but the runtime should preserve and surface
  it when present
- `spec_context.mode` is `embedded`, `linked`, or `none`
- `spec_context.provider` is `none`, `openspec`, `spec-kit`, or `generic`
- `spec_context.status` is `none`, `detected`, `linked`, or `ambiguous`

### Markdown structure

Extend `task_plan.md` so the human-readable task brief matches the state model.

Suggested sections:

- `Goal`
- `Non-Goals`
- `Acceptance Criteria`
- `Constraints`
- `Open Questions`
- `Edge Cases`
- `Definition of Done`
- `Verification Commands`
- `Spec Context`

The top `Hot Context` block should stay compact. It should summarize these
fields rather than duplicate every bullet.

## Runtime Touchpoints

### Init and clarify

`init-task.sh` should keep the current `clarify` mode, but the initial next step
should now explicitly call out acceptance criteria in addition to goal,
non-goals, constraints, and questions.

Expected behavior:

- no new public command
- same task folder layout
- stronger initial template
- optional provider detection during initialization or first recovery

### Current task summary

`current-task.sh --json` should expose spec-aware fields needed by adapters.

Recommended additions:

- `acceptance_criteria`
- `edge_cases`
- `spec_context`
- `brief_quality` or `brief_missing_fields` if we need light guidance without
  hard failure

The human-readable summary should stay short. It should mention only the
highest-signal spec facts, such as:

- whether acceptance criteria exist
- whether the task is using embedded or linked spec context
- whether clarification is still incomplete

### Compact recovery

`compact-context.sh` should include distilled acceptance criteria, edge cases,
and linked artifact refs in the derived compact payload.

This matters because spec coding is valuable mainly when that intent survives
context loss. The compact artifact is the natural place to preserve it.

### Drift checks

`check-task-drift.sh` should expand the task signature beyond the current goal.

Relevant matching inputs should include:

- `goal`
- `acceptance_criteria`
- `non_goals`
- provider-specific artifact names or change identifiers when linked

This should improve routing confidence without introducing an extra LLM-based
classifier.

### Subagent preflight

`subagent-preflight.sh` should inject the smallest useful spec context in the
canonical prompt prefix.

For embedded mode, include a short acceptance summary.

For linked mode, include:

- provider name
- primary artifact reference
- optional artifact refs when they add concrete scope boundaries

The payload should remain short and stable. It should not dump whole spec files
into every subagent launch.

### Validation

`validate-task.sh` should treat missing brief fields as warnings when the task
has already moved into `execute` or `verify` without enough intent captured.

P0 warning candidates:

- `goal` exists but `acceptance_criteria` is empty for a complex task
- `task_plan.md` and `state.json` disagree on acceptance criteria counts or
  content
- `spec_context.status = ambiguous` but no human resolution was recorded

Warnings should stay repairable and advisory in the first pass.

## Provider Model

### Shared provider contract

The shared core should detect providers through a small, explicit contract.

Each provider should answer:

- is this provider present in the repo?
- what artifacts look like the best current task candidates?
- what short summary should the runtime surface?
- what stable refs can recovery and preflight include?

The first implementation can stay inside `task_guard.py`. A separate module only
becomes worth it after the second provider is real.

### OpenSpec first

OpenSpec is the best first linked provider because it has stable, repo-visible
artifacts such as:

- `openspec/specs/...`
- `openspec/changes/...`

P1 behavior for OpenSpec should be read-mostly:

- detect that OpenSpec exists
- detect likely relevant change folders when possible
- link the task to one chosen change or spec reference
- surface those refs in recovery, drift, and preflight
- never auto-edit OpenSpec artifacts in the first pass

### Spec Kit later

Spec Kit should be treated as a follow-on provider, not a reason to block the
first rollout.

Its workflow is real, but the runtime should only claim first-class integration
after we validate stable artifact patterns from real repos. Until then, a
generic or low-confidence detection path is safer than a misleading hardcoded
adapter.

### Linking rules

The runtime should follow conservative rules:

- if no provider is present, use embedded mode
- if exactly one provider and one clear artifact candidate exist, link it
- if several candidates exist, mark `spec_context.status = ambiguous` and ask
  the user to confirm
- never silently switch a task from one linked artifact to another

## Rollout

### P0: Lite Task Brief

Goal: give repos without a spec framework a useful embedded spec layer.

Deliverables:

- add `acceptance_criteria` to the task state schema
- add `Acceptance Criteria`, `Edge Cases`, and `Spec Context` sections to the
  task template
- update `init-task.sh` wording to require a richer clarify step
- surface acceptance criteria in compact recovery
- add warning-level validation for missing acceptance on active complex tasks
- update skill and user docs so the agent-first path asks for a lightweight task
  brief before execution

Why this phase first:

- it improves the default experience immediately
- it does not depend on any external framework
- it keeps the mental model small

### P1: OpenSpec bridge

Goal: integrate with the clearest existing spec framework without cloning it.

Deliverables:

- detect OpenSpec presence from the shared core
- attach `spec_context` metadata to current task resolution
- show linked artifact refs in `current-task`, compact recovery, and preflight
- include linked refs in drift terms
- surface spec context in the OpenCode plugin and Claude/Codex-facing docs

Guardrails:

- do not generate OpenSpec changes automatically
- do not archive OpenSpec changes
- do not write back to OpenSpec files in the first pass

### P2: More providers and stronger verify semantics

Goal: expand the bridge carefully after P0 and P1 prove useful.

Possible follow-ons:

- explicit provider adapters beyond OpenSpec
- better verify summaries tied to acceptance criteria status
- optional commands or prompts to record a manual provider link when detection is
  ambiguous
- a generic linked-artifact path for teams using homegrown spec folders

P2 should stay optional. The default user story should remain lightweight.

## File Changes

### P0

- `skill/templates/task_plan.md`
- `skill/scripts/init-task.sh`
- `skill/schemas/state.schema.json`
- `skill/scripts/compact_context.py`
- `skill/scripts/task_guard.py`
- `skill/scripts/validate-task.sh`
- `skill/SKILL.md`
- `skill/examples.md`
- `README.md`
- `docs/onboarding.md`

### P1

- `skill/scripts/task_guard.py`
- `skill/scripts/compact_context.py`
- `skill/scripts/validate-task.sh`
- `skill/opencode-plugin/task-focus-guard.js`
- `docs/opencode.md`
- `docs/claude.md`
- `docs/codex.md`

## Verification

P0 should extend the existing smoke and validation path instead of creating a
second test style.

Recommended checks:

- extend `skill/scripts/smoke-test-cli-guidance.sh` for acceptance-criteria
  output and warning coverage
- add a focused smoke test for linked-provider detection once P1 exists
- `for f in skill/scripts/*.sh; do sh -n "$f"; done`
- `python3 -m py_compile skill/claude-hooks/scripts/*.py` when Python hook code
  changes
- relevant smoke test plus `sh skill/scripts/validate-task.sh`

## Open Questions

- should `acceptance_criteria` be required for every task, or only for tasks that
  cross a complexity threshold?
- should provider linking live entirely in `task_guard.py` until at least two
  real providers exist?
- the first resolution path can stay lightweight: write an explicit
  `spec_context` override through a thin helper such as
  `set-task-spec-context.sh`, and keep provider files read-only in P1

## Recommended First Implementation

The smallest high-value sequence is:

1. ship P0 embedded brief support
2. dogfood it until acceptance criteria and warning behavior feel right
3. add a read-only OpenSpec bridge in P1
4. delay deeper provider work until the first bridge proves valuable

That sequence keeps the existing low-friction character of the project while
still making it meaningfully better aligned with spec coding workflows.
