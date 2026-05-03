# TraeCLI/Coco Notes

This page only covers TraeCLI/Coco-specific setup and behavior. Use `README.md` for the first success case and `docs/onboarding.md` for the shared workflow.

TraeCLI was previously called Coco. The current command examples still use `coco` because that is the documented CLI command.

## Install

Recommended install:

```bash
coco plugin install --type=github excitedhaha/context-task-planning --name context-task-planning
```

Then restart TraeCLI/Coco. The plugin bundles:

- the main `context-task-planning` skill entry under `skills/context-task-planning/`
- thin task slash commands under `commands/`
- lifecycle hooks declared in `coco.yaml`
- shared runtime scripts under `skill/scripts/`

Local fallback while developing from a clone:

```bash
coco plugin install --type=local . --name context-task-planning
coco plugin validate context-task-planning
```

You can also validate without installing:

```bash
coco plugin validate --path .
```

## What TraeCLI/Coco Adds

After the plugin is enabled, TraeCLI/Coco can surface the shared file-backed task state through:

- automatic task-context recovery on `session_start`
- prompt-time route evidence only for high-signal `likely-unrelated` prompts
- native `Task` preflight guidance through `pre_tool_use` when available
- `post_tool_use` planning evidence tracking for mutating tools
- a `stop` guard that can ask the agent to continue once when a mutating turn is about to finish without planning sync evidence
- namespaced slash commands for the common task loop

The plugin does not provide a native status line or session-title cue today. Use `current-task.sh` in a shell prompt or tmux status line if you want always-visible task text.

## Bundled Slash Commands

TraeCLI/Coco exposes plugin commands under the plugin namespace:

- `/context-task-planning:task-init <task title>` - create a tracked task from a confirmed title and final slug, previewing both when the task is inferred
- `/context-task-planning:task-current` - inspect the current task and next action
- `/context-task-planning:task-list` - list existing tasks in the workspace
- `/context-task-planning:task-validate` - validate the current task without auto-fixing warnings
- `/context-task-planning:task-drift <new request>` - check whether a new ask still fits the current task
- `/context-task-planning:task-done [slug]` - mark the current or named task done after verification

These commands stay thin on purpose. They call the bundled scripts through `${COCO_PLUGIN_ROOT}/skill/scripts/` and should not become a second implementation of task resolution or lifecycle rules.

## Hook Lifecycle

Current hooks in `coco.yaml` map to shared runtime behavior:

- `session_start` - inject explicit task context or a weaker fallback advisory
- `user_prompt_submit` - record turn markers and inject route evidence only for high-signal `likely-unrelated` prompts
- `pre_tool_use` - run shared native-`Task` preflight for `Task` launches
- `post_tool_use` - record whether this turn read planning files, used mutating tools, or updated planning files
- `stop` - continue once if TraeCLI/Coco is about to finish without required planning read or update evidence

The hooks derive a session binding key from TraeCLI/Coco's `session_id`. If you run shell commands outside the host and need deterministic parallel sessions, export `PLAN_SESSION_KEY` before starting TraeCLI/Coco or before running the scripts manually.

## What You Should Notice

After restarting TraeCLI/Coco:

- `/skills` should include `context-task-planning` and the bundled task-entry skills
- `/context-task-planning:task-current` should resolve the current task or explain why no task is active
- a complex first prompt in a repo without `.planning/` should receive an initialization hint instead of silently starting ad hoc work
- when task creation is inferred from context, the command flow should show both the proposed title and proposed slug before the task is created
- a high-signal scope-switch prompt should give the main LLM route evidence so it can ask before mixing unrelated work
- after a code-changing turn, TraeCLI/Coco may ask once to update `.planning/<slug>/progress.md` and `.planning/<slug>/state.json` before finalizing

## Quick Validation And Troubleshooting

Contributor smoke test from a checkout:

```bash
sh skill/scripts/smoke-test-trae-plugin.sh
coco plugin validate --path .
```

If commands or hooks do not appear:

- restart TraeCLI/Coco after installing or upgrading the plugin
- run `coco plugin list` and confirm `context-task-planning` is enabled
- run `coco plugin validate context-task-planning` to inspect the installed plugin
- make sure the plugin was installed from the repository root, not from `skill/`
- verify that `coco.yaml`, `commands/`, `skills/`, and `skill/trae-hooks/` exist in the installed plugin cache

## Manual Fallback

Useful commands when you want direct control:

- `sh skill/scripts/init-task.sh "Implement auth flow"`
- `sh skill/scripts/current-task.sh`
- `sh skill/scripts/check-task-drift.sh --prompt "Also investigate the billing webhook regression" --json`
- `sh skill/scripts/subagent-preflight.sh --cwd "$PWD" --host trae --tool-name Task --task-text "Investigate auth entry points" --json`
- `sh skill/scripts/validate-task.sh`
- `sh skill/scripts/validate-task.sh --fix-warnings`
- `sh skill/scripts/set-task-spec-context.sh --task <slug> --ref <spec-ref>`

For the shared progression from first success to multi-session and multi-repo usage, go back to `docs/onboarding.md`. For the deeper architecture behind session bindings, repo scope, and worktree attachment, use `docs/design.md`.
