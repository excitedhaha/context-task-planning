# Context Task Planning

**Persistent, structured context for long-running AI coding tasks — auto-planned, auto-synced, auto-injected.**

Your agent plans the task, syncs the plan to disk as it works, and re-injects the right context on every turn — even after dozens of conversation rounds and multiple auto-compactions.

Works across Claude Code, OpenCode, Codex, and TraeCLI/Coco.

**[中文文档](README_CN.md)**

```text
┌──────────┐   plan    ┌────────────┐   sync   ┌────────────────────┐
│ your ask │ ────────▶ │ agent plans│ ───────▶ │ .planning/<slug>/  │
└──────────┘           └────────────┘          └────────────────────┘
                              ▲                          │
                              │   inject hot context     │
                              └──────────────────────────┘
                       every turn / after compaction / on resume
```

## The Problem

Long AI coding tasks fail in predictable ways:

- **Context windows fill up.** After many turns the model auto-compacts and loses the precise plan, the failed attempts, and the verification state.
- **The plan lives only in chat.** Switch session, machine, or model — and you re-explain everything from scratch.
- **Parallel work mixes up.** A second task quietly mutates the first one's state because there is no boundary.
- **"Done" is unverifiable.** Nobody can tell whether the task was implemented, verified, or silently abandoned.

This skill turns those failure modes into a file-backed, agent-managed contract.

## How It Works

A simple loop, repeated for as long as the task is alive.

### ① Plan — once, at the start
For non-trivial work, the agent confirms a task title/slug and captures goal, non-goals, acceptance criteria, constraints, and verification target into `.planning/<slug>/task_plan.md`.

### ② Persist — continuously, as work happens
On every meaningful step the agent writes back to local files:
- `state.json` — machine-readable status, phase, next action, blockers
- `task_plan.md` — human-readable plan with a small **Hot Context** section on top
- `progress.md` — chronological execution log
- `findings.md` — distilled, durable conclusions worth re-reading

### ③ Inject — every turn, automatically
Host plugins/hooks read the latest state and feed only the **smallest useful snapshot** back into the model:
- on session start
- before new turns when needed
- before launching sub-agents
- after the conversation gets compacted

The model never has to re-derive what it already figured out — the runtime hands it back.

## What You Actually Get

- **🧠 Compaction-proof context** — Hot Context stays small but always authoritative. After auto-compaction, the next turn still knows the goal, current phase, and next action.
- **📋 Structured plan-as-you-go** — A single conversation produces a real plan, a real progress log, and a real findings file — without you asking.
- **🔄 Cross-session / cross-host recovery** — Switch from Claude Code to Codex, close the laptop, come back tomorrow — pick up exactly where you stopped on any supported host.
- **🪟 Always-visible state** — Status-line cues, session titles, and injected reminders show which task is active, who owns it (writer vs. observer), and what repo/worktree it touches.
- **🚧 Safe parallelism** — Session bindings + writer/observer roles + per-task git worktrees keep two parallel tasks from trampling each other's files or branches.
- **✅ Real verification gate** — A task isn't "done" until verification is recorded in `progress.md`. No silent declarations of victory.

## When to Use

**Use it for:** multi-step tasks, long-running tasks, tasks likely to be interrupted, tasks requiring verification, work that crosses files or repos.

**Skip it for:** one-shot edits, simple changes completable in a short session.

## Quickstart

### 1. Install for your host

**Claude Code:**
```bash
claude plugin marketplace add excitedhaha/context-task-planning
claude plugin install context-task-planning@context-task-planning
```

**OpenCode:**
```bash
npx skills add excitedhaha/context-task-planning -g
opencode plugin context-task-planning-opencode --global
```

**TraeCLI/Coco:**
```bash
coco plugin install --type=github excitedhaha/context-task-planning --name context-task-planning
```

**Codex:**
```bash
codex plugin marketplace add excitedhaha/context-task-planning
codex plugin install context-task-planning@context-task-planning
```

### 2. Start one real task

Just talk normally. The agent will propose a task title/slug and start tracking it under `.planning/<slug>/`.

```
Refactor the auth flow across backend and frontend. This will take multiple
steps and should be verified before wrap-up.
```

### 3. Watch the runtime work

As you keep talking, you should see:
- a `task:<slug>` cue in your host (status line / session title / injected reminder)
- `.planning/<slug>/task_plan.md` and `progress.md` updated as the agent works
- the agent stays on goal across many turns without needing to be re-briefed

Host-specific cues:
- **Claude Code**: Task context auto-injected; optional status-line shows `task!:<slug>` / `obs:<slug>` / `wksp:<slug>`
- **OpenCode**: Session title shows `task:<slug> | ...`
- **TraeCLI/Coco**: Task context auto-injected
- **Codex**: Optional hooks inject task reminders on new turns

### 4. (Bonus) Try a recovery

Close the session, open a new one in the same repo, and say:

```
Resume the active task from local planning files.
```

The agent reads `.planning/<slug>/`, rebuilds context from `state.json` plus Hot Context, and continues from the recorded next action.

**🎉 Once the loop works, read [docs/onboarding.md](docs/onboarding.md) for the full journey.**

## Daily Scenarios

### A. Long refactor over many turns
The plan keeps the goal/non-goals stable. The agent writes progress as it goes. After 30+ turns and one auto-compaction, the next turn still knows exactly which file it was about to touch.

### B. Switching hosts mid-task
You started in Claude Code, ran out of quota, opened OpenCode in the same repo. The new session reads `.planning/<slug>/` and resumes — no re-briefing.

### C. Parallel tasks in the same repo
Main session keeps refactoring auth. A second session is bound as an **observer** to help review without touching the main planning files — or as a **writer** in a separate `.worktrees/<slug>/` checkout when it also needs to write code.

### D. Cross-repo task from a parent workspace
One task spans `frontend/` and `backend/`. Register both repos once, scope the task to them, and the agent treats them as one task instead of two disconnected pieces.

## Core Concepts

### Task file structure

```
.planning/<slug>/
  task_plan.md    # task framework and hot context
  findings.md     # refined conclusions
  progress.md     # execution history
  state.json      # operational snapshot
```

*You don't need to read these files. They exist so the agent can be reset at any time and still know what to do.*

## Documentation Guide

### New user path
1. **README.md** (this file) — quick start
2. **[docs/onboarding.md](docs/onboarding.md)** — full user journey
3. **Host-specific docs** — read as needed

### Host-specific documentation
- **[docs/claude.md](docs/claude.md)** — Claude Code setup and behavior
- **[docs/opencode.md](docs/opencode.md)** — OpenCode plugin and commands
- **[docs/codex.md](docs/codex.md)** — Codex shell-first workflow
- **[docs/trae.md](docs/trae.md)** — TraeCLI/Coco plugin and commands

### Deep dive
- **[docs/design.md](docs/design.md)** — architecture design
- **[docs/spec-aware-task-runtime.md](docs/spec-aware-task-runtime.md)** — spec-aware design

## Limitations

- This is a **context layer**, not a team task-management tool — optimized for one developer plus AI agents on a workstation.
- File-based portable contract; host-specific UI differs.
- No built-in cross-machine coordination.
- No host-specific session-history catchup layer.
- Optional adapters are reminders and visibility aids, not a hard transaction system.
