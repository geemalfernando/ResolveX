from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from google import genai
from pydantic import BaseModel, Field

from ..auth import AuthPrincipal, current_user
from ..config import get_settings
from ..db import get_supabase

router = APIRouter(prefix="/assistant", tags=["assistant"])


class Activity(BaseModel):
    at: str
    method: str = "GET"
    path: str
    status: int | None = None


class AssistantRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1200)
    page: str = Field(default="/", max_length=300)
    activity: list[Activity] = Field(default_factory=list, max_length=25)


class AssistantResponse(BaseModel):
    reply: str
    source: Literal["gemini", "fallback"]


def _safe_account_context(principal: AuthPrincipal) -> dict:
    """Load only records the authenticated role is allowed to know about."""
    sb = get_supabase()
    context: dict = {"role": principal.role, "display_name": principal.display_name}
    try:
        query = sb.table("orders").select(
            "id,status,placed_at,merchant_id,rider_id,is_late_flagged,promised_delivery_minutes"
        )
        if principal.role == "customer" and principal.customer_id:
            query = query.eq("customer_id", principal.customer_id)
        elif principal.role == "partner" and principal.merchant_id:
            query = query.eq("merchant_id", principal.merchant_id)
        elif principal.role == "rider" and principal.rider_id:
            query = query.eq("rider_id", principal.rider_id)
        elif principal.role not in {"ops", "support", "admin"}:
            return context
        context["recent_orders"] = (
            query.order("placed_at", desc=True).limit(5).execute().data or []
        )
    except Exception:
        context["recent_orders"] = []
    return context


def _fallback(body: AssistantRequest, principal: AuthPrincipal) -> str:
    recent = body.activity[-5:]
    if recent:
        last = recent[-1]
        return (
            f"I can see your recent ResolveX activity. Your latest recorded action was "
            f"{last.method} {last.path}"
            + (f" with status {last.status}." if last.status else ".")
            + " Ask me about that action, your order flow, delivery progress, or a claim."
        )
    return (
        f"I’m your ResolveX assistant for the {principal.role} view. "
        "I can explain orders, delivery stages, claims, and the actions you take in this app."
    )


@router.post("/chat", response_model=AssistantResponse)
def chat(body: AssistantRequest, principal: AuthPrincipal = Depends(current_user)) -> AssistantResponse:
    settings = get_settings()
    if not settings.gemini_api_key:
        return AssistantResponse(reply=_fallback(body, principal), source="fallback")

    account_context = _safe_account_context(principal)
    activity = [a.model_dump() for a in body.activity[-20:]]
    prompt = f"""
You are X, the built-in AI assistant for ResolveX, a last-mile delivery and claims platform.

Authenticated user context:
{json.dumps(account_context, default=str)}

Current page: {body.page}
Recent in-app API activity (sanitized; never includes tokens, headers, passwords, or API keys):
{json.dumps(activity, default=str)}

User message:
{body.message}

Rules:
- Be concise, useful, and specific to ResolveX.
- You may explain what the user recently did based on the activity list.
- Use only role-appropriate account context shown above; never invent hidden data.
- Never reveal, request, reconstruct, or echo API keys, bearer tokens, passwords, cookies, or secrets.
- If an action failed, use the recorded HTTP status to explain likely next steps.
- For claims, distinguish operational fault from claim-risk/history signals.
- Do not claim you performed an action unless it appears in activity or account context.
""".strip()

    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(model="gemini-3.6-flash", contents=prompt)
        text = (response.text or "").strip()
        if not text:
            raise ValueError("empty assistant response")
        return AssistantResponse(reply=text, source="gemini")
    except Exception:
        return AssistantResponse(reply=_fallback(body, principal), source="fallback")
