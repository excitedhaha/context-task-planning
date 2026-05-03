#!/usr/bin/env python3
"""
Tests for file_utils module - atomic write operations.
"""

import json
import multiprocessing
import os
import tempfile
from pathlib import Path

import pytest

# Required for macOS multiprocessing
multiprocessing.set_start_method("fork", force=True)

from file_utils import atomic_write_json, atomic_write_text, safe_read_json


class TestAtomicWriteJson:
    """Tests for atomic_write_json function."""

    def test_write_new_file(self, tmp_path):
        """Test writing to a new file."""
        target = tmp_path / "test.json"
        payload = {"key": "value", "number": 42}

        atomic_write_json(target, payload)

        assert target.exists()
        result = json.loads(target.read_text())
        assert result == payload

    def test_overwrite_existing_file(self, tmp_path):
        """Test overwriting an existing file."""
        target = tmp_path / "test.json"
        target.write_text('{"old": "data"}')

        payload = {"new": "data"}
        atomic_write_json(target, payload)

        result = json.loads(target.read_text())
        assert result == payload
        assert "old" not in result

    def test_creates_parent_directories(self, tmp_path):
        """Test that parent directories are created."""
        target = tmp_path / "subdir" / "deep" / "test.json"
        payload = {"nested": True}

        atomic_write_json(target, payload)

        assert target.exists()
        assert target.parent.is_dir()

    def test_write_with_unicode(self, tmp_path):
        """Test writing Unicode content."""
        target = tmp_path / "unicode.json"
        payload = {"chinese": "你好世界", "emoji": "🎉"}

        atomic_write_json(target, payload)

        result = json.loads(target.read_text(encoding="utf-8"))
        assert result["chinese"] == "你好世界"
        assert result["emoji"] == "🎉"

    def test_custom_indent(self, tmp_path):
        """Test custom indentation."""
        target = tmp_path / "indent.json"
        payload = {"key": "value"}

        atomic_write_json(target, payload, indent=4)

        content = target.read_text()
        assert "    " in content  # 4-space indent


class TestAtomicWriteText:
    """Tests for atomic_write_text function."""

    def test_write_text_file(self, tmp_path):
        """Test writing a text file."""
        target = tmp_path / "test.txt"
        content = "Hello, World!"

        atomic_write_text(target, content)

        assert target.read_text() == content

    def test_write_multiline_text(self, tmp_path):
        """Test writing multiline text."""
        target = tmp_path / "multiline.txt"
        content = "Line 1\nLine 2\nLine 3\n"

        atomic_write_text(target, content)

        assert target.read_text() == content


class TestSafeReadJson:
    """Tests for safe_read_json function."""

    def test_read_valid_json(self, tmp_path):
        """Test reading a valid JSON file."""
        target = tmp_path / "valid.json"
        payload = {"key": "value"}
        target.write_text(json.dumps(payload))

        with safe_read_json(target) as result:
            assert result == payload

    def test_read_nonexistent_file(self, tmp_path):
        """Test reading a nonexistent file returns default."""
        target = tmp_path / "nonexistent.json"

        with safe_read_json(target, default={"default": True}) as result:
            assert result == {"default": True}

    def test_read_invalid_json(self, tmp_path):
        """Test reading invalid JSON returns default."""
        target = tmp_path / "invalid.json"
        target.write_text("not valid json {{{")

        with safe_read_json(target, default={"fallback": True}) as result:
            assert result == {"fallback": True}


class TestConcurrency:
    """Tests for concurrent write safety."""

    def test_concurrent_json_writes(self, tmp_path):
        """Test that concurrent writes don't corrupt the file."""
        target = tmp_path / "concurrent.json"
        num_processes = 10
        writes_per_process = 5

        def write_multiple(process_id):
            for i in range(writes_per_process):
                payload = {
                    "process": process_id,
                    "iteration": i,
                    "data": f"data_{process_id}_{i}",
                }
                atomic_write_json(target, payload)

        processes = [
            multiprocessing.Process(target=write_multiple, args=(i,))
            for i in range(num_processes)
        ]

        for p in processes:
            p.start()
        for p in processes:
            p.join()

        # File should exist and be valid JSON
        assert target.exists()
        result = json.loads(target.read_text())

        # Should have one of the written payloads
        assert "process" in result
        assert "iteration" in result
