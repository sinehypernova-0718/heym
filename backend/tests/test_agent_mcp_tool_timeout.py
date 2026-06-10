"""Unit tests for MCP tool execution timeout resolution in the agent path.

An agent's MCP connection has its own ``timeoutSeconds`` (the "Timeout (s)" field
in the UI). That per-connection timeout must govern the actual ``call_tool``
execution, not just tool discovery/listing. Previously the agent-level
``toolTimeoutSeconds`` was passed to every MCP call, so long-running MCP tools
timed out regardless of the connection's configured timeout.
"""

import unittest
from unittest.mock import patch

from app.services.llm_service import _unified_tool_executor


class UnifiedToolExecutorMcpTimeoutTest(unittest.TestCase):
    """MCP tool execution must honor the connection's own timeoutSeconds."""

    def test_mcp_execution_uses_connection_timeout_over_agent_timeout(self) -> None:
        captured: dict = {}

        def fake_execute_mcp_tool(connection, name, args, timeout_seconds):
            captured["timeout"] = timeout_seconds
            return {"ok": True}

        tool_def = {
            "_source": "mcp",
            "_connection": {
                "transport": "streamable_http",
                "url": "https://mcp.example.com",
                "timeoutSeconds": 1800,
            },
        }

        with patch(
            "app.services.mcp_tool_executor.execute_mcp_tool",
            side_effect=fake_execute_mcp_tool,
        ):
            result = _unified_tool_executor(tool_def, "long_tool", {}, 300.0)

        self.assertEqual(captured["timeout"], 1800.0)
        self.assertEqual(result, {"ok": True})

    def test_mcp_execution_falls_back_to_agent_timeout_when_connection_unset(self) -> None:
        captured: dict = {}

        def fake_execute_mcp_tool(connection, name, args, timeout_seconds):
            captured["timeout"] = timeout_seconds
            return {"ok": True}

        tool_def = {
            "_source": "mcp",
            "_connection": {
                "transport": "streamable_http",
                "url": "https://mcp.example.com",
            },
        }

        with patch(
            "app.services.mcp_tool_executor.execute_mcp_tool",
            side_effect=fake_execute_mcp_tool,
        ):
            _unified_tool_executor(tool_def, "tool", {}, 45.0)

        self.assertEqual(captured["timeout"], 45.0)


if __name__ == "__main__":
    unittest.main()
