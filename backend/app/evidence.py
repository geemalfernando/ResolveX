"""Private delivery-evidence storage: packing, handover, and claim photos."""

from __future__ import annotations

import logging
import uuid
from typing import Iterable, Literal, Optional

from fastapi import HTTPException, UploadFile

from .db import get_supabase

logger = logging.getLogger(__name__)

BUCKET = "delivery-evidence"
KINDS = ("packing", "handover", "claim")
EvidenceKind = Literal["packing", "handover", "claim"]
ALLOWED_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
SIGNED_TTL_SECONDS = 60 * 60
MAX_BYTES = 10 * 1024 * 1024


def ensure_bucket(sb=None):
    client = sb or get_supabase()
    try:
        client.storage.get_bucket(BUCKET)
        return
    except Exception:
        pass
    try:
        client.storage.create_bucket(
            BUCKET,
            options={
                "public": False,
                "file_size_limit": MAX_BYTES,
                "allowed_mime_types": list(ALLOWED_TYPES),
            },
        )
    except Exception:
        logger.warning("Could not create %s bucket; uploads will retry against Storage", BUCKET)


def _path(order_id: str, kind: str, extension: str) -> str:
    return f"{order_id}/{kind}.{extension}"


def _signed_url(sb, path: str) -> Optional[str]:
    try:
        data = sb.storage.from_(BUCKET).create_signed_url(path, SIGNED_TTL_SECONDS)
        return data.get("signedURL") or data.get("signedUrl") or data.get("signed_url")
    except Exception:
        logger.warning("Could not sign evidence URL for %s", path)
        return None


def _record_row(sb, order_id: str, kind: str, path: str, content_type: str, uploaded_by: Optional[str]):
    row = {
        "order_id": order_id,
        "kind": kind,
        "storage_path": path,
        "content_type": content_type,
        "uploaded_by": uploaded_by,
    }
    try:
        sb.table("delivery_evidence").upsert(row, on_conflict="order_id,kind").execute()
    except Exception:
        logger.warning("delivery_evidence table unavailable; storage path %s is still the source of truth", path)


def list_paths(order_id: str, sb=None) -> dict[str, str]:
    client = sb or get_supabase()
    found: dict[str, str] = {}
    try:
        rows = (
            client.table("delivery_evidence")
            .select("kind,storage_path")
            .eq("order_id", order_id)
            .execute()
            .data
            or []
        )
        for row in rows:
            if row.get("kind") in KINDS and row.get("storage_path"):
                found[row["kind"]] = row["storage_path"]
    except Exception:
        pass
    if len(found) == len(KINDS):
        return found
    try:
        files = client.storage.from_(BUCKET).list(order_id) or []
        for item in files:
            name = (item.get("name") if isinstance(item, dict) else None) or ""
            kind = name.split(".", 1)[0]
            if kind in KINDS and kind not in found:
                found[kind] = f"{order_id}/{name}"
    except Exception:
        pass
    return found


def has_evidence(order_id: str, kind: EvidenceKind, sb=None) -> bool:
    return kind in list_paths(str(order_id), sb)


def evidence_payload(order_id: str, sb=None) -> dict[str, Optional[dict]]:
    client = sb or get_supabase()
    paths = list_paths(str(order_id), client)
    payload: dict[str, Optional[dict]] = {kind: None for kind in KINDS}
    for kind, path in paths.items():
        payload[kind] = {"path": path, "signed_url": _signed_url(client, path)}
    return payload


def evidence_for_orders(order_ids: Iterable[str], sb=None) -> dict[str, dict]:
    client = sb or get_supabase()
    ids = [str(order_id) for order_id in order_ids]
    empty = {kind: None for kind in KINDS}
    mapped = {order_id: dict(empty) for order_id in ids}
    if not ids:
        return mapped
    rows = []
    try:
        rows = (
            client.table("delivery_evidence")
            .select("order_id,kind,storage_path")
            .in_("order_id", ids)
            .execute()
            .data
            or []
        )
    except Exception:
        rows = []
    if not rows:
        return {order_id: evidence_payload(order_id, client) for order_id in ids}
    for row in rows:
        kind = row.get("kind")
        path = row.get("storage_path")
        order_id = row.get("order_id")
        if order_id in mapped and kind in KINDS and path:
            mapped[order_id][kind] = {"path": path, "signed_url": _signed_url(client, path)}
    return mapped


def download_bytes(path: str, sb=None) -> tuple[bytes, str]:
    client = sb or get_supabase()
    data = client.storage.from_(BUCKET).download(path)
    if not data:
        raise FileNotFoundError(path)
    suffix = path.rsplit(".", 1)[-1].lower()
    mime = {v: k for k, v in ALLOWED_TYPES.items()}.get(suffix, "image/jpeg")
    return data, mime


def save_upload(
    order_id: str,
    kind: EvidenceKind,
    file: UploadFile,
    uploaded_by: Optional[str] = None,
    sb=None,
) -> dict:
    if kind not in KINDS:
        raise HTTPException(422, "Evidence kind must be packing, handover, or claim")
    content_type = (file.content_type or "").split(";")[0].strip()
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(400, "Only JPEG, PNG, and WebP images are supported")
    contents = file.file.read()
    if not contents:
        raise HTTPException(400, "The photo file is empty")
    if len(contents) > MAX_BYTES:
        raise HTTPException(413, "Photo must be 10 MB or smaller")

    client = sb or get_supabase()
    ensure_bucket(client)
    path = _path(str(order_id), kind, ALLOWED_TYPES[content_type])
    try:
        client.storage.from_(BUCKET).upload(
            path,
            contents,
            {"content-type": content_type, "upsert": "true", "x-upsert": "true"},
        )
    except Exception as exc:
        raise HTTPException(502, f"Photo upload failed: {exc}") from exc

    _record_row(client, str(order_id), kind, path, content_type, uploaded_by)
    return {
        "kind": kind,
        "path": path,
        "photo_url": path,
        "signed_url": _signed_url(client, path),
    }


def save_comparison(order_id: str, case_id: Optional[str], result: dict, sb=None) -> None:
    row = {
        "order_id": order_id,
        "case_id": case_id,
        "packing_path": result.get("packing_path"),
        "handover_path": result.get("handover_path"),
        "claim_path": result.get("claim_path"),
        "fault_party": result.get("fault_party") or "INCONCLUSIVE",
        "confidence": result.get("confidence") or 0,
        "reasons": result.get("reasons") or [],
        "details": result.get("details") or {},
        "source": result.get("source") or "gemini",
    }
    try:
        (sb or get_supabase()).table("photo_comparisons").upsert(row, on_conflict="order_id").execute()
    except Exception:
        logger.warning("photo_comparisons table unavailable; comparison remains on the PHOTO check")
