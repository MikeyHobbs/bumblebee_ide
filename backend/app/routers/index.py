"""Router for indexing operations."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.graph.indexer import index_file, index_repository
from app.models.exceptions import IndexingError

router = APIRouter(prefix="/api/v1", tags=["indexing"])


class IndexRequest(BaseModel):
    """Request body for full repository indexing."""

    path: str


class IndexFileRequest(BaseModel):
    """Request body for single file indexing."""

    path: str
    repo_root: str = ""


class IndexResponse(BaseModel):
    """Response from indexing operation."""

    files_indexed: int
    files_skipped: int
    nodes_created: int
    edges_created: int


class IndexFileResponse(BaseModel):
    """Response from single file indexing."""

    module_path: str
    nodes_count: int
    edges_count: int
    checksum: str


@router.post("/index", response_model=IndexResponse)
async def trigger_index(request: IndexRequest) -> IndexResponse:
    """Trigger full repository indexing.

    Args:
        request: Contains the path to the repository to index.

    Returns:
        Statistics about the indexing operation.

    Raises:
        HTTPException: If the repository path is invalid or indexing fails.
    """
    try:
        stats = index_repository(request.path)
    except IndexingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return IndexResponse(**stats)


@router.post("/index/file", response_model=IndexFileResponse)
async def trigger_file_index(request: IndexFileRequest) -> IndexFileResponse:
    """Trigger single file indexing.

    Args:
        request: Contains the file path and optional repo root.

    Returns:
        Details about the indexed file including node/edge counts and checksum.

    Raises:
        HTTPException: If the file cannot be read or parsed.
    """
    try:
        result = index_file(request.path, repo_root=request.repo_root)
    except IndexingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return IndexFileResponse(
        module_path=result.module_path,
        nodes_count=len(result.nodes),
        edges_count=len(result.edges),
        checksum=result.checksum,
    )
