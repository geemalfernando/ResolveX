from fastapi import APIRouter, Depends

from ..auth import AuthPrincipal, require_roles
from ..db import get_supabase

router = APIRouter(prefix="/workflow/ops", tags=["workflow"])


@router.get("/positions")
def positions(principal: AuthPrincipal = Depends(require_roles("ops", "admin"))):
    """Return live order positions through the authenticated backend.

    The browser must not query operational tables/views directly with the anon
    key because that would bypass ResolveX role authorization.
    """
    return (
        get_supabase()
        .table("open_order_positions")
        .select("id,zone_id,lat,lng,status,is_late_flagged")
        .execute()
        .data
        or []
    )
