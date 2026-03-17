"""Tests for round-trip serialize/deserialize using mocked graph client."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.deserializer import deserialize_graph
from app.services.serializer import serialize_graph


def make_mock_node(props: dict) -> MagicMock:
    """Create a mock graph node with a properties dict."""
    node = MagicMock()
    node.properties = props
    return node


def _make_query_dispatcher(
    nodes: list[dict] | None = None,
    variables: list[dict] | None = None,
    edges: list[list] | None = None,
    flows: list[dict] | None = None,
) -> callable:
    """Build a side_effect function that dispatches graph.query calls by query content."""

    def dispatcher(query: str, params: dict | None = None) -> MagicMock:
        result = MagicMock()

        if "LogicNode" in query and "RETURN n" in query and "MERGE" not in query:
            rows = [[make_mock_node(n)] for n in (nodes or [])]
            result.result_set = rows
        elif "Variable" in query and "RETURN v" in query and "MERGE" not in query:
            rows = [[make_mock_node(v)] for v in (variables or [])]
            result.result_set = rows
        elif "type(r)" in query:
            result.result_set = edges or []
        elif "Flow" in query and "RETURN f" in query and "MERGE" not in query:
            rows = [[make_mock_node(f)] for f in (flows or [])]
            result.result_set = rows
        else:
            result.result_set = []

        return result

    return dispatcher


class TestSerializeGraph:
    """Tests for serialize_graph writing the .bumblebee/ directory structure."""

    @patch("app.services.serializer.get_graph")
    def test_creates_directory_structure(self, mock_get_graph: MagicMock, tmp_path: Path) -> None:
        """Serialization must create nodes/, variables/, edges/, flows/, vfs/ subdirectories."""
        mock_graph = MagicMock()
        mock_graph.query.side_effect = _make_query_dispatcher()
        mock_get_graph.return_value = mock_graph

        serialize_graph(str(tmp_path))

        assert (tmp_path / "nodes").is_dir()
        assert (tmp_path / "variables").is_dir()
        assert (tmp_path / "edges").is_dir()
        assert (tmp_path / "flows").is_dir()
        assert (tmp_path / "vfs").is_dir()

    @patch("app.services.serializer.get_graph")
    def test_meta_json_written_with_correct_counts(self, mock_get_graph: MagicMock, tmp_path: Path) -> None:
        """meta.json must contain correct node/edge/flow counts."""
        nodes = [
            {"id": "node-1", "name": "add", "kind": "function", "source_text": "def add(): pass"},
            {"id": "node-2", "name": "sub", "kind": "function", "source_text": "def sub(): pass"},
        ]
        edges_data: list[list] = [["CALLS", "node-1", "node-2", {}]]

        mock_graph = MagicMock()
        mock_graph.query.side_effect = _make_query_dispatcher(nodes=nodes, edges=edges_data)
        mock_get_graph.return_value = mock_graph

        report = serialize_graph(str(tmp_path))

        meta_path = tmp_path / "meta.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["node_count"] == 2
        assert meta["edge_count"] == 1
        assert meta["flow_count"] == 0
        assert meta["graph_name"] == "bumblebee"
        assert report.nodes_written == 2
        assert report.edges_written == 1

    @patch("app.services.serializer.get_graph")
    def test_node_json_files_contain_expected_fields(self, mock_get_graph: MagicMock, tmp_path: Path) -> None:
        """Each node JSON file must contain the id, name, kind, and source_text fields."""
        nodes = [
            {
                "id": "uuid-abc",
                "name": "process",
                "kind": "function",
                "source_text": "def process(): pass",
                "ast_hash": "hashval",
                "module_path": "app.core",
                "signature": "def process()",
                "tags": "[]",
                "decorators": "[]",
                "params": "[]",
            },
        ]

        mock_graph = MagicMock()
        mock_graph.query.side_effect = _make_query_dispatcher(nodes=nodes)
        mock_get_graph.return_value = mock_graph

        serialize_graph(str(tmp_path))

        node_file = tmp_path / "nodes" / "uuid-abc.json"
        assert node_file.exists()
        data = json.loads(node_file.read_text(encoding="utf-8"))
        assert data["id"] == "uuid-abc"
        assert data["name"] == "process"
        assert data["kind"] == "function"
        assert data["source_text"] == "def process(): pass"

    @patch("app.services.serializer.get_graph")
    def test_edge_manifest_has_correct_entries(self, mock_get_graph: MagicMock, tmp_path: Path) -> None:
        """Edge manifest.json must list all edges with type, source, target."""
        edges_data: list[list] = [
            ["CALLS", "n1", "n2", {}],
            ["DEPENDS_ON", "n2", "n3", {"weight": 1}],
        ]

        mock_graph = MagicMock()
        mock_graph.query.side_effect = _make_query_dispatcher(edges=edges_data)
        mock_get_graph.return_value = mock_graph

        report = serialize_graph(str(tmp_path))

        manifest_path = tmp_path / "edges" / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["edge_count"] == 2
        assert len(manifest["edges"]) == 2
        assert manifest["edges"][0]["type"] == "CALLS"
        assert manifest["edges"][0]["source"] == "n1"
        assert manifest["edges"][1]["type"] == "DEPENDS_ON"
        assert report.edges_written == 2

    @patch("app.services.serializer.get_graph")
    def test_serialization_report_counts(self, mock_get_graph: MagicMock, tmp_path: Path) -> None:
        """SerializationReport must accurately reflect written counts."""
        nodes = [{"id": "n1", "name": "a", "kind": "function", "source_text": "def a(): pass"}]
        variables = [{"id": "v1", "name": "x", "scope": "a.x", "origin_node_id": "n1"}]
        flows = [{"id": "f1", "name": "my-flow", "entry_point": "n1", "node_ids": '["n1"]'}]

        mock_graph = MagicMock()
        mock_graph.query.side_effect = _make_query_dispatcher(
            nodes=nodes, variables=variables, flows=flows
        )
        mock_get_graph.return_value = mock_graph

        report = serialize_graph(str(tmp_path))

        assert report.nodes_written == 1
        assert report.variables_written == 1
        assert report.flows_written == 1


class TestDeserializeGraph:
    """Tests for deserialize_graph loading .bumblebee/ directory into the graph."""

    @patch("app.services.deserializer.get_graph")
    def test_loads_nodes_and_calls_merge(self, mock_get_graph: MagicMock, tmp_path: Path) -> None:
        """Deserializer must call graph.query with MERGE_LOGIC_NODE for each node file."""
        mock_graph = MagicMock()
        mock_get_graph.return_value = mock_graph

        # Create node file
        nodes_dir = tmp_path / "nodes"
        nodes_dir.mkdir(parents=True)
        node_data = {
            "id": "node-42",
            "name": "process",
            "kind": "function",
            "source_text": "def process(): pass",
            "ast_hash": "abc123",
        }
        (nodes_dir / "node-42.json").write_text(json.dumps(node_data), encoding="utf-8")

        # Create meta.json
        meta = {"version": "1.0.0", "schema_version": 1, "node_count": 1, "edge_count": 0}
        (tmp_path / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

        report = deserialize_graph(str(tmp_path))

        assert report.nodes_loaded == 1
        # Verify MERGE_LOGIC_NODE was called (second call after DETACH DELETE)
        merge_calls = [
            call for call in mock_graph.query.call_args_list
            if "MERGE" in str(call) and "LogicNode" in str(call)
        ]
        assert len(merge_calls) == 1

    @patch("app.services.deserializer.get_graph")
    def test_loads_edges_from_manifest(self, mock_get_graph: MagicMock, tmp_path: Path) -> None:
        """Deserializer must load edges from the manifest and call merge queries."""
        mock_graph = MagicMock()
        mock_get_graph.return_value = mock_graph

        edges_dir = tmp_path / "edges"
        edges_dir.mkdir(parents=True)
        manifest = {
            "schema_version": 1,
            "edge_count": 1,
            "edges": [{"type": "CALLS", "source": "n1", "target": "n2", "properties": {}}],
        }
        (edges_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (tmp_path / "meta.json").write_text(json.dumps({"version": "1.0.0"}), encoding="utf-8")

        report = deserialize_graph(str(tmp_path))

        assert report.edges_loaded == 1

    @patch("app.services.deserializer.get_graph")
    def test_loads_variables(self, mock_get_graph: MagicMock, tmp_path: Path) -> None:
        """Deserializer must load variables from grouped JSON files."""
        mock_graph = MagicMock()
        mock_get_graph.return_value = mock_graph

        vars_dir = tmp_path / "variables"
        vars_dir.mkdir(parents=True)
        var_data = {
            "scope": "my_module.func",
            "scope_hash": "abcd1234",
            "variables": [
                {
                    "id": "var-1",
                    "name": "x",
                    "scope": "my_module.func.x",
                    "origin_node_id": "n1",
                    "is_parameter": True,
                    "is_attribute": False,
                },
            ],
        }
        (vars_dir / "var_abcd1234.json").write_text(json.dumps(var_data), encoding="utf-8")
        (tmp_path / "meta.json").write_text(json.dumps({"version": "1.0.0"}), encoding="utf-8")

        report = deserialize_graph(str(tmp_path))

        assert report.variables_loaded == 1

    @patch("app.services.deserializer.get_graph")
    def test_loads_flows(self, mock_get_graph: MagicMock, tmp_path: Path) -> None:
        """Deserializer must load flow files and call MERGE_FLOW."""
        mock_graph = MagicMock()
        mock_get_graph.return_value = mock_graph

        flows_dir = tmp_path / "flows"
        flows_dir.mkdir(parents=True)
        flow_data = {
            "id": "flow-1",
            "name": "checkout",
            "entry_point": "n1",
            "node_ids": ["n1", "n2"],
            "exit_points": ["n2"],
            "sub_flow_ids": [],
        }
        (flows_dir / "flow_checkout.json").write_text(json.dumps(flow_data), encoding="utf-8")
        (tmp_path / "meta.json").write_text(json.dumps({"version": "1.0.0"}), encoding="utf-8")

        report = deserialize_graph(str(tmp_path))

        assert report.flows_loaded == 1

    @patch("app.services.deserializer.get_graph")
    def test_handles_missing_directory_gracefully(self, mock_get_graph: MagicMock, tmp_path: Path) -> None:
        """Deserializer must handle a non-existent directory without raising."""
        mock_graph = MagicMock()
        mock_get_graph.return_value = mock_graph

        report = deserialize_graph(str(tmp_path / "nonexistent"))

        assert len(report.errors) >= 1
        assert "Not a directory" in report.errors[0]
        assert report.nodes_loaded == 0

    @patch("app.services.deserializer.get_graph")
    def test_report_counts_are_correct(self, mock_get_graph: MagicMock, tmp_path: Path) -> None:
        """DeserializationReport must correctly count all loaded entities."""
        mock_graph = MagicMock()
        mock_get_graph.return_value = mock_graph

        # Create two nodes
        nodes_dir = tmp_path / "nodes"
        nodes_dir.mkdir(parents=True)
        for i in range(3):
            node = {"id": f"n{i}", "name": f"func_{i}", "kind": "function", "source_text": f"def func_{i}(): pass"}
            (nodes_dir / f"n{i}.json").write_text(json.dumps(node), encoding="utf-8")

        (tmp_path / "meta.json").write_text(json.dumps({"version": "1.0.0"}), encoding="utf-8")

        report = deserialize_graph(str(tmp_path))

        assert report.nodes_loaded == 3
        assert report.errors == []

    @patch("app.services.deserializer.get_graph")
    def test_empty_directory_returns_zero_counts(self, mock_get_graph: MagicMock, tmp_path: Path) -> None:
        """An empty .bumblebee/ directory must deserialize with zero counts."""
        mock_graph = MagicMock()
        mock_get_graph.return_value = mock_graph

        (tmp_path / "meta.json").write_text(json.dumps({"version": "1.0.0"}), encoding="utf-8")

        report = deserialize_graph(str(tmp_path))

        assert report.nodes_loaded == 0
        assert report.variables_loaded == 0
        assert report.edges_loaded == 0
        assert report.flows_loaded == 0
