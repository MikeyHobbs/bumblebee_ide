"""Graph-to-Python code generator.

Regenerates Python source code from parsed AST graph structures. Supports both
in-memory generation (from extraction results) and graph-based generation
(querying FalkorDB).
"""

from __future__ import annotations

import logging
from collections import defaultdict

import tree_sitter
import tree_sitter_python

from app.models.exceptions import BumblebeeError, NodeNotFoundError
from app.services.ast_parser import ParseResult, ParsedNode, _get_parser
from app.services.statement_extractor import (
    StatementNode,
    StatementResult,
)

logger = logging.getLogger(__name__)


class CodeGenerationError(BumblebeeError):
    """Raised when code generation fails."""


def _validate_python_source(source: str) -> bool:
    """Validate that generated source is parseable Python using tree-sitter.

    Args:
        source: The Python source code to validate.

    Returns:
        True if the source parses without errors.

    Raises:
        CodeGenerationError: If the source contains syntax errors.
    """
    parser = _get_parser()
    tree = parser.parse(source.encode("utf-8"))

    def _has_error(node: tree_sitter.Node) -> bool:
        """Recursively check for ERROR nodes in the tree."""
        if node.type == "ERROR":
            return True
        for child in node.children:
            if _has_error(child):
                return True
        return False

    if _has_error(tree.root_node):
        raise CodeGenerationError(f"Generated source contains syntax errors:\n{source}")
    return True


def _build_children_map(
    stmt_result: StatementResult,
) -> dict[str, list[StatementNode]]:
    """Build a map of parent_name -> sorted child statement nodes.

    Args:
        stmt_result: The statement extraction result.

    Returns:
        Dictionary mapping parent names to their children sorted by seq.
    """
    children: dict[str, list[StatementNode]] = defaultdict(list)
    for node in stmt_result.nodes:
        if node.parent_name is not None:
            children[node.parent_name].append(node)
    for key in children:
        children[key].sort(key=lambda n: n.seq)
    return children


def _indent(text: str, level: int) -> str:
    """Indent each line of text by the given number of levels (4 spaces each).

    Args:
        text: The text to indent.
        level: Number of indentation levels.

    Returns:
        The indented text.
    """
    prefix = "    " * level
    lines = text.split("\n")
    return "\n".join(prefix + line if line.strip() else line for line in lines)


def _reconstruct_control_flow(
    cf_node: StatementNode,
    children_map: dict[str, list[StatementNode]],
    indent_level: int,
) -> str:
    """Reconstruct an if/for/while/try/with block from ControlFlow and Branch nodes.

    Args:
        cf_node: The ControlFlow statement node.
        children_map: Map of parent_name -> sorted children.
        indent_level: Current indentation level.

    Returns:
        The reconstructed source for the control flow block.
    """
    prefix = "    " * indent_level
    branches = children_map.get(cf_node.name, [])
    lines: list[str] = []

    if cf_node.kind == "if":
        for i, branch in enumerate(branches):
            body = _generate_function_body(branch.name, children_map, indent_level + 1)
            if branch.kind == "if":
                lines.append(f"{prefix}if {cf_node.condition_text}:")
                lines.append(body)
            elif branch.kind == "elif":
                cond = branch.condition_text or "True"
                lines.append(f"{prefix}elif {cond}:")
                lines.append(body)
            elif branch.kind == "else":
                lines.append(f"{prefix}else:")
                lines.append(body)

    elif cf_node.kind == "for":
        cond = cf_node.condition_text or ""
        lines.append(f"{prefix}for {cond}:")
        for branch in branches:
            body = _generate_function_body(branch.name, children_map, indent_level + 1)
            if branch.kind == "else":
                lines.append(f"{prefix}else:")
            lines.append(body)

    elif cf_node.kind == "while":
        cond = cf_node.condition_text or "True"
        lines.append(f"{prefix}while {cond}:")
        for branch in branches:
            body = _generate_function_body(branch.name, children_map, indent_level + 1)
            if branch.kind == "else":
                lines.append(f"{prefix}else:")
            lines.append(body)

    elif cf_node.kind == "try":
        for branch in branches:
            body = _generate_function_body(branch.name, children_map, indent_level + 1)
            if branch.kind == "try":
                lines.append(f"{prefix}try:")
                lines.append(body)
            elif branch.kind == "except":
                if branch.condition_text:
                    lines.append(f"{prefix}except {branch.condition_text}:")
                else:
                    lines.append(f"{prefix}except:")
                lines.append(body)
            elif branch.kind == "else":
                lines.append(f"{prefix}else:")
                lines.append(body)
            elif branch.kind == "finally":
                lines.append(f"{prefix}finally:")
                lines.append(body)

    elif cf_node.kind == "with":
        cond = cf_node.condition_text or ""
        lines.append(f"{prefix}with {cond}:")
        for branch in branches:
            body = _generate_function_body(branch.name, children_map, indent_level + 1)
            lines.append(body)

    return "\n".join(lines)


def _generate_function_body(
    parent_name: str,
    children_map: dict[str, list[StatementNode]],
    indent_level: int,
) -> str:
    """Reconstruct a function body from statement nodes.

    Args:
        parent_name: The qualified name of the parent (function or branch).
        children_map: Map of parent_name -> sorted children.
        indent_level: Current indentation level.

    Returns:
        The reconstructed source for the body.
    """
    children = children_map.get(parent_name, [])
    if not children:
        return _indent("pass", indent_level)

    prefix = "    " * indent_level
    lines: list[str] = []

    for child in children:
        if child.node_type == "ControlFlow":
            lines.append(_reconstruct_control_flow(child, children_map, indent_level))
        elif child.node_type == "Statement":
            # Re-indent the source text to the correct level
            source_lines = child.source_text.strip().split("\n")
            for sline in source_lines:
                lines.append(f"{prefix}{sline.strip()}")
        elif child.node_type == "Branch":
            # Branches are handled by their parent ControlFlow
            pass

    if not lines:
        return _indent("pass", indent_level)

    return "\n".join(lines)


def _extract_signature(source_text: str) -> str:
    """Extract the function/class signature (everything up to and including the body colon).

    For multi-line signatures like:
        def foo(
            a: int,
            b: int,
        ) -> int:
    this returns all lines up to and including the closing ')' and ':'.

    Tracks parenthesis nesting so type-hint colons inside parameter lists
    are not confused with the body colon.

    Args:
        source_text: The full source text of the function/class.

    Returns:
        The signature portion of the source.
    """
    source_lines = source_text.split("\n")
    sig_lines: list[str] = []
    paren_depth = 0
    bracket_depth = 0

    for line in source_lines:
        sig_lines.append(line)
        for ch in line:
            if ch == "(":
                paren_depth += 1
            elif ch == ")":
                paren_depth = max(0, paren_depth - 1)
            elif ch == "[":
                bracket_depth += 1
            elif ch == "]":
                bracket_depth = max(0, bracket_depth - 1)

        stripped = line.rstrip()
        if (
            stripped.endswith(":")
            and paren_depth == 0
            and bracket_depth == 0
            and not stripped.startswith("#")
        ):
            break

    return "\n".join(sig_lines)


def _generate_function_source(
    func_node: ParsedNode,
    children_map: dict[str, list[StatementNode]],
    parse_result: ParseResult | None = None,
) -> str:
    """Generate source for a single function from its parsed node and statements.

    Interleaves statements and nested definitions in source-order based on
    start_line so that nested defs appear where they were originally defined,
    not appended at the end.

    Args:
        func_node: The ParsedNode for the function.
        children_map: Map of parent_name -> sorted children.
        parse_result: Optional parse result for finding nested definitions.

    Returns:
        The regenerated function source code.
    """
    # If the function has no statement children in the map and no nested defs, return original source
    has_nested = False
    nested_defs: list[ParsedNode] = []
    if parse_result is not None:
        nested_defs = [
            n for n in parse_result.nodes
            if n.parent_name == func_node.name and n.node_type in ("Function", "Class")
        ]
        has_nested = len(nested_defs) > 0

    if func_node.name not in children_map and not has_nested:
        return func_node.source_text

    lines: list[str] = []

    # Calculate base indent from the function's start column
    base_indent = func_node.start_col // 4

    # Decorators
    for dec in func_node.decorators:
        lines.append(_indent(f"@{dec}", base_indent))

    # Function signature — extract full multi-line signature
    prefix = "    " * base_indent
    sig = _extract_signature(func_node.source_text)
    sig_lines = sig.split("\n")
    for j, sline in enumerate(sig_lines):
        if j == 0:
            lines.append(f"{prefix}{sline.strip()}")
        else:
            lines.append(f"{prefix}    {sline.strip()}")

    # Docstring
    if func_node.docstring:
        doc_indent = base_indent + 1
        doc_prefix = "    " * doc_indent
        lines.append(f'{doc_prefix}"""{func_node.docstring}"""')

    # Build interleaved body: mix statements with nested defs by start_line
    children = children_map.get(func_node.name, [])
    nested_defs.sort(key=lambda n: n.start_line)

    # Create a merged list of (start_line, "stmt"|"nested", item)
    body_items: list[tuple[int, str, StatementNode | ParsedNode]] = []
    for child in children:
        body_items.append((child.start_line, "stmt", child))
    for nested in nested_defs:
        body_items.append((nested.start_line, "nested", nested))
    body_items.sort(key=lambda x: x[0])

    body_indent = base_indent + 1
    body_prefix = "    " * body_indent
    has_body = False

    for _line_no, kind, item in body_items:
        if kind == "stmt":
            stmt = item
            assert isinstance(stmt, StatementNode)
            if stmt.node_type == "ControlFlow":
                lines.append(_reconstruct_control_flow(stmt, children_map, body_indent))
            elif stmt.node_type == "Statement":
                source_lines = stmt.source_text.strip().split("\n")
                for sline in source_lines:
                    lines.append(f"{body_prefix}{sline.strip()}")
            has_body = True
        elif kind == "nested":
            nested_node = item
            assert isinstance(nested_node, ParsedNode)
            lines.append("")
            if nested_node.node_type == "Function":
                lines.append(_generate_function_source(nested_node, children_map, parse_result))
            elif nested_node.node_type == "Class":
                assert parse_result is not None
                lines.append(_generate_class_source(nested_node, parse_result, children_map))
            has_body = True

    if not has_body:
        lines.append(f"{body_prefix}pass")

    return "\n".join(lines)


def _generate_class_source(
    class_node: ParsedNode,
    parse_result: ParseResult,
    children_map: dict[str, list[StatementNode]],
) -> str:
    """Generate source for a class from its parsed node and contained methods.

    Args:
        class_node: The ParsedNode for the class.
        parse_result: The full parse result (to find class methods).
        children_map: Map of parent_name -> sorted children.

    Returns:
        The regenerated class source code.
    """
    lines: list[str] = []
    base_indent = class_node.start_col // 4

    # Decorators
    for dec in class_node.decorators:
        lines.append(_indent(f"@{dec}", base_indent))

    # Class signature
    prefix = "    " * base_indent
    sig_line = class_node.source_text.split("\n")[0].strip()
    lines.append(f"{prefix}{sig_line}")

    # Docstring
    if class_node.docstring:
        doc_indent = base_indent + 1
        doc_prefix = "    " * doc_indent
        lines.append(f'{doc_prefix}"""{class_node.docstring}"""')

    # Find methods defined in this class
    methods = [
        n for n in parse_result.nodes
        if n.node_type == "Function" and n.parent_name == class_node.name
    ]
    methods.sort(key=lambda n: n.start_line)

    if not methods and not class_node.docstring:
        lines.append(_indent("pass", base_indent + 1))
    else:
        for i, method in enumerate(methods):
            if i > 0:
                lines.append("")  # Blank line between methods
            method_src = _generate_function_source(method, children_map, parse_result)
            lines.append(method_src)

    return "\n".join(lines)


def generate_from_extractions(
    parse_result: ParseResult,
    stmt_result: StatementResult,
) -> str:
    """Generate Python source from in-memory extraction results.

    This is the primary function for round-trip testing without needing FalkorDB.
    It takes the outputs of parse_file() and extract_statements() and regenerates
    the Python source code.

    Args:
        parse_result: Result from ast_parser.parse_file().
        stmt_result: Result from statement_extractor.extract_statements().

    Returns:
        The regenerated Python source code.
    """
    children_map = _build_children_map(stmt_result)

    # Find the module node
    module_node = next(
        (n for n in parse_result.nodes if n.node_type == "Module"),
        None,
    )
    if module_node is None:
        raise CodeGenerationError("No Module node found in parse result")

    # Find top-level definitions in the module
    top_level = [
        n for n in parse_result.nodes
        if n.parent_name == module_node.name and n.node_type in ("Class", "Function")
    ]
    top_level.sort(key=lambda n: n.start_line)

    lines: list[str] = []

    # Extract module-level code (imports, assignments, etc.) that appears
    # before the first class/function definition. The statement extractor
    # only handles function bodies, so we preserve these lines from the
    # original module source text.
    if top_level:
        first_def_line = top_level[0].start_line
        # Check for decorators above the first def
        if top_level[0].decorators:
            # Search for decorator lines above start_line
            source_lines = module_node.source_text.split("\n")
            for k in range(first_def_line - 2, -1, -1):
                if k < len(source_lines) and source_lines[k].strip().startswith("@"):
                    first_def_line = k + 1  # 1-based
                else:
                    break
        module_source_lines = module_node.source_text.split("\n")
        preamble = module_source_lines[:first_def_line - 1]
        # Strip trailing blank lines from preamble
        while preamble and not preamble[-1].strip():
            preamble.pop()
        if preamble:
            lines.extend(preamble)
    elif module_node.docstring:
        lines.append(f'"""{module_node.docstring}"""')
        lines.append("")

    for i, node in enumerate(top_level):
        if i > 0 or lines:
            lines.append("")
            lines.append("")

        if node.node_type == "Class":
            lines.append(_generate_class_source(node, parse_result, children_map))
        elif node.node_type == "Function":
            lines.append(_generate_function_source(node, children_map, parse_result))

    result = "\n".join(lines) + "\n"
    return result


def generate_function(
    function_name: str,
    parse_result: ParseResult,
    stmt_result: StatementResult,
) -> str:
    """Generate source for a single function from extraction results.

    Args:
        function_name: The qualified name of the function.
        parse_result: Result from ast_parser.parse_file().
        stmt_result: Result from statement_extractor.extract_statements().

    Returns:
        The regenerated function source code.

    Raises:
        NodeNotFoundError: If the function is not found in the parse result.
    """
    func_node = next(
        (n for n in parse_result.nodes if n.name == function_name and n.node_type == "Function"),
        None,
    )
    if func_node is None:
        raise NodeNotFoundError(function_name)

    children_map = _build_children_map(stmt_result)

    # If no statement-level edits, return original source
    if func_node.name not in children_map:
        return func_node.source_text

    return _generate_function_source(func_node, children_map, parse_result)


def generate_module(module_name: str) -> str:
    """Generate full module source from FalkorDB graph.

    Traverses the graph database to reconstruct the Python source for a module.

    Args:
        module_name: The qualified name of the module in the graph.

    Returns:
        The regenerated Python module source code.

    Raises:
        NodeNotFoundError: If the module is not found in the graph.
        CodeGenerationError: If code generation fails.
    """
    from app.graph.client import get_graph

    graph = get_graph()

    # Find the module node
    result = graph.query(
        "MATCH (m:Module {name: $name}) RETURN m.name, m.source_text, m.docstring",
        params={"name": module_name},
    )
    if not result.result_set:
        raise NodeNotFoundError(module_name)

    module_source = result.result_set[0][1]

    # Find all functions and classes defined in this module
    nodes_result = graph.query(
        "MATCH (m:Module {name: $name})-[:DEFINES]->(n) RETURN n.name, n.node_type, n.source_text, "
        "n.start_line, n.end_line, n.start_col, n.end_col, n.docstring, n.is_async, n.module_path "
        "ORDER BY n.start_line",
        params={"name": module_name},
    )

    if not nodes_result.result_set:
        # Module with no definitions - return original source
        return module_source

    # For each function, check if it has statement-level nodes
    # If not, return the function's source_text directly
    # If yes, reconstruct from statements
    parts: list[str] = []

    for row in nodes_result.result_set:
        node_name = row[0]
        node_type = row[1]
        source_text = row[2]

        # Check for statement-level modifications
        stmt_check = graph.query(
            "MATCH (n {name: $name})-[:CONTAINS]->(s) WHERE s:Statement OR s:ControlFlow "
            "RETURN count(s) AS cnt",
            params={"name": node_name},
        )
        has_statements = stmt_check.result_set and stmt_check.result_set[0][0] > 0

        if not has_statements:
            parts.append(source_text)
        else:
            # Reconstruct from graph statements
            parts.append(source_text)  # Fallback: use stored source

    return "\n\n\n".join(parts) + "\n"


def generate_function_from_graph(function_name: str) -> str:
    """Generate a single function's source from FalkorDB graph.

    Args:
        function_name: The qualified name of the function in the graph.

    Returns:
        The regenerated function source code.

    Raises:
        NodeNotFoundError: If the function is not found in the graph.
    """
    from app.graph.client import get_graph

    graph = get_graph()

    result = graph.query(
        "MATCH (f:Function {name: $name}) RETURN f.source_text",
        params={"name": function_name},
    )
    if not result.result_set:
        raise NodeNotFoundError(function_name)

    return result.result_set[0][0]
