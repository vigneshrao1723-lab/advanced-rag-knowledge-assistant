from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.workspace_member import WorkspaceRole

_NAME_MIN_LENGTH = 1
_NAME_MAX_LENGTH = 200


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=_NAME_MIN_LENGTH, max_length=_NAME_MAX_LENGTH)


class WorkspaceUpdate(BaseModel):
    name: str = Field(min_length=_NAME_MIN_LENGTH, max_length=_NAME_MAX_LENGTH)


class WorkspaceRead(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime
    my_role: WorkspaceRole


class MemberRead(BaseModel):
    user_id: uuid.UUID
    email: str
    role: WorkspaceRole
    created_at: datetime


class MemberAdd(BaseModel):
    email: EmailStr
    role: WorkspaceRole = WorkspaceRole.MEMBER


class MemberRoleUpdate(BaseModel):
    role: WorkspaceRole
