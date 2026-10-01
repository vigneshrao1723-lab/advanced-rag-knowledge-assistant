"""Add messages.feedback.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-01

Final quality-hardening pass: closes a real Issue #5 "Chat" requirement
gap ("User feedback on responses") that was previously deferred. Per
docs/DATA_MODEL.md's own "Potential entities" note ("`feedback` — for
user feedback on generated answers, if it needs to be more structured
than a field on `messages`"), a simple nullable field on `messages` is
sufficient — no separate `feedback` table, matching the project's
general "don't add a table when a column answers the actual need"
precedent (see `document_processing_jobs`'s own rejection, same file).

A native Postgres enum (`UP`/`DOWN`), matching `message_role`'s own
precedent (migration `0006`) for a fixed, closed set defined by the
project specification.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

_MESSAGE_FEEDBACK_ENUM = sa.Enum("UP", "DOWN", name="message_feedback")


def upgrade() -> None:
    _MESSAGE_FEEDBACK_ENUM.create(op.get_bind())
    op.add_column(
        "messages",
        sa.Column("feedback", _MESSAGE_FEEDBACK_ENUM, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "feedback")
    _MESSAGE_FEEDBACK_ENUM.drop(op.get_bind())
