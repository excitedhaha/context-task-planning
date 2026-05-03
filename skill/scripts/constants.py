#!/usr/bin/env python3
"""
Shared constants for context-task-planning.

This module contains all constants used across the task management system,
including drift detection patterns, delegate patterns, and configuration values.
"""

import re

# =============================================================================
# Drift Detection Constants
# =============================================================================

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "around",
    "as",
    "at",
    "be",
    "before",
    "by",
    "current",
    "for",
    "from",
    "help",
    "into",
    "keep",
    "make",
    "mode",
    "next",
    "not",
    "phase",
    "plan",
    "planning",
    "project",
    "resume",
    "skill",
    "state",
    "status",
    "step",
    "steps",
    "task",
    "tasks",
    "that",
    "the",
    "then",
    "this",
    "use",
    "using",
    "with",
    "work",
    "workflow",
    "上下文",
    "一个",
    "一些",
    "不是",
    "任务",
    "当前",
    "工作",
    "然后",
    "继续",
    "问题",
}

FOLLOWUP_PHRASES = [
    "continue",
    "keep going",
    "go on",
    "same task",
    "follow up",
    "use the same task",
    "继续",
    "接着",
    "继续做",
    "按上面的改",
    "刚才那个",
    "同一个任务",
]

SWITCH_CUES = [
    "another task",
    "different task",
    "new task",
    "separately",
    "instead",
    "unrelated",
    "另外",
    "另一个",
    "顺便",
    "单独",
    "新任务",
    "换个",
]

COMPLEX_KEYWORDS = [
    "implement",
    "build",
    "create",
    "add",
    "refactor",
    "debug",
    "investigate",
    "migrate",
    "design",
    "plan",
    "optimize",
    "fix",
    "audit",
    "wire",
    "document",
    "实现",
    "设计",
    "重构",
    "排查",
    "调研",
    "迁移",
    "优化",
    "新增",
    "修复",
    "补充",
]

COMPLEX_SIGNALS = [
    "\n",
    "1.",
    "2.",
    "- ",
    "需要",
    "并且",
    "同时",
    "方案",
    "步骤",
]

# =============================================================================
# Delegate Patterns
# =============================================================================

DELEGATE_KIND_PATTERNS = [
    (
        "review",
        ["review", "diff review", "code review", "pr review", "审查", "评审"],
    ),
    (
        "verify",
        [
            "verify",
            "validation",
            "regression",
            "failing test",
            "test failure",
            "triage",
            "验证",
            "回归",
            "测试失败",
            "失败排查",
        ],
    ),
    (
        "spike",
        [
            "spike",
            "prototype",
            "poc",
            "feasibility",
            "compare options",
            "方案对比",
            "可行性",
        ],
    ),
    (
        "discovery",
        [
            "investigate",
            "analyze",
            "map",
            "scan",
            "explore",
            "entry point",
            "dependency",
            "research",
            "调研",
            "分析",
            "找入口",
            "排查",
        ],
    ),
]

DELEGATE_RECOMMEND_SESSION_CUES = [
    "resume later",
    "pick up later",
    "later session",
    "follow up later",
    "后续继续",
    "之后继续",
    "跨会话",
]

DELEGATE_RECOMMEND_ARTIFACT_CUES = [
    "write up",
    "report",
    "summary",
    "matrix",
    "research notes",
    "record findings",
    "整理结论",
    "输出报告",
    "记录结果",
]

DELEGATE_RECOMMEND_MULTI_CUES = [
    "multiple repos",
    "across repos",
    "each repo",
    "for every repo",
    "parallel",
    "多个仓库",
    "多个子问题",
    "逐个仓库",
]

DELEGATE_REQUIRED_LIFECYCLE_CUES = [
    "durable lifecycle",
    "lifecycle state",
    "track lifecycle",
    "resume and promote",
    "blocked then resume",
    "持久生命周期",
    "跟踪生命周期",
    "恢复并提升",
]

DELEGATE_REQUIRED_CLOSEOUT_CUES = [
    "before done",
    "before archive",
    "block done",
    "block archive",
    "gate closeout",
    "完成前",
    "归档前",
    "阻塞 done",
]

DELEGATE_REQUIRED_CONTEXT_CUES = [
    "survive context loss",
    "after context loss",
    "promote later",
    "review later before promote",
    "上下文丢失后",
    "之后再提升",
    "稍后再评审",
]

# =============================================================================
# Regex Patterns
# =============================================================================

SPECIAL_TOKEN_RE = re.compile(
    r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+"
    r"|[A-Za-z0-9_.-]+\.(?:sh|py|md|json|yaml|yml|toml|txt)"
    r"|\.[A-Za-z0-9_.-]+"
    r"|[A-Za-z0-9_.-]*-[A-Za-z0-9_.-]+"
)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}")
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]{2,}")

# =============================================================================
# Configuration Constants
# =============================================================================

SESSION_KEY_ENV = "PLAN_SESSION_KEY"
SESSION_DIR_NAME = ".sessions"
RUNTIME_DIR_NAME = ".runtime"
REPO_REGISTRY_FILE = "repos.json"
TASK_REPO_BINDING_DIR = "task_repo_bindings"
WORKTREE_ROOT_NAME = ".worktrees"

# =============================================================================
# Role Constants
# =============================================================================

ROLE_WRITER = "writer"
ROLE_OBSERVER = "observer"
WORKSPACE_FALLBACK_SESSION_KEY = "workspace:default"

# =============================================================================
# Spec Context Constants
# =============================================================================

SPEC_CONTEXT_MODES = {"none", "embedded", "linked"}
SPEC_CONTEXT_PROVIDERS = {"none", "openspec", "spec-kit", "generic"}
SPEC_CONTEXT_STATUSES = {"none", "detected", "linked", "ambiguous"}
