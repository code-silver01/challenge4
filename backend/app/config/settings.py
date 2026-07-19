"""Application settings loaded from environment variables via pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration — every secret/tunable comes from .env."""

    # --- LLM -----------------------------------------------------------------
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # --- Firestore (optional — in-memory fallback is the default) ------------
    FIRESTORE_PROJECT_ID: str = ""
    USE_FIRESTORE: bool = False

    # --- Server --------------------------------------------------------------
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"  # comma-separated
    RATE_LIMIT_RPM: int = 30
    ENV: str = "dev"  # dev | prod

    # --- Derived helpers -----------------------------------------------------
    @property
    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    """Singleton accessor — cached so .env is read only once."""
    return Settings()
