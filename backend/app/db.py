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


def _linked_ids(column: str, role: str, client: Client | None = None) -> set[str] | None:
    """Ids of merchants/riders that someone can actually sign in as.

    Returns None when `user_profiles` cannot be read, so callers fall back to
    serving every row rather than showing an empty app.
    """
    sb = client or get_supabase()
    try:
        rows = sb.table("user_profiles").select(column).eq("role", role).execute().data or []
    except Exception:
        return None
    return {str(row[column]) for row in rows if row.get(column)}


def merchant_ids_with_login(client: Client | None = None) -> set[str] | None:
    """Merchants with a partner login, so an order placed there can be accepted."""
    return _linked_ids("merchant_id", "partner", client)


def rider_ids_with_login(client: Client | None = None) -> set[str] | None:
    """Riders with a login, so an assigned delivery can actually be worked.

    Rider identity lives in trusted auth app_metadata, which is the fallback
    until `user_profiles.rider_id` exists.
    """
    sb = client or get_supabase()
    from_profiles = _linked_ids("rider_id", "rider", sb)
    if from_profiles:
        return from_profiles
    try:
        users = sb.auth.admin.list_users()
    except Exception:
        return None
    found = set()
    for user in users:
        metadata = getattr(user, "app_metadata", None) or {}
        if metadata.get("role") == "rider" and metadata.get("rider_id"):
            found.add(str(metadata["rider_id"]))
    return found
