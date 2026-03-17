"""Pydantic models for the Code-as-Data graph schema (TICKET-802).

Defines strict models for LogicNode, Variable, Edge, Flow, and all
response/request types for the 800-series API.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


# --- Enums ---


class LogicNodeKind(str, enum.Enum):
    """Valid kinds for a LogicNode."""

    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    CONSTANT = "constant"
    TYPE_ALIAS = "type_alias"
    FLOW_FUNCTION = "flow_function"


class EdgeType(str, enum.Enum):
    """Valid edge types in the graph."""

    # LogicNode -> LogicNode
    CALLS = "CALLS"
    DEPENDS_ON = "DEPENDS_ON"
    IMPLEMENTS = "IMPLEMENTS"
    VALIDATES = "VALIDATES"
    TRANSFORMS = "TRANSFORMS"
    INHERITS = "INHERITS"
    MEMBER_OF = "MEMBER_OF"

    # LogicNode -> Variable
    ASSIGNS = "ASSIGNS"
    MUTATES = "MUTATES"
    READS = "READS"
    RETURNS = "RETURNS"

    # Variable -> Variable
    PASSES_TO = "PASSES_TO"
    FEEDS = "FEEDS"

    # Flow edges
    STEP_OF = "STEP_OF"
    CONTAINS_FLOW = "CONTAINS_FLOW"
    PROMOTED_TO = "PROMOTED_TO"


class MutationKind(str, enum.Enum):
    """Kinds of in-place mutation."""

    METHOD_CALL = "method_call"
    SUBSCRIPT_ASSIGN = "subscript_assign"
    ATTR_ASSIGN = "attr_assign"
    AUGMENTED_ASSIGN = "augmented_assign"


class ParamKind(str, enum.Enum):
    """Kinds of function parameters."""

    POSITIONAL_ONLY = "positional_only"
    POSITIONAL_OR_KEYWORD = "positional_or_keyword"
    KEYWORD_ONLY = "keyword_only"
    VAR_POSITIONAL = "var_positional"
    VAR_KEYWORD = "var_keyword"


class NodeStatus(str, enum.Enum):
    """Status of a LogicNode."""

    ACTIVE = "active"
    DEPRECATED = "deprecated"


class FeedVia(str, enum.Enum):
    """How one variable feeds into another."""

    ASSIGNMENT = "assignment"
    MUTATION_ARG = "mutation_arg"
    CALL_ARG = "call_arg"
    CALL_RETURN = "call_return"


# --- Embedded Models ---


class ParamSpec(BaseModel):
    """Parameter specification for a function/method."""

    name: str
    type_hint: str | None = None
    default: str | None = None
    kind: ParamKind = ParamKind.POSITIONAL_OR_KEYWORD


# --- LogicNode Models ---


class LogicNodeCreate(BaseModel):
    """Input model for creating a LogicNode."""

    name: str
    kind: LogicNodeKind
    source_text: str
    module_path: str = ""
    semantic_intent: str | None = None
    docstring: str | None = None
    decorators: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    class_id: str | None = None
    derived_from: str | None = None


class LogicNodeUpdate(BaseModel):
    """Input model for updating a LogicNode."""

    source_text: str | None = None
    semantic_intent: str | None = None
    tags: list[str] | None = None
    docstring: str | None = None


class LogicNodeResponse(BaseModel):
    """Output model for a LogicNode with all computed fields."""

    id: str
    ast_hash: str
    kind: LogicNodeKind
    name: str
    module_path: str
    signature: str
    source_text: str
    semantic_intent: str | None = None
    docstring: str | None = None
    decorators: list[str] = Field(default_factory=list)
    params: list[ParamSpec] = Field(default_factory=list)
    return_type: str | None = None
    tags: list[str] = Field(default_factory=list)
    class_id: str | None = None
    derived_from: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    status: NodeStatus = NodeStatus.ACTIVE
    created_at: datetime
    updated_at: datetime

    # Metadata returned alongside the response
    warnings: list[str] = Field(default_factory=list)


# --- Variable Models ---


class VariableResponse(BaseModel):
    """Output model for a Variable node."""

    id: str
    name: str
    scope: str
    origin_node_id: str
    origin_line: int | None = None
    type_hint: str | None = None
    is_parameter: bool
    is_attribute: bool
    created_at: datetime


# --- Edge Models ---


class EdgeCreate(BaseModel):
    """Input model for creating an edge."""

    source_id: str
    target_id: str
    edge_type: EdgeType
    properties: dict[str, Any] = Field(default_factory=dict)


class EdgeResponse(BaseModel):
    """Output model for an edge."""

    type: EdgeType
    source: str
    target: str
    properties: dict[str, Any] = Field(default_factory=dict)


# --- Flow Models ---


class FlowCreate(BaseModel):
    """Input model for creating a Flow."""

    name: str
    description: str | None = None
    node_ids: list[str]
    entry_point: str
    exit_points: list[str] = Field(default_factory=list)
    sub_flow_ids: list[str] = Field(default_factory=list)
    parent_flow_id: str | None = None


class FlowUpdate(BaseModel):
    """Input model for updating a Flow."""

    name: str | None = None
    description: str | None = None
    node_ids: list[str] | None = None
    entry_point: str | None = None
    exit_points: list[str] | None = None


class FlowResponse(BaseModel):
    """Output model for a Flow."""

    id: str
    name: str
    description: str | None = None
    entry_point: str
    exit_points: list[str] = Field(default_factory=list)
    node_ids: list[str]
    sub_flow_ids: list[str] = Field(default_factory=list)
    parent_flow_id: str | None = None
    promoted_node_id: str | None = None
    created_at: datetime
    updated_at: datetime


class FlowHierarchy(BaseModel):
    """Recursive response model for flow hierarchy queries."""

    flow: FlowResponse
    children: list[FlowHierarchy] = Field(default_factory=list)
    depth: int = 0


# --- Timeline & Logic Pack Models ---


class MutationTimeline(BaseModel):
    """Response model for the variable mutation timeline query."""

    variable: VariableResponse
    origin: LogicNodeResponse | None = None
    assigns: list[EdgeResponse] = Field(default_factory=list)
    mutations: list[EdgeResponse] = Field(default_factory=list)
    reads: list[EdgeResponse] = Field(default_factory=list)
    returns: list[EdgeResponse] = Field(default_factory=list)
    passes: list[EdgeResponse] = Field(default_factory=list)
    feeds: list[EdgeResponse] = Field(default_factory=list)
    terminal: LogicNodeResponse | None = None


class LogicPack(BaseModel):
    """Pre-processed subgraph for LLM consumption."""

    nodes: list[LogicNodeResponse] = Field(default_factory=list)
    edges: list[EdgeResponse] = Field(default_factory=list)
    snippets: dict[str, str] = Field(default_factory=dict)


# --- Gap Analysis Models ---


class GapReport(BaseModel):
    """Response model for gap analysis."""

    dead_ends: list[LogicNodeResponse] = Field(default_factory=list)
    orphans: list[LogicNodeResponse] = Field(default_factory=list)
    missing_error_handling: list[dict[str, Any]] = Field(default_factory=list)
    circular_deps: list[list[str]] = Field(default_factory=list)
    untested_mutations: list[dict[str, Any]] = Field(default_factory=list)


# --- Serialization Models ---


class GraphMeta(BaseModel):
    """Meta information for graph serialization."""

    version: str = "1.0.0"
    schema_version: int = 1
    graph_name: str = "bumblebee"
    node_count: int = 0
    variable_count: int = 0
    edge_count: int = 0
    flow_count: int = 0
    last_serialized: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_language: str = "python"
    source_root: str = ""


class SemanticDiff(BaseModel):
    """Result of comparing two graph states."""

    added_nodes: list[LogicNodeResponse] = Field(default_factory=list)
    removed_nodes: list[LogicNodeResponse] = Field(default_factory=list)
    modified_nodes: list[dict[str, Any]] = Field(default_factory=list)
    added_edges: list[EdgeResponse] = Field(default_factory=list)
    removed_edges: list[EdgeResponse] = Field(default_factory=list)
    added_variables: list[VariableResponse] = Field(default_factory=list)
    removed_variables: list[VariableResponse] = Field(default_factory=list)


# Enable self-referencing model
FlowHierarchy.model_rebuild()
