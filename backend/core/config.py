"""
config.py — Centralised settings loaded from .env
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    # API Keys
    gemini_api_key: str = Field(default="", env="GEMINI_API_KEY")
    groq_api_key: str = Field(default="", env="GROQ_API_KEY")
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")

    # LLM config
    llm_provider: str = Field(default="gemini", env="LLM_PROVIDER")
    llm_model: str = Field(default="gemini-1.5-flash", env="LLM_MODEL")

    # Vector store
    vector_store: str = Field(default="faiss", env="VECTOR_STORE")

    # Paths
    upload_dir: Path = Field(default=Path("uploads"), env="UPLOAD_DIR")
    vectorstore_dir: Path = Field(default=Path("vectorstores"), env="VECTORSTORE_DIR")

    # App metadata
    app_name: str = Field(default="Multi-Agent Research Assistant", env="APP_NAME")
    app_version: str = Field(default="1.0.0", env="APP_VERSION")
    debug: bool = Field(default=False, env="DEBUG")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    def ensure_dirs(self):
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.vectorstore_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
