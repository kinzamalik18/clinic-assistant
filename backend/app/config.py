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
    gemini_model: str = "gemini-3.8-flash"
    groq_api_key: SecretStr = SecretStr("")
    groq_model: str = "openai/gpt-oss-120b"
    llm_providers: str = "gemini,groq"
    llm_timeout_seconds: float = 30.0

    staff_token: SecretStr = SecretStr("")
    database_path: str = "var/clinic.db"
    knowledge_dir: str = "data/clinic"
    # Built frontend. Served only if the folder exists; in development Vite serves it.
    static_dir: str = "../frontend/dist"

    # Retrieval: chunks scoring below this are treated as "not covered by the documents".
    retrieval_top_k: int = 4
    retrieval_min_score: float = 2.0

    # Abuse limits.
    chat_rate_limit_per_minute: int = 20
    contact_rate_limit_per_hour: int = 5
    booking_rate_limit_per_hour: int = 3

    # Scheduling. Times are shown and checked in the clinic's own time zone.
    clinic_timezone: str = "America/New_York"
    treatment_rooms: int = 3
    booking_lead_minutes: int = 120
    booking_horizon_days: int = 14

    @property
    def provider_order(self) -> list[str]:
        names = [p.strip().lower() for p in self.llm_providers.split(",") if p.strip()]
        unknown = [n for n in names if n not in KNOWN_PROVIDERS]
        if unknown:
            raise ValueError(f"Unknown LLM provider(s) in LLM_PROVIDERS: {', '.join(unknown)}")
        return names

    def resolve(self, relative: str) -> Path:
        path = Path(relative)
        return path if path.is_absolute() else BACKEND_DIR / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
