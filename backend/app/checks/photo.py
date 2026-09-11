"""PHOTO check — AI (Gemini 3.6 Flash multimodal).

Compares the customer's uploaded photo against the ordered items and flags a
mismatch (wrong item) or visible damage.
"""

from __future__ import annotations

import json
import logging

import httpx
from google import genai
from google.genai import types

from ..config import get_settings
from ..models import Case, CheckName, CheckResult

logger = logging.getLogger(__name__)

PHOTO_PROMPT_TEMPLATE = """You are inspecting a photo a customer submitted with a food delivery complaint.

Ordered items:
{items}

Look at the attached photo and answer:
1. Do the items visible in the photo match the ordered items (name/type, not exact plating)?
2. Is there visible damage (spillage, crushed packaging, leaking containers)?

Respond ONLY with JSON matching this shape, no markdown fences, no commentary:
{{
  "match": true | false,
  "detected_items": ["..."],
  "damage_detected": true | false,
  "model_notes": "short explanation"
}}
"""

_STUB_RESULT = {
    "match": True,
    "detected_items": [],
    "damage_detected": False,
    "model_notes": "STUB RESPONSE: GEMINI_API_KEY not set (see checks/photo.py).",
}


def _fetch_image_bytes(photo_url: str) -> tuple[bytes, str]:
    response = httpx.get(photo_url, timeout=15.0, follow_redirects=True)
    response.raise_for_status()
    mime_type = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    return response.content, mime_type


def _call_gemini(photo_url: str, prompt: str) -> dict:
    settings = get_settings()
    if not settings.gemini_api_key:
        return _STUB_RESULT

    try:
        image_bytes, mime_type = _fetch_image_bytes(photo_url)

        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=[
                prompt,
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return json.loads(response.text)
    except Exception:
        logger.exception("PHOTO check Gemini call failed; falling back to inconclusive result")
        return {
            "match": None,
            "detected_items": [],
            "damage_detected": False,
            "model_notes": "Gemini call failed — treated as inconclusive, needs human review.",
        }


def run(case: Case) -> CheckResult:
    if case.complaint is None or not case.complaint.photo_url:
        return CheckResult(
            check_name=CheckName.photo,
            flagged=False,
            confidence=0.0,
            summary="No photo submitted with this case.",
            details={"match": None, "expected_items": [], "detected_items": [], "damage_detected": False},
        )

    expected_items = [item.name for item in case.order.items]
    prompt = PHOTO_PROMPT_TEMPLATE.format(items="\n".join(f"- {name}" for name in expected_items))

    result = _call_gemini(case.complaint.photo_url, prompt)

    mismatch = result.get("match") is False
    damaged = bool(result.get("damage_detected"))
    inconclusive = result.get("match") is None
    flagged = mismatch or damaged

    if inconclusive:
        summary = "Photo could not be evaluated — needs a human look."
    elif mismatch:
        summary = f"Photo does not match ordered items: expected {expected_items}, got {result.get('detected_items')}."
    elif damaged:
        summary = "Photo shows visible damage to the order."
    else:
        summary = "Photo matches the ordered items with no visible damage."

    return CheckResult(
        check_name=CheckName.photo,
        flagged=flagged,
        confidence=0.3 if inconclusive else (0.75 if flagged else 0.9),
        summary=summary,
        details={
            "match": result.get("match"),
            "expected_items": expected_items,
            "detected_items": result.get("detected_items", []),
            "damage_detected": damaged,
            "model_notes": result.get("model_notes", ""),
        },
    )
