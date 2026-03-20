"""FastAPI application entrypoint for Bumblebee IDE."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.graph.client import init_client, close_client
from app.routers.index import router as index_router
from app.routers.graph import router as graph_router
from app.routers.logic_pack import router as logic_pack_router
from app.routers.files import router as files_router
from app.routers.websocket import router as websocket_router
from app.routers.codegen import router as codegen_router
from app.routers.edit import router as edit_router
from app.routers.chat import router as chat_router
from app.routers.logic_nodes import router as logic_nodes_router
from app.routers.edges import router as edges_router
from app.routers.variables import router as variables_router
from app.routers.import_router import router as import_router
from app.routers.flows import router as flows_router
from app.routers.vfs import router as vfs_router
from app.routers.compose import router as compose_router
from app.routers.type_shapes import router as type_shapes_router
from app.routers.cypher_eval import router as cypher_eval_router
from app.routers.suggestions import router as suggestions_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Manage application lifecycle - initialize and cleanup resources."""
    init_client()

    # Initialize 800-series graph indexes
    try:
        from app.services.crud.logic_node_service import ensure_indexes
        ensure_indexes()
        logger.info("800-series graph indexes initialized")
    except Exception:
        logger.debug("Could not initialize 800-series indexes (FalkorDB may not be running)")

    # Start file watcher if watch_path is set
    if settings.watch_path:
        try:
            from app.services.watchers.file_watcher import start_watcher

            loop = asyncio.get_event_loop()
            start_watcher(settings.watch_path, loop=loop)
            logger.info("File watcher started for: %s", settings.watch_path)
        except Exception:
            logger.exception("Failed to start file watcher")

    yield

    # Stop file watcher
    try:
        from app.services.watchers.file_watcher import stop_watcher

        stop_watcher()
    except Exception:
        logger.debug("File watcher cleanup skipped")

    close_client()


app = FastAPI(
    title="Bumblebee IDE",
    description="Visual Logic Engine - treats codebases as living graphs",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(index_router)
app.include_router(graph_router)
app.include_router(logic_pack_router)
app.include_router(files_router)
app.include_router(websocket_router)
app.include_router(codegen_router)
app.include_router(edit_router)
app.include_router(chat_router)

# 800-series Code-as-Data routers
app.include_router(logic_nodes_router)
app.include_router(edges_router)
app.include_router(variables_router)
app.include_router(import_router)
app.include_router(flows_router)
app.include_router(vfs_router)
app.include_router(compose_router)
app.include_router(type_shapes_router)
app.include_router(cypher_eval_router)
app.include_router(suggestions_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
