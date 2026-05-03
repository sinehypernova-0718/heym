"""Unit tests for agent node tool connections (canvas nodes as LLM tools)."""

from __future__ import annotations

import unittest

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
