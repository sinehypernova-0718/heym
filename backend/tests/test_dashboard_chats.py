import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException

from app.api.chats import (
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
    update_conversation,
)
from app.db.models import DashboardConversation, DashboardMessage
from app.models.chat_schemas import ConversationCreate, ConversationUpdate


def _make_user(user_id: uuid.UUID | None = None) -> MagicMock:
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    return user


def _make_conversation(
    user_id: uuid.UUID,
    title: str = "Test Chat",
    is_pinned: bool = False,
) -> DashboardConversation:
    conv = DashboardConversation()
    conv.id = uuid.uuid4()
    conv.user_id = user_id
    conv.title = title
    conv.is_pinned = is_pinned
    conv.created_at = datetime.now(timezone.utc)
    conv.updated_at = datetime.now(timezone.utc)
    conv.messages = []
    return conv


def _make_db(scalars_result: list | None = None, scalar_one: object = None) -> AsyncMock:
    mock_db = AsyncMock()
    mock_result = MagicMock()
    if scalars_result is not None:
        mock_result.scalars.return_value.all.return_value = scalars_result
    mock_result.scalar_one_or_none.return_value = scalar_one
    mock_db.execute.return_value = mock_result
    return mock_db


class TestListConversations(unittest.IsolatedAsyncioTestCase):
    async def test_returns_empty_list_when_no_conversations(self) -> None:
        user = _make_user()
        mock_db = _make_db(scalars_result=[])

        result = await list_conversations(current_user=user, db=mock_db)

        self.assertEqual(result.conversations, [])

    async def test_returns_conversations_for_user(self) -> None:
        user = _make_user()
        conv = _make_conversation(user.id, title="My Chat")
        mock_db = _make_db(scalars_result=[conv])

        result = await list_conversations(current_user=user, db=mock_db)

        self.assertEqual(len(result.conversations), 1)
        self.assertEqual(result.conversations[0].title, "My Chat")

    async def test_pinned_conversations_appear_first(self) -> None:
        user = _make_user()
        pinned = _make_conversation(user.id, title="Pinned", is_pinned=True)
        unpinned = _make_conversation(user.id, title="Unpinned", is_pinned=False)
        mock_db = _make_db(scalars_result=[pinned, unpinned])

        result = await list_conversations(current_user=user, db=mock_db)

        self.assertTrue(result.conversations[0].is_pinned)
        self.assertFalse(result.conversations[1].is_pinned)


class TestCreateConversation(unittest.IsolatedAsyncioTestCase):
    async def test_creates_with_given_title(self) -> None:
        user = _make_user()
        mock_db = AsyncMock()

        added: list[DashboardConversation] = []
        mock_db.add.side_effect = lambda obj: added.append(obj)

        async def fake_refresh(obj: DashboardConversation) -> None:
            obj.id = uuid.uuid4()
            obj.is_pinned = False
            obj.created_at = datetime.now(timezone.utc)
            obj.updated_at = datetime.now(timezone.utc)

        mock_db.refresh.side_effect = fake_refresh

        result = await create_conversation(
            body=ConversationCreate(title="Hello"),
            current_user=user,
            db=mock_db,
        )

        self.assertEqual(result.title, "Hello")
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()

    async def test_defaults_title_to_new_chat(self) -> None:
        user = _make_user()
        mock_db = AsyncMock()

        added: list[DashboardConversation] = []
        mock_db.add = MagicMock(side_effect=lambda obj: added.append(obj))

        async def fake_refresh(obj: DashboardConversation) -> None:
            obj.id = uuid.uuid4()
            obj.is_pinned = False
            obj.created_at = datetime.now(timezone.utc)
            obj.updated_at = datetime.now(timezone.utc)

        mock_db.refresh.side_effect = fake_refresh

        await create_conversation(
            body=ConversationCreate(),
            current_user=user,
            db=mock_db,
        )

        self.assertEqual(added[0].title, "New Chat")


class TestGetConversation(unittest.IsolatedAsyncioTestCase):
    async def test_returns_conversation_with_messages(self) -> None:
        user = _make_user()
        conv = _make_conversation(user.id)
        msg = DashboardMessage()
        msg.id = uuid.uuid4()
        msg.conversation_id = conv.id
        msg.role = "user"
        msg.content = "Hello"
        msg.created_at = datetime.now(timezone.utc)
        conv.messages = [msg]

        mock_db = _make_db(scalar_one=conv)

        result = await get_conversation(
            conversation_id=conv.id,
            current_user=user,
            db=mock_db,
        )

        self.assertEqual(result.id, conv.id)
        self.assertEqual(len(result.messages), 1)
        self.assertEqual(result.messages[0].content, "Hello")

    async def test_raises_404_for_wrong_user(self) -> None:
        user = _make_user()
        mock_db = _make_db(scalar_one=None)

        with self.assertRaises(HTTPException) as ctx:
            await get_conversation(
                conversation_id=uuid.uuid4(),
                current_user=user,
                db=mock_db,
            )

        self.assertEqual(ctx.exception.status_code, 404)


class TestUpdateConversation(unittest.IsolatedAsyncioTestCase):
    async def test_renames_conversation(self) -> None:
        user = _make_user()
        conv = _make_conversation(user.id, title="Old Title")
        mock_db = _make_db(scalar_one=conv)
        mock_db.refresh.side_effect = AsyncMock()

        result = await update_conversation(
            conversation_id=conv.id,
            body=ConversationUpdate(title="New Title"),
            current_user=user,
            db=mock_db,
        )

        self.assertEqual(conv.title, "New Title")
        self.assertEqual(result.title, "New Title")

    async def test_pins_conversation(self) -> None:
        user = _make_user()
        conv = _make_conversation(user.id, is_pinned=False)
        mock_db = _make_db(scalar_one=conv)
        mock_db.refresh.side_effect = AsyncMock()

        await update_conversation(
            conversation_id=conv.id,
            body=ConversationUpdate(is_pinned=True),
            current_user=user,
            db=mock_db,
        )

        self.assertTrue(conv.is_pinned)

    async def test_raises_404_for_wrong_user(self) -> None:
        user = _make_user()
        mock_db = _make_db(scalar_one=None)

        with self.assertRaises(HTTPException) as ctx:
            await update_conversation(
                conversation_id=uuid.uuid4(),
                body=ConversationUpdate(title="x"),
                current_user=user,
                db=mock_db,
            )

        self.assertEqual(ctx.exception.status_code, 404)


class TestDeleteConversation(unittest.IsolatedAsyncioTestCase):
    async def test_deletes_conversation(self) -> None:
        user = _make_user()
        conv = _make_conversation(user.id)
        mock_db = _make_db(scalar_one=conv)

        await delete_conversation(
            conversation_id=conv.id,
            current_user=user,
            db=mock_db,
        )

        mock_db.delete.assert_awaited_once_with(conv)
        mock_db.commit.assert_awaited()

    async def test_raises_404_for_wrong_user(self) -> None:
        user = _make_user()
        mock_db = _make_db(scalar_one=None)

        with self.assertRaises(HTTPException) as ctx:
            await delete_conversation(
                conversation_id=uuid.uuid4(),
                current_user=user,
                db=mock_db,
            )

        self.assertEqual(ctx.exception.status_code, 404)


class TestStreamMessageAuth(unittest.IsolatedAsyncioTestCase):
    async def test_raises_404_when_conversation_not_found(self) -> None:
        from app.api.chats import stream_message
        from app.models.chat_schemas import MessageCreate

        user = _make_user()
        mock_db = _make_db(scalar_one=None)

        with self.assertRaises(HTTPException) as ctx:
            await stream_message(
                conversation_id=uuid.uuid4(),
                body=MessageCreate(
                    content="hello", credential_id=str(uuid.uuid4()), model="gpt-4o"
                ),
                current_user=user,
                db=mock_db,
            )

        self.assertEqual(ctx.exception.status_code, 404)
