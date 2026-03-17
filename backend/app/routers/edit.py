"""Router for graph-based editing endpoints (TICKET-403, Sprint 4 & 5)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.graph.client import get_graph
from app.graph.logic_pack import build_function_flow_pack
from app.models.exceptions import NodeNotFoundError
from app.services.codegen.write_back import (
    WriteBackError,
    delete_statement,
    insert_statement,
    reorder_statements,
    update_statement,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["edit"])


class UpdateStatementRequest(BaseModel):
    """Request to update a statement's source text."""

    source_text: str


class InsertStatementRequest(BaseModel):
    """Request to insert a new statement."""

    after_statement_id: str | None = None
    source_text: str
    kind: str = "expression"


class ReorderRequest(BaseModel):
    """Request to reorder statements within a function."""

    function_id: str
    statement_ids: list[str]


class GhostPreviewRequest(BaseModel):
    """Request for ghost preview of an edit."""

    path: str
    old_text: str
    new_text: str


class GhostPreviewResponse(BaseModel):
    """Response with ghost preview diffs."""

    added_nodes: list[dict[str, Any]]
    removed_nodes: list[dict[str, Any]]
    added_edges: list[dict[str, Any]]
    removed_edges: list[dict[str, Any]]


class ApplyEditRequest(BaseModel):
    """Request to apply a previewed edit."""

    path: str
    old_text: str
    new_text: str


@router.patch("/graph/statement/{statement_id}")
async def patch_statement(statement_id: str, request: UpdateStatementRequest) -> dict[str, str]:
    """Update a statement's source text in the graph and regenerate the file.

    Args:
        statement_id: Qualified name of the statement node.
        request: Contains the new source text.

    Returns:
        Updated statement info.
    """
    try:
        result = update_statement(statement_id, request.source_text)
        return result
    except NodeNotFoundError:
        raise HTTPException(status_code=404, detail=f"Statement not found: {statement_id}") from None
    except WriteBackError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Update failed: {exc}") from exc


@router.post("/graph/statement")
async def create_statement(request: InsertStatementRequest) -> dict[str, str]:
    """Insert a new statement into a function.

    The function_id is inferred from after_statement_id, or must be provided
    if inserting at the beginning.
    """
    try:
        # Infer function_id from after_statement_id
        if request.after_statement_id:
            graph = get_graph()
            func_result = graph.query(
                "MATCH (f:Function)-[:CONTAINS*1..8]->(s {name: $name}) RETURN f.name",
                params={"name": request.after_statement_id},
            )
            if not func_result.result_set:
                raise HTTPException(status_code=404, detail=f"Statement not found: {request.after_statement_id}")
            function_id = func_result.result_set[0][0]
        else:
            raise HTTPException(status_code=400, detail="after_statement_id is required (or use function_id)")

        result = insert_statement(
            function_id, request.after_statement_id, request.source_text, request.kind
        )
        return result
    except HTTPException:
        raise
    except NodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WriteBackError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Insert failed: {exc}") from exc


@router.delete("/graph/statement/{statement_id}")
async def remove_statement(statement_id: str) -> dict[str, str]:
    """Delete a statement from the graph and regenerate the file."""
    try:
        result = delete_statement(statement_id)
        return result
    except NodeNotFoundError:
        raise HTTPException(status_code=404, detail=f"Statement not found: {statement_id}") from None
    except WriteBackError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Delete failed: {exc}") from exc


@router.patch("/graph/statement/reorder")
async def reorder(request: ReorderRequest) -> dict[str, Any]:
    """Reorder statements within a function."""
    try:
        result = reorder_statements(request.function_id, request.statement_ids)
        return result
    except NodeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WriteBackError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Reorder failed: {exc}") from exc


@router.get("/graph/function/{function_id}/flow")
async def get_function_flow(function_id: str) -> dict[str, Any]:
    """Get the full statement/control flow subgraph for a function."""
    try:
        pack = build_function_flow_pack(function_id)
        return pack
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Flow query failed: {exc}") from exc


@router.post("/edit/preview", response_model=GhostPreviewResponse)
async def ghost_preview(request: GhostPreviewRequest) -> GhostPreviewResponse:
    """Preview the graph impact of an edit without applying it.

    Applies the diff in memory, runs the parser pipeline, and diffs the
    shadow graph against the current graph.
    """
    try:
        from app.services.analysis.ghost_preview import compute_ghost_preview

        result = compute_ghost_preview(request.path, request.old_text, request.new_text)
        return GhostPreviewResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Preview failed: {exc}") from exc


@router.post("/edit/apply")
async def apply_edit(request: ApplyEditRequest) -> dict[str, str]:
    """Apply a previewed edit: write to disk and re-index."""
    try:
        from app.services.analysis.ghost_preview import apply_edit as do_apply

        result = do_apply(request.path, request.old_text, request.new_text)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Apply failed: {exc}") from exc
