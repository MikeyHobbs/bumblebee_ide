"""VFS Projection Engine (TICKET-840).

Projects the graph into human-readable Python files in `.bumblebee/vfs/`
with bidirectional sync support.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tree_sitter

from app.graph.client import get_graph
from app.graph import logic_queries as lq
from app.services.analysis.hash_identity import compute_ast_hash

logger = logging.getLogger(__name__)


@dataclass
class ProjectionReport:
    """Summary of a VFS projection operation."""

    files_written: int = 0
    modules_projected: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class SyncReport:
    """Summary of a VFS-to-graph sync operation."""

    nodes_updated: int = 0
    nodes_created: int = 0
    nodes_deprecated: int = 0
    errors: list[str] = field(default_factory=list)


def project_module(module_path: str) -> str:
    """Project a single module from the graph to Python source.

    Args:
        module_path: The logical module path (e.g., "app.services.auth").

    Returns:
        Generated Python source code.
    """
    graph = get_graph()

    # Get all active LogicNodes for this module
    result = graph.query(
        "MATCH (n:LogicNode {module_path: $module_path, status: 'active'}) "
        "RETURN n ORDER BY n.start_line, n.name",
        params={"module_path": module_path},
    )

    if not result.result_set:
        return ""

    nodes = []
    for row in result.result_set:
        props = row[0].properties if hasattr(row[0], "properties") else row[0]
        nodes.append(props)

    return _generate_module_source(nodes, module_path)


def project_node(node_id: str) -> str:
    """Generate source text for a single LogicNode.

    Args:
        node_id: UUID of the LogicNode.

    Returns:
        The node's source_text.
    """
    graph = get_graph()
    result = graph.query(lq.GET_LOGIC_NODE_BY_ID, params={"id": node_id})
    if not result.result_set:
        return ""

    props = result.result_set[0][0].properties if hasattr(result.result_set[0][0], "properties") else result.result_set[0][0]
    return props.get("source_text", "")


def project_modules(module_paths: list[str], output_dir: str = ".bumblebee/vfs") -> ProjectionReport:
    """Project specific modules to the VFS directory.

    Args:
        module_paths: List of module paths to project.
        output_dir: Path to the VFS output directory.

    Returns:
        ProjectionReport with counts.
    """
    report = ProjectionReport()
    base = Path(output_dir)

    for mod_path in module_paths:
        if not mod_path:
            continue
        try:
            source = project_module(mod_path)
            if not source.strip():
                continue

            file_path = base / (mod_path.replace(".", "/") + ".py")
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(source, encoding="utf-8")
            report.files_written += 1
            report.modules_projected += 1
        except Exception as exc:
            report.errors.append(f"Error projecting {mod_path}: {exc}")

    logger.info("VFS projected %d of %d requested modules", report.modules_projected, len(module_paths))
    return report


def project_all(output_dir: str) -> ProjectionReport:
    """Project all modules to `.bumblebee/vfs/` directory.

    Args:
        output_dir: Path to the VFS output directory.

    Returns:
        ProjectionReport with counts.
    """
    report = ProjectionReport()
    graph = get_graph()
    base = Path(output_dir)

    # Get all unique module_paths
    result = graph.query(
        "MATCH (n:LogicNode {status: 'active'}) "
        "RETURN DISTINCT n.module_path"
    )

    if not result.result_set:
        return report

    for row in result.result_set:
        mod_path = row[0]
        if not mod_path:
            continue

        try:
            source = project_module(mod_path)
            if not source.strip():
                continue

            # Convert module path to file path
            file_path = base / (mod_path.replace(".", "/") + ".py")
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(source, encoding="utf-8")
            report.files_written += 1
            report.modules_projected += 1
        except Exception as exc:
            report.errors.append(f"Error projecting {mod_path}: {exc}")

    logger.info("VFS projected: %d modules, %d files", report.modules_projected, report.files_written)
    return report


def sync_vfs_to_graph(vfs_path: str) -> SyncReport:
    """Reverse sync: parse VFS files and update the graph.

    New functions in VFS files become new LogicNodes. Modified functions
    (different AST hash) update existing LogicNodes. Functions removed
    from VFS files are flagged for deprecation.

    Args:
        vfs_path: Path to a VFS Python file or directory.

    Returns:
        SyncReport with counts.
    """
    from app.services.persistence.import_pipeline import import_file  # pylint: disable=import-outside-toplevel

    report = SyncReport()
    path = Path(vfs_path)

    if path.is_file() and path.suffix == ".py":
        _sync_single_file(path, report)
    elif path.is_dir():
        for py_file in sorted(path.rglob("*.py")):
            _sync_single_file(py_file, report)

    return report


def _sync_single_file(file_path: Path, report: SyncReport) -> None:
    """Sync a single VFS file back to the graph."""
    from app.services.persistence.import_pipeline import import_file  # pylint: disable=import-outside-toplevel

    try:
        import_report = import_file(str(file_path))
        report.nodes_created += import_report.nodes_created
        report.nodes_updated += import_report.nodes_updated
        report.errors.extend(import_report.errors)
    except Exception as exc:
        report.errors.append(f"Sync error for {file_path}: {exc}")


def project_type_shape(shape_id: str, output_dir: str = ".bumblebee/vfs") -> tuple[str, str]:
    """Project a TypeShape to a Python stub file in VFS.

    Generates a class stub showing the structural interface of a TypeShape,
    including attributes, methods, subscripts, and connected variables/functions.

    Args:
        shape_id: UUID of the TypeShape node.
        output_dir: VFS output directory path.

    Returns:
        Tuple of (generated_source, file_path_written).
    """
    graph = get_graph()

    # Fetch TypeShape node
    result = graph.query(lq.GET_TYPE_SHAPE_BY_ID, params={"id": shape_id})
    if not result.result_set:
        return "", ""

    props = result.result_set[0][0].properties if hasattr(result.result_set[0][0], "properties") else result.result_set[0][0]
    definition_str = props.get("definition", "{}")
    try:
        definition = json.loads(definition_str) if isinstance(definition_str, str) else definition_str
    except (json.JSONDecodeError, TypeError):
        definition = {}

    kind = definition.get("kind", props.get("kind", ""))
    base_type = props.get("base_type", "") or ""
    type_hint = definition.get("type", "") or ""

    # Fetch connections
    conn_result = graph.query(lq.GET_TYPE_SHAPE_CONNECTIONS, params={"id": shape_id})
    variables: list[dict[str, Any]] = []
    accepting_fns: list[dict[str, Any]] = []
    producing_fns: list[dict[str, Any]] = []
    if conn_result.result_set:
        row = conn_result.result_set[0]
        variables = [v for v in (row[0] or []) if isinstance(v, dict) and v.get("id")]
        accepting_fns = [f for f in (row[1] or []) if isinstance(f, dict) and f.get("id")]
        producing_fns = [f for f in (row[2] or []) if isinstance(f, dict) and f.get("id")]

    source = _generate_type_shape_stub(definition, kind, base_type, type_hint, variables, accepting_fns, producing_fns)

    # Determine class name for file path
    class_name = base_type or type_hint.split("[")[0].rsplit(".", 1)[-1] or f"shape_{shape_id[:8]}"
    class_name = class_name.replace(" ", "_")
    file_rel = f"__typeshapes__/{class_name}.py"
    file_path = Path(output_dir) / file_rel

    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(source, encoding="utf-8")
    logger.info("VFS projected TypeShape %s to %s", shape_id, file_path)

    return source, str(file_path)


def _generate_type_shape_stub(
    definition: dict[str, Any],
    kind: str,
    base_type: str,
    type_hint: str,
    variables: list[dict[str, Any]],
    accepting_fns: list[dict[str, Any]],
    producing_fns: list[dict[str, Any]],
) -> str:
    """Generate a Python stub representing a TypeShape's structural interface.

    Args:
        definition: Parsed TypeShape definition dict.
        kind: Shape kind ("structural" or "hint").
        base_type: Base type name.
        type_hint: Full type hint string.
        variables: Variables with this shape.
        accepting_fns: Functions that accept this shape.
        producing_fns: Functions that produce this shape.

    Returns:
        Python source string.
    """
    lines: list[str] = []
    class_name = base_type or type_hint.split("[")[0].rsplit(".", 1)[-1] or "UnknownType"
    # Sanitise to valid Python identifier
    class_name = "".join(c if c.isalnum() or c == "_" else "_" for c in class_name)

    # Header comment
    lines.append(f'"""TypeShape stub: {kind} evidence for {base_type or type_hint}.')
    lines.append("")
    lines.append(f"Kind: {kind}")
    if type_hint:
        lines.append(f"Type hint: {type_hint}")
    lines.append('"""')
    lines.append("")

    # Variables section
    if variables:
        lines.append(f"# Variables with this shape ({len(variables)})")
        for v in variables:
            hint = v.get("type_hint") or ""
            name = v.get("name", "")
            lines.append(f"#   {name}{': ' + hint if hint else ''}")
        lines.append("")

    # Accepting functions
    if accepting_fns:
        lines.append(f"# Accepted by ({len(accepting_fns)})")
        for f in accepting_fns:
            sig = f.get("signature", "") or f.get("name", "")
            lines.append(f"#   {sig}")
        lines.append("")

    # Producing functions
    if producing_fns:
        lines.append(f"# Produced by ({len(producing_fns)})")
        for f in producing_fns:
            lines.append(f"#   {f.get('name', '')}")
        lines.append("")

    attrs = definition.get("attrs", [])
    methods = definition.get("methods", [])
    subscripts = definition.get("subscripts", [])

    if kind == "hint" and not attrs and not methods and not subscripts:
        # Pure hint shape — no structural evidence
        lines.append(f"{class_name} = {type_hint}")
        lines.append("")
    else:
        # Class stub with structural evidence
        lines.append("")
        lines.append(f"class {class_name}:")
        has_body = False

        if attrs:
            for attr in sorted(attrs):
                lines.append(f"    {attr}: ...")
                has_body = True
            lines.append("")

        if subscripts:
            for sub in sorted(subscripts):
                lines.append(f"    # subscript: [{sub}]")
                has_body = True
            lines.append("")

        if methods:
            for method in sorted(methods):
                lines.append(f"    def {method}(self, *args, **kwargs): ...")
                lines.append("")
                has_body = True

        if not has_body:
            lines.append("    pass")
            lines.append("")

    return "\n".join(lines)


def _generate_module_source(nodes: list[dict[str, Any]], module_path: str) -> str:
    """Generate Python source for a module from its LogicNodes.

    Args:
        nodes: List of node property dicts, sorted by start_line.
        module_path: The module path for import generation.

    Returns:
        Complete Python source code.
    """
    graph = get_graph()
    lines: list[str] = []

    # Collect imports from DEPENDS_ON edges
    imports = _collect_imports(nodes, graph)
    if imports:
        lines.extend(sorted(imports))
        lines.append("")
        lines.append("")

    # Separate classes and standalone functions/constants
    classes: dict[str, dict[str, Any]] = {}
    class_methods: dict[str, list[dict[str, Any]]] = {}
    standalone: list[dict[str, Any]] = []

    for node in nodes:
        kind = node.get("kind", "function")
        if kind == "class":
            classes[node.get("id", "")] = node
            class_methods[node.get("id", "")] = []
        elif kind == "method":
            class_id = node.get("class_id", "")
            if class_id and class_id in class_methods:
                class_methods[class_id].append(node)
            else:
                # Orphan method — treat as standalone
                standalone.append(node)
        else:
            standalone.append(node)

    # Write classes with their methods
    for class_id, class_node in classes.items():
        source = class_node.get("source_text", "")
        if source:
            lines.append(source)
        else:
            # Generate class stub
            lines.append(f"class {class_node.get('name', '').rsplit('.', 1)[-1]}:")
            methods = class_methods.get(class_id, [])
            if methods:
                for method in methods:
                    method_source = method.get("source_text", "")
                    if method_source:
                        # Indent method source
                        indented = "\n".join("    " + line if line.strip() else "" for line in method_source.splitlines())
                        lines.append(indented)
                    lines.append("")
            else:
                lines.append("    pass")
        lines.append("")
        lines.append("")

    # Write standalone functions and constants
    for node in standalone:
        source = node.get("source_text", "")
        if source:
            lines.append(source)
            lines.append("")
            lines.append("")

    result = "\n".join(lines).rstrip() + "\n"
    return result


def _collect_imports(nodes: list[dict[str, Any]], graph: Any) -> set[str]:
    """Collect import statements from DEPENDS_ON edges.

    Args:
        nodes: The module's LogicNodes.
        graph: FalkorDB graph instance.

    Returns:
        Set of import statement strings.
    """
    imports: set[str] = set()

    for node in nodes:
        node_id = node.get("id", "")
        if not node_id:
            continue

        try:
            result = graph.query(
                "MATCH (n:LogicNode {id: $id})-[r:DEPENDS_ON]->(dep:LogicNode) RETURN dep.module_path, dep.name",
                params={"id": node_id},
            )
            for row in result.result_set:
                dep_module = row[0]
                dep_name = row[1]
                if dep_module and dep_name:
                    short_name = dep_name.rsplit(".", 1)[-1]
                    imports.add(f"from {dep_module} import {short_name}")
        except Exception:
            pass

    return imports
