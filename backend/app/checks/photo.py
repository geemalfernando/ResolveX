"""PHOTO check — AI (Gemini 2.5 Flash multimodal).

STUB: wire up your GEMINI_API_KEY in .env and replace `_call_gemini` below.
Compares the customer's uploaded photo against the ordered items and flags a
mismatch (wrong item) or visible damage.
"""

from __future__ import annotations

from ..config import get_settings
from ..models import Case, CheckName, CheckResult

PHOTO_PROMPT_TEMPLATE = """You are inspecting a photo a customer submitted with a food delivery complaint.

Ordered items:
{items}

Look at the attached photo and answer:
1. Do the items visible in the photo match the ordered items (name/type, not exact plating)?
2. Is there visible damage (spillage, crushed packaging, leaking containers)?

Respond ONLY with JSON matching this shape:
{{
  "match": true | false,
  "detected_items": ["..."],
  "damage_detected": true | false,
  "model_notes": "short explanation"
}}
"""


def _call_gemini(photo_url: str, prompt: str) -> dict:
    """
    TODO: replace with a real call to Gemini 2.5 Flash, e.g.:

        from google import genai
        client = genai.Client(api_key=get_settings().gemini_api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt, {"file_data": {"file_uri": photo_url}}],
            config={"response_mime_type": "application/json"},
        )
        return json.loads(response.text)

    Left as a stub so the rest of the pipeline (case build -> checks -> aggregator)
    runs end-to-end before the Gemini key is wired up.
    """
    return {
        "match": True,
        "detected_items": [],
        "damage_detected": False,
        "model_notes": "STUB RESPONSE: Gemini call not yet wired up (see checks/photo.py).",
    }


def run(case: Case) -> CheckResult:
    settings = get_settings()

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

    if not settings.gemini_api_key:
        result = _call_gemini(case.complaint.photo_url, prompt)
    else:
        # TODO: once GEMINI_API_KEY is set, call the real Gemini client here instead of the stub.
        result = _call_gemini(case.complaint.photo_url, prompt)

    mismatch = result.get("match") is False
    damaged = bool(result.get("damage_detected"))
    flagged = mismatch or damaged

    if mismatch:
        summary = f"Photo does not match ordered items: expected {expected_items}, got {result.get('detected_items')}."
    elif damaged:
        summary = "Photo shows visible damage to the order."
    else:
        summary = "Photo matches the ordered items with no visible damage."

    return CheckResult(
        check_name=CheckName.photo,
        flagged=flagged,
        confidence=0.75 if flagged else 0.9,
        summary=summary,
        details={
            "match": result.get("match"),
            "expected_items": expected_items,
            "detected_items": result.get("detected_items", []),
            "damage_detected": damaged,
            "model_notes": result.get("model_notes", ""),
        },
    )
