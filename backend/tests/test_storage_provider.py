"""Tests for the `StorageProvider` abstraction (Issue #3, Slice 3.2). No
upload API, extraction, chunking, or embedding code exists yet — this
covers only `LocalStorage` and the settings-driven factory, against a
real filesystem (`tmp_path`, not mocked), following this project's
established no-mock-for-real-infrastructure convention.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.storage_provider import (
    LocalStorage,
    StorageError,
    StorageKeyError,
    get_storage_provider,
)

# Permission-based tests are meaningless (and would fail) running as root,
# since root bypasses filesystem permission checks entirely — both this
# host environment and the CI runner (a GitHub-hosted `ubuntu-latest` VM,
# not a container) run as a non-root user, but this guard makes that an
# explicit, checked assumption rather than a silent one.
_RUNNING_AS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0


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


def test_symlink_inside_root_escaping_it_is_rejected(tmp_path: Path) -> None:
    # A literal ".." in the key is already rejected by _resolve()'s parts
    # check before any filesystem access — this proves the *other* path
    # to escaping the root (a symlink planted inside it, no ".." in the
    # key at all) is independently caught by the relative_to() check
    # running on the fully *resolved* (symlink-followed) path.
    outside = tmp_path.parent / f"outside-{tmp_path.name}"
    outside.mkdir()
    (outside / "secret.txt").write_bytes(b"outside root")

    root = tmp_path / "root"
    root.mkdir()
    (root / "escape-link").symlink_to(outside)
    storage = LocalStorage(root=str(root))

    with pytest.raises(StorageKeyError):
        storage.read(key="escape-link/secret.txt")


@pytest.mark.skipif(_RUNNING_AS_ROOT, reason="root bypasses filesystem permissions")
def test_save_permission_denied_raises_storage_error_not_os_error(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    readonly_dir.chmod(stat.S_IREAD | stat.S_IEXEC)  # no write permission
    try:
        with pytest.raises(StorageError) as exc_info:
            storage.save(key="readonly/file.txt", content=b"x")
        assert not isinstance(exc_info.value, StorageKeyError)
        assert str(tmp_path) not in str(exc_info.value)
    finally:
        readonly_dir.chmod(stat.S_IRWXU)  # restore so tmp_path cleanup can remove it


@pytest.mark.skipif(_RUNNING_AS_ROOT, reason="root bypasses filesystem permissions")
def test_read_permission_denied_raises_storage_error_not_os_error(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    storage.save(key="secret.txt", content=b"top secret")
    target = tmp_path / "secret.txt"
    target.chmod(0o000)  # no read permission
    try:
        with pytest.raises(StorageError) as exc_info:
            storage.read(key="secret.txt")
        assert not isinstance(exc_info.value, StorageKeyError)
        assert str(tmp_path) not in str(exc_info.value)
    finally:
        target.chmod(stat.S_IRWXU)  # restore so tmp_path cleanup can remove it


@pytest.mark.skipif(_RUNNING_AS_ROOT, reason="root bypasses filesystem permissions")
def test_delete_permission_denied_raises_storage_error_not_os_error(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    locked_dir = tmp_path / "locked"
    locked_dir.mkdir()
    (locked_dir / "file.txt").write_bytes(b"x")
    locked_dir.chmod(stat.S_IREAD | stat.S_IEXEC)  # no write permission on the dir itself
    try:
        with pytest.raises(StorageError) as exc_info:
            storage.delete(key="locked/file.txt")
        assert not isinstance(exc_info.value, StorageKeyError)
        assert str(tmp_path) not in str(exc_info.value)
    finally:
        locked_dir.chmod(stat.S_IRWXU)  # restore so tmp_path cleanup can remove it


@pytest.mark.skipif(_RUNNING_AS_ROOT, reason="root bypasses filesystem permissions")
def test_exists_raises_storage_error_not_os_error_on_permission_denied(
    tmp_path: Path,
) -> None:
    # Empirically (not assumed), Path.resolve() does not itself raise for
    # a blocked containing directory on this project's Python version —
    # resolution succeeds lexically, and the actual PermissionError
    # surfaces later, from is_file()'s own stat() call, which does *not*
    # swallow it (contrary to what earlier stdlib-docs-based reasoning
    # assumed). exists() must therefore guard that call itself, exactly
    # like save/read/delete guard theirs.
    storage = _storage(tmp_path)
    locked_dir = tmp_path / "locked"
    locked_dir.mkdir()
    (locked_dir / "file.txt").write_bytes(b"x")
    locked_dir.chmod(0o000)  # no execute (search) permission on the dir
    try:
        with pytest.raises(StorageError) as exc_info:
            storage.exists(key="locked/file.txt")
        assert not isinstance(exc_info.value, StorageKeyError)
        assert str(tmp_path) not in str(exc_info.value)
    finally:
        locked_dir.chmod(stat.S_IRWXU)  # restore so tmp_path cleanup can remove it


def test_exists_returns_true_when_only_the_files_own_permissions_are_restricted(
    tmp_path: Path,
) -> None:
    # Restricting the file's own permission bits (not its containing
    # directory) doesn't block stat() — only content access (read()/
    # write()) needs those — so exists() correctly still reports True.
    # No root-permission skip needed: this isn't a permission-*denied*
    # case at all, it's proving a case that must keep working regardless.
    storage = _storage(tmp_path)
    storage.save(key="file.txt", content=b"x")
    target = tmp_path / "file.txt"
    target.chmod(0o000)
    try:
        assert storage.exists(key="file.txt") is True
    finally:
        target.chmod(stat.S_IRWXU)  # restore so tmp_path cleanup can remove it


def test_no_error_message_contains_the_configured_storage_root(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    root_str = str(tmp_path)

    with pytest.raises(StorageKeyError) as key_exc:
        storage.save(key="../escape.txt", content=b"x")
    assert root_str not in str(key_exc.value)

    with pytest.raises(StorageError) as missing_exc:
        storage.read(key="missing.txt")
    assert root_str not in str(missing_exc.value)


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
