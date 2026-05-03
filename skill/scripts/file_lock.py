#!/usr/bin/env python3
"""
File locking utilities for cross-process synchronization.

Provides advisory file locks to prevent race conditions when multiple
processes access shared resources.
"""

import errno
import fcntl
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


# Default timeout for acquiring locks
DEFAULT_TIMEOUT = 10.0

# Default retry interval
DEFAULT_RETRY_INTERVAL = 0.1


def lock_path_for(resource_path: Path, plan_root: Path | None = None) -> Path:
    """
    Generate a lock file path for a given resource.

    Args:
        resource_path: The resource being protected
        plan_root: Optional planning root for lock directory

    Returns:
        Path to the lock file
    """
    resource_path = Path(resource_path)

    # Use runtime directory under plan root if available
    if plan_root is not None:
        lock_dir = plan_root / ".runtime" / "locks"
    else:
        # Fall back to same directory as resource
        lock_dir = resource_path.parent

    lock_dir.mkdir(parents=True, exist_ok=True)

    # Create a unique lock filename based on resource path
    resource_name = resource_path.name
    lock_name = f".{resource_name}.lock"
    return lock_dir / lock_name


@contextmanager
def file_lock(
    lock_path: Path,
    timeout: float = DEFAULT_TIMEOUT,
    retry_interval: float = DEFAULT_RETRY_INTERVAL,
) -> Generator[None, None, None]:
    """
    Acquire an exclusive advisory file lock.

    Uses fcntl.flock (BSD/POSIX) for cross-process synchronization.
    Non-blocking acquisition with timeout and retry.

    Args:
        lock_path: Path to the lock file
        timeout: Maximum time to wait for lock (seconds)
        retry_interval: Time between retry attempts (seconds)

    Yields:
        None when lock is acquired

    Raises:
        TimeoutError: If lock cannot be acquired within timeout
    """
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    start_time = time.monotonic()
    lock_file = None

    try:
        while True:
            try:
                lock_file = open(lock_path, "w")
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                # Lock acquired
                break
            except (IOError, OSError) as e:
                if e.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                    # Unexpected error
                    if lock_file is not None:
                        try:
                            lock_file.close()
                        except OSError:
                            pass
                    raise

                # Lock is held by another process
                if time.monotonic() - start_time >= timeout:
                    if lock_file is not None:
                        try:
                            lock_file.close()
                        except OSError:
                            pass
                    raise TimeoutError(
                        f"Could not acquire lock at {lock_path} within {timeout}s"
                    )

                # Wait and retry
                time.sleep(retry_interval)

        # Yield control to caller
        yield

    finally:
        # Release lock
        if lock_file is not None:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()
            except (OSError, ValueError):
                # File may already be closed or invalid
                pass


@contextmanager
def locked_write(
    resource_path: Path,
    plan_root: Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Generator[Path, None, None]:
    """
    Context manager for locked write operations.

    Acquires a lock, yields the resource path, then releases the lock.

    Args:
        resource_path: Path to the resource being written
        plan_root: Optional planning root for lock directory
        timeout: Maximum time to wait for lock

    Yields:
        The resource path (for writing)
    """
    lock_file = lock_path_for(resource_path, plan_root)

    with file_lock(lock_file, timeout=timeout):
        yield resource_path


class LockAcquisitionError(Exception):
    """Raised when a lock cannot be acquired."""

    def __init__(self, lock_path: Path, timeout: float):
        self.lock_path = lock_path
        self.timeout = timeout
        super().__init__(
            f"Failed to acquire lock at {lock_path} within {timeout}s"
        )
