from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central app config, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")

    supabase_url: str = ""
    supabase_key: str = ""
    gemini_api_key: str = ""

    # ZONE check: fraction of open orders in a zone that must be late to flag zone-wide delay
    zone_late_ratio_threshold: float = 0.30

    # RIDER_ROUTE check thresholds
    rider_detour_ratio_threshold: float = 1.6
    rider_stationary_minutes_threshold: float = 8.0
    rider_dropoff_distance_threshold_m: float = 150.0

    # Aggregator
    aggregator_confidence_threshold: float = 0.6

    cors_origins: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
