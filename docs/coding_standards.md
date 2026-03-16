# Coding Standards: Bumblebee IDE

## 1. Guiding Principle

All Python code in this project **must** conform to [PEP 8](https://peps.python.org/pep-0008/) and achieve a **Pylint score of 9.5 or higher**. Code that falls below this threshold must be refactored before merge.

---

## 2. Style & Formatting

### 2.1 PEP 8 Compliance
- **Indentation:** 4 spaces per level. No tabs.
- **Line length:** Maximum **120 characters** (PEP 8 default is 79; we relax this for readability in a modern codebase while remaining PEP 8–compatible via tool configuration).
- **Blank lines:** Two blank lines before top-level definitions (functions, classes). One blank line between methods inside a class.
- **Imports:** Group in the standard order — stdlib → third-party → local — separated by a blank line. Use absolute imports. Avoid wildcard imports (`from x import *`).
- **Trailing whitespace:** None. Configure your editor to strip it on save.
- **String quotes:** Use double quotes (`"`) for strings by default. Single quotes are acceptable only inside f-strings or to avoid escaping.

### 2.2 Autoformatters & Linters
| Tool | Purpose | Config |
|------|---------|--------|
| **Black** | Autoformatter | `line-length = 120` |
| **isort** | Import sorting | `profile = "black"`, `line_length = 120` |
| **Pylint** | Static analysis | `min-score = 9.5`, `max-line-length = 120` |
| **mypy** | Type checking | `strict = true` (recommended) |

Run before every commit:
```bash
black .
isort .
pylint --fail-under=9.5 backend/
mypy backend/
```

---

## 3. Naming Conventions (PEP 8)

| Entity | Convention | Example |
|--------|-----------|---------|
| **Modules** | `snake_case` | `ast_parser.py` |
| **Packages** | `snake_case` | `graph_sync/` |
| **Classes** | `PascalCase` | `LogicPackBuilder` |
| **Functions / Methods** | `snake_case` | `build_subgraph()` |
| **Constants** | `UPPER_SNAKE_CASE` | `MAX_HOP_DEPTH` |
| **Variables** | `snake_case` | `node_count` |
| **Private members** | Leading underscore | `_internal_cache` |
| **Type variables** | `PascalCase` | `NodeT` |

---

## 4. Documentation

### 4.1 Docstrings
- **Required** on every public module, class, function, and method.
- Use **Google-style** docstrings:
```python
def fetch_logic_pack(function_id: str, hops: int = 2) -> dict:
    """Retrieve an atomic subgraph centered on a function node.

    Args:
        function_id: The FalkorDB node ID of the target function.
        hops: Number of relationship hops to traverse.

    Returns:
        A dictionary representing the Logic Pack subgraph.

    Raises:
        NodeNotFoundError: If function_id does not exist in the graph.
    """
```
- One-liner docstrings are acceptable for trivially simple helpers.

### 4.2 Inline Comments
- Use sparingly and only to explain *why*, not *what*.
- Place on the line above the code, not at the end of the line (except for very short clarifications).

---

## 5. Type Hints

- **All** function signatures must include type hints for parameters and return values.
- Use `from __future__ import annotations` at the top of every module for modern annotation syntax.
- Prefer built-in generics (`list[str]`, `dict[str, int]`) over `typing` equivalents where Python 3.10+ is targeted.

```python
from __future__ import annotations

def resolve_callers(node_id: str, depth: int = 1) -> list[dict[str, str]]:
    ...
```

---

## 6. Error Handling

- Never use bare `except:`. Always catch specific exceptions.
- Use custom exception classes (inheriting from a project-level base) for domain errors.
- Let unexpected exceptions propagate; do not silently swallow them.

```python
# Good
try:
    result = db.query(cypher)
except FalkorConnectionError as exc:
    logger.error("Graph query failed: %s", exc)
    raise

# Bad
try:
    result = db.query(cypher)
except:
    pass
```

---

## 7. Project Structure

Follow the layout established in TICKET-101:
```
backend/
    app/
        __init__.py
        main.py            # FastAPI entrypoint
        routers/           # API route modules
        services/          # Business logic
        models/            # Pydantic schemas & DB models
        graph/             # FalkorDB queries & Logic Pack builders
    tests/
        conftest.py
        test_*.py
```

- Keep modules focused — one primary responsibility per file.
- Place reusable utilities in `backend/app/utils/`.

---

## 8. Testing

- Use **pytest** as the test framework.
- Minimum **80% line coverage** on the backend; track with `pytest-cov`.
- Name test files `test_<module>.py` and test functions `test_<behavior>()`.
- Use fixtures and parametrize for DRY tests.

```bash
pytest --cov=backend/app --cov-fail-under=80
```

---

## 9. Git & CI Discipline

- **Branch naming:** `feature/<ticket>-<short-desc>`, `fix/<ticket>-<short-desc>`.
- **Commit messages:** Imperative mood, reference ticket ID — e.g., `TICKET-102: Implement incremental AST parser`.
- **Pre-commit hooks:** Enforce Black, isort, and Pylint via a `.pre-commit-config.yaml`.
- **CI gate:** Pull requests must pass `pylint --fail-under=9.5` and all tests before merge.

---

## 10. Pylint Overrides

If a Pylint rule must be suppressed, disable it **inline on the specific line** with a justification comment:

```python
graph_result = db.execute(query)  # pylint: disable=no-member  # FalkorDB dynamic API
```

- Never add broad disables at the module level without team review.
- Periodically audit all `pylint: disable` comments and remove those that are no longer needed.
