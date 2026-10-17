"""Application settings, read from the environment only (see .env.example)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"

    # Database: SQLite for tests, Supabase Postgres (pooler URL) everywhere else.
    database_url: str = "sqlite:///./rs_assist.db"

    # Supabase Auth
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""  # legacy HS256 secret; JWKS is used when empty

    # LLM
    llm_provider: Literal["anthropic", "openai_compatible", "fake"] = "fake"
    llm_model: str = "claude-opus-5-5"
    llm_effort: Literal["low", "medium", "high"] = "low"
    llm_timeout_seconds: float = 5.0
    llm_base_url: str = ""  # OpenRouter by default; set to Ollama's /v1 to run locally
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""
    fake_llm_delay_ms: int = 0
    llm_debug_log: bool = False

    # OCR
    ocr_engine: Literal["tesseract", "fake"] = "tesseract"
    ocr_confidence_threshold: float = 70.0
    upload_max_bytes: int = 8 * 1024 * 1024

    # Privacy
    field_encryption_key: str = Field(default="")

    # Serving
    frontend_dist: str = "../frontend/dist"


@lru_cache
def get_settings() -> Settings:
    return Settings()
