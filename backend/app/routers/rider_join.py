import logging
from math import asin, cos, radians, sin, sqrt
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import get_supabase, rider_geo_available
from .. import workflows as wf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/commerce", tags=["rider-signup"])


class RiderJoinRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    phone: str = Field(min_length=7, max_length=30)
    vehicle: Literal["bike", "scooter", "car"] = "bike"
    zone_id: Optional[str] = Field(default=None, max_length=100)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)


def _distance_km(lat1, lng1, lat2, lng2):
    if None in (lat1, lng1, lat2, lng2):
        return None
    radius = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * radius * asin(sqrt(a))


def _zone_from_location(sb, lat, lng) -> str:
    merchants = sb.table("merchants").select("zone_id,lat,lng").execute().data or []
    if lat is not None and lng is not None:
        ranked = []
        for merchant in merchants:
            distance = _distance_km(lat, lng, merchant.get("lat"), merchant.get("lng"))
            if distance is not None and merchant.get("zone_id"):
                ranked.append((distance, merchant["zone_id"]))
        if ranked:
            ranked.sort(key=lambda item: item[0])
            return ranked[0][1]
    zones = [m.get("zone_id") for m in merchants if m.get("zone_id")]
    return zones[0] if zones else "ZONE_A"


@router.post("/riders/join", status_code=201)
def join_as_rider(body: RiderJoinRequest):
    sb = get_supabase()
    email = body.email.strip().lower()
    name = body.name.strip()
    phone = body.phone.strip()
    zone_id = _zone_from_location(sb, body.lat, body.lng)

    existing_profiles = (
        sb.table("user_profiles")
        .select("user_id")
        .eq("email", email)
        .limit(1)
        .execute()
        .data
        or []
    )
    if existing_profiles:
        raise HTTPException(409, "An account with this email already exists")

    rider_id = str(uuid4())
    rider_row = {
        "id": rider_id,
        "name": name,
        "phone": phone,
        "vehicle": body.vehicle,
        "zone_id": zone_id,
    }
    if rider_geo_available(sb) and body.lat is not None and body.lng is not None:
        rider_row.update(lat=body.lat, lng=body.lng, last_location_at=wf.now())

    try:
        sb.table("riders").insert(rider_row).execute()
    except Exception as exc:
        logger.exception("Could not insert rider row")
        raise HTTPException(400, "Could not create rider profile") from exc

    try:
        response = sb.auth.admin.create_user(
            {
                "email": email,
                "password": body.password,
                "email_confirm": True,
                "user_metadata": {"display_name": name},
                "app_metadata": {
                    "role": "rider",
                    "rider_id": rider_id,
                    "display_name": name,
                },
            }
        )
        user = response.user
        if user is None:
            raise RuntimeError("Supabase did not return the created user")
    except Exception as exc:
        sb.table("riders").delete().eq("id", rider_id).execute()
        raise HTTPException(
            400,
            "Could not create rider login. The email may already be registered or the password may not meet requirements.",
        ) from exc

    profile = {
        "user_id": str(user.id),
        "email": email,
        "display_name": name,
        "role": "rider",
        "customer_id": None,
        "merchant_id": None,
    }
    try:
        sb.table("user_profiles").insert({**profile, "rider_id": rider_id}).execute()
    except Exception:
        try:
            sb.table("user_profiles").insert(profile).execute()
        except Exception as exc:
            # Login still works from trusted auth app_metadata if the live
            # user_profiles.role check has not been migrated to include rider.
            logger.warning("Rider profile row skipped; using auth app_metadata. %s", exc)

    return {
        "created": True,
        "email": email,
        "rider_id": rider_id,
        "zone_id": zone_id,
        "email_verified": True,
        "message": "Rider account created. You can sign in immediately.",
    }
