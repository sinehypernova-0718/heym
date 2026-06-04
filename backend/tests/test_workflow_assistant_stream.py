import asyncio
import unittest
import uuid
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.api.ai_assistant import AIAssistantRequest, workflow_assistant_stream
from app.db.models import CredentialType


class WorkflowAssistantStreamHeartbeatTests(unittest.IsolatedAsyncioTestCase):
    async def test_emits_hidden_heartbeat_while_waiting_for_model_stream(self) -> None:
        release_stream = Event()
        credential_id = uuid.uuid4()
        user = SimpleNamespace(id=uuid.uuid4())
        credential = SimpleNamespace(
            id=credential_id,
            type=CredentialType.openai,
            encrypted_config={},
        )

        async def fake_stream_llm_response(*_args: object, **_kwargs: object):
            await asyncio.to_thread(release_stream.wait)
            yield 'data: {"type": "done"}\n\n'

        with (
            patch(
                "app.api.ai_assistant.get_credential_for_user",
                AsyncMock(return_value=credential),
            ),
            patch("app.api.ai_assistant.decrypt_config", return_value={"api_key": "test"}),
            patch("app.api.ai_assistant.get_openai_client", return_value=(object(), "openai")),
            patch(
                "app.api.ai_assistant.template_service.list_node_templates",
                AsyncMock(return_value=[]),
            ),
            patch("app.api.ai_assistant.stream_llm_response", fake_stream_llm_response),
            patch("app.api.ai_assistant.WORKFLOW_ASSISTANT_SSE_HEARTBEAT_SECONDS", 0.001),
        ):
            response = await workflow_assistant_stream(
                request=AIAssistantRequest(
                    credential_id=credential_id,
                    model="gpt-test",
                    message="hello",
                    ask_mode=True,
                ),
                current_user=user,
                db=AsyncMock(),
            )

            stream = response.body_iterator
            self.assertEqual(await stream.__anext__(), ": heartbeat\n\n")

            release_stream.set()
            self.assertEqual(await stream.__anext__(), 'data: {"type": "done"}\n\n')
            with self.assertRaises(StopAsyncIteration):
                await stream.__anext__()
