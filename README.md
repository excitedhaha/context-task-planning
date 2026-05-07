# Context Task Planning

**Keep complex coding tasks recoverable, visible, and isolated after context loss**

A shell-first task planning system across Claude Code, OpenCode, Codex, and TraeCLI/Coco.

**[中文文档](README_CN.md)**

## Core Value

- **🔄 Recovery** - Continue work after context loss, model switches, or agent switches
- **👁️ Visibility** - Current task state at a glance
- **🔒 Isolation** - Different tasks stay separate, parallel work has boundaries

Agents automatically manage task files under `.planning/`. You just talk to the agent.

## When to Use

**Use it for:** Multi-step tasks, long-running tasks, tasks likely to be interrupted, tasks requiring verification

**Skip it for:** One-shot edits, simple changes completable in a short session

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

### 2. Give the agent one real task

```
Refactor the auth flow across backend and frontend. This will take multiple steps, may get interrupted, and should be verified before wrap-up.
```

### 3. Verify success

The task should appear in your tool:
- **Claude Code**: Task context auto-injected
- **OpenCode**: Session title shows `task:<slug> | ...`
- **TraeCLI/Coco**: Task context auto-injected
- **Codex**: Optional hooks inject task reminders

### 4. Test recovery

```
I lost context. Recover the active task from local planning files and continue from the recorded next action.
```

If the agent can continue from `.planning/<slug>/` without re-teaching the whole task, the workflow works!

**🎉 After success, read [docs/onboarding.md](docs/onboarding.md) for the full journey.**

## Core Concepts

### Task file structure

```
.planning/<slug>/
  task_plan.md    # Task framework and hot context
  findings.md     # Refined conclusions
  progress.md     # Execution history
  state.json      # Operational snapshot
```

Agents manage these files automatically. You don't need to edit them manually.

## Documentation Guide

### New user path
1. **README.md** (this file) - Quick start
2. **[docs/onboarding.md](docs/onboarding.md)** - Full user journey
3. **Host-specific docs** - Read as needed

### Host-specific documentation
- **[docs/claude.md](docs/claude.md)** - Claude Code setup and behavior
- **[docs/opencode.md](docs/opencode.md)** - OpenCode plugin and commands
- **[docs/codex.md](docs/codex.md)** - Codex shell-first workflow
- **[docs/trae.md](docs/trae.md)** - TraeCLI/Coco plugin and commands

### Deep dive
- **[docs/design.md](docs/design.md)** - Architecture design
- **[docs/spec-aware-task-runtime.md](docs/spec-aware-task-runtime.md)** - Spec-aware design

## Limitations

- File-based portable contract, host-specific UI differs
- No built-in cross-machine coordination
- No host-specific session-history catchup layer
- Optional adapters are reminders and visibility aids, not a hard transaction system
