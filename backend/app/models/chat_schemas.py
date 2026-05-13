from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ConversationCreate(BaseModel):
    title: str = "New Chat"


class ConversationUpdate(BaseModel):
    title: str | None = None
    is_pinned: bool | None = None


class ConversationResponse(BaseModel):
    id: uuid.UUID
    title: str
    is_pinned: bool
    is_running: bool
    has_unread: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationListResponse(BaseModel):
    conversations: list[ConversationResponse]


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetailResponse(BaseModel):
    id: uuid.UUID
    title: str
    is_pinned: bool
    is_running: bool
    has_unread: bool
    last_credential_id: uuid.UUID | None = None
    last_model: str | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse]

    model_config = {"from_attributes": True}


class ChatFileAttachment(BaseModel):
    name: str
    kind: Literal["text", "image", "pdf"]
    content: str


class MessageCreate(BaseModel):
    content: str
    credential_id: str
    model: str
    attachment: ChatFileAttachment | None = None


class ConversationTitleGenerate(BaseModel):
    credential_id: str
    model: str


class SendMessageResponse(BaseModel):
    conversation_id: uuid.UUID


class QuickPromptsResponse(BaseModel):
    prompts: list[str]


class QuickPromptsUpdate(BaseModel):
    prompts: list[str]
