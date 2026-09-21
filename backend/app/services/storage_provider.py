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
        candidate = (self._root / key).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError:
            raise StorageKeyError(f"Rejected unsafe storage key: {key!r}") from None
        return candidate

    def save(self, *, key: str, content: bytes) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def read(self, *, key: str) -> bytes:
        path = self._resolve(key)
        try:
            return path.read_bytes()
        except FileNotFoundError:
            raise StorageError(f"Storage key not found: {key!r}") from None

    def delete(self, *, key: str) -> None:
        self._resolve(key).unlink(missing_ok=True)

    def exists(self, *, key: str) -> bool:
        return self._resolve(key).is_file()


def get_storage_provider() -> StorageProvider:
    """`storage_provider` is `Literal["local"]` today — "local" is the only
    implementation. This gains a branch (matching
    `get_email_provider()`'s `console`/`smtp` split) when a second
    implementation is actually added, not before."""
    settings = get_settings()
    return LocalStorage(root=settings.storage_local_root)
