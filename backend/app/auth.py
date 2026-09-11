from __future__ import annotations

from dataclasses import dataclass
import uuid
from typing import Callable, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import get_supabase

bearer = HTTPBearer(auto_error=False)
VALID_ROLES = {"customer", "ops", "partner", "support", "admin", "rider"}


@dataclass(frozen=True)
class AuthPrincipal:
    user_id: str
    email: Optional[str]
    role: str
    customer_id: Optional[str] = None
    merchant_id: Optional[str] = None
    display_name: Optional[str] = None
    rider_id: Optional[str] = None


def _profile_for(user) -> AuthPrincipal:
    """Resolve authorization data from server-controlled profile/app metadata.

    `user_profiles` is the preferred source because users cannot change it from
    the browser. Trusted Supabase app_metadata is kept as a deployment fallback.
    Customer accounts may be linked automatically by their existing customer
    email so the demo remains usable after the RBAC migration is applied.
    """
    sb = get_supabase()
    profile = None
    try:
        rows = (
            sb.table("user_profiles")
            .select("user_id,email,display_name,role,customer_id,merchant_id")
            .eq("user_id", str(user.id))
            .limit(1)
            .execute()
            .data
            or []
        )
        profile = rows[0] if rows else None
    except Exception:
        # Allows deployments to authenticate while the RBAC migration is being
        # rolled out. Authorization still requires trusted app metadata below.
        profile = None

    app_metadata = getattr(user, "app_metadata", None) or {}
    email = getattr(user, "email", None)
    role = (profile or {}).get("role") or app_metadata.get("role")
    customer_id = (profile or {}).get("customer_id") or app_metadata.get("customer_id")
    merchant_id = (profile or {}).get("merchant_id") or app_metadata.get("merchant_id")
    display_name = (profile or {}).get("display_name") or app_metadata.get("display_name")

    # Existing customer records can safely establish a customer identity by the
    # verified Supabase email address. Staff roles are NEVER inferred this way.
    if not role and email:
        try:
            matches = sb.table("customers").select("id,name").eq("email", email).limit(1).execute().data or []
            if matches:
                role = "customer"
                customer_id = matches[0]["id"]
                display_name = display_name or matches[0].get("name")
        except Exception:
            pass

    if not role and email and getattr(user, "email_confirmed_at", None):
        customer_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "resolvex/customer/" + str(user.id)))
        display_name = (getattr(user, "user_metadata", None) or {}).get("name") or email.split("@")[0]
        sb.table("customers").upsert(dict(id=customer_id, name=display_name, email=email, phone="", address="Address collected at checkout", lat=0, lng=0, zone_id="UNASSIGNED"), on_conflict="id").execute()
        role = "customer"
        sb.table("user_profiles").upsert(dict(user_id=str(user.id), email=email, display_name=display_name, role=role, customer_id=customer_id), on_conflict="user_id").execute()

    if role == "rider" and not app_metadata.get("rider_id"):
        raise HTTPException(403, "Rider account is not linked")
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has no ResolveX role. Ask an administrator to assign one.",
        )

    if role == "partner" and not merchant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Partner account is not linked to a merchant.",
        )

    return AuthPrincipal(
        rider_id=app_metadata.get("rider_id"),
        user_id=str(user.id),
        email=email,
        role=role,
        customer_id=str(customer_id) if customer_id else None,
        merchant_id=str(merchant_id) if merchant_id else None,
        display_name=display_name,
    )


def current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> AuthPrincipal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    try:
        response = get_supabase().auth.get_user(credentials.credentials)
        user = response.user
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session") from exc

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    return _profile_for(user)


def require_roles(*roles: str) -> Callable:
    allowed = set(roles)

    def dependency(principal: AuthPrincipal = Depends(current_user)) -> AuthPrincipal:
        if principal.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This area is restricted to: {', '.join(sorted(allowed))}",
            )
        return principal

    return dependency
