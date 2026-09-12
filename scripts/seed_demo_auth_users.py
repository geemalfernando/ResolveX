#!/usr/bin/env python3
"""Create ResolveX demo Supabase Auth users and RBAC profiles.

This script is intentionally server-side only. It requires SUPABASE_URL and a
SUPABASE_SECRET_KEY (or legacy SUPABASE_KEY) from the repository root .env.

Run the RBAC SQL migration first:
    supabase/migrations/20260912_rbac_auth.sql

For hackathon/demo credentials:
    python scripts/seed_demo_auth_users.py --demo-passwords

For safer custom passwords, export the five DEMO_*_PASSWORD variables and run
without --demo-passwords.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from supabase import create_client

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DEMO_PASSWORDS = {
    "customer": "ResolveX@Customer26",
    "ops": "ResolveX@Ops26",
    "partner": "ResolveX@Partner26",
    "support": "ResolveX@Support26",
    "admin": "ResolveX@Admin26",
}

DEMO_USERS = [
    {"role": "customer", "email": "customer@resolvex.demo", "display_name": "Demo Customer"},
    {"role": "ops", "email": "ops@resolvex.demo", "display_name": "Operations Team"},
    {"role": "partner", "email": "partner@resolvex.demo", "display_name": "Merchant Partner"},
    {"role": "support", "email": "support@resolvex.demo", "display_name": "Support Agent"},
    {"role": "admin", "email": "admin@resolvex.demo", "display_name": "ResolveX Admin"},
]


def require_env(name: str, *fallbacks: str) -> str:
    for key in (name, *fallbacks):
        value = os.getenv(key)
        if value:
            return value
    raise SystemExit(f"Missing {name}. Add it to {ROOT / '.env'} before running this script.")


def password_for(role: str, use_demo_passwords: bool) -> str:
    env_name = f"DEMO_{role.upper()}_PASSWORD"
    value = os.getenv(env_name)
    if value:
        return value
    if use_demo_passwords:
        return DEMO_PASSWORDS[role]
    raise SystemExit(
        f"Missing {env_name}. Export it, or rerun with --demo-passwords for the hackathon-only credentials."
    )


def auth_headers(secret: str) -> dict[str, str]:
    return {
        "apikey": secret,
        "Authorization": f"Bearer {secret}",
        "Content-Type": "application/json",
    }


def existing_auth_users(base_url: str, secret: str) -> dict[str, dict[str, Any]]:
    users: dict[str, dict[str, Any]] = {}
    page = 1
    with httpx.Client(timeout=20) as client:
        while True:
            response = client.get(
                f"{base_url}/auth/v1/admin/users",
                headers=auth_headers(secret),
                params={"page": page, "per_page": 1000},
            )
            response.raise_for_status()
            payload = response.json()
            batch = payload.get("users", payload if isinstance(payload, list) else [])
            for user in batch:
                email = (user.get("email") or "").lower()
                if email:
                    users[email] = user
            if len(batch) < 1000:
                break
            page += 1
    return users


def upsert_auth_user(
    base_url: str,
    secret: str,
    existing: dict[str, dict[str, Any]],
    *,
    email: str,
    password: str,
    app_metadata: dict[str, Any],
    display_name: str,
) -> str:
    body = {
        "email": email,
        "password": password,
        "email_confirm": True,
        "user_metadata": {"display_name": display_name},
        "app_metadata": app_metadata,
    }
    current = existing.get(email.lower())
    with httpx.Client(timeout=20) as client:
        if current:
            user_id = current["id"]
            response = client.put(
                f"{base_url}/auth/v1/admin/users/{user_id}",
                headers=auth_headers(secret),
                json=body,
            )
        else:
            response = client.post(
                f"{base_url}/auth/v1/admin/users",
                headers=auth_headers(secret),
                json=body,
            )
        response.raise_for_status()
        return response.json()["id"]


def ensure_demo_customer(sb) -> str:
    email = "customer@resolvex.demo"
    rows = sb.table("customers").select("id").eq("email", email).limit(1).execute().data or []
    if rows:
        return str(rows[0]["id"])
    created = sb.table("customers").insert(
        {
            "name": "Demo Customer",
            "email": email,
            "phone": "+94000000000",
            "address": "ResolveX Demo Address",
            "lat": 6.9271,
            "lng": 79.8612,
            "zone_id": "ZONE_A",
        }
    ).execute().data
    return str(created[0]["id"])


def ensure_demo_merchant(sb) -> str:
    name = "ResolveX Demo Merchant"
    rows = sb.table("merchants").select("id").eq("name", name).limit(1).execute().data or []
    if rows:
        return str(rows[0]["id"])
    created = sb.table("merchants").insert(
        {
            "name": name,
            "zone_id": "ZONE_A",
            "address": "ResolveX Demo Kitchen",
            "lat": 6.9275,
            "lng": 79.8615,
            "avg_prep_minutes": 15,
        }
    ).execute().data
    return str(created[0]["id"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--demo-passwords",
        action="store_true",
        help="Use the public hackathon-only passwords documented for the demo accounts.",
    )
    args = parser.parse_args()

    url = require_env("SUPABASE_URL").rstrip("/")
    secret = require_env("SUPABASE_SECRET_KEY", "SUPABASE_KEY")
    sb = create_client(url, secret)

    # Fail early with a useful message when the SQL migration was not applied.
    try:
        sb.table("user_profiles").select("user_id").limit(1).execute()
    except Exception as exc:
        print("ERROR: public.user_profiles is unavailable.", file=sys.stderr)
        print("Run supabase/migrations/20260912_rbac_auth.sql in Supabase SQL Editor first.", file=sys.stderr)
        print(f"Underlying error: {exc}", file=sys.stderr)
        return 2

    customer_id = ensure_demo_customer(sb)
    merchant_id = ensure_demo_merchant(sb)
    current_users = existing_auth_users(url, secret)

    print("\nSeeding ResolveX demo accounts...\n")
    for spec in DEMO_USERS:
        role = spec["role"]
        email = spec["email"]
        password = password_for(role, args.demo_passwords)
        profile: dict[str, Any] = {
            "email": email,
            "display_name": spec["display_name"],
            "role": role,
            "customer_id": customer_id if role == "customer" else None,
            "merchant_id": merchant_id if role == "partner" else None,
        }
        app_metadata = {
            "role": role,
            "customer_id": profile["customer_id"],
            "merchant_id": profile["merchant_id"],
            "display_name": spec["display_name"],
        }
        user_id = upsert_auth_user(
            url,
            secret,
            current_users,
            email=email,
            password=password,
            app_metadata=app_metadata,
            display_name=spec["display_name"],
        )
        sb.table("user_profiles").upsert(
            {"user_id": user_id, **profile}, on_conflict="user_id"
        ).execute()
        print(f"{role:8}  {email:28}  {password}")

    print("\nDone. All five users are email-confirmed and linked to ResolveX roles.")
    print("Restart the frontend/backend, then sign in at http://127.0.0.1:5173/login")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
