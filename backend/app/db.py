from functools import lru_cache

from supabase import Client, create_client

from .config import get_settings


@lru_cache
def get_supabase() -> Client:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_KEY are not set. Copy .env.example to .env and fill them in."
        )
    return create_client(settings.supabase_url, settings.supabase_key)
