from functools import lru_cache

from supabase import Client, create_client

from .config import get_settings


@lru_cache
def get_supabase() -> Client:
    settings = get_settings()
    supabase_key = settings.supabase_secret_key or settings.supabase_key
    if not settings.supabase_url or not supabase_key:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_SECRET_KEY are not set. Copy .env.example to .env and fill them in."
        )
    return create_client(settings.supabase_url, supabase_key)
