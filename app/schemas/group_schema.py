# app/schemas/group_schema.py

from uuid import UUID

from pydantic import BaseModel, EmailStr


class CreateGroupRequest(BaseModel):
    name: str


class GroupResponse(BaseModel):
    group_id: UUID
    name: str


class InviteRequest(BaseModel):
    email: EmailStr


class MessageResponse(BaseModel):
    message: str
