from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, computed_field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ComplaintType(str, Enum):
    late = "late"
    wrong_item = "wrong_item"
    damaged = "damaged"
    missing_item = "missing_item"


class CaseTrigger(str, Enum):
    customer_complaint = "customer_complaint"
    live_feed_late = "live_feed_late"
    zone_delay = "zone_delay"


class FaultParty(str, Enum):
    merchant = "merchant"
    rider = "rider"
    external = "external"
    neither = "neither"
    customer_abuse = "customer_abuse"


class Outcome(str, Enum):
    need_more_info = "NEED_MORE_INFO"
    auto_refund = "AUTO_REFUND"
    zone_broadcast = "ZONE_BROADCAST"
    support_ticket = "SUPPORT_TICKET"


class CheckName(str, Enum):
    photo = "photo"
    timing = "timing"
    rider_route = "rider_route"
    zone = "zone"
    claim_history = "claim_history"


# ---------------------------------------------------------------------------
# Case object (Case Builder output / check input) — see docs/case_contract.md
# ---------------------------------------------------------------------------


class OrderItem(BaseModel):
    name: str
    qty: int
    price: float


class OrderTimestamps(BaseModel):
    placed_at: datetime
    prep_started_at: Optional[datetime] = None
    ready_at: Optional[datetime] = None
    picked_up_at: Optional[datetime] = None
    dropped_off_at: Optional[datetime] = None


class OrderSnapshot(BaseModel):
    id: str
    status: str
    zone_id: str
    items: list[OrderItem]
    promised_prep_minutes: int
    promised_delivery_minutes: int
    timestamps: OrderTimestamps


class MerchantSnapshot(BaseModel):
    id: str
    name: str
    zone_id: str
    lat: float
    lng: float
    avg_prep_minutes: int


class RiderSnapshot(BaseModel):
    id: str
    name: str
    vehicle: str


class GpsPoint(BaseModel):
    lat: float
    lng: float
    speed_kmh: Optional[float] = None
    recorded_at: datetime


class CustomerSnapshot(BaseModel):
    id: str
    name: str
    address: str
    lat: float
    lng: float


class RefundHistoryEntry(BaseModel):
    reason: str
    amount: float
    outcome: str
    created_at: datetime


class ComplaintSnapshot(BaseModel):
    id: str
    type: ComplaintType
    description: Optional[str] = None
    photo_url: Optional[str] = None


class ZoneSnapshot(BaseModel):
    zone_id: str
    open_orders_count: int
    average_delay_minutes: Optional[float] = Field(default=None, ge=0)
    late_orders_count: int


class Case(BaseModel):
    case_id: str
    trigger: CaseTrigger
    order: OrderSnapshot
    merchant: MerchantSnapshot
    rider: Optional[RiderSnapshot] = None
    rider_gps_trail: list[GpsPoint] = Field(default_factory=list)
    customer: CustomerSnapshot
    customer_refund_history: list[RefundHistoryEntry] = Field(default_factory=list)
    complaint: Optional[ComplaintSnapshot] = None
    zone_snapshot: ZoneSnapshot


# ---------------------------------------------------------------------------
# Check result envelope — see docs/case_contract.md section 2
# ---------------------------------------------------------------------------


class CheckResult(BaseModel):
    check_name: CheckName
    flagged: bool
    confidence: float
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Aggregator input / output — see docs/aggregator_contract.md
# ---------------------------------------------------------------------------


class AggregatorInput(BaseModel):
    case: Case
    check_results: list[CheckResult]


class VerdictReason(BaseModel):
    check: CheckName
    reason: str


class Verdict(BaseModel):
    claim_valid: bool
    fault_party: FaultParty
    confidence: float = Field(ge=0.0, le=1.0)
    outcome: Outcome
    reasons: list[VerdictReason]
    label_provenance: Optional[str] = None
    model_used: bool = False
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    model_prediction: Optional[str] = None
    fault_prediction: Optional[str] = None
    fault_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    resolution: Optional[Outcome] = None
    class_probabilities: dict[str, float] = Field(default_factory=dict)
    features: dict[str, Optional[float]] = Field(default_factory=dict)
    feature_names: list[str] = Field(default_factory=list)
    feature_vector: list[Optional[float]] = Field(default_factory=list)
    fallback_reason: Optional[str] = "Legacy verdict: ML inference was not recorded"


# ---------------------------------------------------------------------------
# API request/response bodies
# ---------------------------------------------------------------------------


class CreateCaseRequest(BaseModel):
    order_id: str
    complaint_type: Optional[ComplaintType] = None
    description: Optional[str] = None
    photo_url: Optional[str] = None
    trigger: CaseTrigger = CaseTrigger.customer_complaint


class CaseResponse(BaseModel):
    case_id: str
    status: str
    case: Case
    check_results: list[CheckResult] = Field(default_factory=list)
    verdict: Optional[Verdict] = None


    @computed_field
    @property
    def eta(self) -> dict[str, Any]:
        timing = next((c for c in self.check_results if c.check_name == CheckName.timing), None)
        details = timing.details if timing else {}
        prediction = details.get("predicted_delivery_minutes")
        used = details.get("eta_model_used", prediction is not None)
        return {"predicted_minutes": prediction, "model_used": used,
                "fallback_reason": details.get("eta_fallback_reason") if used else details.get("eta_fallback_reason", "ETA inference not recorded")}

    @computed_field
    @property
    def fault(self) -> Optional[dict[str, Any]]:
        if self.verdict is None:
            return None
        from .config import get_settings
        settings = get_settings()
        verdict = self.verdict
        level = "High" if verdict.confidence >= settings.auto_action_confidence_threshold else "Moderate" if verdict.confidence >= settings.support_review_confidence_threshold else "Low"
        return {"prediction": verdict.fault_prediction or verdict.fault_party.value.upper(),
                "confidence": verdict.confidence, "confidence_level": level,
                "model_used": verdict.model_used, "class_probabilities": verdict.class_probabilities,
                "fallback_reason": verdict.fallback_reason}

    @computed_field
    @property
    def resolution(self) -> Optional[dict[str, str]]:
        return {"action": self.verdict.outcome.value} if self.verdict else None
