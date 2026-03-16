"""FastAPI application entrypoint for Bumblebee IDE."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI

from app.graph.client import init_client, close_client
from app.routers.index import router as index_router
from app.routers.variables import router as variables_router
from app.routers.graph import router as graph_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Manage application lifecycle - initialize and cleanup resources."""
    init_client()
    yield
    close_client()


app = FastAPI(
    title="Bumblebee IDE",
    description="Visual Logic Engine - treats codebases as living graphs",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(index_router)
app.include_router(variables_router)
app.include_router(graph_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
