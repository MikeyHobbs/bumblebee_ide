"""Module loader helper for evaluation tasks.

The sample_app test repo doesn't have __init__.py files and has naming conflicts
(e.g., utils.py shadows utils/ directory). This module provides a reliable way
to load any Python file from the repo regardless of package structure.

Both retrieval conditions get access to this helper equally — it's part of the
sandbox, not part of the retrieval context.
"""

from __future__ import annotations

LOADER_SETUP = '''\
import importlib.util as _ilu
import sys as _sys
import os as _os
import types as _types

def _ensure_package(pkg_path, pkg_name):
    """Ensure a directory is importable as a Python package."""
    if pkg_name in _sys.modules:
        return
    abs_pkg = _os.path.join(_os.getcwd(), pkg_path)
    if _os.path.isdir(abs_pkg):
        pkg = _types.ModuleType(pkg_name)
        pkg.__path__ = [abs_pkg]
        pkg.__package__ = pkg_name
        _sys.modules[pkg_name] = pkg

# Register all subdirectories as packages so cross-module imports work
for _entry in _os.listdir(_os.getcwd()):
    _full = _os.path.join(_os.getcwd(), _entry)
    if _os.path.isdir(_full) and not _entry.startswith((".", "_")):
        _ensure_package(_entry, _entry)

def load_module(relative_path, module_name=None):
    """Load a Python module from a relative file path.

    Args:
        relative_path: Path relative to the repo root (e.g., 'utils/math_helpers.py').
        module_name: Optional module name. Defaults to dotted path (e.g., 'utils.math_helpers').

    Returns:
        The loaded module object.
    """
    if module_name is None:
        # Convert path to dotted module name: utils/math_helpers.py -> utils.math_helpers
        module_name = relative_path.replace("/", ".").replace(".py", "")
    abs_path = _os.path.join(_os.getcwd(), relative_path)
    # Ensure parent package exists
    parts = module_name.split(".")
    if len(parts) > 1:
        _ensure_package(parts[0], parts[0])
    spec = _ilu.spec_from_file_location(module_name, abs_path)
    mod = _ilu.module_from_spec(spec)
    _sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod
'''
