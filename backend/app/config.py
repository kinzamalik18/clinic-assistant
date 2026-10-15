"""Application settings, read from environment variables and the repo-level .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

KNOWN_PROVIDERS = ("gemini", "groq")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-2.5-flash"
    groq_api_key: SecretStr = SecretStr("")
    groq_model: str = "llama-3.3-70b-versatile"
    llm_providers: str = "gemini,groq"
    llm_timeout_seconds: float = 30.0

    staff_token: SecretStr = SecretStr("")
    database_path: str = "var/clinic.db"
    knowledge_dir: str = "data/clinic"
    cors_origins: str = "http://localhost:5173"

    # Retrieval: chunks scoring below this are treated as "not covered by the documents".
    retrieval_top_k: int = 4
    retrieval_min_score: float = 2.0

    # Abuse limits.
    chat_rate_limit_per_minute: int = 20
    contact_rate_limit_per_hour: int = 5

    @property
    def provider_order(self) -> list[str]:
        names = [p.strip().lower() for p in self.llm_providers.split(",") if p.strip()]
        unknown = [n for n in names if n not in KNOWN_PROVIDERS]
        if unknown:
            raise ValueError(f"Unknown LLM provider(s) in LLM_PROVIDERS: {', '.join(unknown)}")
        return names

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def resolve(self, relative: str) -> Path:
        path = Path(relative)
        return path if path.is_absolute() else BACKEND_DIR / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
