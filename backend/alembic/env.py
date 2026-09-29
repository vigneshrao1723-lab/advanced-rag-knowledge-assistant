from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.models import Base  # noqa: F401 — import registers all models on Base.metadata

config = context.config

if config.config_file_name is not None:
    # `disable_existing_loggers=False`: `fileConfig()`'s own default
    # (True) disables every logger that already exists at call time
    # except the ones `alembic.ini`'s `[loggers]` section explicitly
    # lists (`root`/`sqlalchemy`/`alembic`) -- harmless for a one-shot
    # `alembic upgrade` CLI process, but genuinely breaking when
    # migrations run inside the same process as the rest of the test
    # suite (`tests/conftest.py`'s session-scoped migration fixture):
    # every `app.*` logger created before this point (e.g.
    # `app.retrieval`, `app.generation`) would otherwise be silently
    # disabled for the remainder of the pytest session, discovered via
    # a real `caplog`-based observability test unexpectedly seeing zero
    # log records (GitHub Issue #7) -- see `SOLVING.md`.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
