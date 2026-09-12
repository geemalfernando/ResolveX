#!/usr/bin/env python3
"""Create one customer, merchant and rider demo account for the delivery workflow."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

ACCOUNTS = {
    "customer": {"email": "customer2@resolvex.demo", "display_name": "Nimal Customer"},
    "partner": {"email": "merchant2@resolvex.demo", "display_name": "Lakeview Restaurant"},
    "rider": {"email": "rider@resolvex.demo", "display_name": "Kasun Rider"},
}


def require_env(name: str, *fallbacks: str) -> str:
    for key in (name, *fallbacks):
        value = os.getenv(key)
        if value:
            return value
    raise SystemExit(f"Missing {name}. Add it to {ROOT / '.env'}")


def auth_headers(secret: str) -> dict[str, str]:
    return {"apikey": secret, "Authorization": f"Bearer {secret}", "Content-Type": "application/json"}


def find_auth_user(url: str, secret: str, email: str) -> dict[str, Any] | None:
    page = 1
    with httpx.Client(timeout=20) as client:
        while True:
            response = client.get(f"{url}/auth/v1/admin/users", headers=auth_headers(secret), params={"page": page, "per_page": 1000})
            response.raise_for_status()
            users = response.json().get("users", [])
            for user in users:
                if (user.get("email") or "").lower() == email.lower():
                    return user
            if len(users) < 1000:
                return None
            page += 1


def upsert_auth_user(url: str, secret: str, email: str, password: str, display_name: str, app_metadata: dict[str, Any]) -> str:
    existing = find_auth_user(url, secret, email)
    body = {"email": email, "password": password, "email_confirm": True, "user_metadata": {"display_name": display_name}, "app_metadata": app_metadata}
    with httpx.Client(timeout=20) as client:
        if existing:
            response = client.put(f"{url}/auth/v1/admin/users/{existing['id']}", headers=auth_headers(secret), json=body)
        else:
            response = client.post(f"{url}/auth/v1/admin/users", headers=auth_headers(secret), json=body)
        response.raise_for_status()
        return response.json()["id"]


def ensure_customer(sb) -> str:
    email = ACCOUNTS["customer"]["email"]
    rows = sb.table("customers").select("id").eq("email", email).limit(1).execute().data or []
    if rows:
        return str(rows[0]["id"])
    row = sb.table("customers").insert({"name": "Nimal Customer", "email": email, "phone": "+94771234567", "address": "12 Galle Road, Colombo 03", "lat": 6.9147, "lng": 79.8486, "zone_id": "ZONE_A"}).execute().data[0]
    return str(row["id"])


def ensure_merchant(sb) -> str:
    name = ACCOUNTS["partner"]["display_name"]
    rows = sb.table("merchants").select("id").eq("name", name).limit(1).execute().data or []
    if rows:
        return str(rows[0]["id"])
    row = sb.table("merchants").insert({"name": name, "zone_id": "ZONE_A", "address": "88 Duplication Road, Colombo 03", "lat": 6.9115, "lng": 79.8520, "avg_prep_minutes": 15}).execute().data[0]
    return str(row["id"])


def ensure_rider(sb) -> str:
    name = ACCOUNTS["rider"]["display_name"]
    rows = sb.table("riders").select("id").eq("name", name).limit(1).execute().data or []
    if rows:
        return str(rows[0]["id"])
    row = sb.table("riders").insert({"name": name, "phone": "+94772345678", "vehicle": "bike", "zone_id": "ZONE_A", "lat": 6.9124, "lng": 79.8504}).execute().data[0]
    return str(row["id"])


def main() -> int:
    url = require_env("SUPABASE_URL").rstrip("/")
    secret = require_env("SUPABASE_SECRET_KEY", "SUPABASE_KEY")
    passwords = {
        "customer": require_env("DEMO_CUSTOMER2_PASSWORD"),
        "partner": require_env("DEMO_MERCHANT2_PASSWORD"),
        "rider": require_env("DEMO_RIDER_PASSWORD"),
    }
    sb = create_client(url, secret)
    customer_id = ensure_customer(sb)
    merchant_id = ensure_merchant(sb)
    rider_id = ensure_rider(sb)
    links = {
        "customer": {"customer_id": customer_id, "merchant_id": None, "rider_id": None},
        "partner": {"customer_id": None, "merchant_id": merchant_id, "rider_id": None},
        "rider": {"customer_id": None, "merchant_id": None, "rider_id": rider_id},
    }
    for role, account in ACCOUNTS.items():
        metadata = {"role": role, "display_name": account["display_name"], **links[role]}
        user_id = upsert_auth_user(url, secret, account["email"], passwords[role], account["display_name"], metadata)
        sb.table("user_profiles").upsert({"user_id": user_id, "email": account["email"], "display_name": account["display_name"], "role": role, **links[role]}, on_conflict="user_id").execute()
    print("Created/updated customer2@resolvex.demo, merchant2@resolvex.demo, and rider@resolvex.demo in ZONE_A.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
