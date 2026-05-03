"""Unit tests for agent node tool connections (canvas nodes as LLM tools)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.services.workflow_executor import WorkflowExecutor


def _make_executor(nodes: dict, edges: list) -> WorkflowExecutor:
    """Minimal WorkflowExecutor with given nodes and edges, no DB."""
    ex = WorkflowExecutor.__new__(WorkflowExecutor)
    ex.nodes = nodes
    ex.edges = edges
    ex.node_results = {}
    return ex


class TestBuildNodeToolSchemas(unittest.TestCase):
    def test_builds_schema_from_agent_provided_fields(self) -> None:
        agent_id = "agent-1"
        http_id = "http-1"
        nodes = {
            agent_id: {"type": "agent", "data": {"label": "My Agent"}},
            http_id: {
                "type": "http",
                "data": {
                    "label": "Fetch Data",
                    "curl": "curl https://fixed.com",
                    "agentProvidedFields": ["curl"],
                },
            },
        }
        edges = [{"source": http_id, "target": agent_id, "targetHandle": "tool-input"}]
        ex = _make_executor(nodes, edges)

        schemas = ex._build_node_tool_schemas(agent_id)

        self.assertEqual(len(schemas), 1)
        self.assertEqual(schemas[0]["name"], "fetch_data")
        self.assertEqual(schemas[0]["_source"], "node_tool")
        self.assertEqual(schemas[0]["_node_id"], http_id)
        self.assertIn("curl", schemas[0]["parameters"]["properties"])
        self.assertEqual(schemas[0]["parameters"]["required"], ["curl"])

    def test_empty_agent_provided_fields_creates_parameterless_tool(self) -> None:
        agent_id = "agent-1"
        code_id = "code-1"
        nodes = {
            agent_id: {"type": "agent", "data": {"label": "Agent"}},
            code_id: {"type": "code", "data": {"label": "Run Script", "agentProvidedFields": []}},
        }
        edges = [{"source": code_id, "target": agent_id, "targetHandle": "tool-input"}]
        ex = _make_executor(nodes, edges)

        schemas = ex._build_node_tool_schemas(agent_id)

        self.assertEqual(len(schemas), 1)
        self.assertEqual(schemas[0]["parameters"]["properties"], {})
        self.assertEqual(schemas[0]["parameters"]["required"], [])

    def test_ignores_non_tool_input_edges(self) -> None:
        agent_id = "agent-1"
        http_id = "http-1"
        nodes = {
            agent_id: {"type": "agent", "data": {"label": "Agent"}},
            http_id: {"type": "http", "data": {"label": "HTTP", "agentProvidedFields": ["curl"]}},
        }
        edges = [{"source": http_id, "target": agent_id, "targetHandle": "input"}]
        ex = _make_executor(nodes, edges)

        schemas = ex._build_node_tool_schemas(agent_id)
        self.assertEqual(schemas, [])

    def test_name_collision_adds_numeric_suffix(self) -> None:
        agent_id = "agent-1"
        nodes = {
            agent_id: {"type": "agent", "data": {}},
            "http-1": {"type": "http", "data": {"label": "Fetch Data", "agentProvidedFields": []}},
            "http-2": {"type": "http", "data": {"label": "Fetch Data", "agentProvidedFields": []}},
        }
        edges = [
            {"source": "http-1", "target": agent_id, "targetHandle": "tool-input"},
            {"source": "http-2", "target": agent_id, "targetHandle": "tool-input"},
        ]
        ex = _make_executor(nodes, edges)

        schemas = ex._build_node_tool_schemas(agent_id)
        names = [s["name"] for s in schemas]
        self.assertEqual(len(set(names)), 2)
        self.assertIn("fetch_data", names)
        self.assertIn("fetch_data_2", names)

    def test_missing_node_is_skipped(self) -> None:
        agent_id = "agent-1"
        nodes = {agent_id: {"type": "agent", "data": {}}}
        edges = [{"source": "ghost-node", "target": agent_id, "targetHandle": "tool-input"}]
        ex = _make_executor(nodes, edges)

        schemas = ex._build_node_tool_schemas(agent_id)
        self.assertEqual(schemas, [])


class TestExecuteNodeTool(unittest.TestCase):
    def _make_executor_with_execute(
        self, nodes: dict, edges: list, node_results: dict | None = None
    ) -> WorkflowExecutor:
        ex = _make_executor(nodes, edges)
        ex.node_results = node_results or {}
        ex.check_cancelled = MagicMock()
        return ex

    def test_merges_agent_args_into_node_data(self) -> None:
        from app.services.workflow_executor import NodeResult

        http_id = "http-1"
        nodes = {
            http_id: {
                "type": "http",
                "data": {
                    "label": "Fetch",
                    "curl": "curl https://fixed.com",
                    "agentProvidedFields": ["curl"],
                    "active": True,
                },
            }
        }
        ex = self._make_executor_with_execute(nodes, [])

        captured_data: list[dict] = []

        def fake_execute_node(node_id: str, inputs: dict, **kwargs) -> NodeResult:
            captured_data.append(dict(ex.nodes[node_id]["data"]))
            return NodeResult(
                node_id=node_id,
                node_label="Fetch",
                node_type="http",
                status="success",
                output={"body": "ok"},
                execution_time_ms=10.0,
            )

        ex.execute_node = fake_execute_node  # type: ignore[assignment]

        tool_def = {"_source": "node_tool", "_node_id": http_id}
        result = ex._execute_node_tool(tool_def, {"curl": "curl https://dynamic.com"})

        self.assertEqual(captured_data[0]["curl"], "curl https://dynamic.com")
        self.assertEqual(result, {"body": "ok"})
        # Original data restored after execution
        self.assertEqual(ex.nodes[http_id]["data"]["curl"], "curl https://fixed.com")

    def test_returns_error_dict_on_node_failure(self) -> None:
        from app.services.workflow_executor import NodeResult

        http_id = "http-1"
        nodes = {http_id: {"type": "http", "data": {"label": "Fetch", "agentProvidedFields": []}}}
        ex = self._make_executor_with_execute(nodes, [])

        def fake_execute_node(node_id: str, inputs: dict, **kwargs) -> NodeResult:
            return NodeResult(
                node_id=node_id,
                node_label="Fetch",
                node_type="http",
                status="error",
                output={},
                execution_time_ms=5.0,
                error="Connection refused",
            )

        ex.execute_node = fake_execute_node  # type: ignore[assignment]

        tool_def = {"_source": "node_tool", "_node_id": http_id}
        result = ex._execute_node_tool(tool_def, {})

        self.assertIn("error", result)
        self.assertEqual(result["error"], "Connection refused")

    def test_returns_error_when_node_not_found(self) -> None:
        ex = _make_executor({}, [])
        tool_def = {"_source": "node_tool", "_node_id": "ghost"}
        result = ex._execute_node_tool(tool_def, {})
        self.assertIn("error", result)

    def test_restores_original_data_on_exception(self) -> None:
        http_id = "http-1"
        original_curl = "curl https://original.com"
        nodes = {
            http_id: {
                "type": "http",
                "data": {
                    "label": "Fetch",
                    "curl": original_curl,
                    "agentProvidedFields": ["curl"],
                },
            }
        }
        ex = self._make_executor_with_execute(nodes, [])

        def boom(node_id: str, inputs: dict, **kwargs):  # type: ignore[misc]
            raise RuntimeError("simulated crash")

        ex.execute_node = boom  # type: ignore[assignment]

        tool_def = {"_source": "node_tool", "_node_id": http_id}
        with self.assertRaises(RuntimeError):
            ex._execute_node_tool(tool_def, {"curl": "curl https://other.com"})

        self.assertEqual(ex.nodes[http_id]["data"]["curl"], original_curl)
