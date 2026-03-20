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
        base_type = definition.get("base_type", "")
        canonical = f"structural:{{base_type:{base_type}|attrs:{attrs}|methods:{methods}|subscripts:{subscripts}}}"
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
    """Compute COMPATIBLE_WITH edges between TypeShapes.

    Creates edges in two cases:
    1. Structural↔Structural: S1 COMPATIBLE_WITH S2 if S1 is a superset of S2.
    2. Hint↔Structural: A hint shape is COMPATIBLE_WITH every structural shape
       whose base_type matches the hint type (bridging typed variables to
       duck-typed consumers).

    Args:
        graph: FalkorDB graph instance.

    Returns:
        Number of COMPATIBLE_WITH edges created.
    """
    result = graph.query(lq.GET_ALL_TYPE_SHAPES)
    structural_shapes: list[dict[str, Any]] = []
    hint_shapes: list[dict[str, Any]] = []

    for row in result.result_set:
        node = row[0]
        props = node.properties if hasattr(node, "properties") else node
        kind = props.get("kind", "")

        definition_str = props.get("definition", "{}")
        try:
            definition = json.loads(definition_str) if isinstance(definition_str, str) else definition_str
        except (json.JSONDecodeError, TypeError):
            continue

        if kind == "structural":
            structural_shapes.append({
                "id": props.get("id", ""),
                "base_type": props.get("base_type", "") or definition.get("base_type", ""),
                "attrs": set(definition.get("attrs", [])),
                "subscripts": set(definition.get("subscripts", [])),
                "methods": set(definition.get("methods", [])),
            })
        elif kind == "hint":
            hint_shapes.append({
                "id": props.get("id", ""),
                "type": definition.get("type", ""),
            })

    edges_created = 0

    # Minimum evidence items (attrs + subscripts + methods) for a structural
    # shape to participate as the subset side of COMPATIBLE_WITH.  Single-
    # attribute shapes (e.g. just {data}) are too generic — common attributes
    # like data, name, value, id would false-match across unrelated types.
    MIN_STRUCTURAL_EVIDENCE = 2

    # Structural ↔ Structural: superset relationships
    for i, s1 in enumerate(structural_shapes):
        for j, s2 in enumerate(structural_shapes):
            if i == j:
                continue

            # Skip subset shapes with too little evidence
            total_s2 = len(s2["attrs"]) + len(s2["subscripts"]) + len(s2["methods"])
            if total_s2 < MIN_STRUCTURAL_EVIDENCE:
                continue

            # If either shape has a base_type, skip direct edge — typed
            # shapes connect through the hint hub only.
            s1_base = s1["base_type"]
            s2_base = s2["base_type"]
            if s1_base or s2_base:
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

    # Facet clustering: connect untyped shapes with complementary facets.
    # One shape has attrs/subscripts only, the other has methods only.
    for i, s1 in enumerate(structural_shapes):
        if s1["base_type"]:
            continue
        for j, s2 in enumerate(structural_shapes):
            if i >= j or s2["base_type"]:
                continue
            s1_has_data = bool(s1["attrs"] or s1["subscripts"])
            s1_has_methods = bool(s1["methods"])
            s2_has_data = bool(s2["attrs"] or s2["subscripts"])
            s2_has_methods = bool(s2["methods"])
            if not ((s1_has_data and not s1_has_methods and s2_has_methods and not s2_has_data)
                    or (s1_has_methods and not s1_has_data and s2_has_data and not s2_has_methods)):
                continue
            s1_total = len(s1["attrs"]) + len(s1["subscripts"]) + len(s1["methods"])
            s2_total = len(s2["attrs"]) + len(s2["subscripts"]) + len(s2["methods"])
            if s1_total >= 1 and s2_total >= 1:
                for src_id, tgt_id in [(s1["id"], s2["id"]), (s2["id"], s1["id"])]:
                    try:
                        graph.query(
                            lq.EDGE_MERGE_QUERIES["COMPATIBLE_WITH"],
                            params={
                                "source_id": src_id,
                                "target_id": tgt_id,
                                "properties": {"strength": "facet_cluster"},
                            },
                        )
                        edges_created += 1
                    except Exception as exc:
                        logger.warning("COMPATIBLE_WITH facet cluster edge error: %s", exc)

    # Hint ↔ Structural: bridge typed variables to duck-typed consumers.
    # A hint shape (e.g. pd.DataFrame) is COMPATIBLE_WITH any structural shape
    # that was extracted from the same base type, allowing consumer discovery
    # across the typed/untyped boundary.
    # Skip primitive containers — they're too generic to be useful for matching.
    _PRIMITIVE_CONTAINERS = {"list", "dict", "set", "tuple", "frozenset", "deque"}
    for hint in hint_shapes:
        hint_type = hint["type"]
        if not hint_type:
            continue
        # Normalize: "pd.DataFrame" → "DataFrame", "list[str]" → "list"
        hint_base = hint_type.split("[")[0].rsplit(".", 1)[-1].strip()
        if hint_base.lower() in _PRIMITIVE_CONTAINERS:
            continue
        for structural in structural_shapes:
            st_base = structural["base_type"]
            if not st_base:
                # Structural shapes without base_type are duck-typed — connect
                # them to hints if they have any evidence at all (conservative
                # match: any structural shape from a parameter with no base_type
                # is a potential consumer shape)
                continue
            st_base_norm = st_base.split("[")[0].rsplit(".", 1)[-1].strip()
            if hint_base.lower() == st_base_norm.lower():
                try:
                    graph.query(
                        lq.EDGE_MERGE_QUERIES["COMPATIBLE_WITH"],
                        params={
                            "source_id": hint["id"],
                            "target_id": structural["id"],
                            "properties": {},
                        },
                    )
                    edges_created += 1
                except Exception as exc:
                    logger.warning("COMPATIBLE_WITH hint→structural edge error: %s", exc)

    # Also bridge structural shapes to hint shapes with matching base_type.
    # This allows a variable with structural evidence + base_type to find
    # consumers that accept parameters with only a type hint.
    for structural in structural_shapes:
        st_base = structural["base_type"]
        if not st_base:
            continue
        st_base_norm = st_base.split("[")[0].rsplit(".", 1)[-1].strip()
        if st_base_norm.lower() in _PRIMITIVE_CONTAINERS:
            continue
        for hint in hint_shapes:
            hint_base = hint["type"].split("[")[0].rsplit(".", 1)[-1].strip()
            if st_base_norm.lower() == hint_base.lower():
                try:
                    graph.query(
                        lq.EDGE_MERGE_QUERIES["COMPATIBLE_WITH"],
                        params={
                            "source_id": structural["id"],
                            "target_id": hint["id"],
                            "properties": {},
                        },
                    )
                    edges_created += 1
                except Exception as exc:
                    logger.warning("COMPATIBLE_WITH structural→hint edge error: %s", exc)

    # Generic hint → bare hint: e.g. hint:list[str] COMPATIBLE_WITH hint:list
    # This bridges typed generics to their bare type as weak matches.
    bare_hints: dict[str, dict[str, Any]] = {}
    for hint in hint_shapes:
        hint_type = hint["type"]
        if not hint_type or "[" in hint_type:
            continue
        bare_hints[hint_type.lower()] = hint

    for hint in hint_shapes:
        hint_type = hint["type"]
        if not hint_type or "[" not in hint_type:
            continue
        bare_name = hint_type.split("[")[0].strip().lower()
        bare = bare_hints.get(bare_name)
        if bare and bare["id"] != hint["id"]:
            try:
                graph.query(
                    lq.EDGE_MERGE_QUERIES["COMPATIBLE_WITH"],
                    params={
                        "source_id": hint["id"],
                        "target_id": bare["id"],
                        "properties": {"strength": "generalization"},
                    },
                )
                edges_created += 1
            except Exception as exc:
                logger.warning("COMPATIBLE_WITH generic→bare edge error: %s", exc)

    logger.info(
        "Computed %d COMPATIBLE_WITH edges from %d structural + %d hint shapes",
        edges_created, len(structural_shapes), len(hint_shapes),
    )
    return edges_created
