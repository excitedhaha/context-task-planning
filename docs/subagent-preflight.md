# Subagent Preflight

## Goal

Strengthen multi-repo subagent behavior by giving Claude Code, OpenCode, Codex, and TraeCLI/Coco one shared preflight contract for routing, repo/worktree context injection, and delegate escalation.

The intended result is:

- native host subagents stay the default path for bounded work
- delegate remains optional durability and isolation infrastructure
- multi-repo context reaches child agents consistently across hosts
- shell-first workflows remain first-class instead of depending on hidden adapter logic

## Non-goals

- do not make delegate the default wrapper around every subagent launch
- do not auto-create delegate lanes in the first pass
- do not duplicate task, repo, or worktree resolution inside host adapters
- do not make Codex depend on hidden runtime interception before a real adapter exists
- do not change the single-writer rule for `task_plan.md`, `progress.md`, `findings.md`, or `state.json`

## Design Summary

The system should treat native subagent execution as primary and file-backed delegate lanes as optional escalation.

Escalation is driven by durable workflow needs, not by subagent usage alone.

- `multi-repo` alone is not enough to require delegate
- `Task` launch alone is not enough to require delegate
- bounded same-session work should usually stay on the native path
- observer-safe concurrency, durable lifecycle, or closeout blocking should escalate to delegate

## Shared Core

P0 adds one shared shell-first preflight entry point:

- `skill/scripts/subagent-preflight.sh`

The wrapper should call a new `task_guard.py` subcommand instead of introducing a second Python core:

- `python task_guard.py subagent-preflight ...`

This keeps task resolution, drift classification, repo scope, and worktree binding truth in one place.

## Inputs

### CLI

Recommended shell contract:

```bash
sh skill/scripts/subagent-preflight.sh \
  --cwd <path> \
  --session-key <key> \
  --host claude|opencode|codex|trae \
  --task-text "<description prompt command subagent_type combined>" \
  --tool-name Task \
  --json
```

P0 flags:

- `--cwd` - current working directory for workspace and task resolution
- `--session-key` - optional session binding key; defaults to normal resolution rules
- `--host` - `claude`, `opencode`, `codex`, `trae`, or `generic`; used only for formatting hints, not for source-of-truth routing
- `--task` - optional explicit task slug override
- `--task-text` - normalized text that represents the outbound subagent request
- `--tool-name` - defaults to `Task`; allows future reuse in other tool-time checks
- `--json` - machine-readable output for adapters and wrappers
- `--text` - optional prompt-ready text output for manual shell-first usage
- `--compact` - optional short decision summary

### Data sources

The helper should reuse existing shared state only:

- current task resolution from `task_guard.py current-task`
- drift classification from `task_guard.py check-drift`
- repo scope and bindings from current task metadata
- session role from the resolved binding (`writer` or `observer`)

Adapters must not re-derive this information independently.

## Decision Model

P0 decisions:

- `routing_only`
- `payload_only`
- `payload_plus_delegate_recommended`
- `delegate_required`

### Decision rules

#### `routing_only`

Return this when:

- there is no active task
- the prompt is empty
- drift is `likely-unrelated`
- drift is `unclear`
- there is no meaningful repo/worktree payload to inject

Effect:

- do not inject canonical repo/worktree payload
- emit routing or confirmation language only

#### `payload_only`

Return this when all of these are true:

- active task exists
- drift is `related`
- the host request is a native `Task` launch
- repo/worktree context exists and is meaningful
- delegate is not required or especially helpful

Effect:

- inject canonical repo/worktree payload
- no delegate escalation language beyond normal guardrails

#### `payload_plus_delegate_recommended`

Return this when `payload_only` would apply and at least one recommendation trigger is true:

- child work may outlive the current session
- output is large enough that durable artifacts would help
- multiple sibling side quests need explicit tracking
- prompt looks like bounded discovery, review, verify, or spike work

Effect:

- inject canonical payload
- add explicit but non-blocking delegate recommendation

#### `delegate_required`

Return this when any hard escalation trigger is true:

- current session is `observer`
- side work must block `done` or `archive`
- side work needs durable lifecycle states
- side work must survive context loss before promotion

Effect:

- do not treat the native subagent launch as sufficient on its own
- show explicit delegate-required guidance
- keep delegate creation explicit in P0

## Canonical Payload

The helper must emit both structured JSON and a prompt-ready text block derived from the same fields.

### JSON contract

Recommended P0 JSON fields:

```json
{
  "found": true,
  "host": "claude",
  "tool_name": "Task",
  "decision": "payload_only",
  "decision_reason": "task-related request with meaningful repo context",
  "routing": {
    "classification": "related",
    "recommendation": "continue-current-task"
  },
  "task": {
    "slug": "strengthen-subagent-use-in-multi-repo-workflows",
    "status": "active",
    "mode": "execute",
    "current_phase": "execute",
    "spec_context": {
      "mode": "linked",
      "provider": "openspec",
      "status": "ambiguous",
      "primary_ref": "",
      "artifact_refs": [
        "openspec/changes/auth-runtime",
        "openspec/changes/runtime-auth"
      ],
      "summary": [
        "Detected OpenSpec under openspec but found multiple plausible artifact candidates.",
        "Record a manual link or narrow the task wording before treating one candidate as authoritative."
      ]
    },
    "spec_candidate_refs": [
      "openspec/changes/auth-runtime",
      "openspec/changes/runtime-auth"
    ],
    "spec_resolution_hint": "sh skill/scripts/set-task-spec-context.sh --task strengthen-subagent-use-in-multi-repo-workflows --ref <chosen-spec-ref>",
    "spec_resolution_commands": [
      "sh skill/scripts/set-task-spec-context.sh --task strengthen-subagent-use-in-multi-repo-workflows --ref openspec/changes/auth-runtime",
      "sh skill/scripts/set-task-spec-context.sh --task strengthen-subagent-use-in-multi-repo-workflows --ref openspec/changes/runtime-auth"
    ],
    "binding_role": "writer",
    "writer_display": "manual:feature-auth",
    "observer_count": 0
  },
  "repo_context": {
    "primary_repo": "frontend",
    "repo_scope": ["frontend", "backend"],
    "repo_summary": "frontend shared; backend isolated in task worktree",
    "repos": [
      {
        "id": "frontend",
        "path": "/workspace/frontend",
        "binding_mode": "shared",
        "checkout_path": "/workspace/frontend",
        "branch": "feature/subagent-preflight",
        "base_branch": "main",
        "write_policy": "allowed"
      },
      {
        "id": "backend",
        "path": "/workspace/backend",
        "binding_mode": "worktree",
        "checkout_path": "/workspace/.worktrees/task/backend",
        "branch": "task/subagent-preflight-backend",
        "base_branch": "main",
        "write_policy": "prefer_isolated"
      }
    ]
  },
  "delegate": {
    "kind": "discovery",
    "recommended": false,
    "required": false,
    "reason": "",
    "command": ""
  },
  "prompt_prefix": "...",
  "operator_message": "..."
}
```

### Prompt prefix template

P0 text block should be short, stable, and host-neutral:

```text
[context-task-planning] Current task: <slug> | role: <writer-or-observer> | routing: <classification>
Treat this subagent request as part of the current task only. Do not silently broaden scope.
Primary repo: <primary_repo>
Repo scope: <repo_scope>
Repo/worktree bindings:
- <repo-id>: <binding_mode> at <checkout_path>
- <repo-id>: <binding_mode> at <checkout_path>
- Spec context: mode=`linked` | provider=`openspec` | status=`ambiguous`
- Spec candidates: <candidate-ref>; <candidate-ref>
- Resolve explicitly: sh skill/scripts/set-task-spec-context.sh --task <slug> --ref <chosen-spec-ref>
- If this subagent needs an authoritative spec ref, resolve one explicitly first. Exploratory work may reference these as non-authoritative candidates.
If repo ownership or task fit becomes unclear, report that back instead of switching tasks implicitly.
```

When the spec context is already `linked`, keep the existing primary ref or linked artifact refs in the same slot instead of the ambiguous candidate list.

If `decision` is `payload_plus_delegate_recommended`, append:

```text
Delegate recommended: this looks like bounded <kind> work and may benefit from a durable lane.
Optional command: <prepare-delegate-command>
```

If `decision` is `delegate_required`, replace the normal payload-first guidance with:

```text
Delegate required: do not treat this side work as a free-form native subagent task under the current session.
Create or reuse a delegate lane first: <prepare-delegate-command>
```

## Host Integration

### Claude Code

Flow:

```text
Task launch
-> pre_tool_use.py
-> hook_common.py helper wrapper
-> sh skill/scripts/subagent-preflight.sh --json ...
-> decision + prompt_prefix
-> mutate outgoing Task prompt if allowed
```

Implementation points:

- `skill/claude-hooks/scripts/hook_common.py`
  - add a wrapper that shells out to `subagent-preflight.sh`
  - stop hardcoding blanket delegate-preferred Task messaging
- `skill/claude-hooks/scripts/pre_tool_use.py`
  - keep this as the only prompt mutation point
  - call the helper for `Task` tools only
  - inject `prompt_prefix` only for `payload_only` and `payload_plus_delegate_recommended`
  - emit routing-only or delegate-required guidance otherwise
- `skill/claude-hooks/scripts/user_prompt_submit.py`
  - keep advisory messaging aligned with the same decisions
  - do not mutate Task prompts here

### OpenCode

Flow:

```text
Task launch
-> tool.execute.before
-> runJsonScript(subagent-preflight.sh, ...)
-> decision + prompt_prefix
-> mutate output.args.prompt if allowed
```

Implementation points:

- `skill/opencode-plugin/task-focus-guard.js`
  - derive `task_text` from actual Task args at `tool.execute.before`
  - call `subagent-preflight.sh` through the existing JSON script path
  - keep freshness reminders separate from preflight decisions
  - preserve current title/toast behavior in P0

### Codex

Flow:

```text
manual or wrapper-driven Task launch
-> sh skill/scripts/subagent-preflight.sh --json or --text ...
-> decision + prompt_prefix
-> wrapper or operator includes prompt_prefix in Task input
```

Implementation points:

- Codex hooks can inject prompt-time reminders, but current Codex `PreToolUse` cannot safely inject `additionalContext` or rewrite native subagent prompts
- keep native subagent preflight as a shell-first or wrapper-driven flow in P0
- if a future native interception surface exists, it must call this same helper

## File Changes For P0

New files:

- `docs/subagent-preflight.md`
- `skill/scripts/subagent-preflight.sh`

Modified files:

- `skill/scripts/task_guard.py`
- `skill/claude-hooks/scripts/hook_common.py`
- `skill/claude-hooks/scripts/pre_tool_use.py`
- `skill/claude-hooks/scripts/user_prompt_submit.py`
- `skill/opencode-plugin/task-focus-guard.js`
- `skill/trae-hooks/scripts/pre_tool_use.py`
- `docs/claude.md`
- `docs/opencode.md`
- `docs/codex.md`
- `docs/trae.md`
- `skill/reference.md`

Optional follow-up files:

- `skill/scripts/smoke-test-subagent-preflight.sh`

## Rollout Plan

### Step 1 - shared helper

- add `subagent-preflight` subcommand to `task_guard.py`
- add `subagent-preflight.sh`
- support `--json`, `--text`, and `--compact`

### Step 2 - Claude

- wire the helper into `pre_tool_use.py`
- align `user_prompt_submit.py` copy
- keep `state_summary()` neutral and trigger-aware

### Step 3 - OpenCode

- wire the helper into `tool.execute.before`
- use actual Task args to build `task_text`
- keep title/toast logic unchanged in the first pass

### Step 4 - Codex

- add Codex hook docs for prompt-time reminders and Stop-time planning sync
- keep documented shell-first `subagent-preflight.sh` usage examples
- add wrapper examples if the repository wants automatic native subagent prompt mutation later

### Step 5 - docs and polish

- document the new helper contract in host notes and `skill/reference.md`
- only after dogfooding, revisit repo-aware delegate brief generation or tighter automation

## Verification

P0 verification should include:

- `sh skill/scripts/validate-task.sh`
- a new shell smoke test that covers at least:
  - related multi-repo Task -> `payload_only`
  - related bounded discovery -> `payload_plus_delegate_recommended`
  - observer session -> `delegate_required`
  - likely unrelated Task -> `routing_only`
- `python3 -m py_compile skill/claude-hooks/scripts/*.py`
- any existing OpenCode plugin smoke or lint path the repo already uses

## Acceptance Criteria

- Claude and OpenCode produce the same `decision` for the same resolved task state and `task_text`
- Codex shell-first usage can obtain the same `decision` and `prompt_prefix`
- multi-repo bounded work is not forced into delegate by default
- observer-only sessions escalate to `delegate_required`
- adapters do not fork trigger rules or repo/worktree resolution logic
- `.planning/` remains the single durable source of truth for task state

## Why This Shape

This keeps the architecture consistent with the rest of the repository:

- shell-first core
- thin host adapters
- portable file-backed truth
- explicit rather than hidden lifecycle changes

It also solves the current weakness directly: not by forcing every subagent through delegate, but by making the native subagent path carry the right repo and worktree context automatically.
