from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Tavily Search API
    TAVILY_API_KEY: str = "tvly-xxxxxxxx"

    # Bifrost gateway
    BIFROST_BASE_URL: str = "http://localhost:8080/v1"
    BIFROST_API_KEY: str = "dummy"
    LLM_MODEL: str = "gemini/gemini-2.5-flash"
    LLM_VERIFY_MODEL: Optional[str] = None

    # Pipeline behaviour
    WINDOW_DAYS: int = 30
    MAX_QUERIES: int = 8
    MAX_RESULTS_PER_QUERY: int = 6
    SEARCH_DEPTH: str = "basic"
    ENABLE_EXTRACT: bool = True
    EXTRACT_TOP_N: int = 4
    VERIFY_CLAIMS: bool = True
    CONCURRENCY: int = 4
    CACHE_TTL_HOURS: int = 12
    MOCK_MODE: bool = False
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
