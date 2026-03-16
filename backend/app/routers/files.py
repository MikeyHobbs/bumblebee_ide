"""Router for file content serving (for Monaco editor)."""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Query

from app.config import settings

router = APIRouter(prefix="/api/v1", tags=["files"])


@router.get("/file")
async def get_file_content(
    path: str = Query(..., description="Relative path within the indexed repository"),
) -> dict[str, str]:
    """Serve raw file content from the indexed repo for Monaco.

    Args:
        path: Relative file path within the watched repository.

    Returns:
        Dict with path and content keys.
    """
    if not settings.watch_path:
        raise HTTPException(status_code=400, detail="No repository indexed. Use POST /api/v1/index first.")

    abs_path = os.path.join(os.path.abspath(settings.watch_path), path)

    # Prevent directory traversal
    repo_root = os.path.abspath(settings.watch_path)
    if not os.path.abspath(abs_path).startswith(repo_root):
        raise HTTPException(status_code=403, detail="Path traversal not allowed")

    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    try:
        with open(abs_path, encoding="utf-8") as f:
            content = f.read()
        return {"path": path, "content": content}
    except UnicodeDecodeError:
        raise HTTPException(status_code=415, detail="File is not valid UTF-8 text") from None
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot read file: {exc}") from exc
