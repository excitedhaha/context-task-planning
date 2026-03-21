# OpenCode Notes

## Install

Recommended install:

```bash
npx skills add excitedhaha/context-task-planning -g
```

Choose `context-task-planning` and the OpenCode agent when prompted.

Local fallback while developing from a clone:

```bash
sh skill/scripts/install-macos.sh
```

A global install makes the skill available under:

```text
~/.config/opencode/skills/context-task-planning
```

## Usage

This skill is designed so that OpenCode does not need full session-history parsing in order to recover context.

Most teammates should use it through normal conversation with the agent.

Good asks for OpenCode:

- describe the real task in normal language
- mention when the work is multi-step, long-running, or likely to be resumed later
- expect OpenCode to create or resume the task under `.planning/<slug>/` when needed
- ask for bounded discovery, review, or verify side work when it should stay isolated

Example prompts:

```text
Implement this auth refactor across backend and frontend. It will take multiple steps, may get interrupted, and should be verified before you wrap up.
```

```text
I lost context. Recover the active task from .planning/ and continue from the recorded next_action.
```

```text
Scan the repo for the entry points relevant to this task. Keep that side investigation bounded, and promote only the distilled findings.
```

For multi-step or recovery-sensitive work, OpenCode should usually pick the skill automatically. If it does not in your setup, mention `context-task-planning` explicitly or use the scripts directly.

The canonical state is the task folder itself under `.planning/<slug>/`.

If your OpenCode setup uses a custom skill source list, make sure `~/.config/opencode/skills` is enabled.

## Optional plugin adapter

If you installed from a local clone with:

```bash
sh skill/scripts/install-macos.sh
```

the OpenCode plugin is installed automatically by default.

If you installed the skill through `npx skills add`, OpenCode still needs one extra plugin-install step because it loads skills and local plugins from different directories. Run the bundled helper:

```bash
sh ~/.config/opencode/skills/context-task-planning/scripts/install-opencode-plugin.sh
```

You can also run the helper from a local clone:

```bash
sh skill/scripts/install-opencode-plugin.sh
```

Then restart OpenCode.

If you want the skill symlink but not the runtime plugin from the local installer, use:

```bash
sh skill/scripts/install-macos.sh --skip-opencode-plugin
```

## What users should notice

After the plugin is enabled and OpenCode is restarted, you should see:

- the session title prefixed as `task:<slug> | ...`
- an info toast when the current task is first detected
- a warning toast when a new prompt looks like likely task drift
- a warning toast when tracked work has happened but `.planning/<slug>/` has not been synced for a while
- stronger routing guidance before `Task` runs on mismatched work

Sample illustration:

![OpenCode title and toast sample](assets/opencode-title-toast-sample.svg)

This is a sample illustration of the expected title/toast fallback, not a live screenshot from your machine.

What the plugin adds:

- injects the current task summary into OpenCode's system prompt each turn
- prefixes the session title as `task:<slug> | ...`, which is the closest current plugin-level path to sidebar visibility
- shows a toast when the current task is first detected or when a likely task switch is detected
- warns when the newest user prompt looks likely unrelated to the current task
- warns when task files look stale after tracked work without a planning sync
- adds a stronger note before `Task` launches if the prompt looks mismatched
- exports `PLAN_SESSION_KEY` into shell commands so task-aware scripts bind work to the current OpenCode session

If an OpenCode session is bound as an observer, the injected task summary will say so explicitly and remind the model to keep main planning files read-only while still allowing delegate-lane work.

When a task declares `repo_scope` and `primary_repo`, the injected summary now carries that repo context too, which helps parent-directory multi-repo sessions choose the right checkout.

When OpenCode starts inside a registered repo path or recorded `.worktrees/...` checkout under a parent workspace, the plugin still resolves the shared parent `.planning/`. Unrelated ancestor `.planning/` directories should not capture that session.

This is still a best-effort UI layer. The current OpenCode plugin SDK exposes hooks, session title updates, and TUI toasts, but not a dedicated custom sidebar/statusbar widget API.

It is also still advisory, not a hard transaction layer: the plugin can detect likely stale task state and remind the model to sync `.planning/`, but the actual task file edits are still performed by the model/tools rather than by the plugin itself.

So if you do not see a dedicated sidebar widget, that is expected today; the title prefix is the current visibility fallback.

To reduce global noise, the plugin stays quiet in repositories that do not already use `.planning/`.

## Manual fallback

Useful commands when you want direct control:

- `sh skill/scripts/init-task.sh "Implement auth flow"`
- `sh skill/scripts/validate-task.sh`
- `sh skill/scripts/prepare-delegate.sh --kind discovery "Map auth entry points"`
