# ResolveX — Case Contract

Defines the exact JSON shapes that flow **Case Builder → Checks → Fairness Aggregator**.
Backend Pydantic models in `backend/app/models.py` are the source of truth; this doc mirrors them.

## 1. Case object (output of Case Builder, input to every check)

Built by `POST /cases` (or by the live-feed watcher / zone monitor) from `orders`, `merchants`,
`riders`, `rider_gps_points`, `customers`, `refund_history`, and — if customer-triggered — `complaints`.

```jsonc
{
  "case_id": "uuid",
  "trigger": "customer_complaint | live_feed_late | zone_delay",
  "order": {
    "id": "uuid",
    "status": "dropped_off",
    "zone_id": "ZONE_A",
    "items": [{ "name": "Chicken Biryani", "qty": 1, "price": 450 }],
    "promised_prep_minutes": 15,
    "promised_delivery_minutes": 35,
    "timestamps": {
      "placed_at": "2026-09-11T18:00:00Z",
      "prep_started_at": "2026-09-11T18:01:00Z",
      "ready_at": "2026-09-11T18:20:00Z",
      "picked_up_at": "2026-09-11T18:25:00Z",
      "dropped_off_at": "2026-09-11T19:10:00Z"
    }
  },
  "merchant": {
    "id": "uuid",
    "name": "Spice Villa",
    "zone_id": "ZONE_A",
    "lat": 6.9271,
    "lng": 79.8612,
    "avg_prep_minutes": 18
  },
  "rider": {
    "id": "uuid",
    "name": "Kasun P.",
    "vehicle": "bike"
  },
  "rider_gps_trail": [
    { "lat": 6.9271, "lng": 79.8612, "speed_kmh": 0, "recorded_at": "2026-09-11T18:25:00Z" },
    { "lat": 6.9280, "lng": 79.8620, "speed_kmh": 22.4, "recorded_at": "2026-09-11T18:27:00Z" }
  ],
  "customer": {
    "id": "uuid",
    "name": "Amaya S.",
    "address": "12 Galle Rd, Colombo",
    "lat": 6.9150,
    "lng": 79.8500
  },
  "customer_refund_history": [
    { "reason": "late", "amount": 350, "outcome": "approved", "created_at": "2026-08-01T12:00:00Z" }
  ],
  "complaint": {
    "id": "uuid",
    "type": "wrong_item",
    "description": "Got fried rice instead of biryani",
    "photo_url": "https://.../complaint-photos/abc.jpg"
  },
  "zone_snapshot": {
    "zone_id": "ZONE_A",
    "open_orders_count": 24,
    "late_orders_count": 9
  }
}
```

Notes:
- `complaint` is `null` when `trigger` is `live_feed_late` or `zone_delay`.
- `zone_snapshot` is computed at case-build time and passed through so the ZONE check doesn't
  need to re-query.

## 2. Check result (output of each of the 5 checks)

Every check returns this common envelope; `details` is check-specific.

```jsonc
{
  "check_name": "timing | rider_route | zone | claim_history | photo",
  "flagged": true,
  "confidence": 0.82,
  "summary": "Drop-off took 45 min against a 35 min promise (+10 min late).",
  "details": { /* check-specific, see below */ }
}
```

### timing.details
```jsonc
{
  "prep_minutes": 19,
  "prep_promised_minutes": 15,
  "prep_delay_minutes": 4,
  "delivery_minutes": 70,
  "delivery_promised_minutes": 35,
  "delivery_delay_minutes": 35,
  "stage_breached": "delivery"   // "prep" | "delivery" | "none"
}
```

### rider_route.details
```jsonc
{
  "total_distance_km": 6.4,
  "straight_line_km": 3.1,
  "detour_ratio": 2.06,          // total_distance / straight_line
  "max_stationary_minutes": 14.5,
  "stationary_points": [{ "lat": 6.93, "lng": 79.86, "minutes": 14.5 }],
  "dropoff_distance_from_address_m": 320,
  "issues": ["long_detour", "long_stationary_stop"]
}
```

### zone.details
```jsonc
{
  "zone_id": "ZONE_A",
  "open_orders_count": 24,
  "late_orders_count": 9,
  "late_ratio": 0.375,
  "threshold": 0.30,
  "zone_wide_delay": true
}
```

### claim_history.details
```jsonc
{
  "claims_last_90_days": 4,
  "approved_ratio": 1.0,
  "reason_diversity": 3,          // distinct complaint reasons used
  "risk_score": 0.71,             // 0..1 heuristic
  "risk_flags": ["high_frequency", "always_approved"]
}
```

### photo.details (Gemini 3.6 Flash multimodal call)
```jsonc
{
  "match": false,
  "expected_items": ["Chicken Biryani"],
  "detected_items": ["Fried Rice"],
  "damage_detected": false,
  "model_notes": "Photo shows fried rice, not biryani; packaging appears intact."
}
```

## 3. Aggregator input

The Fairness Aggregator receives the original case plus all 5 check results:

```jsonc
{
  "case": { /* Case object, section 1 */ },
  "check_results": [
    { "check_name": "timing", "flagged": true, ... },
    { "check_name": "rider_route", "flagged": false, ... },
    { "check_name": "zone", "flagged": false, ... },
    { "check_name": "claim_history", "flagged": false, ... },
    { "check_name": "photo", "flagged": true, ... }
  ]
}
```

See `docs/aggregator_contract.md` for the verdict JSON it must return.
