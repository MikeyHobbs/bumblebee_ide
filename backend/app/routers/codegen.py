"""Router for code generation endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.graph.client import get_graph
from app.models.exceptions import NodeNotFoundError
from app.services.codegen.code_generator import (
    CodeGenerationError,
    generate_function_from_graph,
    generate_module,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/codegen", tags=["codegen"])


class CodegenResponse(BaseModel):
    """Response containing generated source code.

    Attributes:
        source: The generated Python source code.
        module_name: The qualified name of the module or function.
    """

    source: str
    module_name: str


@router.post("/{module_id}", response_model=CodegenResponse)
async def generate_module_source(module_id: str) -> CodegenResponse:
    """Generate full module source from graph.

    Args:
        module_id: The qualified name of the module in the graph.

    Returns:
        CodegenResponse with the generated source code.
    """
    try:
        source = generate_module(module_id)
        return CodegenResponse(source=source, module_name=module_id)
    except NodeNotFoundError:
        raise HTTPException(status_code=404, detail=f"Module not found: {module_id}") from None
    except CodeGenerationError as exc:
        raise HTTPException(status_code=500, detail=f"Code generation failed: {exc}") from exc
    except Exception as exc:
        logger.exception("Unexpected error generating module source")
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}") from exc


@router.post("/function/{function_id}", response_model=CodegenResponse)
async def generate_function_source(function_id: str) -> CodegenResponse:
    """Generate single function source from graph.

    Args:
        function_id: The qualified name of the function in the graph.

    Returns:
        CodegenResponse with the generated source code.
    """
    try:
        source = generate_function_from_graph(function_id)
        return CodegenResponse(source=source, module_name=function_id)
    except NodeNotFoundError:
        raise HTTPException(status_code=404, detail=f"Function not found: {function_id}") from None
    except CodeGenerationError as exc:
        raise HTTPException(status_code=500, detail=f"Code generation failed: {exc}") from exc
    except Exception as exc:
        logger.exception("Unexpected error generating function source")
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}") from exc
