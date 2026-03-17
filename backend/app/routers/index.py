"""Router for indexing operations."""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.graph.indexer import index_file
from app.models.exceptions import IndexingError
from app.routers.websocket import broadcast
from app.services.persistence.import_pipeline import import_directory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["indexing"])

# In-memory job tracking
_jobs: dict[str, dict[str, object]] = {}


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


class IndexJobResponse(BaseModel):
    """Response from async indexing trigger."""

    job_id: str
    status: str


class IndexJobStatus(BaseModel):
    """Status of an indexing job."""

    job_id: str
    status: str
    files_done: int
    files_total: int
    current_file: str


async def _run_index_job(job_id: str, repo_path: str) -> None:
    """Run repository indexing in the background with progress reporting.

    Args:
        job_id: Unique job identifier.
        repo_path: Path to the repository to index.
    """
    progress_queue: asyncio.Queue[tuple[str, int, int]] = asyncio.Queue()

    def _progress_cb(file_path: str, total: int, done: int) -> None:
        progress_queue.put_nowait((file_path, total, done))

    async def _drain_progress() -> None:
        while True:
            try:
                file_path, total, done = progress_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            _jobs[job_id] = {
                "status": "indexing",
                "files_done": done,
                "files_total": total,
                "current_file": file_path,
            }
            await broadcast("index:progress", {"file": file_path, "done": done, "total": total})

    try:
        import_task = asyncio.get_event_loop().run_in_executor(
            None, lambda: import_directory(repo_path, progress_callback=_progress_cb)
        )
        while not import_task.done():
            await _drain_progress()
            await asyncio.sleep(0.1)
        report = await import_task
        await _drain_progress()
        _jobs[job_id] = {
            "status": "complete",
            "files_done": report.files_processed,
            "files_total": report.files_processed,
            "current_file": "",
        }
        await broadcast("index:progress", {"file": "", "done": report.files_processed, "total": report.files_processed})
        await broadcast("graph:updated", {"affected_modules": []})

        # Start file watcher for the indexed repo
        try:
            from app.services.watchers.file_watcher import start_watcher  # pylint: disable=import-outside-toplevel

            loop = asyncio.get_event_loop()
            start_watcher(repo_path, loop=loop)
            logger.info("File watcher started after index for: %s", repo_path)
        except Exception:  # pylint: disable=broad-except  # Watcher is optional
            logger.debug("Could not start file watcher after index")
    except Exception:
        logger.exception("Indexing job %s failed", job_id)
        _jobs[job_id] = {
            "status": "error",
            "files_done": 0,
            "files_total": 0,
            "current_file": "",
        }
        await broadcast("index:progress", {"file": "", "done": 1, "total": 1})


@router.post("/index", status_code=202)
async def trigger_index(request: IndexRequest) -> JSONResponse:
    """Trigger full repository indexing asynchronously.

    Returns HTTP 202 immediately with a job_id. The indexing runs in the background
    and sends progress via WebSocket events. Poll GET /api/v1/index/status/{job_id}
    for status.

    Args:
        request: Contains the path to the repository to index.

    Returns:
        JSON with job_id and status.

    Raises:
        HTTPException: If the repository path is invalid.
    """
    import os

    repo_path = os.path.abspath(request.path)
    if not os.path.isdir(repo_path):
        raise HTTPException(status_code=400, detail=f"Repository path does not exist: {request.path}")

    settings.watch_path = repo_path

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "indexing", "files_done": 0, "files_total": 0, "current_file": ""}
    asyncio.create_task(_run_index_job(job_id, request.path))

    return JSONResponse(
        status_code=202,
        content={"job_id": job_id, "status": "indexing"},
    )


@router.get("/index/status/{job_id}")
async def get_index_status(job_id: str) -> IndexJobStatus:
    """Get the status of an indexing job.

    Args:
        job_id: The job identifier returned from POST /index.

    Returns:
        Current job status including progress.

    Raises:
        HTTPException: If the job_id is not found.
    """
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return IndexJobStatus(
        job_id=job_id,
        status=str(job["status"]),
        files_done=int(job.get("files_done", 0)),  # type: ignore[arg-type]
        files_total=int(job.get("files_total", 0)),  # type: ignore[arg-type]
        current_file=str(job.get("current_file", "")),
    )


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
