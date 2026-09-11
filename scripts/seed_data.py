"""Seeds Supabase with ~20 merchants, ~10 riders, ~30 customers, and ~50 orders using Faker.

Orders come in two flavours:
  - "historical" orders: fully completed, with all stage timestamps and a full GPS trail
    already inserted. These exist so TIMING / RIDER_ROUTE / CLAIM_HISTORY have real data to
    check against as soon as the app boots. One historical order deliberately gets a rider
    detour + a long stationary stop.
  - "tonight" orders: inserted as just-placed (status='placed', only placed_at set). Their
    full future timeline (prep/pickup/dropoff timestamps + GPS trail) is precomputed and
    written to scripts/seed_output/live_orders_plan.json for replay_feed.py to play out on
    an accelerated timer. A cluster of these in ZONE_B is deliberately planned to run late,
    simulating a rain-driven zone-wide delay.

Run: python scripts/seed_data.py
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import timedelta

from faker import Faker

from common import (
    LIVE_ORDERS_PLAN_PATH,
    ZONES,
    get_client,
    inject_detour,
    inject_stationary_stop,
    interpolate_route,
    now_utc,
    zone_point,
)

fake = Faker()
random.seed(7)
Faker.seed(7)

MERCHANTS_PER_ZONE = 5
RIDERS_TOTAL = 10
CUSTOMERS_TOTAL = 30
HISTORICAL_ORDERS = 30
TONIGHT_ORDERS_ZONE_B = 10  # the "rain delay" cluster
TONIGHT_ORDERS_OTHER = 10

MENU_ITEMS = [
    ("Chicken Biryani", 450),
    ("Fried Rice", 380),
    ("Cheese Kottu", 520),
    ("Margherita Pizza", 990),
    ("Chicken Burger", 650,),
    ("Veg Noodles", 420),
    ("Fish Curry Rice", 480),
    ("Butter Chicken", 890),
]


def make_items() -> list[dict]:
    picks = random.sample(MENU_ITEMS, k=random.randint(1, 3))
    return [{"name": name, "qty": random.randint(1, 2), "price": price} for name, price in picks]


def seed_merchants(sb) -> list[dict]:
    merchants = []
    for zone_id in ZONES:
        for _ in range(MERCHANTS_PER_ZONE):
            lat, lng = zone_point(zone_id)
            merchants.append(
                {
                    "id": str(uuid.uuid4()),
                    "name": fake.company(),
                    "zone_id": zone_id,
                    "address": fake.address().replace("\n", ", "),
                    "lat": lat,
                    "lng": lng,
                    "avg_prep_minutes": random.randint(10, 25),
                }
            )
    sb.table("merchants").insert(merchants).execute()
    print(f"Seeded {len(merchants)} merchants")
    return merchants


def seed_riders(sb) -> list[dict]:
    zone_ids = list(ZONES.keys())
    riders = []
    for i in range(RIDERS_TOTAL):
        riders.append(
            {
                "id": str(uuid.uuid4()),
                "name": fake.name(),
                "phone": fake.phone_number(),
                "vehicle": random.choice(["bike", "scooter", "car"]),
                "zone_id": zone_ids[i % len(zone_ids)],
            }
        )
    sb.table("riders").insert(riders).execute()
    print(f"Seeded {len(riders)} riders")
    return riders


def seed_customers(sb) -> list[dict]:
    zone_ids = list(ZONES.keys())
    customers = []
    for _ in range(CUSTOMERS_TOTAL):
        zone_id = random.choice(zone_ids)
        lat, lng = zone_point(zone_id)
        customers.append(
            {
                "id": str(uuid.uuid4()),
                "name": fake.name(),
                "email": fake.unique.email(),
                "phone": fake.phone_number(),
                "address": fake.address().replace("\n", ", "),
                "lat": lat,
                "lng": lng,
                "zone_id": zone_id,
            }
        )
    sb.table("customers").insert(customers).execute()
    print(f"Seeded {len(customers)} customers")
    return customers


def seed_refund_history(sb, customers: list[dict]) -> None:
    """A handful of customers with a normal claim or two, plus two deliberately
    suspicious accounts (many claims, always approved) to trip the CLAIM_HISTORY check."""
    entries = []

    normal_customers = random.sample(customers, k=6)
    for customer in normal_customers:
        for _ in range(random.randint(1, 2)):
            entries.append(
                {
                    "id": str(uuid.uuid4()),
                    "customer_id": customer["id"],
                    "order_id": None,
                    "reason": random.choice(["late", "wrong_item", "damaged", "missing_item"]),
                    "amount": round(random.uniform(200, 800), 2),
                    "outcome": random.choice(["approved", "denied", "voucher"]),
                    "created_at": (now_utc() - timedelta(days=random.randint(1, 60))).isoformat(),
                }
            )

    suspicious_customers = random.sample([c for c in customers if c not in normal_customers], k=2)
    for customer in suspicious_customers:
        for reason in ["late", "wrong_item", "damaged", "missing_item"]:
            entries.append(
                {
                    "id": str(uuid.uuid4()),
                    "customer_id": customer["id"],
                    "order_id": None,
                    "reason": reason,
                    "amount": round(random.uniform(300, 900), 2),
                    "outcome": "approved",
                    "created_at": (now_utc() - timedelta(days=random.randint(1, 30))).isoformat(),
                }
            )
        print(f"  -> flagged suspicious refund history for {customer['name']} ({customer['id']})")

    sb.table("refund_history").insert(entries).execute()
    print(f"Seeded {len(entries)} refund_history rows")


def seed_historical_orders(sb, merchants: list[dict], riders: list[dict], customers: list[dict]) -> list[dict]:
    orders = []
    gps_rows = []

    for i in range(HISTORICAL_ORDERS):
        merchant = random.choice(merchants)
        rider = random.choice(riders)
        customer = random.choice(customers)
        order_id = str(uuid.uuid4())

        placed_at = now_utc() - timedelta(days=random.randint(1, 5), hours=random.randint(0, 12))
        promised_prep = random.choice([12, 15, 18, 20])
        promised_delivery = random.choice([30, 35, 40, 45])

        is_detour_demo = i == 0  # exactly one historical order gets the deliberate detour

        prep_actual = promised_prep + (random.randint(15, 25) if is_detour_demo else random.randint(-3, 6))
        prep_started_at = placed_at + timedelta(minutes=1)
        ready_at = prep_started_at + timedelta(minutes=prep_actual)
        picked_up_at = ready_at + timedelta(minutes=random.randint(2, 6))

        route = interpolate_route(
            (merchant["lat"], merchant["lng"]),
            (customer["lat"], customer["lng"]),
            picked_up_at,
            picked_up_at + timedelta(minutes=random.randint(12, 20)),
            num_points=10,
        )
        if is_detour_demo:
            route = inject_detour(route)
            route = inject_stationary_stop(route, minutes=18)

        dropped_off_at = route[-1]["recorded_at"]
        delivery_actual = (dropped_off_at - placed_at).total_seconds() / 60

        orders.append(
            {
                "id": order_id,
                "merchant_id": merchant["id"],
                "rider_id": rider["id"],
                "customer_id": customer["id"],
                "zone_id": customer["zone_id"],
                "items": make_items(),
                "status": "completed",
                "promised_prep_minutes": promised_prep,
                "promised_delivery_minutes": promised_delivery,
                "placed_at": placed_at.isoformat(),
                "prep_started_at": prep_started_at.isoformat(),
                "ready_at": ready_at.isoformat(),
                "picked_up_at": picked_up_at.isoformat(),
                "dropped_off_at": dropped_off_at.isoformat(),
                "is_late_flagged": delivery_actual > promised_delivery,
            }
        )

        for p in route:
            gps_rows.append(
                {
                    "order_id": order_id,
                    "rider_id": rider["id"],
                    "lat": p["lat"],
                    "lng": p["lng"],
                    "speed_kmh": p["speed_kmh"],
                    "recorded_at": p["recorded_at"].isoformat(),
                }
            )

        if is_detour_demo:
            print(f"  -> detour/stationary-stop demo order: {order_id}")

    sb.table("orders").insert(orders).execute()
    sb.table("rider_gps_points").insert(gps_rows).execute()
    print(f"Seeded {len(orders)} historical orders with {len(gps_rows)} GPS points")
    return orders


def seed_tonight_orders(sb, merchants: list[dict], riders: list[dict], customers: list[dict]) -> None:
    """Inserts 'tonight' orders as just-placed, and writes their full future timeline to a
    JSON plan for replay_feed.py to play out live."""
    plan: dict[str, dict] = {}
    orders_to_insert = []

    zone_b_merchants = [m for m in merchants if m["zone_id"] == "ZONE_B"]
    zone_b_customers = [c for c in customers if c["zone_id"] == "ZONE_B"]
    other_customers = [c for c in customers if c["zone_id"] != "ZONE_B"]

    session_start = now_utc() + timedelta(seconds=5)

    def build_order(zone_id: str, merchant: dict, customer: dict, force_late: bool) -> tuple[dict, dict]:
        order_id = str(uuid.uuid4())
        rider = random.choice(riders)

        placed_at = session_start + timedelta(seconds=random.randint(0, 120))
        promised_prep = random.choice([12, 15, 18])
        promised_delivery = random.choice([30, 35, 40])

        prep_actual = promised_prep + (random.randint(15, 30) if force_late else random.randint(-2, 5))
        delivery_padding = random.randint(20, 35) if force_late else random.randint(-3, 8)

        prep_started_at = placed_at + timedelta(minutes=1)
        ready_at = prep_started_at + timedelta(minutes=prep_actual)
        picked_up_at = ready_at + timedelta(minutes=random.randint(2, 5))
        route = interpolate_route(
            (merchant["lat"], merchant["lng"]),
            (customer["lat"], customer["lng"]),
            picked_up_at,
            picked_up_at + timedelta(minutes=promised_delivery - (promised_prep + 5) + delivery_padding),
            num_points=8,
        )
        dropped_off_at = route[-1]["recorded_at"]

        order_row = {
            "id": order_id,
            "merchant_id": merchant["id"],
            "rider_id": rider["id"],
            "customer_id": customer["id"],
            "zone_id": zone_id,
            "items": make_items(),
            "status": "placed",
            "promised_prep_minutes": promised_prep,
            "promised_delivery_minutes": promised_delivery,
            "placed_at": placed_at.isoformat(),
            "prep_started_at": None,
            "ready_at": None,
            "picked_up_at": None,
            "dropped_off_at": None,
            "is_late_flagged": False,
        }

        order_plan = {
            "rider_id": rider["id"],
            "zone_id": zone_id,
            "placed_at": placed_at.isoformat(),
            "promised_delivery_minutes": promised_delivery,
            "forced_late": force_late,
            "stages": [
                {"status": "preparing", "at": prep_started_at.isoformat(), "field": "prep_started_at"},
                {"status": "ready", "at": ready_at.isoformat(), "field": "ready_at"},
                {"status": "picked_up", "at": picked_up_at.isoformat(), "field": "picked_up_at"},
                {"status": "dropped_off", "at": dropped_off_at.isoformat(), "field": "dropped_off_at"},
            ],
            "gps_trail": [
                {
                    "lat": p["lat"],
                    "lng": p["lng"],
                    "speed_kmh": p["speed_kmh"],
                    "recorded_at": p["recorded_at"].isoformat(),
                }
                for p in route
            ],
        }
        return order_row, order_plan

    for i in range(TONIGHT_ORDERS_ZONE_B):
        merchant = random.choice(zone_b_merchants)
        customer = random.choice(zone_b_customers)
        force_late = i < 8  # 8/10 late -> zone-wide delay demo
        row, order_plan = build_order("ZONE_B", merchant, customer, force_late)
        orders_to_insert.append(row)
        plan[row["id"]] = order_plan

    for _ in range(TONIGHT_ORDERS_OTHER):
        customer = random.choice(other_customers)
        merchant = random.choice([m for m in merchants if m["zone_id"] == customer["zone_id"]])
        row, order_plan = build_order(customer["zone_id"], merchant, customer, force_late=random.random() < 0.15)
        orders_to_insert.append(row)
        plan[row["id"]] = order_plan

    sb.table("orders").insert(orders_to_insert).execute()

    LIVE_ORDERS_PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LIVE_ORDERS_PLAN_PATH, "w") as f:
        json.dump(plan, f, indent=2)

    print(f"Seeded {len(orders_to_insert)} 'tonight' orders (status=placed)")
    print(f"Wrote live order plan for replay_feed.py -> {LIVE_ORDERS_PLAN_PATH}")


def main() -> None:
    sb = get_client()
    merchants = seed_merchants(sb)
    riders = seed_riders(sb)
    customers = seed_customers(sb)
    seed_refund_history(sb, customers)
    seed_historical_orders(sb, merchants, riders, customers)
    seed_tonight_orders(sb, merchants, riders, customers)
    print("\nDone. Run scripts/replay_feed.py to play tonight's orders live.")


if __name__ == "__main__":
    main()
