import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException

from app.api.chats import DEFAULT_QUICK_PROMPTS, get_quick_prompts, save_quick_prompts
from app.db.models import DashboardChatQuickPrompts
from app.models.chat_schemas import QuickPromptsUpdate


def _make_user(user_id: uuid.UUID | None = None) -> MagicMock:
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    return user


def _make_prompts_row(user_id: uuid.UUID, prompts: list[str]) -> DashboardChatQuickPrompts:
    row = DashboardChatQuickPrompts()
    row.user_id = user_id
    row.prompts = prompts
    row.updated_at = datetime.now(timezone.utc)
    return row


class TestGetQuickPrompts(unittest.IsolatedAsyncioTestCase):
    async def test_returns_defaults_when_no_row(self) -> None:
        user = _make_user()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await get_quick_prompts(current_user=user, db=mock_db)

        self.assertEqual(result.prompts, DEFAULT_QUICK_PROMPTS)

    async def test_returns_saved_prompts(self) -> None:
        user = _make_user()
        saved = ["Run a workflow", "List my teams"]
        row = _make_prompts_row(user.id, saved)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = row
        mock_db.execute.return_value = mock_result

        result = await get_quick_prompts(current_user=user, db=mock_db)

        self.assertEqual(result.prompts, saved)


class TestSaveQuickPrompts(unittest.IsolatedAsyncioTestCase):
    async def test_saves_new_prompts_when_no_existing_row(self) -> None:
        user = _make_user()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        added: list = []
        mock_db.add = MagicMock(side_effect=added.append)

        body = QuickPromptsUpdate(prompts=["List workflows", "Run something"])
        result = await save_quick_prompts(body=body, current_user=user, db=mock_db)

        self.assertEqual(result.prompts, ["List workflows", "Run something"])
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()

    async def test_updates_existing_row(self) -> None:
        user = _make_user()
        existing_row = _make_prompts_row(user.id, ["old prompt"])

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_row
        mock_db.execute.return_value = mock_result

        body = QuickPromptsUpdate(prompts=["new prompt"])
        result = await save_quick_prompts(body=body, current_user=user, db=mock_db)

        self.assertEqual(result.prompts, ["new prompt"])
        self.assertEqual(existing_row.prompts, ["new prompt"])
        mock_db.add.assert_not_called()

    async def test_strips_empty_prompts(self) -> None:
        user = _make_user()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        mock_db.add = MagicMock()

        body = QuickPromptsUpdate(prompts=["  ", "valid prompt", ""])
        result = await save_quick_prompts(body=body, current_user=user, db=mock_db)

        self.assertEqual(result.prompts, ["valid prompt"])

    async def test_rejects_more_than_7_prompts(self) -> None:
        user = _make_user()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        body = QuickPromptsUpdate(prompts=[f"prompt {i}" for i in range(8)])

        with self.assertRaises(HTTPException) as ctx:
            await save_quick_prompts(body=body, current_user=user, db=mock_db)
        self.assertEqual(ctx.exception.status_code, 422)

    async def test_rejects_prompt_over_200_chars(self) -> None:
        user = _make_user()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        body = QuickPromptsUpdate(prompts=["x" * 201])

        with self.assertRaises(HTTPException) as ctx:
            await save_quick_prompts(body=body, current_user=user, db=mock_db)
        self.assertEqual(ctx.exception.status_code, 422)

    async def test_accepts_exactly_7_prompts(self) -> None:
        user = _make_user()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        mock_db.add = MagicMock()

        body = QuickPromptsUpdate(prompts=[f"prompt {i}" for i in range(7)])
        result = await save_quick_prompts(body=body, current_user=user, db=mock_db)

        self.assertEqual(len(result.prompts), 7)
