# Context Task Planning

**为长任务 AI 编码提供持久化、结构化的上下文运行时——自动规划、自动落盘、自动注入。**

代理在任务一开始就做规划，边干边把计划/进展/结论结构化同步到本地文件，并在每一轮对话里只把"当下需要的那部分上下文"重新注入回会话——哪怕经过几十轮压缩，AI 依然清楚自己在哪、要干什么、下一步是什么。

支持 Claude Code、OpenCode、Codex、TraeCLI/Coco。

**[English Documentation](README.md)**

```text
┌──────────┐   规划    ┌────────────┐   同步   ┌────────────────────┐
│  你的请求 │ ────────▶ │ 代理做规划 │ ───────▶ │ .planning/<slug>/  │
└──────────┘           └────────────┘          └────────────────────┘
                              ▲                          │
                              │   注入 hot context        │
                              └──────────────────────────┘
                     每轮对话 / 压缩之后 / 会话恢复时
```

## 解决什么问题

长任务 AI 编码常见的失败模式：

- **上下文窗口被撑爆**：多轮对话后自动压缩，精确的计划、失败过的尝试、验证状态全部丢失。
- **计划只活在聊天里**：换会话、换机器、换模型，一切都得从头复述。
- **并行任务相互污染**：第二个任务悄悄改掉了第一个任务的状态，因为根本没有边界。
- **"完成"无从验证**：没人说得清任务是真的实现了、验证了，还是只是被默默放弃了。

这个 skill 把上述失败模式转换成一份由代理管理、以文件为载体的契约。

## 工作机制

一个简单的循环，只要任务还在跑就一直转下去。

### ① 规划（Plan）—— 任务开始时做一次
对于非一次性的工作，代理会确认任务标题/slug，并把 goal、non-goals、验收标准、约束、验证目标写进 `.planning/<slug>/task_plan.md`。

### ② 落盘（Persist）—— 干活过程中持续同步
每有一步有意义的推进，代理都会写回本地文件：
- `state.json` — 机器可读的状态、阶段、下一步动作、阻塞项
- `task_plan.md` — 人可读的计划，顶部有一小段 **Hot Context**
- `progress.md` — 按时间顺序的执行日志
- `findings.md` — 提炼出来、值得回头再看的结论

### ③ 注入（Inject）—— 每一轮都自动做
Host 插件/hooks 读取最新状态，并**只**把"当下最小够用的上下文切片"喂回模型：
- 会话启动时
- 需要时，在新一轮对话开始前
- 启动子代理之前
- 对话被压缩之后

模型不再需要重新推导它已经搞清楚的东西——由运行时直接递回去。

## 你实际能拿到什么

- **🧠 抗压缩的上下文**：Hot Context 保持精简但始终权威。即便自动压缩发生，下一轮依然知道 goal、当前阶段、下一步动作。
- **📋 边干边成型的结构化方案**：一次普通的对话就会产出真实的 plan、真实的 progress 日志、真实的 findings——不用你专门要求。
- **🔄 跨会话 / 跨 host 恢复**：Claude Code 切 Codex，关笔记本第二天再开，在任意支持的 host 从上次停下的地方继续。
- **🪟 状态永远可见**：状态栏提示、会话标题、注入的 reminder 告诉你当前在哪个任务、谁是 writer 或 observer、涉及哪个 repo / worktree。
- **🚧 安全的并行**：Session bindings + writer/observer 角色 + 任务专属 git worktree，两个并行任务不会互相踩代码/分支。
- **✅ 真实的验证闸门**：没有在 `progress.md` 记录过验证的任务不算 "done"，不允许默默宣告胜利。

## 何时使用

**适合**：多步骤任务、长运行任务、可能中断的任务、需要验证的任务、跨文件/跨 repo 的工作。

**不适合**：一次性小修改、短会话可完成的简单编辑。

## Quickstart

### 1. 安装（选择你的工具）

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

### 2. 开一个真实任务

正常说话即可。代理会提议任务标题/slug，然后开始在 `.planning/<slug>/` 下追踪它。

```
重构前后端的认证流程。这需要多个步骤，完成前需要验证。
```

### 3. 观察运行时工作

随着对话继续，你应该看到：
- host 里出现 `task:<slug>` 提示（状态栏 / 会话标题 / 注入的 reminder）
- `.planning/<slug>/task_plan.md` 和 `progress.md` 在代理推进过程中被持续更新
- 经过很多轮对话代理依然不跑偏，也不需要重新讲一遍任务

各 host 的可见线索：
- **Claude Code**：任务上下文自动注入；可选 status-line 显示 `task!:<slug>` / `obs:<slug>` / `wksp:<slug>`
- **OpenCode**：会话标题显示 `task:<slug> | ...`
- **TraeCLI/Coco**：任务上下文自动注入
- **Codex**：可选 hooks 在新轮次注入任务提醒

### 4. （附加）试一次恢复

关掉会话，在同一个 repo 里打开新会话，然后说：

```
从本地规划文件恢复当前任务。
```

代理会读取 `.planning/<slug>/`，基于 `state.json` + Hot Context 重建上下文，从记录的下一步继续。

**🎉 跑通循环之后，阅读 [docs/onboarding.md](docs/onboarding.md) 了解完整旅程。**

## 日常场景

### A. 一个跨很多轮的长重构
计划让 goal/non-goals 保持稳定，代理边做边写 progress。经过 30+ 轮 + 一次自动压缩之后，下一轮依然精确知道自己正要改哪个文件。

### B. 中途换 host
在 Claude Code 起的任务，额度用完后切到 OpenCode。新会话读 `.planning/<slug>/` 直接续上——不用重新铺垫。

### C. 同一个 repo 里并行两个任务
主会话继续重构认证流程。第二个会话绑成 **observer** 帮你看代码但不改主规划文件；或者在单独的 `.worktrees/<slug>/` 里绑成 **writer**，这样两个都需要写代码也互不干扰。

### D. 跨 repo 的一个任务
一个任务同时改 `frontend/` 和 `backend/`。在父目录注册两个 repo，把任务 scope 到它们，代理会把这件事当作一个任务来处理，而不是两件断了联系的事。

## 核心概念

### 任务文件结构

```
.planning/<slug>/
  task_plan.md    # 任务框架 + Hot Context
  findings.md     # 提炼的结论
  progress.md     # 执行历史
  state.json      # 运行快照
```

*你并不需要去读这些文件。它们存在的意义是：代理随时可以被 reset，但依然知道该做什么。*

## 文档导航

### 新手路径
1. **README.md**（本文）—— 快速上手
2. **[docs/onboarding.md](docs/onboarding.md)** —— 完整用户旅程
3. **主机特定文档** —— 按需阅读

### 主机特定文档
- **[docs/claude.md](docs/claude.md)** —— Claude Code 设置和行为
- **[docs/opencode.md](docs/opencode.md)** —— OpenCode 插件和命令
- **[docs/codex.md](docs/codex.md)** —— Codex shell-first 工作流
- **[docs/trae.md](docs/trae.md)** —— TraeCLI/Coco 插件和命令

### 深入了解
- **[docs/design.md](docs/design.md)** —— 架构设计
- **[docs/spec-aware-task-runtime.md](docs/spec-aware-task-runtime.md)** —— Spec-aware 设计

## 局限性

- 这是一个 **上下文层**，不是团队任务管理工具——面向单个开发者 + AI 代理在工作站上协作的场景。
- 文件型的可移植协议，各 host 的 UI 细节有差异。
- 无内置跨机器协调。
- 无主机特定的会话历史回放。
- 可选适配器是提醒和可见性辅助，不是硬事务系统。
