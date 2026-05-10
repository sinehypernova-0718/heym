import os
import unittest

from app.services.python_tool_executor import execute_tool


class PythonToolExecutorSecurityTest(unittest.TestCase):
    def test_executes_basic_tool_code(self) -> None:
        code = """
def add(left: int, right: int) -> int:
    return left + right
"""

        result = execute_tool(code, "add", {"left": 2, "right": 3}, 5)

        self.assertEqual(result, 5)

    def test_rejects_object_graph_import_bypass(self) -> None:
        code = """
def leak() -> dict:
    cw = [
        c for c in ().__class__.__base__.__subclasses__()
        if c.__name__ == "catch_warnings"
    ][0]
    imp = cw()._module.__builtins__["__import__"]
    os_mod = imp("os")
    return {"secret": os_mod.environ.get("HEYM_PYTHON_TOOL_SECRET")}
"""

        os.environ["HEYM_PYTHON_TOOL_SECRET"] = "should-not-leak"
        try:
            with self.assertRaisesRegex(ValueError, "restricted Python introspection primitive"):
                execute_tool(code, "leak", {}, 5)
        finally:
            os.environ.pop("HEYM_PYTHON_TOOL_SECRET", None)

    def test_rejects_private_attribute_access(self) -> None:
        code = """
def probe(value):
    return value._private
"""

        with self.assertRaisesRegex(ValueError, "private Python attributes"):
            execute_tool(code, "probe", {"value": {"_private": "x"}}, 5)

    def test_does_not_inherit_backend_environment(self) -> None:
        code = """
def read_env() -> str:
    import json
    return "ok"
"""

        os.environ["HEYM_PYTHON_TOOL_SECRET"] = "should-not-leak"
        try:
            result = execute_tool(code, "read_env", {}, 5)
        finally:
            os.environ.pop("HEYM_PYTHON_TOOL_SECRET", None)

        self.assertEqual(result, "ok")


if __name__ == "__main__":
    unittest.main()
