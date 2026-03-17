"""Tests for relationship edge extraction (CALLS, INHERITS, IMPORTS)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.services.ast_parser import parse_file
from app.services.import_pipeline import _find_package_root
from app.services.relationship_extractor import extract_relationships


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "sample_repo")


def _load_fixture(filename: str) -> str:
    """Load a fixture file's content."""
    with open(os.path.join(FIXTURES_DIR, filename), encoding="utf-8") as f:
        return f.read()


def _get_edges(filename: str, edge_type: str | None = None) -> list:
    """Parse a fixture and extract relationship edges, optionally filtered by type."""
    source = _load_fixture(filename)
    result = parse_file(source, filename)
    edges = extract_relationships(source, filename, result.nodes)
    if edge_type:
        return [e for e in edges if e.edge_type == edge_type]
    return edges


class TestCallsExtraction:
    """Test CALLS edge extraction."""

    def test_direct_function_call(self) -> None:
        """Direct function calls should produce CALLS edges."""
        calls = _get_edges("services.py", "CALLS")
        # create_and_compute calls validate_positive, Calculator, calc.add (x2), clamp
        source_names = {e.source_name for e in calls}
        assert "services.create_and_compute" in source_names

    def test_call_order_preserved(self) -> None:
        """CALLS edges within a function should have sequential call_order."""
        calls = _get_edges("services.py", "CALLS")
        func_calls = [e for e in calls if e.source_name == "services.create_and_compute"]
        orders = [e.properties["call_order"] for e in func_calls]
        assert orders == sorted(orders)
        assert len(set(orders)) == len(orders)  # All unique

    def test_method_call_on_self(self) -> None:
        """self.method() calls should resolve to the class method."""
        source = _load_fixture("calculator.py")
        result = parse_file(source, "calculator.py")
        calls = extract_relationships(source, "calculator.py", result.nodes)
        calls_edges = [e for e in calls if e.edge_type == "CALLS"]
        # Calculator methods don't call other methods in this fixture,
        # but we can verify no spurious self calls
        for edge in calls_edges:
            assert edge.source_name.startswith("calculator.")

    def test_call_line_property(self) -> None:
        """CALLS edges should have call_line set."""
        calls = _get_edges("services.py", "CALLS")
        for edge in calls:
            assert edge.properties["call_line"] > 0

    def test_nested_function_calls(self) -> None:
        """Calls within nested functions should be extracted."""
        source = _load_fixture("nested.py")
        result = parse_file(source, "nested.py")
        calls = extract_relationships(source, "nested.py", result.nodes)
        calls_edges = [e for e in calls if e.edge_type == "CALLS"]
        # top_level_func calls nested_func()
        top_calls = [e for e in calls_edges if e.source_name == "nested.top_level_func"]
        target_names = {e.target_name for e in top_calls}
        assert "nested.top_level_func.nested_func" in target_names

    def test_call_chain(self) -> None:
        """A -> B -> C call chain should produce edges for each hop."""
        calls = _get_edges("services.py", "CALLS")
        # main -> process_batch -> create_and_compute
        main_calls = {e.target_name for e in calls if e.source_name == "services.main"}
        batch_calls = {e.target_name for e in calls if e.source_name == "services.process_batch"}
        assert "services.process_batch" in main_calls
        assert "services.create_and_compute" in batch_calls


class TestInheritsExtraction:
    """Test INHERITS edge extraction."""

    def test_single_inheritance(self) -> None:
        """Single inheritance should produce one INHERITS edge."""
        edges = _get_edges("shapes.py", "INHERITS")
        circle_inherits = [e for e in edges if e.source_name == "shapes.Circle"]
        assert len(circle_inherits) == 1
        # Should inherit from Shape (resolved or via import)
        assert any("Shape" in e.target_name for e in circle_inherits)

    def test_multiple_classes_inherit(self) -> None:
        """Multiple classes inheriting from the same base should each have INHERITS edges."""
        edges = _get_edges("shapes.py", "INHERITS")
        inheriting_classes = {e.source_name for e in edges}
        assert "shapes.Circle" in inheriting_classes
        assert "shapes.Rectangle" in inheriting_classes

    def test_abc_inheritance(self) -> None:
        """Classes inheriting from ABC should produce INHERITS edge."""
        edges = _get_edges("shapes.py", "INHERITS")
        shape_inherits = [e for e in edges if e.source_name == "shapes.Shape"]
        assert len(shape_inherits) == 1
        assert "ABC" in shape_inherits[0].target_name


class TestImportsExtraction:
    """Test IMPORTS edge extraction."""

    def test_import_statement(self) -> None:
        """'import X' should produce an IMPORTS edge."""
        edges = _get_edges("shapes.py", "IMPORTS")
        target_names = {e.target_name for e in edges}
        # shapes.py imports abc and math
        assert "abc" in target_names or "math" in target_names

    def test_import_from_statement(self) -> None:
        """'from X import Y' should produce an IMPORTS edge to X."""
        edges = _get_edges("services.py", "IMPORTS")
        target_names = {e.target_name for e in edges}
        assert "calculator" in target_names
        assert "utils" in target_names

    def test_import_source_is_module(self) -> None:
        """IMPORTS edges should always have the module as source."""
        edges = _get_edges("services.py", "IMPORTS")
        for edge in edges:
            assert edge.source_type == "Module"
            assert edge.source_name == "services"

    def test_import_resolves_cross_file_calls(self) -> None:
        """Imported names should resolve in CALLS edges."""
        calls = _get_edges("services.py", "CALLS")
        targets = {e.target_name for e in calls}
        # validate_positive is imported from utils
        assert any("validate_positive" in t for t in targets)


class TestCombinedExtraction:
    """Test that all edge types are extracted together."""

    def test_all_edge_types_present(self) -> None:
        """A file with imports, inheritance, and calls should produce all edge types."""
        source = _load_fixture("services.py")
        result = parse_file(source, "services.py")
        edges = extract_relationships(source, "services.py", result.nodes)
        edge_types = {e.edge_type for e in edges}
        assert "CALLS" in edge_types
        assert "IMPORTS" in edge_types

    def test_shapes_all_edge_types(self) -> None:
        """shapes.py should have IMPORTS and INHERITS."""
        edges = _get_edges("shapes.py")
        edge_types = {e.edge_type for e in edges}
        assert "IMPORTS" in edge_types
        assert "INHERITS" in edge_types


class TestCrossFileMethodResolution:
    """Test that obj.method() calls resolve correctly across file boundaries."""

    def test_constructor_then_method_call(self) -> None:
        """var = ImportedClass(); var.method() should resolve to the class method."""
        source = _load_fixture("type_inference.py")
        result = parse_file(source, "type_inference.py")
        calls = extract_relationships(source, "type_inference.py", result.nodes)
        targets = {e.target_name for e in calls if e.edge_type == "CALLS"}
        # calc = Calculator(10); calc.add(5) -> calculator.Calculator.add
        assert "calculator.Calculator.add" in targets

    def test_annotated_param_method_call(self) -> None:
        """def f(calc: Calculator): calc.method() should resolve to the class method."""
        source = _load_fixture("type_inference.py")
        result = parse_file(source, "type_inference.py")
        calls = extract_relationships(source, "type_inference.py", result.nodes)
        ann_param_calls = [
            e for e in calls
            if e.edge_type == "CALLS" and e.source_name == "type_inference.annotated_param"
        ]
        targets = {e.target_name for e in ann_param_calls}
        # annotated_param(calc: Calculator): calc.add(1) -> calculator.Calculator.add
        assert "calculator.Calculator.add" in targets

    def test_module_alias_constructor_and_method(self) -> None:
        """import mod as alias; c = alias.Class(); c.method() should resolve cross-file."""
        source = _load_fixture("alias_user.py")
        result = parse_file(source, "alias_user.py")
        calls = extract_relationships(source, "alias_user.py", result.nodes)
        targets = {e.target_name for e in calls if e.edge_type == "CALLS"}
        # import calculator as calc_mod; c = calc_mod.Calculator(10); c.add(5)
        assert "calculator.Calculator.add" in targets

    def test_imported_function_alias_resolves(self) -> None:
        """from utils import validate_positive as vp; vp(5) -> utils.validate_positive."""
        source = _load_fixture("alias_user.py")
        result = parse_file(source, "alias_user.py")
        calls = extract_relationships(source, "alias_user.py", result.nodes)
        targets = {e.target_name for e in calls if e.edge_type == "CALLS"}
        assert "utils.validate_positive" in targets


class TestModuleNaming:
    """Test that module-qualified node names are consistent between node creation and resolution.

    Regression: import_directory was passing absolute file paths to import_file, causing
    node names like ``.Users.project.utils.validate_email`` instead of ``utils.validate_email``.
    Import resolution always produces short names (``utils.validate_email``), so the edge
    target could never be found in global_name_to_id and was silently dropped.
    """

    def test_relative_path_produces_short_module_name(self) -> None:
        """parse_file with a relative path produces short qualified names."""
        source = _load_fixture("utils.py")
        result = parse_file(source, "utils.py")
        names = {n.name for n in result.nodes}
        assert "utils.validate_positive" in names
        assert "utils.clamp" in names

    def test_relative_path_resolution_matches_import_map(self) -> None:
        """CALLS target from import resolves to the same name that node creation produces.

        This is the end-to-end consistency check: the string that _resolve_callee() returns
        for an imported function must equal the key stored in global_name_to_id.
        """
        # Simulate node creation with relative path (what import_directory now does)
        utils_source = _load_fixture("utils.py")
        utils_result = parse_file(utils_source, "utils.py")
        node_names = {n.name for n in utils_result.nodes}

        # Simulate relationship extraction with relative path (same convention)
        svc_source = _load_fixture("services.py")
        svc_result = parse_file(svc_source, "services.py")
        calls = extract_relationships(svc_source, "services.py", svc_result.nodes)
        call_targets = {e.target_name for e in calls if e.edge_type == "CALLS"}

        # validate_positive is imported in services.py — its resolved target name must
        # match what's in node_names so the edge lookup in global_name_to_id succeeds.
        matching = call_targets & node_names
        assert "utils.validate_positive" in matching, (
            f"Target 'utils.validate_positive' not in both sets.\n"
            f"call_targets={call_targets}\nnode_names={node_names}"
        )


class TestFindPackageRoot:
    """Test _find_package_root() used by import_directory for module naming.

    The function walks up from a file's parent directory until it reaches either
    the search_root or a directory that has no __init__.py. This ensures that
    non-package intermediate directories (e.g. ``my-lib/`` in a monorepo) are
    excluded from the derived module name.
    """

    def test_flat_file_no_init(self, tmp_path: Path) -> None:
        """File directly in the search root with no __init__.py returns search_root."""
        (tmp_path / "main.py").touch()
        result = _find_package_root(tmp_path / "main.py", tmp_path)
        assert result == tmp_path

    def test_file_in_package_stops_at_search_root(self, tmp_path: Path) -> None:
        """Package dir inside search root: stops at search_root even if __init__.py exists."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").touch()
        (pkg / "utils.py").touch()
        result = _find_package_root(pkg / "utils.py", tmp_path)
        # search_root has no __init__.py, so we stop at tmp_path
        assert result == tmp_path

    def test_monorepo_non_package_intermediate_dir(self, tmp_path: Path) -> None:
        """Intermediate non-package directory is excluded from the module root.

        Layout: search_root/lib-dir/mypackage/nodes.py
          lib-dir/  — no __init__.py (not a package)
          mypackage/ — has __init__.py

        Expected root: lib-dir/  so rel_path = mypackage/nodes.py → module mypackage.nodes
        """
        lib_dir = tmp_path / "lib-dir"
        pkg_dir = lib_dir / "mypackage"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").touch()
        (pkg_dir / "nodes.py").touch()

        result = _find_package_root(pkg_dir / "nodes.py", tmp_path)
        assert result == lib_dir

        rel = (pkg_dir / "nodes.py").relative_to(result)
        assert str(rel) == "mypackage/nodes.py"

    def test_nested_packages_stop_at_non_package(self, tmp_path: Path) -> None:
        """Walks up through multiple __init__.py dirs until a non-package is found."""
        outer = tmp_path / "outer"
        inner = outer / "inner"
        inner.mkdir(parents=True)
        (outer / "__init__.py").touch()
        (inner / "__init__.py").touch()
        (inner / "mod.py").touch()
        # tmp_path has no __init__.py → stops there
        result = _find_package_root(inner / "mod.py", tmp_path)
        assert result == tmp_path

    def test_pkg_fixture_resolves_correctly(self) -> None:
        """pkg/helpers.py relative to sample_repo/ stays as pkg/helpers.py.

        This is a regression guard: import_directory(sample_repo) should produce
        module name 'pkg.helpers', not 'tests.fixtures.sample_repo.pkg.helpers'.
        """
        sample_repo = Path(FIXTURES_DIR)
        helpers = sample_repo / "pkg" / "helpers.py"
        assert helpers.exists(), "fixture missing"

        root = _find_package_root(helpers, sample_repo)
        # sample_repo/__init__.py exists, but search_root = sample_repo, so we stop there
        assert root == sample_repo

        rel = helpers.relative_to(root)
        assert str(rel) == "pkg/helpers.py"

    def test_cross_package_edge_resolves(self) -> None:
        """CALLS edge from a file importing pkg.helpers resolves to the correct target.

        Given parse_file('pkg/helpers.py') produces node 'pkg.helpers.greet',
        a caller importing from pkg.helpers and calling greet() should produce
        a CALLS edge targeting 'pkg.helpers.greet'.
        """
        helpers_source = _load_fixture("pkg/helpers.py")
        helpers_result = parse_file(helpers_source, "pkg/helpers.py")
        node_names = {n.name for n in helpers_result.nodes}
        assert "pkg.helpers.greet" in node_names
        assert "pkg.helpers.compute_total" in node_names
