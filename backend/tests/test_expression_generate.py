import unittest
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.expressions import (
    ExpressionGeneratePriorAttempt,
    ExpressionGenerateRequest,
    NodeResultItem,
    _build_node_context_string,
    _finalize_generated_expression,
    _generate_expression,
    _normalize_generated_expression,
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


class NormalizeGeneratedExpressionTests(unittest.TestCase):
    def test_extracts_expression_from_code_fence(self) -> None:
        result = _normalize_generated_expression("```expression\n$api.customer.name\n```")
        self.assertEqual(result, "$api.customer.name")

    def test_extracts_expression_when_fence_not_closed(self) -> None:
        result = _normalize_generated_expression("```expression\n$api.customer.name\n")
        self.assertEqual(result, "$api.customer.name")

    def test_extracts_expression_from_json_response(self) -> None:
        result = _normalize_generated_expression('{"expression": "$api.customer.name"}')
        self.assertEqual(result, "$api.customer.name")

    def test_extracts_expression_after_prose_line(self) -> None:
        text = 'Here is the expression:\n$node["HTTP"].output.body.items[0].id'
        result = _normalize_generated_expression(text)
        self.assertEqual(result, '$node["HTTP"].output.body.items[0].id')

    def test_finalize_strips_trailing_backticks(self) -> None:
        self.assertEqual(_finalize_generated_expression('$node["A"].out.x`'), '$node["A"].out.x')
        self.assertEqual(_finalize_generated_expression("$vars.foo``"), "$vars.foo")

    def test_rejects_non_expression_text(self) -> None:
        with self.assertRaises(ValueError):
            _normalize_generated_expression("Use the customer name from the API response.")


class GenerateExpressionTests(unittest.IsolatedAsyncioTestCase):
    def _workflow_and_globals(self) -> tuple[Any, Any]:
        workflow = MagicMock()
        workflow.nodes = []
        workflow.edges = []
        return (
            patch("app.api.expressions.get_workflow_by_id", AsyncMock(return_value=workflow)),
            patch("app.api.expressions.get_global_variables_context", AsyncMock(return_value={})),
        )

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
            input_value="customer name from the API response",
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
        execute_mock = AsyncMock(
            return_value={"text": '```expression\n$node["API Call"].output.customer.name\n```'}
        )
        wf_patch, gv_patch = self._workflow_and_globals()
        with (
            patch(
                "app.api.expressions.get_accessible_credential",
                AsyncMock(return_value=cred),
            ),
            patch(
                "app.api.expressions.decrypt_config",
                return_value={"api_key": "sk-test"},
            ),
            wf_patch,
            gv_patch,
            patch(
                "app.api.expressions.execute_llm",
                execute_mock,
            ),
        ):
            result = await _generate_expression(db=db, request=request, current_user=user)
        self.assertEqual(result, '$node["API Call"].output.customer.name')
        user_message = execute_mock.await_args.kwargs["user_message"]
        self.assertIn("Evaluator input value: customer name from the API response", user_message)
        self.assertIn("### Workflow `$vars` namespace", user_message)
        self.assertIn("### Global variables", user_message)

    async def test_regenerate_prior_attempt_and_temperature(self) -> None:
        db = AsyncMock()
        user = MagicMock()
        user.id = uuid.uuid4()
        request = ExpressionGenerateRequest(
            description="fix it",
            workflow_id=uuid.uuid4(),
            credential_id=uuid.uuid4(),
            model="gpt-4o",
            node_results=[],
            prior_attempt=ExpressionGeneratePriorAttempt(
                expression="$bad.old.path",
                evaluation_error="Path not found",
                evaluated_result=None,
            ),
        )
        cred = self._make_credential()
        execute_mock = AsyncMock(return_value={"text": "$good.new.path"})
        wf_patch, gv_patch = self._workflow_and_globals()
        with (
            patch(
                "app.api.expressions.get_accessible_credential",
                AsyncMock(return_value=cred),
            ),
            patch(
                "app.api.expressions.decrypt_config",
                return_value={"api_key": "sk-test"},
            ),
            wf_patch,
            gv_patch,
            patch(
                "app.api.expressions.execute_llm",
                execute_mock,
            ),
        ):
            result = await _generate_expression(db=db, request=request, current_user=user)
        self.assertEqual(result, "$good.new.path")
        kwargs = execute_mock.await_args.kwargs
        self.assertEqual(kwargs["temperature"], 0.42)
        self.assertIn("Previous expression:", kwargs["user_message"])
        self.assertIn("$bad.old.path", kwargs["user_message"])
        self.assertIn("Path not found", kwargs["user_message"])

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
        wf_patch, gv_patch = self._workflow_and_globals()
        with (
            patch(
                "app.api.expressions.get_accessible_credential",
                AsyncMock(return_value=cred),
            ),
            patch(
                "app.api.expressions.decrypt_config",
                return_value={"api_key": "sk-test"},
            ),
            wf_patch,
            gv_patch,
            patch(
                "app.api.expressions.execute_llm",
                AsyncMock(return_value={"text": "$textInput.body.text"}),
            ),
        ):
            result = await _generate_expression(db=db, request=request, current_user=user)
        self.assertEqual(result, "$textInput.body.text")
