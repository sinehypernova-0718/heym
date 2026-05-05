import unittest

from app.db.models import MCPServer, MCPServerWorkflow


class MCPServerModelImportTests(unittest.TestCase):
    def test_mcp_server_model_importable(self) -> None:
        assert MCPServer.__tablename__ == "mcp_servers"

    def test_mcp_server_workflow_model_importable(self) -> None:
        assert MCPServerWorkflow.__tablename__ == "mcp_server_workflows"
