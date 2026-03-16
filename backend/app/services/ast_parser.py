"""AST parser using tree-sitter to extract structural nodes from Python source."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import tree_sitter
import tree_sitter_python


@dataclass
class ParsedNode:
    """Represents a parsed AST node (Module, Class, or Function).

    Attributes:
        node_type: One of "Module", "Class", or "Function".
        name: Fully qualified name (e.g. "app.services.ast_parser.ParsedNode").
        start_line: 1-based start line number.
        end_line: 1-based end line number.
        start_col: 0-based start column.
        end_col: 0-based end column.
        source_text: Raw source text of the node.
        module_path: File path this node was extracted from.
        params: Parameter names for functions (empty for classes/modules).
        decorators: Decorator strings (without leading @).
        docstring: Extracted docstring content, or None.
        is_async: Whether this is an async function.
        parent_name: Qualified name of the parent node, or None for top-level modules.
    """

    node_type: str
    name: str
    start_line: int
    end_line: int
    start_col: int
    end_col: int
    source_text: str
    module_path: str
    params: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    docstring: str | None = None
    is_async: bool = False
    parent_name: str | None = None


@dataclass
class ParsedEdge:
    """Represents a structural edge (DEFINES).

    Attributes:
        edge_type: The relationship type (currently always "DEFINES").
        source_name: Qualified name of the parent node.
        target_name: Qualified name of the child node.
        source_type: Node type of the source ("Module", "Class", or "Function").
        target_type: Node type of the target ("Class" or "Function").
    """

    edge_type: str
    source_name: str
    target_name: str
    source_type: str
    target_type: str


@dataclass
class ParseResult:
    """Result of parsing a single file.

    Attributes:
        nodes: All extracted structural nodes.
        edges: All extracted DEFINES edges.
        checksum: SHA-256 hex digest of the source content.
        module_path: File path that was parsed.
    """

    nodes: list[ParsedNode]
    edges: list[ParsedEdge]
    checksum: str
    module_path: str


def _get_parser() -> tree_sitter.Parser:
    """Create and return a tree-sitter parser configured for Python."""
    lang = tree_sitter.Language(tree_sitter_python.language())
    return tree_sitter.Parser(lang)


def compute_checksum(source: str) -> str:
    """Compute SHA-256 checksum of source content.

    Args:
        source: The source code string.

    Returns:
        Hex digest of the SHA-256 hash.
    """
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _extract_decorators(node: tree_sitter.Node) -> list[str]:
    """Extract decorator names from a class or function definition.

    Args:
        node: A tree-sitter node of type class_definition or function_definition.

    Returns:
        List of decorator strings (without leading @).
    """
    decorators: list[str] = []
    parent = node.parent
    if parent and parent.type == "decorated_definition":
        for child in parent.children:
            if child.type == "decorator":
                decorators.append(child.text.decode("utf-8").lstrip("@").strip())
    return decorators


def _extract_docstring(node: tree_sitter.Node) -> str | None:
    """Extract docstring from a class or function body.

    Args:
        node: A tree-sitter node of type class_definition or function_definition.

    Returns:
        The docstring content with surrounding quotes stripped, or None.
    """
    body = node.child_by_field_name("body")
    if body is None:
        return None
    for child in body.named_children:
        if child.type == "expression_statement":
            expr = child.named_children[0] if child.named_children else None
            if expr and expr.type == "string":
                text = expr.text.decode("utf-8")
                for quote in ('"""', "'''"):
                    if text.startswith(quote) and text.endswith(quote):
                        return text[3:-3].strip()
                return text[1:-1].strip()
        break  # Only check first statement
    return None


def _extract_params(node: tree_sitter.Node) -> list[str]:
    """Extract parameter names from a function definition.

    Args:
        node: A tree-sitter node of type function_definition.

    Returns:
        List of parameter name strings (with * or ** prefixes where applicable).
    """
    params_node = node.child_by_field_name("parameters")
    if params_node is None:
        return []
    params: list[str] = []
    for child in params_node.named_children:
        if child.type == "identifier":
            params.append(child.text.decode("utf-8"))
        elif child.type in ("default_parameter", "typed_parameter", "typed_default_parameter"):
            name_node = child.child_by_field_name("name") or (
                child.named_children[0] if child.named_children else None
            )
            if name_node:
                params.append(name_node.text.decode("utf-8"))
        elif child.type == "list_splat_pattern":
            if child.named_children:
                params.append("*" + child.named_children[0].text.decode("utf-8"))
        elif child.type == "dictionary_splat_pattern":
            if child.named_children:
                params.append("**" + child.named_children[0].text.decode("utf-8"))
    return params


def parse_file(source: str, file_path: str) -> ParseResult:
    """Parse a Python source file and extract structural nodes and edges.

    Walks the tree-sitter AST to find module, class, and function definitions.
    Produces ParsedNode entries for each and DEFINES edges linking parents to children.

    Args:
        source: The Python source code as a string.
        file_path: The file path (used as module_path and to derive the module name).

    Returns:
        ParseResult with all extracted nodes, edges, and a SHA-256 checksum.
    """
    parser = _get_parser()
    tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node

    checksum = compute_checksum(source)
    nodes: list[ParsedNode] = []
    edges: list[ParsedEdge] = []

    module_name = file_path.replace("/", ".").replace("\\", ".").removesuffix(".py")

    module_node = ParsedNode(
        node_type="Module",
        name=module_name,
        start_line=root.start_point[0] + 1,
        end_line=root.end_point[0] + 1,
        start_col=0,
        end_col=0,
        source_text=source,
        module_path=file_path,
    )
    nodes.append(module_node)

    def _walk(ts_node: tree_sitter.Node, parent_name: str, parent_type: str) -> None:
        """Recursively walk the AST and extract class/function nodes.

        Args:
            ts_node: The current tree-sitter node to inspect.
            parent_name: Qualified name of the enclosing scope.
            parent_type: Node type of the enclosing scope.
        """
        for child in ts_node.children:
            actual_child = child
            is_decorated = child.type == "decorated_definition"

            if is_decorated:
                for sub in child.children:
                    if sub.type in ("class_definition", "function_definition"):
                        actual_child = sub
                        break
                else:
                    continue

            if actual_child.type == "class_definition":
                _process_class(actual_child, parent_name, parent_type)
            elif actual_child.type == "function_definition":
                _process_function(child, actual_child, parent_name, parent_type, is_decorated)

    def _process_class(
        actual_child: tree_sitter.Node, parent_name: str, parent_type: str
    ) -> None:
        """Extract a class definition node and recurse into its body.

        Args:
            actual_child: The class_definition tree-sitter node.
            parent_name: Qualified name of the enclosing scope.
            parent_type: Node type of the enclosing scope.
        """
        name_node = actual_child.child_by_field_name("name")
        if name_node is None:
            return
        name = name_node.text.decode("utf-8")
        qualified_name = f"{parent_name}.{name}" if parent_type != "Module" else f"{module_name}.{name}"

        parsed = ParsedNode(
            node_type="Class",
            name=qualified_name,
            start_line=actual_child.start_point[0] + 1,
            end_line=actual_child.end_point[0] + 1,
            start_col=actual_child.start_point[1],
            end_col=actual_child.end_point[1],
            source_text=actual_child.text.decode("utf-8"),
            module_path=file_path,
            decorators=_extract_decorators(actual_child),
            docstring=_extract_docstring(actual_child),
            parent_name=parent_name,
        )
        nodes.append(parsed)
        edges.append(ParsedEdge(
            edge_type="DEFINES",
            source_name=parent_name,
            target_name=qualified_name,
            source_type=parent_type,
            target_type="Class",
        ))

        body = actual_child.child_by_field_name("body")
        if body:
            _walk(body, qualified_name, "Class")

    def _process_function(
        child: tree_sitter.Node,
        actual_child: tree_sitter.Node,
        parent_name: str,
        parent_type: str,
        is_decorated: bool,
    ) -> None:
        """Extract a function definition node and recurse into its body.

        Args:
            child: The original child node (may be decorated_definition wrapper).
            actual_child: The function_definition tree-sitter node.
            parent_name: Qualified name of the enclosing scope.
            parent_type: Node type of the enclosing scope.
            is_decorated: Whether the function is wrapped in a decorated_definition.
        """
        name_node = actual_child.child_by_field_name("name")
        if name_node is None:
            return
        name = name_node.text.decode("utf-8")
        qualified_name = f"{parent_name}.{name}"

        # Detect async: the "async" keyword is a direct child of function_definition
        is_async = any(c.type == "async" for c in actual_child.children)

        parsed = ParsedNode(
            node_type="Function",
            name=qualified_name,
            start_line=actual_child.start_point[0] + 1,
            end_line=actual_child.end_point[0] + 1,
            start_col=actual_child.start_point[1],
            end_col=actual_child.end_point[1],
            source_text=actual_child.text.decode("utf-8"),
            module_path=file_path,
            params=_extract_params(actual_child),
            decorators=_extract_decorators(actual_child),
            docstring=_extract_docstring(actual_child),
            is_async=is_async,
            parent_name=parent_name,
        )
        nodes.append(parsed)
        edges.append(ParsedEdge(
            edge_type="DEFINES",
            source_name=parent_name,
            target_name=qualified_name,
            source_type=parent_type,
            target_type="Function",
        ))

        body = actual_child.child_by_field_name("body")
        if body:
            _walk(body, qualified_name, "Function")

    _walk(root, module_name, "Module")

    return ParseResult(
        nodes=nodes,
        edges=edges,
        checksum=checksum,
        module_path=file_path,
    )
