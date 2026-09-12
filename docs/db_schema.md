# ResolveX — Database Schema (Supabase / Postgres)

All tables live in the `public` schema. IDs are `uuid` (default `gen_random_uuid()`) unless noted.
Timestamps are `timestamptz`, always stored in UTC.

Enable the `pgcrypto` extension for `gen_random_uuid()`:

```sql
create extension if not exists pgcrypto;
```

---

## merchants

One row per restaurant/store partner.

| column        | type          | notes                                  |
|---------------|---------------|-----------------------------------------|
| id            | uuid PK       | default gen_random_uuid()               |
| name          | text          |                                          |
| zone_id       | text          | e.g. "ZONE_A" — coarse delivery zone    |
| address       | text          |                                          |
| lat           | double precision |                                       |
| lng           | double precision |                                       |
| avg_prep_minutes | int        | historical average prep time            |
| created_at    | timestamptz   | default now()                           |

## riders

| column        | type          | notes                                  |
|---------------|---------------|------------------------------------------|
| id            | uuid PK       |                                          |
| name          | text          |                                          |
| phone         | text          |                                          |
| vehicle       | text          | bike / scooter / car                    |
| zone_id       | text          | home zone                               |
| created_at    | timestamptz   | default now()                           |

## customers

| column        | type          | notes                                  |
|---------------|---------------|------------------------------------------|
| id            | uuid PK       |                                          |
| name          | text          |                                          |
| email         | text          | unique                                  |
| phone         | text          |                                          |
| address       | text          |                                          |
| lat           | double precision |                                       |
| lng           | double precision |                                       |
| zone_id       | text          |                                          |
| created_at    | timestamptz   | default now()                           |

## orders

Central order record with stage timestamps used by the TIMING check.

| column                | type          | notes                                                        |
|-----------------------|---------------|---------------------------------------------------------------|
| id                    | uuid PK       |                                                                 |
| merchant_id           | uuid FK -> merchants.id |                                                       |
| rider_id              | uuid FK -> riders.id, nullable | assigned once picked up (or earlier)                 |
| customer_id           | uuid FK -> customers.id |                                                       |
| zone_id               | text          | delivery zone (usually customer's zone)                        |
| items                 | jsonb         | `[{ "name": "Chicken Biryani", "qty": 1, "price": 450 }, ...]` |
| status                | text          | `placed \| preparing \| ready \| picked_up \| dropped_off \| completed \| cancelled` |
| promised_prep_minutes | int           | SLA for merchant prep                                          |
| promised_delivery_minutes | int       | SLA from placed -> dropped_off                                 |
| placed_at             | timestamptz   |                                                                 |
| prep_started_at       | timestamptz   | nullable                                                        |
| ready_at              | timestamptz   | nullable — merchant marks food ready                            |
| picked_up_at          | timestamptz   | nullable — rider collects order                                 |
| dropped_off_at        | timestamptz   | nullable — rider marks delivered                                |
| is_late_flagged       | boolean       | default false — set by the mocked live feed watcher             |
| created_at            | timestamptz   | default now()                                                   |

Indexes: `(zone_id, status)`, `(rider_id)`, `(merchant_id)`.

## rider_gps_points

Append-only GPS trail per order leg (pickup -> drop-off). Powers the RIDER ROUTE check and the live map.

| column        | type          | notes                                  |
|---------------|---------------|------------------------------------------|
| id            | bigserial PK  |                                          |
| order_id      | uuid FK -> orders.id |                                   |
| rider_id      | uuid FK -> riders.id |                                   |
| lat           | double precision |                                       |
| lng           | double precision |                                       |
| speed_kmh     | double precision | nullable                             |
| recorded_at   | timestamptz   |                                          |

Index: `(order_id, recorded_at)`. Realtime is enabled on this table so the dashboard map can subscribe to inserts.

## refund_history

One row per past refund/claim event for a customer. Powers the CLAIM_HISTORY check.

| column        | type          | notes                                  |
|---------------|---------------|------------------------------------------|
| id            | uuid PK       |                                          |
| customer_id   | uuid FK -> customers.id |                               |
| order_id      | uuid FK -> orders.id, nullable |                        |
| reason        | text          | `late \| wrong_item \| damaged \| missing_item \| other` |
| amount        | numeric       |                                          |
| outcome       | text          | `approved \| denied \| voucher`         |
| created_at    | timestamptz   |                                          |

## complaints

Customer-reported problem that kicks off a case.

| column        | type          | notes                                  |
|---------------|---------------|------------------------------------------|
| id            | uuid PK       |                                          |
| order_id      | uuid FK -> orders.id |                                   |
| customer_id   | uuid FK -> customers.id |                                |
| type          | text          | `late \| wrong_item \| damaged \| missing_item` |
| description   | text          | nullable, free text from customer       |
| photo_url     | text          | nullable, Supabase Storage path         |
| created_at    | timestamptz   | default now()                           |

## cases

The assembled case object (see `docs/case_contract.md`) plus a pointer to its verdict.

| column        | type          | notes                                  |
|---------------|---------------|------------------------------------------|
| id            | uuid PK       |                                          |
| order_id      | uuid FK -> orders.id |                                   |
| complaint_id  | uuid FK -> complaints.id, nullable | null for zone-triggered cases |
| trigger       | text          | `customer_complaint \| live_feed_late \| zone_delay` |
| case_payload  | jsonb         | full assembled case object (order, rider trail, merchant, refund history) |
| status        | text          | `open \| checks_running \| aggregated \| resolved` default `open` |
| created_at    | timestamptz   | default now()                           |
| updated_at    | timestamptz   | default now()                           |

## check_results

One row per check run against a case (PHOTO / TIMING / RIDER_ROUTE / ZONE / CLAIM_HISTORY).

| column        | type          | notes                                  |
|---------------|---------------|------------------------------------------|
| id            | uuid PK       |                                          |
| case_id       | uuid FK -> cases.id |                                    |
| check_name    | text          | `photo \| timing \| rider_route \| zone \| claim_history` |
| result        | jsonb         | check-specific output, see `case_contract.md` |
| flagged       | boolean       | whether this check raised a concern     |
| created_at    | timestamptz   | default now()                           |

## verdicts

Output of the Fairness Aggregator LLM call, one per case.

| column        | type          | notes                                  |
|---------------|---------------|------------------------------------------|
| id            | uuid PK       |                                          |
| case_id       | uuid FK -> cases.id, unique |                          |
| claim_valid   | boolean       |                                          |
| fault_party   | text          | `merchant \| rider \| neither \| customer_abuse` |
| confidence    | numeric       | 0..1                                    |
| outcome       | text          | `NEED_MORE_INFO \| AUTO_REFUND \| ZONE_BROADCAST \| SUPPORT_TICKET` |
| reasons       | jsonb         | `[{ "check": "timing", "reason": "..." }, ...]` |
| raw_llm_response | jsonb      | full response for debugging/audit       |
| created_at    | timestamptz   | default now()                           |

## support_tickets

Human-in-the-loop queue, created when a verdict's outcome is `SUPPORT_TICKET`.

| column        | type          | notes                                  |
|---------------|---------------|------------------------------------------|
| id            | uuid PK       |                                          |
| case_id       | uuid FK -> cases.id |                                    |
| assigned_agent| text          | nullable                                |
| status        | text          | `open \| in_progress \| resolved` default `open` |
| resolution_notes | text       | nullable                                |
| created_at    | timestamptz   | default now()                           |
| resolved_at   | timestamptz   | nullable                                |

---

## Realtime

Enable Postgres replication (Supabase Realtime) on:
- `orders` (status changes drive the ops dashboard)
- `rider_gps_points` (live map trails)
- `cases` / `verdicts` (dashboard + Claim Risk live updates)

```sql
alter publication supabase_realtime add table orders;
alter publication supabase_realtime add table rider_gps_points;
alter publication supabase_realtime add table cases;
alter publication supabase_realtime add table verdicts;
```

## Storage

Bucket `complaint-photos` (public read for demo simplicity) holds customer-uploaded photos referenced by `complaints.photo_url`.

## Optional: `open_order_positions` view

The dashboard map (`frontend/src/components/MapView.jsx`) wants one lat/lng per open order.
Orders don't carry their own coordinates — before pickup use the merchant's location, after
pickup use the most recent `rider_gps_points` row. A convenience view:

```sql
create or replace view open_order_positions as
select
  o.id,
  o.zone_id,
  o.status,
  o.is_late_flagged,
  coalesce(g.lat, m.lat) as lat,
  coalesce(g.lng, m.lng) as lng
from orders o
join merchants m on m.id = o.merchant_id
left join lateral (
  select lat, lng
  from rider_gps_points
  where order_id = o.id
  order by recorded_at desc
  limit 1
) g on true
where o.status in ('placed', 'preparing', 'ready', 'picked_up');
```
