#!/usr/bin/env python3
"""
Tests for file_lock module - file locking operations.
"""

import multiprocessing
import tempfile
import time
from pathlib import Path

import pytest

# Required for macOS multiprocessing
multiprocessing.set_start_method("fork", force=True)

from file_lock import file_lock, lock_path_for, LockAcquisitionError


class TestLockPathFor:
    """Tests for lock_path_for function."""

    def test_creates_lock_path(self, tmp_path):
        """Test that lock path is generated correctly."""
        resource = tmp_path / "resource.json"
        lock_file = lock_path_for(resource)

        assert lock_file.name == ".resource.json.lock"
        assert lock_file.parent == resource.parent

    def test_lock_path_with_plan_root(self, tmp_path):
        """Test lock path with explicit plan root."""
        resource = tmp_path / "data.json"
        plan_root = tmp_path / ".planning"

        lock_file = lock_path_for(resource, plan_root)

        assert ".runtime" in str(lock_file)
        assert "locks" in str(lock_file)


class TestFileLock:
    """Tests for file_lock context manager."""

    def test_basic_lock_acquire_release(self, tmp_path):
        """Test basic lock acquisition and release."""
        lock_file = tmp_path / "test.lock"

        with file_lock(lock_file):
            assert lock_file.exists()

        # Lock file may still exist after release
        assert True  # Just verify no exception

    def test_nested_lock_same_process(self, tmp_path):
        """Test that same process can re-acquire after release."""
        lock_file = tmp_path / "nested.lock"

        with file_lock(lock_file):
            pass

        # Should be able to acquire again
        with file_lock(lock_file):
            pass

    def test_concurrent_lock_contention(self, tmp_path):
        """Test that concurrent processes serialize access."""
        lock_file = tmp_path / "concurrent.lock"
        result_file = tmp_path / "result.txt"
        result_file.write_text("0")

        def increment_counter():
            for _ in range(10):
                with file_lock(lock_file):
                    current = int(result_file.read_text())
                    time.sleep(0.001)  # Small delay to increase contention
                    result_file.write_text(str(current + 1))

        processes = [
            multiprocessing.Process(target=increment_counter)
            for _ in range(3)
        ]

        for p in processes:
            p.start()
        for p in processes:
            p.join()

        # All increments should have succeeded
        final_count = int(result_file.read_text())
        assert final_count == 30

    def test_lock_timeout(self, tmp_path):
        """Test that lock acquisition times out."""
        lock_file = tmp_path / "timeout.lock"

        def hold_lock():
            with file_lock(lock_file, timeout=30):
                time.sleep(5)  # Hold lock for 5 seconds

        # Start process that holds the lock
        p = multiprocessing.Process(target=hold_lock)
        p.start()

        # Give it time to acquire the lock
        time.sleep(0.5)

        # Try to acquire with short timeout - should fail
        try:
            with file_lock(lock_file, timeout=0.1):
                pass
            pytest.fail("Expected TimeoutError")
        except TimeoutError:
            pass  # Expected
        finally:
            # Cleanup
            p.terminate()
            p.join()


class TestLockAcquisitionError:
    """Tests for LockAcquisitionError exception."""

    def test_error_message(self, tmp_path):
        """Test error message contains relevant info."""
        lock_path = tmp_path / "test.lock"
        error = LockAcquisitionError(lock_path, timeout=5.0)

        assert str(lock_path) in str(error)
        assert "5" in str(error)
