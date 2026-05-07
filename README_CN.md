# Context Task Planning

**让复杂编码任务在上下文丢失后可恢复、可见、隔离**

跨 Claude Code、OpenCode、Codex、TraeCLI/Coco 的 shell-first 任务规划系统。

**[English Documentation](README.md)**

## 核心价值

- **🔄 恢复** - 上下文丢失、模型切换、代理切换后继续工作
- **👁️ 可见** - 当前任务状态一目了然
- **🔒 隔离** - 不同任务不混淆，并行工作有边界

代理会自动管理 `.planning/` 下的任务文件，你只需与代理对话即可。

## 何时使用

**适合：** 多步骤任务、长运行任务、可能中断的任务、需要验证的任务

**不适合：** 一次性小修改、短会话可完成的简单编辑

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

### 2. 给代理一个真实任务

```
重构前后端的认证流程。这需要多个步骤，可能会被中断，完成前需要验证。
```

### 3. 验证成功

任务应该出现在你的工具中：
- **Claude Code**: 自动注入任务上下文
- **OpenCode**: 会话标题显示 `task:<slug> | ...`
- **TraeCLI/Coco**: 自动注入任务上下文
- **Codex**: 可选 hooks 注入任务提醒

### 4. 测试恢复

```
我丢失了上下文。从本地规划文件恢复当前任务，从记录的下一步继续。
```

如果代理能从 `.planning/<slug>/` 继续，工作流就成功了！

**🎉 成功后，阅读 [docs/onboarding.md](docs/onboarding.md) 了解完整旅程。**

## 核心概念

### 任务文件结构

```
.planning/<slug>/
  task_plan.md    # 任务框架和热上下文
  findings.md     # 提炼的结论
  progress.md     # 执行历史
  state.json      # 操作快照
```

代理会自动管理这些文件，你不需要手动编辑。

## 文档导航

### 新手路径
1. **README.md** (本文) - 快速上手
2. **[docs/onboarding.md](docs/onboarding.md)** - 完整用户旅程
3. **主机特定文档** - 按需阅读

### 主机特定文档
- **[docs/claude.md](docs/claude.md)** - Claude Code 设置和行为
- **[docs/opencode.md](docs/opencode.md)** - OpenCode 插件和命令
- **[docs/codex.md](docs/codex.md)** - Codex shell-first 工作流
- **[docs/trae.md](docs/trae.md)** - TraeCLI/Coco 插件和命令

### 深入了解
- **[docs/design.md](docs/design.md)** - 架构设计
- **[docs/spec-aware-task-runtime.md](docs/spec-aware-task-runtime.md)** - Spec-aware 设计

## 局限性

- 文件基础的便携协议，各主机UI不同
- 无内置跨机器协调
- 无主机特定的会话历史回放
- 可选适配器是提醒和可见性辅助，不是硬事务系统
