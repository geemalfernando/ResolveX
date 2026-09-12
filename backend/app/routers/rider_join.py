from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import get_supabase
from .. import workflows as wf

router = APIRouter(prefix="/commerce", tags=["rider-signup"])


class RiderJoinRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    phone: str = Field(min_length=7, max_length=30)
    vehicle: Literal["bike", "scooter", "car"] = "bike"
    zone_id: str = Field(min_length=1, max_length=100)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)


@router.post("/riders/join", status_code=201)
def join_as_rider(body: RiderJoinRequest):
    sb = get_supabase()
    email = body.email.strip().lower()
    name = body.name.strip()
    phone = body.phone.strip()
    zone_id = body.zone_id.strip()

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
        "lat": body.lat,
        "lng": body.lng,
        "last_location_at": wf.now() if body.lat is not None and body.lng is not None else None,
    }

    try:
        sb.table("riders").insert(rider_row).execute()
    except Exception as exc:
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

    try:
        sb.table("user_profiles").insert(
            {
                "user_id": str(user.id),
                "email": email,
                "display_name": name,
                "role": "rider",
                "customer_id": None,
                "merchant_id": None,
                "rider_id": rider_id,
            }
        ).execute()
    except Exception as exc:
        try:
            sb.auth.admin.delete_user(str(user.id))
        finally:
            sb.table("riders").delete().eq("id", rider_id).execute()
        raise HTTPException(500, "Rider account could not be linked") from exc

    return {
        "created": True,
        "email": email,
        "rider_id": rider_id,
        "email_verified": True,
        "message": "Rider account created. You can sign in immediately.",
    }
