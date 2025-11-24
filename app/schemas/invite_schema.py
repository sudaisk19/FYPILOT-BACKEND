# app/schemas/invite_schema.py
from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field


class InviteRole(str):
    PRIMARY = "primary"
    CO = "co"


class SendSupervisorInviteRequest(BaseModel):
    supervisor_id: UUID = Field(..., description="Supervisor user_id")
    role: str = Field(
        ...,
        pattern="^(supervisor|cosupervisor)$",
        description="Requested role (must match db enum)",
    )
    message: str | None = Field(None, description="Optional message to supervisor")


class PendingInviteItem(BaseModel):
    invite_id: UUID
    group_id: UUID
    group_name: str
    requested_role: str = Field(..., description="primary or co")
    created_at: datetime


class PendingInvitesResponse(BaseModel):
    invites: List[PendingInviteItem] = Field(default_factory=list)


class SentRequestItem(BaseModel):
    """Request sent by a group to a supervisor."""

    request_id: UUID
    supervisor_id: UUID
    supervisor_name: str = Field(..., description="Supervisor's full name")
    requested_role: str = Field(..., description="supervisor or cosupervisor")
    status: str = Field(..., description="pending, accepted, rejected, or cancelled")
    message: str | None = None
    created_at: datetime
    updated_at: datetime


class SentRequestsResponse(BaseModel):
    """All requests sent by a group."""

    group_id: UUID
    requests: List[SentRequestItem] = Field(default_factory=list)
