"""REST API endpoints for the import pipeline (TICKET-831)."""

from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from app.services.persistence.import_pipeline import ImportReport, import_directory, import_file, import_incremental

router = APIRouter(prefix="/api/v1/import", tags=["import"])


class ImportFileRequest(BaseModel):
    """Request body for importing a single file."""

    path: str


class ImportDirectoryRequest(BaseModel):
    """Request body for importing a directory."""

    path: str
    patterns: list[str] = Field(default_factory=lambda: ["*.py"])


class ImportReportResponse(BaseModel):
    """Response model for import operations."""

    nodes_created: int
    nodes_updated: int
    edges_created: int
    variables_created: int
    errors: list[str]
    files_processed: int


def _report_to_response(report: ImportReport) -> ImportReportResponse:
    """Convert an ImportReport to the response model."""
    return ImportReportResponse(
        nodes_created=report.nodes_created,
        nodes_updated=report.nodes_updated,
        edges_created=report.edges_created,
        variables_created=report.variables_created,
        errors=report.errors,
        files_processed=report.files_processed,
    )


@router.post("/file", status_code=201, response_model=ImportReportResponse)
def import_file_endpoint(data: ImportFileRequest) -> ImportReportResponse:
    """Import a single Python file into the graph."""
    report = import_file(data.path)
    return _report_to_response(report)


@router.post("/directory", status_code=201, response_model=ImportReportResponse)
def import_directory_endpoint(data: ImportDirectoryRequest) -> ImportReportResponse:
    """Import all matching files from a directory."""
    report = import_directory(data.path, patterns=data.patterns)
    return _report_to_response(report)


@router.post("/incremental", status_code=200, response_model=ImportReportResponse)
def import_incremental_endpoint(data: ImportFileRequest) -> ImportReportResponse:
    """Incrementally re-import a file (only changed functions)."""
    report = import_incremental(data.path)
    return _report_to_response(report)
