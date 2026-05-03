#!/usr/bin/env python3
"""
File utilities for atomic operations.

Provides atomic write and safe file operations to prevent data corruption
in concurrent scenarios.
"""

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def atomic_write_json(
    path: Path, payload: dict[str, Any], indent: int = 2, encoding: str = "utf-8"
) -> None:
    """
    Atomically write a JSON file using temp file + rename pattern.

    This prevents partial writes and data corruption when multiple processes
    write to the same file concurrently.

    Args:
        path: Target file path
        payload: JSON-serializable dictionary
        indent: JSON indentation (default: 2)
        encoding: File encoding (default: utf-8)
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Use temp file in same directory for atomic rename
    fd, temp_path_str = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.tmp.",
        suffix=".json",
    )

    temp_path = Path(temp_path_str)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            json.dump(payload, f, indent=indent, ensure_ascii=False)
            f.write("\n")

        # Atomic rename (POSIX guarantees atomicity)
        temp_path.replace(path)
    finally:
        # Cleanup temp file if still exists (e.g., on exception)
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def atomic_write_text(
    path: Path, content: str, encoding: str = "utf-8"
) -> None:
    """
    Atomically write a text file using temp file + rename pattern.

    Args:
        path: Target file path
        content: Text content to write
        encoding: File encoding (default: utf-8)
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path_str = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.tmp.",
    )

    temp_path = Path(temp_path_str)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)

        temp_path.replace(path)
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


@contextmanager
def safe_read_json(path: Path, default: dict[str, Any] | None = None):
    """
    Safely read a JSON file with a default fallback.

    Args:
        path: File path to read
        default: Default value if file doesn't exist or is invalid

    Yields:
        The parsed JSON dict or default value
    """
    if default is None:
        default = {}

    path = Path(path)
    if not path.exists():
        yield default
        return

    try:
        content = path.read_text(encoding="utf-8")
        yield json.loads(content)
    except (OSError, json.JSONDecodeError):
        yield default
