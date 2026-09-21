"""File storage abstraction (docs/ARCHITECTURE.md "Provider abstractions").

Mirrors `EmailProvider`'s shape exactly (`app/services/email_provider.py`):
a `Protocol`, one concrete implementation today ("local"), and a
settings-driven factory. A later slice (document upload) depends on this
to persist file bytes without knowing whether they're on a local
filesystem or a future object-storage backend — no commercial vendor is
selected yet (docs/ARCHITECTURE.md).

Storage keys are always server-generated (see the `storage_key` column on
`app/models/document.py`'s `Document`) — never derived from a
user-supplied filename, per docs/SECURITY.md "Upload & document safety".
This module still rejects a key that would resolve outside its configured
root as defense in depth, not as the primary path-traversal control (the
primary control is "never let a filename become a key," enforced upstream
by whatever later slice generates the key — this module has no way to
know where a key came from).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.core.config import get_settings


class StorageError(Exception):
    """Any storage operation failure. Never leaks a raw filesystem path to
    a caller outside this module (docs/SECURITY.md "Errors and information
    disclosure") — callers that surface this to an HTTP response are
    responsible for mapping it to a generic message, same as every other
    exception type in this codebase (`app/core/errors.py`)."""


class StorageKeyError(StorageError):
    """A storage key would resolve outside the configured root, is empty,
    or is otherwise unsafe."""


class StorageProvider(Protocol):
    def save(self, *, key: str, content: bytes) -> None: ...
    def read(self, *, key: str) -> bytes: ...
    def delete(self, *, key: str) -> None: ...
    def exists(self, *, key: str) -> bool: ...


class LocalStorage:
    """Filesystem-backed implementation for local dev/CI."""

    def __init__(self, *, root: str) -> None:
        self._root = Path(root).resolve()

    def _resolve(self, key: str) -> Path:
        if not key or key.startswith("/") or ".." in Path(key).parts:
            raise StorageKeyError(f"Rejected unsafe storage key: {key!r}")
        try:
            # .resolve() follows symlinks, so a symlink planted inside the
            # root that points outside it still lands on the
            # relative_to() check below rather than silently escaping —
            # this is what makes the traversal check effective against
            # symlinks, not just literal ".." segments. Empirically (not
            # just assumed), a blocked-permission directory along the way
            # does *not* make .resolve() itself raise on this project's
            # Python version — the actual I/O failure surfaces later, at
            # each operation's own read_bytes()/write_bytes()/unlink()/
            # is_file() call, all of which have their own try/except
            # below. This catch is retained as defense-in-depth against
            # a genuine resolution-time OSError this runtime doesn't
            # happen to produce for the scenarios tested (e.g. a stale
            # network-mount handle) — not proven reachable by a test.
            candidate = (self._root / key).resolve()
        except OSError as exc:
            raise StorageError(f"Failed to resolve storage key: {key!r}") from exc
        try:
            candidate.relative_to(self._root)
        except ValueError:
            raise StorageKeyError(f"Rejected unsafe storage key: {key!r}") from None
        return candidate

    def save(self, *, key: str, content: bytes) -> None:
        path = self._resolve(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        except OSError as exc:
            raise StorageError(f"Failed to save storage key: {key!r}") from exc

    def read(self, *, key: str) -> bytes:
        path = self._resolve(key)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise StorageError(f"Storage key not found: {key!r}") from exc
        except OSError as exc:
            raise StorageError(f"Failed to read storage key: {key!r}") from exc

    def delete(self, *, key: str) -> None:
        path = self._resolve(key)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError(f"Failed to delete storage key: {key!r}") from exc

    def exists(self, *, key: str) -> bool:
        path = self._resolve(key)
        try:
            return path.is_file()
        except OSError as exc:
            # `Path.is_file()` does *not* swallow a permission failure on
            # this project's actual Python version — verified empirically
            # (not assumed from the stdlib docs, which describe behavior
            # that turned out not to hold here): it calls `stat()`
            # directly and lets a `PermissionError` propagate raw. Must
            # not leak past this module, same as save/read/delete.
            raise StorageError(f"Failed to check storage key: {key!r}") from exc


def get_storage_provider() -> StorageProvider:
    """`storage_provider` is `Literal["local"]` today — "local" is the only
    implementation. This gains a branch (matching
    `get_email_provider()`'s `console`/`smtp` split) when a second
    implementation is actually added, not before."""
    settings = get_settings()
    return LocalStorage(root=settings.storage_local_root)
