# Sharing Notes

This repository is meant to be shared as a context engineering skill while keeping real task state local.

## What teammates are getting

- task-scoped workspaces under `.planning/<slug>/`
- durable recovery after context loss or agent switching
- delegate lanes for sub-agents, review, verify, and discovery side quests
- verification-aware task closure instead of "done means I think it is done"

## What should be shared

- `README.md`
- `docs/`
- `skill/`
- `LICENSE`

## What should stay local

- `.planning/`
- local `.claude/`, `.codex/`, or `.opencode/` project settings
- generated Python cache files

Those paths are ignored by `.gitignore` on purpose.

## Recommended install for a teammate

The shortest path is:

```bash
npx skills add excitedhaha/context-task-planning -g
```

Notes:

1. The CLI will discover the skill under `skill/` automatically.
2. Choose `context-task-planning` and the agent(s) your teammate uses when prompted.
3. If they want to preview before installing, they can run `npx skills add excitedhaha/context-task-planning -l`.
4. If they use Claude Code and want hook automation, merge `skill/claude-hooks/settings.example.json` into either `~/.claude/settings.json` or `.claude/settings.local.json`.
5. If they already use `planning-with-files`, disable its hooks or old skill link first to avoid duplicate planning prompts.

## Local fallback for contributors

If someone wants to inspect or develop the repository locally first:

```bash
git clone https://github.com/excitedhaha/context-task-planning.git
cd context-task-planning
sh skill/scripts/install-macos.sh
```

## How teammates should use it

- Preferred: give the agent a real multi-step task in normal language; it should usually pick `context-task-planning` automatically, create or resume a task, keep `.planning/` current, and record verification as the work progresses
- Ask for delegate lanes when there is a bounded subproblem such as review, discovery, or verify triage
- Use scripts when you want explicit control, debugging, or a fallback when a host does not auto-invoke the skill
- If a teammate asks "how do I start", give them the GitHub install command first and one of the example prompts below second

Example prompts you can hand to a teammate:

```text
Implement this feature across the relevant backend and frontend paths. This will take multiple steps, may get interrupted, and should be verified before you wrap up.
```

```text
I lost context. Recover the active task from .planning/ and continue from the recorded next_action.
```

```text
Review the risky parts of this migration. Keep the main task focused, and if you need a bounded side investigation, promote only the distilled findings.
```

## Recommended publish checklist

Before pushing to GitHub:

1. Run:

```bash
for f in skill/scripts/*.sh; do sh -n "$f"; done
python3 -m py_compile skill/claude-hooks/scripts/*.py
npx skills add . -l
sh skill/scripts/validate-task.sh || true
```

2. Confirm `.planning/` is not staged.
3. Confirm local absolute paths only appear in private planning state, not in shareable docs.
4. Confirm README and docs lead with context engineering, delegate lanes, and agent-first usage rather than a script-only workflow.
5. Confirm install commands point at `excitedhaha/context-task-planning`.
6. Confirm hook docs still match `skill/claude-hooks/settings.example.json`.

## Notes on `.planning/`

The repository itself can have a local `.planning/` directory while you are building the skill. That state is intentionally not part of the shared artifact.

If you want to publish an example planning task, create a scrubbed example under `docs/` instead of committing a real local workspace.
