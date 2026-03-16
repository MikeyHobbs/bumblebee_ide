"""Router for variable timeline and search endpoints."""

from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/v1", tags=["variables"])


class TimelineEntryResponse(BaseModel):
    """A single entry in a mutation timeline."""

    edge_type: str
    function_name: str
    variable_name: str
    line: int
    seq: int
    properties: dict[str, str | int | bool | None]


class TimelineResponse(BaseModel):
    """Full mutation timeline for a variable."""

    variable: dict[str, str | int | None]
    origin: TimelineEntryResponse | None
    mutations: list[TimelineEntryResponse]
    reads: list[TimelineEntryResponse]
    passes: list[TimelineEntryResponse]
    returns: list[TimelineEntryResponse]
    feeds: list[TimelineEntryResponse]
    terminal: TimelineEntryResponse | None


class VariableSearchResult(BaseModel):
    """A single variable search result."""

    name: str
    scope: str
    origin_line: int
    origin_func: str
    type_hint: str | None
    module_path: str


@router.get("/variables/{variable_id}/timeline", response_model=TimelineResponse)
async def get_variable_timeline(variable_id: str) -> TimelineResponse:
    """Get the full mutation timeline for a variable.

    The variable_id should be the fully qualified variable name
    (e.g., "module.function.variable_name").
    """
    # This endpoint requires an indexed graph. For now, return a placeholder.
    # In production, this would query FalkorDB directly.
    raise HTTPException(
        status_code=501,
        detail="Timeline query requires FalkorDB. Use POST /api/v1/index first, then query.",
    )


@router.get("/variables/search", response_model=list[VariableSearchResult])
async def search_variables(
    name: str = Query(..., description="Variable name to search for"),
    scope: str | None = Query(None, description="Optional scope filter"),
) -> list[VariableSearchResult]:
    """Search for variables by name, optionally filtered by scope."""
    # This endpoint requires an indexed graph.
    raise HTTPException(
        status_code=501,
        detail="Variable search requires FalkorDB. Use POST /api/v1/index first.",
    )
