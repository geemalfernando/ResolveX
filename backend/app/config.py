from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central app config, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str = ""
    supabase_key: str = ""
    supabase_publishable_key: str = ""
    supabase_secret_key: str = ""
    supabase_jwks_url: str = ""
    gemini_api_key: str = ""

    # ZONE check: fraction of open orders in a zone that must be late to flag zone-wide delay
    zone_late_ratio_threshold: float = 0.30

    # RIDER_ROUTE check thresholds
    rider_detour_ratio_threshold: float = 1.6
    rider_stationary_minutes_threshold: float = 8.0
    rider_dropoff_distance_threshold_m: float = 150.0

    eta_model_path: str = str(Path(__file__).parent / "ml" / "eta_model.joblib")
    fault_model_path: str = str(Path(__file__).parent / "ml" / "fault_model.joblib")
    auto_action_confidence_threshold: float = 0.85

    support_review_confidence_threshold: float = 0.55

    # Legacy aggregator setting retained for compatibility
    aggregator_confidence_threshold: float = 0.6

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
