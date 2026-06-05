from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""
    supabase_jwt_secret: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # AI
    anthropic_api_key: str = ""
    ai_model: str = "anthropic/claude-opus-4-8"
    ai_max_tokens: int = 8000

    # Search
    tavily_api_key: str = ""
    alpha_vantage_api_key: str = ""
    search_provider: str = "tavily"
    search_fallback_provider: str = "google_news"
    search_max_concurrency: int = 8

    # Agent
    agent_user_id: str = ""

    # App
    environment: str = "development"
    frontend_url: str = "http://localhost:5173"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
