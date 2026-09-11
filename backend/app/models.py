from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


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
