from functools import lru_cache

from supabase import Client, create_client

from .config import get_settings

_RIDER_GEO_COLUMNS: dict[int, bool] = {}


@lru_cache
def get_supabase() -> Client:
    settings = get_settings()
    supabase_key = settings.supabase_secret_key or settings.supabase_key
    if not settings.supabase_url or not supabase_key:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_SECRET_KEY are not set. Copy .env.example to .env and fill them in."
        )
    return create_client(settings.supabase_url, supabase_key)


def rider_geo_available(client: Client | None = None) -> bool:
    """True when lat/lng/last_location_at exist on public.riders."""
    sb = client or get_supabase()
    key = id(sb)
    if key in _RIDER_GEO_COLUMNS:
        return _RIDER_GEO_COLUMNS[key]
    try:
        sb.table("riders").select("id,lat,lng,last_location_at").limit(1).execute()
        _RIDER_GEO_COLUMNS[key] = True
    except Exception:
        _RIDER_GEO_COLUMNS[key] = False
    return _RIDER_GEO_COLUMNS[key]


def rider_select_columns(client: Client | None = None) -> str:
    if rider_geo_available(client):
        return "id,name,phone,vehicle,zone_id,lat,lng,last_location_at"
    return "id,name,phone,vehicle,zone_id"
