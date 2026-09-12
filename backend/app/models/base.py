"""Shared SQLAlchemy declarative base.

No concrete models exist yet — Issue #1 only proves the database/migration
plumbing works (see the pgvector-extension migration in `backend/alembic`).
Feature issues (#2 onward) add models here as `models/<entity>.py`.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
