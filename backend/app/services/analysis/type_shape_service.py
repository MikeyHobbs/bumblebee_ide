"""TypeShape builder service (TICKET-962).

Builds TypeShape definitions from shape evidence, computes canonical hashes,
and manages COMPATIBLE_WITH edges for structural type matching.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.graph.client import get_graph
from app.graph import logic_queries as lq
from app.services.analysis.hash_identity import generate_deterministic_node_id
from app.services.parsing.variable_extractor import ShapeEvidence

logger = logging.getLogger(__name__)

# Known primitive types for hint-based shape classification
_PRIMITIVE_TYPES = frozenset({"int", "float", "str", "bool", "bytes", "complex", "None", "NoneType"})


def build_shape_definition(evidence: ShapeEvidence) -> dict[str, Any] | None:
    """Convert shape evidence to a canonical shape definition.

    Returns None if there is no evidence (no structural access, no type hint).

    Args:
        evidence: Shape evidence from variable extraction.

    Returns:
        Shape definition dict, or None if no evidence exists.
    """
    has_structural = bool(evidence.attrs_accessed or evidence.subscripts_accessed or evidence.methods_called)

    if has_structural:
        definition: dict[str, Any] = {
            "kind": "structural",
            "attrs": sorted(evidence.attrs_accessed),
            "subscripts": sorted(evidence.subscripts_accessed),
            "methods": sorted(evidence.methods_called),
        }
        if evidence.type_hint:
            definition["base_type"] = evidence.type_hint
        return definition

    if evidence.type_hint:
        # Strip generic parameters for base type check
        base = evidence.type_hint.split("[")[0].strip()
        if base in _PRIMITIVE_TYPES:
            return {"kind": "primitive", "type": evidence.type_hint}
        return {"kind": "hint", "type": evidence.type_hint}

    # No evidence at all — no TypeShape
    return None


def compute_shape_hash(definition: dict[str, Any]) -> str:
    """Compute a canonical SHA-256 hash of a shape definition.

    Sorts all lists and builds a deterministic string representation.

    Args:
        definition: Shape definition dict.

    Returns:
        Hex digest of SHA-256 hash.
    """
    kind = definition.get("kind", "")

    if kind == "structural":
        attrs = ",".join(sorted(definition.get("attrs", [])))
        subscripts = ",".join(sorted(definition.get("subscripts", [])))
        methods = ",".join(sorted(definition.get("methods", [])))
        canonical = f"structural:{{attrs:{attrs}|methods:{methods}|subscripts:{subscripts}}}"
    elif kind == "primitive":
        canonical = f"primitive:{definition.get('type', '')}"
    elif kind == "hint":
        canonical = f"hint:{definition.get('type', '')}"
    else:
        canonical = json.dumps(definition, sort_keys=True)

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_or_get_type_shape(graph: Any, definition: dict[str, Any]) -> str:
    """MERGE a TypeShape node by shape_hash, returning its node ID.

    Args:
        graph: FalkorDB graph instance.
        definition: Shape definition dict.

    Returns:
        The TypeShape node ID.
    """
    shape_hash = compute_shape_hash(definition)
    node_id = generate_deterministic_node_id(f"typeshape::{shape_hash}")
    now = datetime.now(timezone.utc).isoformat()

    kind = definition.get("kind", "structural")
    base_type = definition.get("base_type", "") or ""
    if kind in ("primitive", "hint"):
        base_type = definition.get("type", "")

    graph.query(
        lq.MERGE_TYPE_SHAPE,
        params={
            "id": node_id,
            "shape_hash": shape_hash,
            "kind": kind,
            "base_type": base_type,
            "definition": json.dumps(definition, sort_keys=True),
            "created_at": now,
        },
    )

    return node_id


def compute_compatible_with_edges(graph: Any) -> int:
    """Compute COMPATIBLE_WITH edges between structural shapes.

    A shape S1 is COMPATIBLE_WITH S2 if S1 is a superset of S2
    (S1 has all the attrs/subscripts/methods of S2, plus more).

    Args:
        graph: FalkorDB graph instance.

    Returns:
        Number of COMPATIBLE_WITH edges created.
    """
    result = graph.query(lq.GET_ALL_TYPE_SHAPES)
    structural_shapes: list[dict[str, Any]] = []

    for row in result.result_set:
        node = row[0]
        props = node.properties if hasattr(node, "properties") else node
        kind = props.get("kind", "")
        if kind != "structural":
            continue

        definition_str = props.get("definition", "{}")
        try:
            definition = json.loads(definition_str) if isinstance(definition_str, str) else definition_str
        except (json.JSONDecodeError, TypeError):
            continue

        structural_shapes.append({
            "id": props.get("id", ""),
            "attrs": set(definition.get("attrs", [])),
            "subscripts": set(definition.get("subscripts", [])),
            "methods": set(definition.get("methods", [])),
        })

    edges_created = 0

    for i, s1 in enumerate(structural_shapes):
        for j, s2 in enumerate(structural_shapes):
            if i == j:
                continue
            # S1 is superset of S2 if all of S2's sets are subsets of S1's
            if (
                s2["attrs"] <= s1["attrs"]
                and s2["subscripts"] <= s1["subscripts"]
                and s2["methods"] <= s1["methods"]
                and (s1["attrs"] | s1["subscripts"] | s1["methods"]) != (s2["attrs"] | s2["subscripts"] | s2["methods"])
            ):
                try:
                    graph.query(
                        lq.EDGE_MERGE_QUERIES["COMPATIBLE_WITH"],
                        params={
                            "source_id": s1["id"],
                            "target_id": s2["id"],
                            "properties": {},
                        },
                    )
                    edges_created += 1
                except Exception as exc:
                    logger.warning("COMPATIBLE_WITH edge error: %s", exc)

    logger.info("Computed %d COMPATIBLE_WITH edges from %d structural shapes", edges_created, len(structural_shapes))
    return edges_created
