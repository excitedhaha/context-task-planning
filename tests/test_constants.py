#!/usr/bin/env python3
"""
Tests for constants module.
"""

import re

from constants import (
    CHINESE_RE,
    COMPLEX_KEYWORDS,
    COMPLEX_SIGNALS,
    DELEGATE_KIND_PATTERNS,
    DELEGATE_RECOMMEND_ARTIFACT_CUES,
    DELEGATE_RECOMMEND_MULTI_CUES,
    DELEGATE_RECOMMEND_SESSION_CUES,
    DELEGATE_REQUIRED_CLOSEOUT_CUES,
    DELEGATE_REQUIRED_CONTEXT_CUES,
    DELEGATE_REQUIRED_LIFECYCLE_CUES,
    FOLLOWUP_PHRASES,
    REPO_REGISTRY_FILE,
    ROLE_OBSERVER,
    ROLE_WRITER,
    RUNTIME_DIR_NAME,
    SESSION_DIR_NAME,
    SESSION_KEY_ENV,
    SPECIAL_TOKEN_RE,
    SPEC_CONTEXT_MODES,
    SPEC_CONTEXT_PROVIDERS,
    SPEC_CONTEXT_STATUSES,
    STOPWORDS,
    SWITCH_CUES,
    TASK_REPO_BINDING_DIR,
    WORKSPACE_FALLBACK_SESSION_KEY,
    WORKTREE_ROOT_NAME,
    WORD_RE,
)


class TestConstants:
    """Tests for constant values."""

    def test_role_constants(self):
        """Test role constants are valid strings."""
        assert ROLE_WRITER == "writer"
        assert ROLE_OBSERVER == "observer"
        assert ROLE_WRITER != ROLE_OBSERVER

    def test_directory_constants(self):
        """Test directory name constants."""
        assert SESSION_DIR_NAME == ".sessions"
        assert RUNTIME_DIR_NAME == ".runtime"
        assert WORKTREE_ROOT_NAME == ".worktrees"
        assert TASK_REPO_BINDING_DIR == "task_repo_bindings"

    def test_file_constants(self):
        """Test file name constants."""
        assert REPO_REGISTRY_FILE == "repos.json"

    def test_env_constant(self):
        """Test environment variable constant."""
        assert SESSION_KEY_ENV == "PLAN_SESSION_KEY"

    def test_spec_context_modes(self):
        """Test spec context mode set."""
        assert "none" in SPEC_CONTEXT_MODES
        assert "embedded" in SPEC_CONTEXT_MODES
        assert "linked" in SPEC_CONTEXT_MODES
        assert len(SPEC_CONTEXT_MODES) == 3

    def test_spec_context_providers(self):
        """Test spec context provider set."""
        assert "none" in SPEC_CONTEXT_PROVIDERS
        assert "openspec" in SPEC_CONTEXT_PROVIDERS
        assert "spec-kit" in SPEC_CONTEXT_PROVIDERS
        assert "generic" in SPEC_CONTEXT_PROVIDERS

    def test_spec_context_statuses(self):
        """Test spec context status set."""
        assert "none" in SPEC_CONTEXT_STATUSES
        assert "detected" in SPEC_CONTEXT_STATUSES
        assert "linked" in SPEC_CONTEXT_STATUSES
        assert "ambiguous" in SPEC_CONTEXT_STATUSES


class TestRegexPatterns:
    """Tests for compiled regex patterns."""

    def test_special_token_re_matches_paths(self):
        """Test SPECIAL_TOKEN_RE matches file paths."""
        assert SPECIAL_TOKEN_RE.search("src/main.py")
        assert SPECIAL_TOKEN_RE.search("path/to/file.json")

    def test_special_token_re_matches_extensions(self):
        """Test SPECIAL_TOKEN_RE matches file extensions."""
        assert SPECIAL_TOKEN_RE.search("script.sh")
        assert SPECIAL_TOKEN_RE.search("config.yaml")

    def test_special_token_re_matches_kebab_case(self):
        """Test SPECIAL_TOKEN_RE matches kebab-case."""
        assert SPECIAL_TOKEN_RE.search("my-component-name")

    def test_word_re_matches_english(self):
        """Test WORD_RE matches English words."""
        assert WORD_RE.search("hello")
        assert WORD_RE.search("variable_name")

    def test_word_re_requires_min_length(self):
        """Test WORD_RE requires minimum length."""
        # Pattern is [A-Za-z][A-Za-z0-9_]{2,} which means 3+ chars total
        assert WORD_RE.search("abc")  # 3 chars minimum
        assert not WORD_RE.search("ab")  # too short

    def test_chinese_re_matches_chinese(self):
        """Test CHINESE_RE matches Chinese characters."""
        assert CHINESE_RE.search("你好")
        assert CHINESE_RE.search("任务管理")

    def test_chinese_re_requires_min_length(self):
        """Test CHINESE_RE requires minimum 2 characters."""
        # Pattern is {2,} which means 2+ chars
        assert CHINESE_RE.search("你好")  # 2 chars minimum
        assert not CHINESE_RE.search("你")  # only 1 char


class TestDriftDetectionConstants:
    """Tests for drift detection related constants."""

    def test_stopwords_contains_english(self):
        """Test STOPWORDS contains common English words."""
        assert "the" in STOPWORDS
        assert "and" in STOPWORDS
        assert "for" in STOPWORDS

    def test_stopwords_contains_chinese(self):
        """Test STOPWORDS contains common Chinese words."""
        assert "任务" in STOPWORDS
        assert "继续" in STOPWORDS

    def test_followup_phrases(self):
        """Test FOLLOWUP_PHRASES contains expected values."""
        assert "continue" in FOLLOWUP_PHRASES
        assert "继续" in FOLLOWUP_PHRASES

    def test_switch_cues(self):
        """Test SWITCH_CUES contains expected values."""
        assert "another task" in SWITCH_CUES
        assert "新任务" in SWITCH_CUES

    def test_complex_keywords(self):
        """Test COMPLEX_KEYWORDS contains expected values."""
        assert "implement" in COMPLEX_KEYWORDS
        assert "实现" in COMPLEX_KEYWORDS

    def test_complex_signals(self):
        """Test COMPLEX_SIGNALS contains expected values."""
        assert "\n" in COMPLEX_SIGNALS
        assert "需要" in COMPLEX_SIGNALS


class TestDelegatePatterns:
    """Tests for delegate-related constants."""

    def test_delegate_kind_patterns_structure(self):
        """Test DELEGATE_KIND_PATTERNS has correct structure."""
        for kind, patterns in DELEGATE_KIND_PATTERNS:
            assert isinstance(kind, str)
            assert isinstance(patterns, list)
            assert len(patterns) > 0

    def test_delegate_kind_patterns_contains_review(self):
        """Test DELEGATE_KIND_PATTERNS contains review kind."""
        kinds = [k for k, _ in DELEGATE_KIND_PATTERNS]
        assert "review" in kinds

    def test_delegate_recommend_session_cues(self):
        """Test DELEGATE_RECOMMEND_SESSION_CUES."""
        assert "resume later" in DELEGATE_RECOMMEND_SESSION_CUES
        assert "后续继续" in DELEGATE_RECOMMEND_SESSION_CUES

    def test_delegate_recommend_artifact_cues(self):
        """Test DELEGATE_RECOMMEND_ARTIFACT_CUES."""
        assert "write up" in DELEGATE_RECOMMEND_ARTIFACT_CUES
        assert "整理结论" in DELEGATE_RECOMMEND_ARTIFACT_CUES

    def test_delegate_required_cues(self):
        """Test DELEGATE_REQUIRED_*_CUES lists."""
        assert len(DELEGATE_REQUIRED_LIFECYCLE_CUES) > 0
        assert len(DELEGATE_REQUIRED_CLOSEOUT_CUES) > 0
        assert len(DELEGATE_REQUIRED_CONTEXT_CUES) > 0
