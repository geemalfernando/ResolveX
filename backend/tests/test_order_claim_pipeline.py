from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from backend.app.auth import AuthPrincipal
from backend.app.case_builder import build_case
from backend.app.checks import rider_route, timing
from backend.app.models import CaseTrigger, ComplaintType
from backend.app.routers import commerce


class FakeSupabase:
    def __init__(self):
        self.tables = {
            "orders": [],
            "merchants": [],
            "riders": [],
            "rider_gps_points": [],
            "customers": [],
            "refund_history": [],
        }

    def table(self, name):
        return FakeQuery(self, name)


class FakeQuery:
    def __init__(self, db, table):
        self.db = db
        self.table_name = table
        self.filters = []
        self.in_filters = []
        self.action = "select"
        self.body = None
        self.one = False
        self.order_key = None
        self.order_desc = False

    def select(self, *args, **kwargs):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def in_(self, key, values):
        self.in_filters.append((key, set(values)))
        return self

    def insert(self, body):
        self.action = "insert"
        self.body = body
        return self

    def update(self, body):
        self.action = "update"
        self.body = body
        return self

    def single(self):
        self.one = True
        return self

    def order(self, key, desc=False):
        self.order_key = key
        self.order_desc = desc
        return self

    def _matches(self, row):
        return all(row.get(k) == v for k, v in self.filters) and all(
            row.get(k) in values for k, values in self.in_filters
        )

    def execute(self):
        rows = self.db.tables[self.table_name]
        if self.action == "insert":
            new_rows = self.body if isinstance(self.body, list) else [self.body]
            stored = [dict(row) for row in new_rows]
            rows.extend(stored)
            result = stored
        else:
            result = [row for row in rows if self._matches(row)]
            if self.action == "update":
                for row in result:
                    row.update(self.body)
        if self.order_key:
            result = sorted(result, key=lambda row: row.get(self.order_key) or "", reverse=self.order_desc)
        payload = dict(result[0]) if self.one and result else [dict(row) for row in result]
        return SimpleNamespace(data=payload, count=len(result))


def test_customer_order_to_claim_analysis_pipeline():
    db = FakeSupabase()
    merchant_id = str(uuid4())
    rider_id = str(uuid4())
    customer_id = str(uuid4())

    db.tables["merchants"].append(
        {
            "id": merchant_id,
            "name": "ResolveX Demo Kitchen",
            "address": "10 Kitchen Road",
            "zone_id": "ZONE_A",
            "avg_prep_minutes": 15,
            "lat": 6.9000,
            "lng": 79.8000,
        }
    )
    db.tables["riders"].append(
        {
            "id": rider_id,
            "name": "Demo Rider",
            "phone": "0770000000",
            "vehicle": "bike",
            "zone_id": "ZONE_A",
        }
    )
    db.tables["customers"].append(
        {
            "id": customer_id,
            "name": "Demo Customer",
            "email": "customer@example.com",
            "phone": "0771111111",
            "address": "Old saved address",
            "lat": 0.0,
            "lng": 0.0,
            "zone_id": "ZONE_A",
        }
    )
    db.tables["refund_history"].append(
        {
            "id": str(uuid4()),
            "customer_id": customer_id,
            "order_id": str(uuid4()),
            "reason": "late",
            "amount": 500,
            "outcome": "approved",
            "created_at": "2026-09-01T10:00:00+00:00",
        }
    )

    customer = AuthPrincipal("customer-user", "customer@example.com", "customer", customer_id=customer_id)
    partner = AuthPrincipal("partner-user", "partner@example.com", "partner", merchant_id=merchant_id)
    rider = AuthPrincipal("rider-user", "rider@example.com", "rider", rider_id=rider_id)

    with patch.object(commerce, "get_supabase", return_value=db), patch(
        "backend.app.case_builder.get_supabase", return_value=db
    ):
        checkout = commerce.Checkout(
            request_id=uuid4(),
            merchant_id=merchant_id,
            items=[{"product_id": "rice", "qty": 2}],
            address="12 Colombo Lane",
            phone="0771234567",
            lat=6.9100,
            lng=79.8100,
            instructions="Call on arrival",
        )
        created = commerce.checkout(checkout, customer)

        # Pricing is server-authoritative and the delivery snapshot is persisted
        # with the order so later claims use the address that was actually ordered to.
        assert created["items"][0]["price"] == 1250
        assert created["items"][0]["delivery"]["address"] == "12 Colombo Lane"
        assert created["customer_id"] == customer_id

        # Merchant preparation writes every stage timestamp the timing model consumes.
        accepted = commerce.stage(created["id"], commerce.Stage(action="accept"), partner)
        packed = commerce.stage(created["id"], commerce.Stage(action="pack"), partner)
        handed_over = commerce.stage(
            created["id"], commerce.Stage(action="handover", rider_id=rider_id), partner
        )
        assert accepted["prep_started_at"]
        assert packed["ready_at"]
        assert handed_over["picked_up_at"]
        assert handed_over["rider_id"] == rider_id

        # Rider movement and final drop-off are saved as GPS evidence.
        commerce.position(
            created["id"], commerce.Position(lat=6.9050, lng=79.8050, speed_kmh=18), rider
        )
        delivered = commerce.stage(
            created["id"], commerce.Stage(action="deliver", lat=6.9100, lng=79.8100), rider
        )
        assert delivered["status"] == "dropped_off"
        assert delivered["dropped_off_at"]
        assert len(db.tables["rider_gps_points"]) == 3

        # Build the same Case object used by the claims pipeline and verify that
        # fulfillment evidence survives the hand-off from commerce -> analysis.
        case = build_case(
            created["id"],
            CaseTrigger.customer_complaint,
            complaint_type=ComplaintType.damaged,
            description="Package arrived damaged",
        )

    assert case.order.timestamps.prep_started_at is not None
    assert case.order.timestamps.ready_at is not None
    assert case.order.timestamps.picked_up_at is not None
    assert case.order.timestamps.dropped_off_at is not None
    assert len(case.rider_gps_trail) == 3
    assert case.rider is not None and case.rider.id == rider_id
    assert case.customer.address == "12 Colombo Lane"
    assert case.customer.lat == 6.9100
    assert case.customer.lng == 79.8100
    assert len(case.customer_refund_history) == 1
    assert case.complaint is not None and case.complaint.type == ComplaintType.damaged

    timing_result = timing.run(case)
    route_result = rider_route.run(case)
    assert timing_result.details["prep_minutes"] is not None
    assert timing_result.details["delivery_minutes"] is not None
    assert route_result.details.get("reason") != "insufficient_gps_data"
