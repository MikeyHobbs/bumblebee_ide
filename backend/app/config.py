"""Application configuration via Pydantic Settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    backend_port: int = 8000
    falkor_host: str = "localhost"
    falkor_port: int = 6379
    falkor_graph_name: str = "bumblebee"
    watch_path: str = ""
    ollama_host: str = "http://localhost:11434"
    orchestrator_model: str = "llama3.2:latest"
    cypher_model: str = "llama3.2:latest"


settings = Settings()
