"""Tests for Pydantic models and enums in app.models.logic_models."""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.logic_models import (
    EdgeCreate,
    EdgeResponse,
    EdgeType,
    FeedVia,
    FlowCreate,
    FlowHierarchy,
    FlowResponse,
    LogicNodeCreate,
    LogicNodeKind,
    LogicNodeResponse,
    MutationKind,
    NodeStatus,
    ParamKind,
    SemanticDiff,
)


class TestEnumCoverage:
    """Tests verifying all enum members are defined with expected values."""

    def test_logic_node_kind_values(self) -> None:
        """LogicNodeKind must have all six expected members."""
        expected = {"function", "method", "class", "constant", "type_alias", "flow_function"}
        actual = {member.value for member in LogicNodeKind}
        assert actual == expected

    def test_edge_type_values(self) -> None:
        """EdgeType must have all 16 expected members."""
        expected = {
            "CALLS", "DEPENDS_ON", "IMPLEMENTS", "VALIDATES", "TRANSFORMS",
            "INHERITS", "MEMBER_OF", "ASSIGNS", "MUTATES", "READS", "RETURNS",
            "PASSES_TO", "FEEDS", "STEP_OF", "CONTAINS_FLOW", "PROMOTED_TO",
        }
        actual = {member.value for member in EdgeType}
        assert actual == expected

    def test_node_status_values(self) -> None:
        """NodeStatus must have active and deprecated."""
        expected = {"active", "deprecated"}
        actual = {member.value for member in NodeStatus}
        assert actual == expected

    def test_mutation_kind_values(self) -> None:
        """MutationKind must have all four mutation types."""
        expected = {"method_call", "subscript_assign", "attr_assign", "augmented_assign"}
        actual = {member.value for member in MutationKind}
        assert actual == expected

    def test_param_kind_values(self) -> None:
        """ParamKind must have all five parameter kinds."""
        expected = {"positional_only", "positional_or_keyword", "keyword_only", "var_positional", "var_keyword"}
        actual = {member.value for member in ParamKind}
        assert actual == expected

    def test_feed_via_values(self) -> None:
        """FeedVia must have all four feed methods."""
        expected = {"assignment", "mutation_arg", "call_arg", "call_return"}
        actual = {member.value for member in FeedVia}
        assert actual == expected


class TestModelValidation:
    """Tests for Pydantic model creation and validation."""

    def test_logic_node_create_minimal(self) -> None:
        """LogicNodeCreate must accept minimal required fields."""
        node = LogicNodeCreate(
            name="add",
            kind=LogicNodeKind.FUNCTION,
            source_text="def add(a, b): return a + b",
        )
        assert node.name == "add"
        assert node.kind == LogicNodeKind.FUNCTION
        assert node.source_text == "def add(a, b): return a + b"
        assert node.module_path == ""
        assert node.semantic_intent is None
        assert node.decorators == []
        assert node.tags == []

    def test_logic_node_response_all_fields(self) -> None:
        """LogicNodeResponse must accept and store all fields."""
        now = datetime.now(timezone.utc)
        node = LogicNodeResponse(
            id="abc-123",
            ast_hash="sha256hex",
            kind=LogicNodeKind.METHOD,
            name="calculate",
            module_path="app.services.calc",
            signature="def calculate(self, x: int) -> int",
            source_text="def calculate(self, x: int) -> int:\n    return x * 2",
            semantic_intent="Doubles the input",
            docstring="Double x.",
            decorators=["staticmethod"],
            params=[],
            return_type="int",
            tags=["math", "pure"],
            class_id="class-uuid",
            derived_from="original-uuid",
            start_line=10,
            end_line=12,
            status=NodeStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        assert node.id == "abc-123"
        assert node.kind == LogicNodeKind.METHOD
        assert node.tags == ["math", "pure"]
        assert node.start_line == 10
        assert node.status == NodeStatus.ACTIVE

    def test_edge_create(self) -> None:
        """EdgeCreate must accept source, target, and edge_type."""
        edge = EdgeCreate(
            source_id="node-1",
            target_id="node-2",
            edge_type=EdgeType.CALLS,
        )
        assert edge.source_id == "node-1"
        assert edge.target_id == "node-2"
        assert edge.edge_type == EdgeType.CALLS
        assert edge.properties == {}

    def test_edge_create_with_properties(self) -> None:
        """EdgeCreate must accept optional properties dict."""
        edge = EdgeCreate(
            source_id="a",
            target_id="b",
            edge_type=EdgeType.MUTATES,
            properties={"line": 42, "kind": "method_call"},
        )
        assert edge.properties["line"] == 42

    def test_flow_create(self) -> None:
        """FlowCreate must accept required fields and default optional ones."""
        flow = FlowCreate(
            name="user-registration",
            node_ids=["n1", "n2", "n3"],
            entry_point="n1",
        )
        assert flow.name == "user-registration"
        assert flow.node_ids == ["n1", "n2", "n3"]
        assert flow.entry_point == "n1"
        assert flow.exit_points == []
        assert flow.sub_flow_ids == []
        assert flow.parent_flow_id is None

    def test_flow_create_with_all_fields(self) -> None:
        """FlowCreate must accept all optional fields."""
        flow = FlowCreate(
            name="checkout",
            description="End-to-end checkout flow",
            node_ids=["n1", "n2"],
            entry_point="n1",
            exit_points=["n2"],
            sub_flow_ids=["sub1"],
            parent_flow_id="parent1",
        )
        assert flow.description == "End-to-end checkout flow"
        assert flow.sub_flow_ids == ["sub1"]
        assert flow.parent_flow_id == "parent1"


class TestSemanticDiff:
    """Tests for SemanticDiff model defaults."""

    def test_default_empty_lists(self) -> None:
        """SemanticDiff must default all list fields to empty."""
        diff = SemanticDiff()
        assert diff.added_nodes == []
        assert diff.removed_nodes == []
        assert diff.modified_nodes == []
        assert diff.added_edges == []
        assert diff.removed_edges == []
        assert diff.added_variables == []
        assert diff.removed_variables == []


class TestFlowHierarchy:
    """Tests for FlowHierarchy self-referencing model."""

    def test_self_referencing_works(self) -> None:
        """FlowHierarchy must allow nesting child FlowHierarchy instances."""
        now = datetime.now(timezone.utc)
        child_flow = FlowResponse(
            id="child-1",
            name="sub-flow",
            entry_point="n2",
            node_ids=["n2"],
            created_at=now,
            updated_at=now,
        )
        parent_flow = FlowResponse(
            id="parent-1",
            name="main-flow",
            entry_point="n1",
            node_ids=["n1", "n2"],
            created_at=now,
            updated_at=now,
        )
        child_hierarchy = FlowHierarchy(flow=child_flow, depth=1)
        parent_hierarchy = FlowHierarchy(flow=parent_flow, children=[child_hierarchy], depth=0)

        assert parent_hierarchy.depth == 0
        assert len(parent_hierarchy.children) == 1
        assert parent_hierarchy.children[0].flow.id == "child-1"
        assert parent_hierarchy.children[0].depth == 1

    def test_default_empty_children(self) -> None:
        """FlowHierarchy must default children to empty list."""
        now = datetime.now(timezone.utc)
        flow = FlowResponse(
            id="f1",
            name="solo",
            entry_point="n1",
            node_ids=["n1"],
            created_at=now,
            updated_at=now,
        )
        hierarchy = FlowHierarchy(flow=flow)
        assert hierarchy.children == []
        assert hierarchy.depth == 0


class TestEdgeResponse:
    """Tests for EdgeResponse model."""

    def test_edge_response_minimal(self) -> None:
        """EdgeResponse with minimal fields."""
        edge = EdgeResponse(
            type=EdgeType.CALLS,
            source="src-id",
            target="tgt-id",
        )
        assert edge.type == EdgeType.CALLS
        assert edge.properties == {}
