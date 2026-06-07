import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, status

from app.api.logs import get_docker_logs, stream_docker_logs
from app.config import settings


class DockerLogsFeatureFlagTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.original_enabled = settings.docker_logs_enabled
        self.original_allowed_emails = settings.docker_logs_allowed_emails
        settings.docker_logs_enabled = False
        settings.docker_logs_allowed_emails = ""

    async def asyncTearDown(self) -> None:
        settings.docker_logs_enabled = self.original_enabled
        settings.docker_logs_allowed_emails = self.original_allowed_emails

    async def test_get_docker_logs_rejects_before_docker_client_when_disabled(self) -> None:
        user = SimpleNamespace(id=uuid.uuid4())

        with patch("app.api.logs.get_docker_client") as get_client:
            with self.assertRaises(HTTPException) as ctx:
                await get_docker_logs("heym-backend", current_user=user, db=AsyncMock())

        self.assertEqual(ctx.exception.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Docker log access is disabled", ctx.exception.detail)
        get_client.assert_not_called()

    async def test_get_docker_logs_rejects_before_docker_client_without_allowed_emails(
        self,
    ) -> None:
        settings.docker_logs_enabled = True
        user = SimpleNamespace(id=uuid.uuid4(), email="admin@example.com")

        with patch("app.api.logs.get_docker_client") as get_client:
            with self.assertRaises(HTTPException) as ctx:
                await get_docker_logs("heym-backend", current_user=user, db=AsyncMock())

        self.assertEqual(ctx.exception.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("no allowed user emails", ctx.exception.detail)
        get_client.assert_not_called()

    async def test_get_docker_logs_rejects_before_docker_client_for_unlisted_user(
        self,
    ) -> None:
        settings.docker_logs_enabled = True
        settings.docker_logs_allowed_emails = "admin@example.com"
        user = SimpleNamespace(id=uuid.uuid4(), email="viewer@example.com")

        with patch("app.api.logs.get_docker_client") as get_client:
            with self.assertRaises(HTTPException) as ctx:
                await get_docker_logs("heym-backend", current_user=user, db=AsyncMock())

        self.assertEqual(ctx.exception.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("not allowed", ctx.exception.detail)
        get_client.assert_not_called()

    async def test_get_docker_logs_allows_configured_user_to_reach_docker_client(
        self,
    ) -> None:
        settings.docker_logs_enabled = True
        settings.docker_logs_allowed_emails = "Admin@Example.com, ops@example.com"
        user = SimpleNamespace(id=uuid.uuid4(), email="admin@example.com")

        with patch("app.api.logs.get_docker_client", return_value=None) as get_client:
            with self.assertRaises(HTTPException) as ctx:
                await get_docker_logs("heym-backend", current_user=user, db=AsyncMock())

        self.assertEqual(ctx.exception.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        get_client.assert_called_once()

    async def test_stream_docker_logs_rejects_before_docker_client_when_disabled(self) -> None:
        user = SimpleNamespace(id=uuid.uuid4())

        with patch("app.api.logs.get_docker_client") as get_client:
            with self.assertRaises(HTTPException) as ctx:
                await stream_docker_logs("heym-backend", current_user=user, db=AsyncMock())

        self.assertEqual(ctx.exception.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Docker log access is disabled", ctx.exception.detail)
        get_client.assert_not_called()
