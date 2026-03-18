"""Hash-based identity system for LogicNodes (TICKET-800).

Implements the dual-identity model: stable UUID7 primary keys + SHA-256 AST hash
for deduplication detection.
"""

from __future__ import annotations

import hashlib
import re
import uuid

import tree_sitter
import tree_sitter_python
from uuid_extensions import uuid7

_BUMBLEBEE_NS = uuid.UUID("d7e6f5a4-b3c2-1d0e-9f8a-7b6c5d4e3f2a")


_parser_instance: tree_sitter.Parser | None = None


def _get_parser() -> tree_sitter.Parser:
    """Return a cached tree-sitter parser configured for Python."""
    global _parser_instance  # pylint: disable=global-statement  # Singleton for performance
    if _parser_instance is None:
        _parser_instance = tree_sitter.Parser(tree_sitter.Language(tree_sitter_python.language()))
    return _parser_instance


def generate_node_id() -> str:
    """Generate a new UUID7 node identifier.

    UUID7 is time-sortable and globally unique, making it suitable for
    primary keys that need temporal ordering.

    Returns:
        String representation of a UUID7.
    """
    return str(uuid7())


def generate_deterministic_node_id(name: str) -> str:
    """Generate a stable node ID from the node's qualified name.

    Uses UUID5 (SHA-1, deterministic) so the same function always
    gets the same ID regardless of when it is indexed.

    Args:
        name: Module-qualified name (e.g. ``app.services.utils.my_function``).

    Returns:
        String representation of a deterministic UUID5.
    """
    return str(uuid.uuid5(_BUMBLEBEE_NS, name))


def _canonicalize_ast(source_text: str) -> str:
    """Produce a canonical string representation of Python source for hashing.

    Canonicalization rules (from docs/schema.md Section 3.1):
    1. Parse source text with tree-sitter.
    2. Strip comments and docstrings.
    3. Normalize whitespace (single space between tokens, no trailing whitespace).
    4. Sort decorator list alphabetically.
    5. Serialize the normalized AST to a deterministic string representation.

    Args:
        source_text: The raw Python source code.

    Returns:
        A canonical string suitable for hashing.
    """
    parser = _get_parser()
    tree = parser.parse(source_text.encode("utf-8"))
    tokens: list[str] = []
    decorators: list[str] = []
    in_decorator_block = False

    def _walk(node: tree_sitter.Node) -> None:
        nonlocal in_decorator_block

        # Skip comments entirely
        if node.type == "comment":
            return

        # Skip docstrings (string expression as first statement in body)
        if node.type == "expression_statement" and node.parent and node.parent.type == "block":
            if node.parent.named_children and node.parent.named_children[0] == node:
                first_child = node.named_children[0] if node.named_children else None
                if first_child and first_child.type == "string":
                    return

        # Collect decorators for sorting
        if node.type == "decorator":
            decorators.append(node.text.decode("utf-8").lstrip("@").strip())
            in_decorator_block = True
            return

        # When we hit the definition after decorators, flush sorted decorators
        if in_decorator_block and node.type in ("class_definition", "function_definition"):
            for dec in sorted(decorators):
                tokens.append(f"@{dec}")
            decorators.clear()
            in_decorator_block = False

        # Leaf nodes contribute tokens
        if node.child_count == 0:
            text = node.text.decode("utf-8").strip()
            if text:
                tokens.append(text)
        else:
            for child in node.children:
                _walk(child)

    _walk(tree.root_node)

    # Flush any remaining decorators (edge case: decorated at end of file)
    if decorators:
        for dec in sorted(decorators):
            tokens.append(f"@{dec}")
        decorators.clear()

    return " ".join(tokens)


def compute_ast_hash(source_text: str) -> str:
    """Compute SHA-256 hash of the canonical AST representation.

    Used for deduplication detection — two nodes with the same ast_hash contain
    identical logic regardless of formatting, comments, or decorator ordering.

    Args:
        source_text: The raw Python source code of a LogicNode.

    Returns:
        Hex digest of SHA-256 hash of the canonical AST.
    """
    canonical = _canonicalize_ast(source_text)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def detect_signature_change(old_source: str, new_source: str) -> bool:
    """Detect whether a function's signature has changed between two versions.

    Compares parameter names/types and return type annotation. Body changes
    are NOT considered signature changes.

    Args:
        old_source: Previous version of the function source.
        new_source: New version of the function source.

    Returns:
        True if the signature (params or return type) changed.
    """
    old_sig = _extract_signature(old_source)
    new_sig = _extract_signature(new_source)
    return old_sig != new_sig


def _extract_signature(source_text: str) -> dict[str, str | list[dict[str, str | None]]]:
    """Extract the function signature (params + return type) from source.

    Args:
        source_text: Python function source text.

    Returns:
        Dict with 'params' list and 'return_type' string.
    """
    parser = _get_parser()
    tree = parser.parse(source_text.encode("utf-8"))

    result: dict[str, str | list[dict[str, str | None]]] = {
        "params": [],
        "return_type": "",
    }

    def _find_function(node: tree_sitter.Node) -> tree_sitter.Node | None:
        if node.type == "function_definition":
            return node
        for child in node.children:
            found = _find_function(child)
            if found:
                return found
        return None

    func_node = _find_function(tree.root_node)
    if func_node is None:
        return result

    # Extract return type
    return_type_node = func_node.child_by_field_name("return_type")
    if return_type_node:
        result["return_type"] = return_type_node.text.decode("utf-8")

    # Extract parameters
    params_node = func_node.child_by_field_name("parameters")
    params: list[dict[str, str | None]] = []
    if params_node:
        for child in params_node.named_children:
            param_info: dict[str, str | None] = {"name": "", "type": None}
            if child.type == "identifier":
                param_info["name"] = child.text.decode("utf-8")
            elif child.type in ("typed_parameter", "typed_default_parameter"):
                name_node = child.child_by_field_name("name") or (
                    child.named_children[0] if child.named_children else None
                )
                type_node = child.child_by_field_name("type")
                if name_node:
                    param_info["name"] = name_node.text.decode("utf-8")
                if type_node:
                    param_info["type"] = type_node.text.decode("utf-8")
            elif child.type == "default_parameter":
                name_node = child.child_by_field_name("name") or (
                    child.named_children[0] if child.named_children else None
                )
                if name_node:
                    param_info["name"] = name_node.text.decode("utf-8")
            elif child.type == "list_splat_pattern":
                if child.named_children:
                    param_info["name"] = "*" + child.named_children[0].text.decode("utf-8")
            elif child.type == "dictionary_splat_pattern":
                if child.named_children:
                    param_info["name"] = "**" + child.named_children[0].text.decode("utf-8")
            params.append(param_info)
    result["params"] = params
    return result


def extract_signature_text(source_text: str) -> str:
    """Extract the full signature line from a function/class definition.

    Args:
        source_text: Python source text of a function or class.

    Returns:
        The signature line (e.g., 'def foo(x: int) -> bool').
    """
    parser = _get_parser()
    tree = parser.parse(source_text.encode("utf-8"))

    def _find_def(node: tree_sitter.Node) -> tree_sitter.Node | None:
        if node.type in ("function_definition", "class_definition"):
            return node
        for child in node.children:
            found = _find_def(child)
            if found:
                return found
        return None

    def_node = _find_def(tree.root_node)
    if def_node is None:
        # Fallback: return first line
        return source_text.split("\n")[0].rstrip(":")

    # Build signature from start of def to the colon before body
    body_node = def_node.child_by_field_name("body")
    if body_node:
        sig_end = body_node.start_byte
        sig_bytes = source_text.encode("utf-8")[:sig_end]
        sig_text = sig_bytes.decode("utf-8").rstrip().rstrip(":")
        # Collapse multiline signatures to single line
        sig_text = " ".join(line.strip() for line in sig_text.splitlines())
        return sig_text

    return source_text.split("\n")[0].rstrip(":")


def extract_return_type(source_text: str) -> str | None:
    """Extract the return type annotation from a function definition.

    Args:
        source_text: Python function source text.

    Returns:
        Return type as string, or None if not annotated.
    """
    parser = _get_parser()
    tree = parser.parse(source_text.encode("utf-8"))

    def _find_function(node: tree_sitter.Node) -> tree_sitter.Node | None:
        if node.type == "function_definition":
            return node
        for child in node.children:
            found = _find_function(child)
            if found:
                return found
        return None

    func_node = _find_function(tree.root_node)
    if func_node is None:
        return None

    return_type_node = func_node.child_by_field_name("return_type")
    if return_type_node:
        return return_type_node.text.decode("utf-8")
    return None


def extract_params_detailed(source_text: str) -> list[dict[str, str | None]]:
    """Extract detailed parameter specs from a function definition.

    Args:
        source_text: Python function source text.

    Returns:
        List of param dicts with name, type_hint, default, and kind.
    """
    parser = _get_parser()
    tree = parser.parse(source_text.encode("utf-8"))

    def _find_function(node: tree_sitter.Node) -> tree_sitter.Node | None:
        if node.type == "function_definition":
            return node
        for child in node.children:
            found = _find_function(child)
            if found:
                return found
        return None

    func_node = _find_function(tree.root_node)
    if func_node is None:
        return []

    params_node = func_node.child_by_field_name("parameters")
    if params_node is None:
        return []

    params: list[dict[str, str | None]] = []
    seen_star = False

    for child in params_node.children:
        if child.type == ",":
            continue

        # Bare * separator for keyword-only params
        if child.type == "*" and child.text == b"*":
            seen_star = True
            continue

        param: dict[str, str | None] = {
            "name": "",
            "type_hint": None,
            "default": None,
            "kind": "positional_or_keyword",
        }

        if child.type == "identifier":
            param["name"] = child.text.decode("utf-8")
            if seen_star:
                param["kind"] = "keyword_only"

        elif child.type == "typed_parameter":
            name_node = child.child_by_field_name("name") or (
                child.named_children[0] if child.named_children else None
            )
            type_node = child.child_by_field_name("type")
            if name_node:
                param["name"] = name_node.text.decode("utf-8")
            if type_node:
                param["type_hint"] = type_node.text.decode("utf-8")
            if seen_star:
                param["kind"] = "keyword_only"

        elif child.type == "default_parameter":
            name_node = child.child_by_field_name("name") or (
                child.named_children[0] if child.named_children else None
            )
            value_node = child.child_by_field_name("value")
            if name_node:
                param["name"] = name_node.text.decode("utf-8")
            if value_node:
                param["default"] = value_node.text.decode("utf-8")
            if seen_star:
                param["kind"] = "keyword_only"

        elif child.type == "typed_default_parameter":
            name_node = child.child_by_field_name("name") or (
                child.named_children[0] if child.named_children else None
            )
            type_node = child.child_by_field_name("type")
            value_node = child.child_by_field_name("value")
            if name_node:
                param["name"] = name_node.text.decode("utf-8")
            if type_node:
                param["type_hint"] = type_node.text.decode("utf-8")
            if value_node:
                param["default"] = value_node.text.decode("utf-8")
            if seen_star:
                param["kind"] = "keyword_only"

        elif child.type == "list_splat_pattern":
            if child.named_children:
                param["name"] = child.named_children[0].text.decode("utf-8")
            param["kind"] = "var_positional"
            seen_star = True

        elif child.type == "dictionary_splat_pattern":
            if child.named_children:
                param["name"] = child.named_children[0].text.decode("utf-8")
            param["kind"] = "var_keyword"

        else:
            continue

        if param["name"]:
            params.append(param)

    return params
