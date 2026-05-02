from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.db.models import Credential, DashboardConversation, DashboardMessage, User
from app.db.session import async_session_maker
from app.models.chat_schemas import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
    MessageCreate,
    MessageResponse,
)
from app.services.encryption import decrypt_config

router = APIRouter()


async def _get_conversation_or_404(
    conversation_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> DashboardConversation:
    result = await db.execute(
        select(DashboardConversation).where(
            DashboardConversation.id == conversation_id,
            DashboardConversation.user_id == user_id,
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationListResponse:
    """List all conversations for the current user, pinned first then newest."""
    result = await db.execute(
        select(DashboardConversation)
        .where(DashboardConversation.user_id == current_user.id)
        .order_by(
            DashboardConversation.is_pinned.desc(),
            DashboardConversation.updated_at.desc(),
        )
    )
    conversations = result.scalars().all()
    return ConversationListResponse(
        conversations=[ConversationResponse.model_validate(c) for c in conversations]
    )


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """Create a new conversation."""
    conversation = DashboardConversation(
        user_id=current_user.id,
        title=body.title or "New Chat",
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return ConversationResponse.model_validate(conversation)


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationDetailResponse:
    """Get a conversation with all its messages."""
    result = await db.execute(
        select(DashboardConversation)
        .where(
            DashboardConversation.id == conversation_id,
            DashboardConversation.user_id == current_user.id,
        )
        .options(selectinload(DashboardConversation.messages))
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    sorted_messages = sorted(conversation.messages, key=lambda m: m.created_at)
    return ConversationDetailResponse(
        id=conversation.id,
        title=conversation.title,
        is_pinned=conversation.is_pinned,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[MessageResponse.model_validate(m) for m in sorted_messages],
    )


@router.put("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: uuid.UUID,
    body: ConversationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """Rename a conversation and/or toggle its pin state."""
    conversation = await _get_conversation_or_404(conversation_id, current_user.id, db)
    if body.title is not None:
        conversation.title = body.title
    if body.is_pinned is not None:
        conversation.is_pinned = body.is_pinned
    await db.commit()
    await db.refresh(conversation)
    return ConversationResponse.model_validate(conversation)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a conversation and all its messages."""
    conversation = await _get_conversation_or_404(conversation_id, current_user.id, db)
    await db.delete(conversation)
    await db.commit()


async def _generate_chat_stream(
    conversation_id: uuid.UUID,
    api_key: str,
    base_url: str | None,
    model: str,
    history: list[dict[str, str]],
    user_content: str,
) -> AsyncGenerator[str, None]:
    """Stream an LLM reply, persisting user and assistant messages via fresh DB sessions."""
    async with async_session_maker() as session:
        session.add(
            DashboardMessage(
                conversation_id=conversation_id,
                role="user",
                content=user_content,
            )
        )
        await session.commit()

    messages = history + [{"role": "user", "content": user_content}]
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    chunks: list[str] = []

    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            stream=True,
        )
        async for chunk in stream:
            text = chunk.choices[0].delta.content or ""
            if text:
                chunks.append(text)
                yield f"data: {json.dumps({'type': 'content', 'text': text})}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'type': 'error', 'text': str(exc)})}\n\n"
        return

    async with async_session_maker() as session:
        session.add(
            DashboardMessage(
                conversation_id=conversation_id,
                role="assistant",
                content="".join(chunks),
            )
        )
        await session.commit()

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


@router.post("/{conversation_id}/messages")
async def stream_message(
    conversation_id: uuid.UUID,
    body: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Send a user message and stream the assistant reply via SSE."""
    await _get_conversation_or_404(conversation_id, current_user.id, db)

    msg_result = await db.execute(
        select(DashboardMessage)
        .where(DashboardMessage.conversation_id == conversation_id)
        .order_by(DashboardMessage.created_at)
    )
    history = [{"role": m.role, "content": m.content} for m in msg_result.scalars().all()[-25:]]

    cred_result = await db.execute(
        select(Credential).where(
            Credential.id == uuid.UUID(body.credential_id),
            Credential.user_id == current_user.id,
        )
    )
    credential = cred_result.scalar_one_or_none()
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")

    config = decrypt_config(credential.config)

    return StreamingResponse(
        _generate_chat_stream(
            conversation_id=conversation_id,
            api_key=config.get("api_key", ""),
            base_url=config.get("base_url") or None,
            model=body.model,
            history=history,
            user_content=body.content,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
