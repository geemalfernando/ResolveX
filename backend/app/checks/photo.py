"""PHOTO check — packing vs handover vs claim comparison.

Gemini compares the three delivery-evidence photos when they exist. The result is
an evidence signal (MERCHANT / RIDER / NEITHER / INCONCLUSIVE), not the verdict.
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
PHOTO_ANALYSIS_TIMEOUT_SECONDS = 12
COMPARISON_PARTIES = {"MERCHANT", "RIDER", "NEITHER", "INCONCLUSIVE"}

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

COMPARE_PROMPT = """You compare three food-delivery photos for the same order.

Ordered items:
{items}

Complaint type: {complaint_type}
Customer description: {description}

Photos, in order:
1. PACKING — merchant photo taken before the order was marked packed
2. HANDOVER — rider photo taken before confirming delivery
3. CLAIM — customer refund/claim photo

Decide which party the photos support as responsible for a visible item/quality issue.
This is an evidence signal only; do not decide refunds.

Rules:
- MERCHANT if the packing photo already shows damage, the wrong item, or missing items.
- RIDER if packing looks intact and correct, but handover or claim shows damage, substitution, or loss.
- NEITHER if all available photos look consistent, intact, and match the order — the claim is not supported by the images.
- INCONCLUSIVE if images are unreadable, incomplete, or conflict without a clear chain.

Respond ONLY with JSON:
{{
  "fault_party": "MERCHANT" | "RIDER" | "NEITHER" | "INCONCLUSIVE",
  "confidence": 0.0,
  "reasons": ["short evidence reason"],
  "packing_ok": true | false | null,
  "handover_ok": true | false | null,
  "claim_shows_issue": true | false | null,
  "match": true | false | null,
  "damage_detected": true | false,
  "detected_items": ["..."],
  "complaint_supported": true | false | null,
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
            "complaint_supported": True,
            "model_notes": "Local fallback: damaged complaint treated as visible damage because Gemini was unavailable.",
        }
    if complaint_type == ComplaintType.wrong_item:
        return {
            "match": False,
            "detected_items": ["unrecognized item"],
            "damage_detected": False,
            "complaint_supported": True,
            "model_notes": "Local fallback: wrong-item complaint treated as a mismatch because Gemini was unavailable.",
        }
    if complaint_type == ComplaintType.missing_item:
        return {
            "match": False,
            "detected_items": [],
            "damage_detected": False,
            "complaint_supported": True,
            "model_notes": "Local fallback: missing-item complaint treated as incomplete because Gemini was unavailable.",
        }
    return {
        "match": True,
        "detected_items": expected_items,
        "damage_detected": False,
        "complaint_supported": None,
        "model_notes": "Local fallback: photo is not the deciding signal for this complaint type.",
    }


def _load_storage_image(path: str) -> tuple[bytes, str] | None:
    try:
        from ..evidence import download_bytes

        return download_bytes(path)
    except Exception:
        logger.warning("Could not download evidence image %s", path)
        return None


def _fetch_image_bytes(photo_url: str) -> tuple[bytes, str]:
    if photo_url and "/" in photo_url and not photo_url.startswith("http"):
        stored = _load_storage_image(photo_url)
        if stored:
            return stored
    response = httpx.get(photo_url, timeout=15.0, follow_redirects=True)
    response.raise_for_status()
    mime_type = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    return response.content, mime_type


def _image_part(data: bytes, mime_type: str):
    return types.Part.from_bytes(data=data, mime_type=mime_type or "image/jpeg")


def _parse_json(text: str | None) -> dict | None:
    if not text:
        return None
    return json.loads(text)


def _normalize_party(value) -> str:
    party = str(value or "INCONCLUSIVE").upper()
    return party if party in COMPARISON_PARTIES else "INCONCLUSIVE"


def _confidence(value, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, 0.0), 1.0)


def _call_gemini(contents: list, prompt_label: str) -> dict | None:
    settings = get_settings()
    if not settings.gemini_api_key or not settings.photo_use_gemini:
        return None
    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=contents,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return _parse_json(response.text)
    except Exception:
        logger.exception("PHOTO check Gemini %s failed; using local fallback", prompt_label)
        return None


def _with_timeout(fn, timeout: float):
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(fn)
    try:
        return future.result(timeout=timeout)
    except TimeoutError:
        logger.warning("PHOTO analysis timed out; continuing with fallback")
        return None
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _evidence_images(case: Case) -> dict[str, tuple[bytes, str] | None]:
    evidence = case.evidence
    images = {"packing": None, "handover": None, "claim": None}
    for kind in ("packing", "handover", "claim"):
        path = getattr(evidence, f"{kind}_path", None)
        if path:
            images[kind] = _load_storage_image(path)
    claim_url = case.complaint.photo_url if case.complaint else None
    if images["claim"] is None and claim_url:
        try:
            images["claim"] = _fetch_image_bytes(claim_url)
        except Exception:
            logger.warning("Could not fetch claim photo")
    return images


def _compare_three(case: Case, images: dict, expected_items: list[str]) -> dict | None:
    packing = images.get("packing")
    handover = images.get("handover")
    claim = images.get("claim")
    if not (packing and handover and claim):
        return None
    prompt = COMPARE_PROMPT.format(
        items="\n".join(f"- {name}" for name in expected_items) or "- (items not listed)",
        complaint_type=case.complaint.type.value if case.complaint else "unknown",
        description=case.complaint.description if case.complaint else "No description",
    )
    result = _with_timeout(
        lambda: _call_gemini(
            [
                prompt,
                "PACKING photo:",
                _image_part(*packing),
                "HANDOVER photo:",
                _image_part(*handover),
                "CLAIM photo:",
                _image_part(*claim),
            ],
            "comparison",
        ),
        PHOTO_ANALYSIS_TIMEOUT_SECONDS,
    )
    if not result:
        return None
    party = _normalize_party(result.get("fault_party"))
    reasons = result.get("reasons") if isinstance(result.get("reasons"), list) else []
    return {
        "fault_party": party,
        "confidence": _confidence(result.get("confidence"), 0.55),
        "reasons": [str(r) for r in reasons][:6],
        "packing_ok": result.get("packing_ok"),
        "handover_ok": result.get("handover_ok"),
        "claim_shows_issue": result.get("claim_shows_issue"),
        "match": result.get("match"),
        "damage_detected": bool(result.get("damage_detected")),
        "detected_items": result.get("detected_items") or [],
        "complaint_supported": result.get("complaint_supported"),
        "model_notes": result.get("model_notes") or "",
        "source": "gemini",
    }


def run(case: Case) -> CheckResult:
    expected_items = [item.name for item in case.order.items]
    images = _evidence_images(case)
    present = {kind: image is not None for kind, image in images.items()}
    claim_ref = case.evidence.claim_path or (case.complaint.photo_url if case.complaint else None)

    if case.complaint is None or not claim_ref:
        if case.complaint and case.complaint.type in {
            ComplaintType.wrong_item,
            ComplaintType.damaged,
            ComplaintType.missing_item,
            ComplaintType.tampering,
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
                    "images_present": present,
                    "comparison_party": None,
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
                "images_present": present,
                "comparison_party": None,
            },
        )

    comparison = _compare_three(case, images, expected_items)
    source = "gemini"
    if comparison:
        result = comparison
        party = comparison["fault_party"]
        from ..evidence import save_comparison

        save_comparison(
            case.order.id,
            case.case_id,
            {
                "packing_path": case.evidence.packing_path,
                "handover_path": case.evidence.handover_path,
                "claim_path": case.evidence.claim_path or claim_ref,
                "fault_party": party,
                "confidence": comparison["confidence"],
                "reasons": comparison["reasons"],
                "details": comparison,
                "source": "gemini",
            },
        )
    else:
        prompt = PHOTO_PROMPT_TEMPLATE.format(
            items="\n".join(f"- {name}" for name in expected_items),
            complaint_type=case.complaint.type.value,
            description=case.complaint.description or "No description",
        )
        result = None
        if images["claim"]:
            data, mime = images["claim"]
            result = _with_timeout(
                lambda: _call_gemini([prompt, _image_part(data, mime)], "claim photo"),
                PHOTO_ANALYSIS_TIMEOUT_SECONDS,
            )
        elif case.complaint.photo_url and str(case.complaint.photo_url).startswith("http"):
            result = _with_timeout(
                lambda: _call_gemini(
                    [prompt, _image_part(*_fetch_image_bytes(case.complaint.photo_url))],
                    "claim photo",
                ),
                PHOTO_ANALYSIS_TIMEOUT_SECONDS,
            )
        if result is None:
            result = _fallback_from_complaint(case, expected_items)
            source = "local_fallback"
        missing = [kind for kind in ("packing", "handover") if not present[kind]]
        party = "INCONCLUSIVE" if missing else _normalize_party(result.get("fault_party"))
        if missing:
            result.setdefault(
                "model_notes",
                f"Compared the claim photo only; missing {', '.join(missing)} photo(s).",
            )
        comparison = {
            "fault_party": party,
            "confidence": _confidence(result.get("confidence"), 0.4 if missing else 0.55),
            "reasons": [
                result.get("model_notes")
                or "Claim photo reviewed without a complete packing/handover chain."
            ],
            "source": source,
        }

    mismatch = result.get("match") is False
    damaged = bool(result.get("damage_detected"))
    party = comparison["fault_party"]
    inconclusive = party == "INCONCLUSIVE" or result.get("match") is None
    flagged = party in {"MERCHANT", "RIDER"} or ((mismatch or damaged) and party != "NEITHER")
    supported = result.get("complaint_supported")
    if party in {"MERCHANT", "RIDER"}:
        supported = True
    elif party == "NEITHER":
        supported = False
        flagged = False

    if party == "MERCHANT":
        summary = "Packing photo already shows the issue, so the image signal points to the merchant."
    elif party == "RIDER":
        summary = "Packing looked fine; handover or claim photo shows the issue, so the image signal points to the rider."
    elif party == "NEITHER":
        summary = "The three photos look consistent with the order, so the images do not support the claim."
    elif inconclusive:
        summary = "Photo comparison is inconclusive — this remains one evidence signal, not the verdict."
    elif mismatch:
        summary = f"Photo does not match ordered items: expected {expected_items}, got {result.get('detected_items')}."
    elif damaged:
        summary = "Photo shows visible damage to the order."
    else:
        summary = "Photo matches the ordered items with no visible damage."
    if comparison.get("reasons"):
        summary = f"{summary} {comparison['reasons'][0]}"

    return CheckResult(
        check_name=CheckName.photo,
        flagged=flagged,
        confidence=comparison.get("confidence") or (0.3 if inconclusive else (0.75 if flagged else 0.9)),
        summary=summary,
        details={
            "complaint_supported": supported if isinstance(supported, bool) else None,
            "spillage_detected": result.get("spillage_detected") is True,
            "missing_items_possible": result.get("missing_items_possible", []),
            "evidence_confidence": comparison.get("confidence"),
            "match": result.get("match"),
            "expected_items": expected_items,
            "detected_items": result.get("detected_items", []),
            "damage_detected": damaged,
            "model_notes": result.get("model_notes", ""),
            "source": comparison.get("source") or source,
            "images_present": present,
            "comparison_party": party,
            "comparison": comparison,
        },
    )
