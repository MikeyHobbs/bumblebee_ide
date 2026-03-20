"""Single source of truth for the Bumblebee graph schema description.

Derives the schema text from logic_models.py enums and Pydantic models
so that prompts never diverge from the actual graph structure.
"""

from __future__ import annotations

from app.models.logic_models import (
    EdgeType,
    FlowResponse,
    LogicNodeKind,
    LogicNodeResponse,
    TypeShapeResponse,
    VariableResponse,
)


# ---------------------------------------------------------------------------
# Derive node labels + properties from Pydantic models
# ---------------------------------------------------------------------------

def _model_fields(model_cls: type, exclude: set[str] | None = None) -> str:
    """Return a comma-separated list of field names from a Pydantic model."""
    exclude = exclude or set()
    return ", ".join(f for f in model_cls.model_fields if f not in exclude)


def _enum_values(enum_cls: type) -> str:
    """Return pipe-separated enum member values."""
    return "|".join(m.value for m in enum_cls)  # type: ignore[attr-defined]


# Edge type → (source_label, target_label, description)
_EDGE_DOCS: dict[str, tuple[str, str, str]] = {
    "CALLS": ("LogicNode", "LogicNode", "function/method calls another"),
    "DEPENDS_ON": ("LogicNode", "LogicNode", "general dependency"),
    "IMPLEMENTS": ("LogicNode", "LogicNode", "implements an interface/protocol"),
    "VALIDATES": ("LogicNode", "LogicNode", "validates input for another"),
    "TRANSFORMS": ("LogicNode", "LogicNode", "transforms data for another"),
    "INHERITS": ("LogicNode", "LogicNode", "class inherits from parent"),
    "MEMBER_OF": ("LogicNode", "LogicNode", "method belongs to class"),
    "ASSIGNS": ("LogicNode", "Variable", "function assigns a value to variable"),
    "MUTATES": ("LogicNode", "Variable", "function mutates a variable"),
    "READS": ("LogicNode", "Variable", "function reads a variable"),
    "RETURNS": ("LogicNode", "Variable", "function returns a variable"),
    "PASSES_TO": ("Variable", "Variable", "data flow: argument passed to callee parameter"),
    "FEEDS": ("Variable", "Variable", "intra-function: read feeds into assignment"),
    "HAS_SHAPE": ("Variable", "TypeShape", "variable has a structural type shape"),
    "ACCEPTS": ("LogicNode", "TypeShape", "function parameter accepts this shape"),
    "PRODUCES": ("LogicNode", "TypeShape", "function produces this shape"),
    "COMPATIBLE_WITH": ("TypeShape", "TypeShape", "structural type compatibility"),
    "STEP_OF": ("LogicNode", "Flow", "function is a step in a flow"),
    "CONTAINS_FLOW": ("Flow", "Flow", "parent flow contains sub-flow"),
    "PROMOTED_TO": ("Flow", "LogicNode", "flow promoted to a logic node"),
}


def _build_graph_schema() -> str:
    """Build the schema text from models — called once at import time."""
    # Node labels
    logic_node_props = _model_fields(LogicNodeResponse, exclude={"warnings"})
    variable_props = _model_fields(VariableResponse)
    typeshape_props = _model_fields(TypeShapeResponse)
    flow_props = _model_fields(FlowResponse)
    kind_values = _enum_values(LogicNodeKind)

    lines = [
        "Node Labels and Properties:",
        "",
        f"- LogicNode: kind ({kind_values}), {logic_node_props}",
        f"- Variable: {variable_props}",
        f"- TypeShape: {typeshape_props}",
        f"- Flow: {flow_props}",
        "",
        "Edge Types (source -> target):",
    ]

    # Edges — iterate over the EdgeType enum so new edges auto-appear
    for member in EdgeType:
        doc = _EDGE_DOCS.get(member.value)
        if doc:
            src, tgt, desc = doc
            lines.append(f"- {member.value}: {src} -> {tgt} ({desc})")
        else:
            lines.append(f"- {member.value}")

    lines.extend([
        "",
        "CRITICAL schema rules:",
        "- All code entities use :LogicNode with a 'kind' property. There are NO separate labels.",
        "- Node names are module-qualified: 'services.register_user', 'ingestion_flow.run'.",
        "  ALWAYS use CONTAINS for name matching, never exact match.",
        "- Variable names include their scope: 'ingestion_flow.run.parsed'.",
        "- Variable.scope holds the owning function name: Variable {scope: 'ingestion_flow.run'}.",
    ])

    return "\n".join(lines)


GRAPH_SCHEMA = _build_graph_schema()


# ---------------------------------------------------------------------------
# Few-shot examples — manually curated, tested against live data
# (see tests/test_cypher_examples.py)
# ---------------------------------------------------------------------------

FEW_SHOT_EXAMPLES = """
Examples of natural language questions and their Cypher translations:

1. "What does register_user call?"
   MATCH (f:LogicNode)-[:CALLS]->(g:LogicNode)
   WHERE f.name CONTAINS 'register_user'
   RETURN f, g

2. "What variables does matrix_flatten mutate?"
   MATCH (f:LogicNode)-[:MUTATES]->(v:Variable)
   WHERE f.name CONTAINS 'matrix_flatten'
   RETURN f, v

3. "Show the inheritance tree"
   MATCH (child:LogicNode)-[:INHERITS]->(parent:LogicNode)
   RETURN child, parent

4. "What methods belong to OrderRepository?"
   MATCH (m:LogicNode)-[:MEMBER_OF]->(c:LogicNode {kind: 'class'})
   WHERE c.name CONTAINS 'OrderRepository'
   RETURN m, c

5. "Trace data flow from run"
   MATCH (caller:LogicNode)-[:CALLS]->(callee:LogicNode),
         (v:Variable)-[:PASSES_TO]->(p:Variable)
   WHERE caller.name CONTAINS 'run'
     AND v.scope = caller.name
     AND p.scope = callee.name
   RETURN caller, callee

6. "What functions accept an Event type?"
   MATCH (fn:LogicNode)-[:ACCEPTS]->(ts:TypeShape)
   WHERE ts.base_type CONTAINS 'Event'
   RETURN fn

7. "Show cross-file calls"
   MATCH (a:LogicNode)-[:CALLS]->(b:LogicNode)
   WHERE a.module_path <> b.module_path
   RETURN a, b LIMIT 20

8. "Functions with high fan-out"
   MATCH (n:LogicNode)-[r:CALLS]->()
   WITH n, count(r) AS calls
   WHERE calls > 2
   RETURN n ORDER BY calls DESC LIMIT 10

9. "Show me all classes"
   MATCH (n:LogicNode {kind: 'class'})
   RETURN n

10. "What does run assign?"
    MATCH (f:LogicNode)-[:ASSIGNS]->(v:Variable)
    WHERE f.name CONTAINS 'run'
    RETURN f, v

11. "What does parse_input return?"
    MATCH (f:LogicNode)-[:RETURNS]->(v:Variable)
    WHERE f.name CONTAINS 'parse_input'
    RETURN f, v

12. "Show intra-function data flow in parse_input"
    MATCH (f:LogicNode)-[:ASSIGNS]->(v1:Variable)-[:FEEDS]->(v2:Variable)
    WHERE f.name CONTAINS 'parse_input'
    RETURN f, v1, v2
""".strip()


# ---------------------------------------------------------------------------
# System prompts (composed from schema + examples)
# ---------------------------------------------------------------------------

CYPHER_SYSTEM_PROMPT = f"""You are a Cypher query generator for a FalkorDB graph database that models a code repository.

{GRAPH_SCHEMA}

{FEW_SHOT_EXAMPLES}

Instructions:
- Generate ONLY a valid Cypher query. No explanations, no markdown code blocks.
- ALWAYS use CONTAINS for name matching. Names are module-qualified (e.g. 'services.register_user').
- Always RETURN meaningful properties (name, module_path) rather than raw nodes.
- For traversal queries, use variable-length relationships like [:CALLS*1..3].
- If the question is ambiguous, prefer a broader query that returns more results.
- NEVER use CREATE, SET, DELETE, DETACH, MERGE, or any write operations.
"""

ORCHESTRATOR_SYSTEM_PROMPT = f"""You are Bumblebee, a codebase assistant. You MUST use the query_graph tool for EVERY question.

NEVER write Cypher in your response text. NEVER show queries to the user. ALWAYS call the query_graph tool.

{GRAPH_SCHEMA}

{FEW_SHOT_EXAMPLES}

RULES:
- You MUST call query_graph for EVERY question. No exceptions. Do not explain, just call the tool.
- ALWAYS use CONTAINS for name matching. Names are module-qualified (e.g. 'services.register_user').
- After receiving results, summarise them briefly.
- If results are empty, call query_graph again with a broader CONTAINS match.
"""
