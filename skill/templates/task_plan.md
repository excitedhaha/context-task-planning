# Task Plan: {{TASK_TITLE}}

## Hot Context

- Task Slug: `{{TASK_SLUG}}`
- Task Status: `active`
- Goal: [fill this first]
- Acceptance Summary: [capture this before implementation]
- Current Mode: `clarify`
- Current Phase: `clarify`
- Next Action: {{INITIAL_NEXT_ACTION}}
- Spec Context: `embedded` by default until an external spec is linked
- Primary Repo: (unset)
- Repo Scope: (unset)
- Blockers:
  - None
- Verification Target:
  - [fill this before marking done]

## Goal

[One clear sentence describing the target outcome]

## Non-Goals

- [What this task will not do]

## Acceptance Criteria

- [Observable result that must be true before this task is done]

## Constraints

- Source Path: `{{SOURCE_PATH}}`
- Planning Path: `.planning/{{TASK_SLUG}}`
- Primary Repo Constraint: (unset)
- Repo Scope Constraint: (unset)
- Single Writer: only the coordinator updates `task_plan.md`, `progress.md`, and `state.json`

## Open Questions

- [Question or assumption that must be resolved]

## Edge Cases

- [Optional: important edge case or failure mode]

## Definition of Done

- [Observable completion condition]

## Verification Commands

- [ ] [command or validation step]

## Spec Context

- Mode: `embedded`
- Provider: `none`
- Status: `none`
- Primary Ref: (none)
- Artifact Refs: none
- Summary:
  - [Optional short note about linked or embedded spec context]

## Phases

### clarify

- **Status:** in_progress
- Outcomes:
  - Goal, non-goals, acceptance criteria, constraints, and open questions are captured
- Exit Criteria:
  - No critical ambiguity remains unresolved

### plan

- **Status:** pending
- Outcomes:
  - Technical direction, phased execution, and verification targets are documented
- Exit Criteria:
  - `next_action` is concrete enough to start implementation

### execute

- **Status:** pending
- Outcomes:
  - Implementation or research is carried out in small, verifiable steps
- Exit Criteria:
  - Work is ready for validation

### verify

- **Status:** pending
- Outcomes:
  - Verification commands are run and actual results are recorded
- Exit Criteria:
  - Definition of done is satisfied or blockers are explicitly recorded

## Delegation Policy

- Safe delegate work: discovery, spikes, verification triage, review, catchup
- Unsafe delegate work: concurrent edits to main planning files
- Delegate output stays in `delegates/<delegate-id>/`
- Use `create-delegate.sh`, `start-delegate.sh`, `resume-delegate.sh`, `block-delegate.sh`, `cancel-delegate.sh`, `complete-delegate.sh`, and `promote-delegate.sh` to manage the lane lifecycle

## Decision Log

| Decision | Rationale |
|----------|-----------|
|          |           |

## Errors and Recovery

| Error | Attempt | Recovery |
|-------|---------|----------|
|       | 1       |          |
