"""Tests for the `StorageProvider` abstraction (Issue #3, Slice 3.2). No
upload API, extraction, chunking, or embedding code exists yet — this
covers only `LocalStorage` and the settings-driven factory, against a
real filesystem (`tmp_path`, not mocked), following this project's
established no-mock-for-real-infrastructure convention.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.storage_provider import (
    LocalStorage,
    StorageError,
    StorageKeyError,
    get_storage_provider,
)


def _storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(root=str(tmp_path))


def test_save_then_read_round_trips_identical_bytes(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    storage.save(key="ws/doc/file.pdf", content=b"hello world")

    assert storage.read(key="ws/doc/file.pdf") == b"hello world"


def test_save_creates_nested_parent_directories(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    storage.save(key="a/b/c/file.txt", content=b"nested")

    assert storage.read(key="a/b/c/file.txt") == b"nested"


def test_exists_reflects_save_and_delete(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    assert storage.exists(key="doc.txt") is False

    storage.save(key="doc.txt", content=b"x")
    assert storage.exists(key="doc.txt") is True

    storage.delete(key="doc.txt")
    assert storage.exists(key="doc.txt") is False


def test_delete_of_nonexistent_key_does_not_raise(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    storage.delete(key="never-existed.txt")  # must not raise


def test_read_of_nonexistent_key_raises_storage_error(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with pytest.raises(StorageError):
        storage.read(key="missing.txt")


@pytest.mark.parametrize(
    "key",
    [
        "../escape.txt",
        "a/../../escape.txt",
        "../../etc/passwd",
        "/etc/passwd",
        "",
    ],
)
def test_unsafe_keys_are_rejected(tmp_path: Path, key: str) -> None:
    storage = _storage(tmp_path)
    with pytest.raises(StorageKeyError):
        storage.save(key=key, content=b"x")


def test_unsafe_key_rejected_on_read_exists_and_delete_too(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with pytest.raises(StorageKeyError):
        storage.read(key="../escape.txt")
    with pytest.raises(StorageKeyError):
        storage.exists(key="../escape.txt")
    with pytest.raises(StorageKeyError):
        storage.delete(key="../escape.txt")


def test_two_different_keys_do_not_collide(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    storage.save(key="ws-a/doc.txt", content=b"a")
    storage.save(key="ws-b/doc.txt", content=b"b")

    assert storage.read(key="ws-a/doc.txt") == b"a"
    assert storage.read(key="ws-b/doc.txt") == b"b"


def test_get_storage_provider_returns_local_storage_by_default() -> None:
    # get_storage_provider() reads the process-wide cached get_settings()
    # (like get_email_provider() does), not a fresh Settings instance —
    # config-validation behavior itself is test_config.py's job, not this
    # file's; this only proves the factory wires up correctly.
    provider = get_storage_provider()
    assert isinstance(provider, LocalStorage)


def test_storage_provider_setting_defaults_to_local() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://u:p@localhost:5432/db",
        secret_key="test-secret",
        _env_file=None,  # type: ignore[call-arg]
    )
    assert settings.storage_provider == "local"
    assert settings.storage_local_root == "./data/documents"
