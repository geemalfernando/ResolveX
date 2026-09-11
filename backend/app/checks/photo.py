"""PHOTO check — Gemini when available, complaint-type fallback otherwise.

Gemini is optional. Token / quota failures must not blank the rest of the
pipeline: a late / damaged / wrong-item complaint still produces a usable signal.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError

import httpx
from google import genai
from google.genai import types

from ..config import get_settings
from ..models import Case, CheckName, CheckResult, ComplaintType

logger = logging.getLogger(__name__)
_gemini_quota_exhausted = False
PHOTO_ANALYSIS_TIMEOUT_SECONDS = 5

PHOTO_PROMPT_TEMPLATE = """You are inspecting a photo a customer submitted with a food delivery complaint.

Ordered items:
{items}

Complaint type: {complaint_type}
Customer description: {description}

Look at the attached photo and answer:
1. Do the items visible in the photo match the ordered items (name/type, not exact plating)?
2. Is there visible damage (spillage, crushed packaging, leaking containers)?

Respond ONLY with JSON matching this shape, no markdown fences, no commentary:
{{
  "complaint_supported": true | false | null,
  "spillage_detected": true | false,
  "missing_items_possible": ["..."],
  "confidence": 0.0,
  "match": true | false,
  "detected_items": ["..."],
  "damage_detected": true | false,
  "model_notes": "short explanation"
}}
"""


def _fallback_from_complaint(case: Case, expected_items: list[str]) -> dict:
    complaint_type = case.complaint.type if case.complaint else None
    if complaint_type == ComplaintType.damaged:
        return {
            "match": True,
            "detected_items": expected_items,
            "damage_detected": True,
            "model_notes": "Local fallback: damaged complaint treated as visible damage because Gemini was unavailable.",
        }
    if complaint_type == ComplaintType.wrong_item:
        return {
            "match": False,
            "detected_items": ["unrecognized item"],
            "damage_detected": False,
            "model_notes": "Local fallback: wrong-item complaint treated as a mismatch because Gemini was unavailable.",
        }
    if complaint_type == ComplaintType.missing_item:
        return {
            "match": False,
            "detected_items": [],
            "damage_detected": False,
            "model_notes": "Local fallback: missing-item complaint treated as incomplete because Gemini was unavailable.",
        }
    return {
        "match": True,
        "detected_items": expected_items,
        "damage_detected": False,
        "model_notes": "Local fallback: photo is not the deciding signal for this complaint type.",
    }


def _fetch_image_bytes(photo_url: str) -> tuple[bytes, str]:
    response = httpx.get(photo_url, timeout=15.0, follow_redirects=True)
    response.raise_for_status()
    mime_type = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    return response.content, mime_type


def _call_gemini(photo_url: str, prompt: str) -> dict | None:
    settings = get_settings()
    if not settings.gemini_api_key or not settings.photo_use_gemini:
        return None

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
        logger.exception("PHOTO check Gemini call failed; using local complaint-type fallback")
        return None


def _call_gemini_with_timeout(photo_url: str, prompt: str) -> dict:
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_call_gemini, photo_url, prompt)
    try:
        return future.result(timeout=PHOTO_ANALYSIS_TIMEOUT_SECONDS)
    except TimeoutError:
        logger.warning("PHOTO analysis timed out; continuing with human-review fallback")
        return {
            "match": None,
            "detected_items": [],
            "damage_detected": False,
            "model_notes": "Photo analysis timed out — needs human review.",
        }
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def run(case: Case) -> CheckResult:
    expected_items = [item.name for item in case.order.items]

    if case.complaint is None or not case.complaint.photo_url:
        if case.complaint and case.complaint.type in {
            ComplaintType.wrong_item,
            ComplaintType.damaged,
            ComplaintType.missing_item,
        }:
            return CheckResult(
                check_name=CheckName.photo,
                flagged=False,
                confidence=0.25,
                summary="Photo required for this complaint type — asking the customer for one more photo.",
                details={
                    "match": None,
                    "expected_items": expected_items,
                    "detected_items": [],
                    "damage_detected": False,
                    "source": "missing_photo",
                },
            )
        return CheckResult(
            check_name=CheckName.photo,
            flagged=False,
            confidence=0.0,
            summary="No photo submitted with this case.",
            details={
                "match": None,
                "expected_items": expected_items,
                "detected_items": [],
                "damage_detected": False,
                "source": "no_photo",
            },
        )

    prompt = PHOTO_PROMPT_TEMPLATE.format(items="\n".join(f"- {name}" for name in expected_items))
    result = _call_gemini(case.complaint.photo_url, prompt)
    source = "gemini"
    if result is None:
        result = _fallback_from_complaint(case, expected_items)
        source = "local_fallback"

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
            "complaint_supported": result.get("complaint_supported") if isinstance(result.get("complaint_supported"), bool) else None,
            "spillage_detected": result.get("spillage_detected") is True,
            "missing_items_possible": result.get("missing_items_possible", []),
            "evidence_confidence": result.get("confidence") if isinstance(result.get("confidence"), (int, float)) and 0 <= result["confidence"] <= 1 else None,
            "match": result.get("match"),
            "expected_items": expected_items,
            "detected_items": result.get("detected_items", []),
            "damage_detected": damaged,
            "model_notes": result.get("model_notes", ""),
            "source": source,
        },
    )
