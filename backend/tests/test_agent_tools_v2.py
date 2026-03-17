"""Tests for the agent tool executor in app.services.agent_tools_v2."""

from __future__ import annotations

from unittest.mock import MagicMock, patch  # noqa: F401 — patch used via patch.dict

from app.services.agent_tools_v2 import TOOL_DEFINITIONS, execute_tool


class TestToolDefinitions:
    """Tests for the TOOL_DEFINITIONS list structure and completeness."""

    def test_seventeen_tools_defined(self) -> None:
        """TOOL_DEFINITIONS must contain exactly 17 tools."""
        assert len(TOOL_DEFINITIONS) == 17

    def test_each_tool_has_name(self) -> None:
        """Every tool definition must have a function.name field."""
        for tool in TOOL_DEFINITIONS:
            assert "function" in tool
            assert "name" in tool["function"]
            assert isinstance(tool["function"]["name"], str)
            assert len(tool["function"]["name"]) > 0

    def test_each_tool_has_description(self) -> None:
        """Every tool definition must have a function.description field."""
        for tool in TOOL_DEFINITIONS:
            assert "description" in tool["function"]
            assert isinstance(tool["function"]["description"], str)
            assert len(tool["function"]["description"]) > 0

    def test_each_tool_has_parameters(self) -> None:
        """Every tool definition must have a function.parameters field."""
        for tool in TOOL_DEFINITIONS:
            assert "parameters" in tool["function"]
            params = tool["function"]["parameters"]
            assert params["type"] == "object"
            assert "properties" in params

    def test_all_expected_tool_names_present(self) -> None:
        """All 17 expected tool names must be present."""
        expected_names = {
            "find_node", "get_node", "get_dependencies", "get_dependents",
            "get_variable_timeline", "trace_variable", "get_logic_pack",
            "get_flow", "find_gaps", "run_cypher", "project_vfs",
            "create_node", "update_node", "deprecate_node",
            "add_edge", "remove_edge", "create_flow",
        }
        actual_names = {tool["function"]["name"] for tool in TOOL_DEFINITIONS}
        assert actual_names == expected_names

    def test_all_tools_have_type_function(self) -> None:
        """Every tool must have type='function'."""
        for tool in TOOL_DEFINITIONS:
            assert tool["type"] == "function"

    def test_required_params_are_lists(self) -> None:
        """Required fields in parameters must be lists of strings."""
        for tool in TOOL_DEFINITIONS:
            params = tool["function"]["parameters"]
            if "required" in params:
                assert isinstance(params["required"], list)
                for req in params["required"]:
                    assert isinstance(req, str)


class TestExecuteTool:
    """Tests for the execute_tool dispatcher."""

    def test_unknown_tool_returns_error(self) -> None:
        """Calling an unknown tool name must return an error dict."""
        result = execute_tool("nonexistent_tool", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]
        assert "nonexistent_tool" in result["error"]

    def test_unknown_tool_does_not_raise(self) -> None:
        """Unknown tool must not raise an exception."""
        result = execute_tool("totally_fake", {"foo": "bar"})
        assert isinstance(result, dict)

    def test_find_node_dispatches_to_handler(self) -> None:
        """execute_tool('find_node', ...) must dispatch to the find_node handler."""
        mock_handler = MagicMock(return_value={"nodes": []})
        with patch.dict("app.services.agent_tools_v2._TOOL_HANDLERS", {"find_node": mock_handler}):
            result = execute_tool("find_node", {"query": "add"})
        mock_handler.assert_called_once_with({"query": "add"})
        assert result == {"nodes": []}

    def test_get_node_dispatches_to_handler(self) -> None:
        """execute_tool('get_node', ...) must dispatch to the get_node handler."""
        mock_handler = MagicMock(return_value={"node": {"id": "abc"}})
        with patch.dict("app.services.agent_tools_v2._TOOL_HANDLERS", {"get_node": mock_handler}):
            result = execute_tool("get_node", {"node_id": "abc"})
        mock_handler.assert_called_once_with({"node_id": "abc"})
        assert result == {"node": {"id": "abc"}}

    def test_create_node_dispatches_to_handler(self) -> None:
        """execute_tool('create_node', ...) must dispatch to the create_node handler."""
        mock_handler = MagicMock(return_value={"node": {"id": "new-1"}})
        args = {"name": "foo", "kind": "function", "source_text": "def foo(): pass"}
        with patch.dict("app.services.agent_tools_v2._TOOL_HANDLERS", {"create_node": mock_handler}):
            result = execute_tool("create_node", args)
        mock_handler.assert_called_once_with(args)
        assert result == {"node": {"id": "new-1"}}

    def test_deprecate_node_dispatches(self) -> None:
        """execute_tool('deprecate_node', ...) must dispatch correctly."""
        mock_handler = MagicMock(return_value={"status": "deprecated", "node_id": "n1"})
        with patch.dict("app.services.agent_tools_v2._TOOL_HANDLERS", {"deprecate_node": mock_handler}):
            result = execute_tool("deprecate_node", {"node_id": "n1"})
        mock_handler.assert_called_once_with({"node_id": "n1"})
        assert result["status"] == "deprecated"

    def test_add_edge_dispatches(self) -> None:
        """execute_tool('add_edge', ...) must dispatch correctly."""
        mock_handler = MagicMock(return_value={"edge": {"type": "CALLS"}})
        args = {"source": "n1", "target": "n2", "type": "CALLS"}
        with patch.dict("app.services.agent_tools_v2._TOOL_HANDLERS", {"add_edge": mock_handler}):
            result = execute_tool("add_edge", args)
        mock_handler.assert_called_once_with(args)
        assert result["edge"]["type"] == "CALLS"

    def test_create_flow_dispatches(self) -> None:
        """execute_tool('create_flow', ...) must dispatch correctly."""
        mock_handler = MagicMock(return_value={"flow": {"id": "f1"}})
        args = {"name": "test-flow", "node_ids": ["n1"], "entry_point": "n1"}
        with patch.dict("app.services.agent_tools_v2._TOOL_HANDLERS", {"create_flow": mock_handler}):
            result = execute_tool("create_flow", args)
        mock_handler.assert_called_once_with(args)
        assert result["flow"]["id"] == "f1"

    def test_handler_exception_returns_error_dict(self) -> None:
        """If a handler raises, execute_tool must catch it and return an error dict."""
        with patch.dict("app.services.agent_tools_v2._TOOL_HANDLERS", {"boom": MagicMock(side_effect=RuntimeError("fail"))}):
            result = execute_tool("boom", {})
        assert "error" in result
        assert "fail" in result["error"]

    def test_run_cypher_dispatches(self) -> None:
        """execute_tool('run_cypher', ...) must dispatch to the cypher handler."""
        mock_handler = MagicMock(return_value={"result_set": [["node-1"]]})
        with patch.dict("app.services.agent_tools_v2._TOOL_HANDLERS", {"run_cypher": mock_handler}):
            result = execute_tool("run_cypher", {"query": "MATCH (n) RETURN n LIMIT 1"})
        mock_handler.assert_called_once()
        assert result["result_set"] == [["node-1"]]

    def test_project_vfs_dispatches(self) -> None:
        """execute_tool('project_vfs', ...) must dispatch correctly."""
        mock_handler = MagicMock(return_value={"source": "def foo(): pass"})
        with patch.dict("app.services.agent_tools_v2._TOOL_HANDLERS", {"project_vfs": mock_handler}):
            result = execute_tool("project_vfs", {"scope": "app.core"})
        mock_handler.assert_called_once_with({"scope": "app.core"})
        assert "source" in result

    def test_find_gaps_dispatches(self) -> None:
        """execute_tool('find_gaps', ...) must dispatch correctly."""
        mock_handler = MagicMock(return_value={"nodes": []})
        with patch.dict("app.services.agent_tools_v2._TOOL_HANDLERS", {"find_gaps": mock_handler}):
            result = execute_tool("find_gaps", {"analysis_type": "dead_ends"})
        mock_handler.assert_called_once_with({"analysis_type": "dead_ends"})
        assert result == {"nodes": []}
