from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncGenerator
from threading import Event

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.ai_assistant import (
    _ATTACHMENT_ROUTING_INSTRUCTIONS,
    DASHBOARD_CHAT_SYSTEM_PROMPT,
    MAX_DASHBOARD_CHAT_HISTORY,
    FileAttachment,
    _build_user_message,
    _format_workflows_for_prompt,
    _load_agents_md_content,
    get_openai_client,
    get_workflows_for_user_with_inputs,
    stream_dashboard_chat,
)
from app.api.deps import get_current_user, get_db
from app.db.models import CredentialType, DashboardConversation, DashboardMessage, User
from app.models.chat_schemas import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    ConversationTitleGenerate,
    ConversationUpdate,
    MessageCreate,
    MessageResponse,
)
from app.services.credential_access import get_accessible_credential
from app.services.encryption import decrypt_config
from app.services.hitl_service import build_public_base_url
from app.services.llm_trace import LLMTraceContext

router = APIRouter()
logger = logging.getLogger(__name__)

DEFAULT_CONVERSATION_TITLE = "New Chat"


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
        title=body.title or DEFAULT_CONVERSATION_TITLE,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return ConversationResponse.model_validate(conversation)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete all conversations for the current user."""
    await db.execute(
        delete(DashboardConversation).where(DashboardConversation.user_id == current_user.id)
    )
    await db.commit()


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


def _fallback_title_from_content(content: str) -> str:
    cleaned = " ".join(content.replace("\n", " ").split())
    cleaned = cleaned.split("[ATTACHED", maxsplit=1)[0].strip()
    if not cleaned:
        return DEFAULT_CONVERSATION_TITLE
    title_source = cleaned.strip("\"'`“”‘’")
    if len(title_source) > 50:
        word_boundary = title_source.find(" ", 50)
        title_source = title_source[: word_boundary if word_boundary != -1 else 50]
    title = title_source.rstrip(".,:;!?")
    return f"{title}..." if title else DEFAULT_CONVERSATION_TITLE


@router.post("/{conversation_id}/title", response_model=ConversationResponse)
async def generate_conversation_title(
    conversation_id: uuid.UUID,
    body: ConversationTitleGenerate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """Generate a deterministic title for a new conversation."""
    conversation = await _get_conversation_or_404(conversation_id, current_user.id, db)
    if conversation.title != DEFAULT_CONVERSATION_TITLE:
        return ConversationResponse.model_validate(conversation)

    msg_result = await db.execute(
        select(DashboardMessage)
        .where(DashboardMessage.conversation_id == conversation_id)
        .order_by(DashboardMessage.created_at)
    )
    messages = msg_result.scalars().all()
    user_message = next((m for m in messages if m.role == "user" and m.content.strip()), None)
    if user_message is None:
        return ConversationResponse.model_validate(conversation)
    title = _fallback_title_from_content(user_message.content)
    if title is not None and conversation.title == DEFAULT_CONVERSATION_TITLE:
        conversation.title = title
        await db.commit()
        await db.refresh(conversation)

    return ConversationResponse.model_validate(conversation)


@router.post("/{conversation_id}/messages")
async def stream_message(
    http_request: Request,
    conversation_id: uuid.UUID,
    body: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Send a user message and stream the assistant reply via SSE."""
    conversation = await _get_conversation_or_404(conversation_id, current_user.id, db)

    msg_result = await db.execute(
        select(DashboardMessage)
        .where(DashboardMessage.conversation_id == conversation_id)
        .order_by(DashboardMessage.created_at)
    )
    existing_messages = msg_result.scalars().all()
    history = [{"role": m.role, "content": m.content} for m in existing_messages[-25:]]

    credential = await get_accessible_credential(
        db,
        uuid.UUID(body.credential_id),
        current_user.id,
    )
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")
    if credential.type not in (CredentialType.openai, CredentialType.google, CredentialType.custom):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Credential must be an LLM type (OpenAI, Google, or Custom)",
        )

    config = decrypt_config(credential.encrypted_config)
    client, provider = get_openai_client(credential.type, config)
    attachment = (
        FileAttachment(
            name=body.attachment.name,
            kind=body.attachment.kind,
            content=body.attachment.content,
        )
        if body.attachment
        else None
    )
    user_message = _build_user_message(body.content, attachment)
    if len(history) > MAX_DASHBOARD_CHAT_HISTORY:
        history = history[-MAX_DASHBOARD_CHAT_HISTORY:]
    messages = list(history)
    messages.append(user_message)

    trace_context = LLMTraceContext(
        user_id=current_user.id,
        credential_id=credential.id,
        workflow_id=None,
        node_label="Dashboard Chat",
        source="dashboard_chat",
    )
    workflows = await get_workflows_for_user_with_inputs(db, current_user.id)
    workflows_block = _format_workflows_for_prompt(workflows)
    agents_md = _load_agents_md_content()
    system_prompt = DASHBOARD_CHAT_SYSTEM_PROMPT
    if agents_md:
        system_prompt = (
            "## Heym Platform Context\n\n"
            "Use the following Heym platform documentation to answer questions about the platform, structure, commands, code style, and conventions:\n\n"
            + agents_md
            + "\n\n---\n\n"
            + system_prompt
        )
    if workflows_block:
        system_prompt = (
            system_prompt
            + "\n\nAvailable workflows (always check these first when user asks for information):\n"
            + workflows_block
        )
    if body.attachment:
        system_prompt = system_prompt + "\n\n" + _ATTACHMENT_ROUTING_INSTRUCTIONS
    public_base_url = build_public_base_url(http_request)
    cancel_event = Event()

    db.add(
        DashboardMessage(
            conversation_id=conversation_id,
            role="user",
            content=user_message["content"],
        )
    )
    await db.commit()
    should_generate_title = (
        len(existing_messages) == 0 and conversation.title == DEFAULT_CONVERSATION_TITLE
    )

    async def event_generator() -> AsyncGenerator[str, None]:
        assistant_chunks: list[str] = []
        try:
            async for chunk in stream_dashboard_chat(
                client,
                body.model,
                system_prompt,
                messages,
                db,
                current_user,
                provider,
                public_base_url,
                trace_context,
                cancel_event,
                attachment,
            ):
                if cancel_event.is_set():
                    break
                if chunk.startswith("data: "):
                    try:
                        payload = json.loads(chunk[6:].strip())
                    except json.JSONDecodeError:
                        payload = {}
                    if payload.get("type") == "content":
                        assistant_chunks.append(str(payload.get("text") or ""))
                    elif payload.get("type") == "done":
                        assistant_content = "".join(assistant_chunks)
                        if assistant_content:
                            db.add(
                                DashboardMessage(
                                    conversation_id=conversation_id,
                                    role="assistant",
                                    content=assistant_content,
                                )
                            )
                        if should_generate_title:
                            title = _fallback_title_from_content(body.content)
                            conversation.title = title
                            await db.commit()
                            yield f"data: {json.dumps({'type': 'title', 'title': title})}\n\n"
                        elif assistant_content:
                            await db.commit()
                yield chunk
        finally:
            cancel_event.set()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
