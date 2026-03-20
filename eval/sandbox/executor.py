"""Sandboxed Python code executor for evaluation tasks.

Executes code in an isolated subprocess with timeout, stdout/stderr capture,
and return value extraction. Both Graph RAG and File RAG conditions use
the same executor — the only difference is what context the model receives.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExecutionResult:
    """Result of a sandboxed code execution."""

    exit_code: int
    stdout: str
    stderr: str
    return_value: Any | None = None
    duration_ms: float = 0.0
    error: str | None = None

    def succeeded(self) -> bool:
        """Whether the execution completed without error."""
        return self.exit_code == 0 and self.error is None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSONL storage."""
        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "return_value": self.return_value,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


def _build_wrapper(user_code: str) -> str:
    """Build the wrapper script that executes user code and captures the result.

    Args:
        user_code: Python source code to execute.

    Returns:
        Complete wrapper script as a string.
    """
    indented = textwrap.indent(user_code, "    ")
    return f"""\
import json
import sys
import os

__result__ = None

try:
{indented}

    # Capture result via answer() if defined
    if callable(locals().get("answer")):
        __result__ = answer()
except Exception as __exc__:
    print(f"EXECUTION_ERROR: {{type(__exc__).__name__}}: {{__exc__}}", file=sys.stderr)
    sys.exit(1)

# Write return value as JSON to a temp file for the harness to read
__result_path__ = os.environ.get("__RESULT_PATH__", "")
if __result_path__ and __result__ is not None:
    try:
        with open(__result_path__, "w") as __f__:
            json.dump(__result__, __f__)
    except (TypeError, ValueError):
        with open(__result_path__, "w") as __f__:
            __f__.write(repr(__result__))
"""


def execute_code(
    code: str,
    repo_path: str | Path,
    timeout_seconds: float = 30.0,
    extra_sys_paths: list[str] | None = None,
) -> ExecutionResult:
    """Execute Python code in an isolated subprocess.

    The code runs with the target repository on sys.path, so it can import
    modules from the codebase being evaluated. A return value can be captured
    by either defining an `answer()` function or assigning to `__result__`.

    Args:
        code: Python source code to execute.
        repo_path: Path to the repository root (added to sys.path).
        timeout_seconds: Maximum execution time before killing the process.
        extra_sys_paths: Additional paths to add to sys.path.

    Returns:
        ExecutionResult with exit code, stdout, stderr, return value, and timing.
    """
    repo_path = Path(repo_path).resolve()

    wrapper = _build_wrapper(code)

    # Write wrapper to a temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, prefix="eval_sandbox_"
    ) as script_file:
        script_file.write(wrapper)
        script_path = script_file.name

    # Temp file for return value
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, prefix="eval_result_"
    ) as result_file:
        result_path = result_file.name

    # Build PYTHONPATH
    sys_paths = [str(repo_path)]
    if extra_sys_paths:
        sys_paths.extend(extra_sys_paths)

    env = {
        "PYTHONPATH": ":".join(sys_paths),
        "PATH": "/usr/bin:/usr/local/bin",
        "__RESULT_PATH__": result_path,
        # Inherit minimal env for Python to work
        "HOME": str(Path.home()),
        "LANG": "en_US.UTF-8",
    }

    start = time.perf_counter()

    try:
        proc = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
            cwd=str(repo_path),
        )
        duration_ms = (time.perf_counter() - start) * 1000

        # Read return value if available
        return_value = None
        result_file_path = Path(result_path)
        if result_file_path.exists() and result_file_path.stat().st_size > 0:
            content = result_file_path.read_text()
            try:
                return_value = json.loads(content)
            except json.JSONDecodeError:
                return_value = content  # raw repr fallback

        return ExecutionResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            return_value=return_value,
            duration_ms=round(duration_ms, 1),
        )

    except subprocess.TimeoutExpired:
        duration_ms = (time.perf_counter() - start) * 1000
        return ExecutionResult(
            exit_code=-1,
            stdout="",
            stderr="",
            duration_ms=round(duration_ms, 1),
            error=f"Execution timed out after {timeout_seconds}s",
        )

    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        return ExecutionResult(
            exit_code=-1,
            stdout="",
            stderr="",
            duration_ms=round(duration_ms, 1),
            error=f"Sandbox error: {exc}",
        )

    finally:
        # Clean up temp files
        Path(script_path).unlink(missing_ok=True)
        Path(result_path).unlink(missing_ok=True)
