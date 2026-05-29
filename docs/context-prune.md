# Context Prune

`context-prune` keeps long-running task files useful after `progress.md` grows too large for repeated recovery reads.

The design separates detection from pruning.

- Detection is deterministic and cheap enough for hooks and plugins.
- Pruning is a writer-only operation that requires a model-authored summary and keeps a full archive for rollback.

## Trigger Model

Detection can run often:

- session start or resume
- prompt-time context injection
- before reading a very large `progress.md`
- after OpenCode `session.idle` or Trae/Coco stop-time progress sync
- `validate-task.sh`
- explicit `context-prune.sh --status`

Pruning should stay explicit:

- the user asks to prune, compact, or slim the task context
- a coordinator chooses to run `context-prune.sh --prepare`
- task closeout or archive suggests pruning historical noise first

Hooks and plugins must not directly rewrite `progress.md`.

## Thresholds

The shared status classifies `progress.md` as:

- `ok` below 500 lines and 64 KB
- `warn` at 500 lines or 64 KB
- `recommend_prune` at 2000 lines, 128 KB, or 100 sessions
- `strongly_recommend` at 5000 lines or 256 KB
- `read_guard` at 10000 lines or 512 KB

Only `recommend_prune`, `strongly_recommend`, and `read_guard` produce hook-facing prune hints.

## Commands

Check the current task:

```bash
sh skill/scripts/context-prune.sh --status
```

Prepare a model summary brief:

```bash
sh skill/scripts/context-prune.sh --prepare
```

The prepare step writes:

```text
.planning/<slug>/.derived/prune/<run-id>/
  brief.md
  manifest.json
```

After a coordinator or delegate writes a summary from `brief.md`, apply the prune:

```bash
sh skill/scripts/context-prune.sh --apply --summary-file <summary.md>
```

Restore the archived original if needed:

```bash
sh skill/scripts/context-prune.sh --restore latest
```

## Agent Responsibilities

Coordinator agent:

- decides whether pruning is appropriate
- asks the model or a delegate to summarize the prepared range
- runs `--apply`
- validates the task afterwards

Summary delegate:

- reads only the prepared range or archive references named in `brief.md`
- writes a concise summary with decisions, verification, risks, and omitted noise
- does not edit main planning files

Hook or plugin adapter:

- runs status checks or consumes shared status output
- injects reminders or toasts
- never rewrites task files

Script layer:

- measures file size and session count
- records source hash, size, and mtime in `manifest.json`
- refuses apply if `progress.md` changed after prepare
- archives the full original before rewriting
- restores from the archive on request

## Host Coverage

Claude Code:

- session and subagent context can include a prune hint from the shared status
- Claude hooks do not auto-prune

OpenCode:

- `session.idle` can show a cooldown toast when pruning is recommended
- idle progress sync skips turns that only changed main planning files, reducing self-referential log growth
- OpenCode does not auto-prune

Codex:

- shared hook context can surface the same prune hint on recovery
- stop hooks continue to ask for planning sync, but pruning remains manual

TraeCLI/Coco:

- shared hook context can surface the same prune hint on recovery
- stop-time progress sync remains separate from pruning

## Safety

Prune apply and restore require writer access. The command stores the full original under `.derived/prune/<run-id>/progress.original.md` before rewriting `progress.md`.

If the source file changes between `--prepare` and `--apply`, apply fails and asks for a fresh prepare run.
