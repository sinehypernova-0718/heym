import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.expressions import (
    ExpressionGenerateRequest,
    NodeResultItem,
    _build_node_context_string,
    _generate_expression,
)
from app.db.models import CredentialType


class BuildNodeContextStringTests(unittest.TestCase):
    def test_empty_returns_no_prior_data(self) -> None:
        result = _build_node_context_string([])
        self.assertIn("No prior run data", result)

    def test_formats_each_node(self) -> None:
        items = [
            NodeResultItem(node_id="n1", label="API Call", output={"name": "John"}),
            NodeResultItem(node_id="n2", label="Transform", output="hello"),
        ]
        result = _build_node_context_string(items)
        self.assertIn("API Call", result)
        self.assertIn("Transform", result)
        self.assertIn('"name"', result)


class GenerateExpressionTests(unittest.IsolatedAsyncioTestCase):
    def _make_credential(self, cred_type: CredentialType = CredentialType.openai) -> MagicMock:
        cred = MagicMock()
        cred.type = cred_type
        cred.encrypted_config = b"encrypted"
        return cred

    async def test_credential_not_found_raises(self) -> None:
        db = AsyncMock()
        user = MagicMock()
        user.id = uuid.uuid4()
        request = ExpressionGenerateRequest(
            description="get name",
            workflow_id=uuid.uuid4(),
            credential_id=uuid.uuid4(),
            model="gpt-4o",
        )
        with patch(
            "app.api.expressions.get_accessible_credential",
            AsyncMock(return_value=None),
        ):
            with self.assertRaises(ValueError):
                await _generate_expression(db=db, request=request, current_user=user)

    async def test_returns_stripped_expression(self) -> None:
        db = AsyncMock()
        user = MagicMock()
        user.id = uuid.uuid4()
        request = ExpressionGenerateRequest(
            description="get customer name from API response",
            workflow_id=uuid.uuid4(),
            credential_id=uuid.uuid4(),
            model="gpt-4o",
            node_results=[
                NodeResultItem(
                    node_id="n1", label="API Call", output={"customer": {"name": "John"}}
                ),
            ],
        )
        cred = self._make_credential()
        with (
            patch(
                "app.api.expressions.get_accessible_credential",
                AsyncMock(return_value=cred),
            ),
            patch(
                "app.api.expressions.decrypt_config",
                return_value={"api_key": "sk-test"},
            ),
            patch(
                "app.api.expressions.execute_llm",
                AsyncMock(return_value={"text": '  $node["API Call"].output.customer.name  \n'}),
            ),
        ):
            result = await _generate_expression(db=db, request=request, current_user=user)
        self.assertEqual(result, '$node["API Call"].output.customer.name')

    async def test_invalid_credential_type_raises(self) -> None:
        db = AsyncMock()
        user = MagicMock()
        user.id = uuid.uuid4()
        request = ExpressionGenerateRequest(
            description="get name",
            workflow_id=uuid.uuid4(),
            credential_id=uuid.uuid4(),
            model="gpt-4o",
        )
        cred = self._make_credential(cred_type=CredentialType.bearer)
        with patch(
            "app.api.expressions.get_accessible_credential",
            AsyncMock(return_value=cred),
        ):
            with self.assertRaises(
                ValueError, msg="Credential must be OpenAI, Google, or Custom type"
            ):
                await _generate_expression(db=db, request=request, current_user=user)

    async def test_empty_node_results_still_generates(self) -> None:
        db = AsyncMock()
        user = MagicMock()
        user.id = uuid.uuid4()
        request = ExpressionGenerateRequest(
            description="get the input text",
            workflow_id=uuid.uuid4(),
            credential_id=uuid.uuid4(),
            model="gpt-4o",
            node_results=[],
        )
        cred = self._make_credential()
        with (
            patch(
                "app.api.expressions.get_accessible_credential",
                AsyncMock(return_value=cred),
            ),
            patch(
                "app.api.expressions.decrypt_config",
                return_value={"api_key": "sk-test"},
            ),
            patch(
                "app.api.expressions.execute_llm",
                AsyncMock(return_value={"text": "$textInput.body.text"}),
            ),
        ):
            result = await _generate_expression(db=db, request=request, current_user=user)
        self.assertEqual(result, "$textInput.body.text")
