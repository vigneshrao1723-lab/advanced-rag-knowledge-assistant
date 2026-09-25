"""SQLAlchemy models. Imported here so `Base.metadata` (used by Alembic
autogenerate and by tests) is aware of every table."""

from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.citation import Citation
from app.models.conversation import Conversation
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.models.message import Message, MessageRole
from app.models.password_reset_token import PasswordResetToken
from app.models.retrieval_event import RetrievalEvent
from app.models.session import Session
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember, WorkspaceRole

__all__ = [
    "AuditLog",
    "Base",
    "Citation",
    "Conversation",
    "Document",
    "DocumentChunk",
    "DocumentStatus",
    "Message",
    "MessageRole",
    "PasswordResetToken",
    "RetrievalEvent",
    "Session",
    "User",
    "Workspace",
    "WorkspaceMember",
    "WorkspaceRole",
]
