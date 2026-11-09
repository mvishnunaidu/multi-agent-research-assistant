"""
config.py — Centralised settings loaded from .env
"""

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API Keys
    gemini_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
    groq_api_key: str = Field(default="")
    deepseek_api_key: str = Field(default="")

    # LLM config
    llm_provider: str = Field(default="gemini")

    # Model names (override in .env if a provider deprecates/renames a model)
    gemini_model: str = Field(default="gemini-1.5-flash")
    gemini_embedding_model: str = Field(
        default="models/gemini-embedding-001"
    )
    openai_model: str = Field(default="gpt-4o-mini")
    groq_model: str = Field(default="qwen/qwen3.8-27b")
    deepseek_model: str = Field(default="deepseek-chat")

    # CORS - comma-separated list of allowed origins for the frontend dev server
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173"
    )

    # Paths
    upload_dir: Path = Field(default=Path("uploads"))
    vectorstore_dir: Path = Field(
        default=Path("vectorstores")
    )

    # Security & limits
    max_upload_size_bytes: int = Field(
        default=20 * 1024 * 1024,  # 20 MB max file size
        description="Maximum allowed upload file size in bytes"
    )
    request_timeout_seconds: int = Field(
        default=90,
        description="Timeout for downstream pipeline operations"
    )

    # App metadata
    app_name: str = Field(
        default="Multi-Agent Research Assistant"
    )
    app_version: str = Field(default="1.0.0")
    debug: bool = Field(default=False)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def ensure_dirs(self):
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.vectorstore_dir.mkdir(parents=True, exist_ok=True)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
settings.ensure_dirs()
