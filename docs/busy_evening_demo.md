# Busy evening mock + automatic rider reassignment

ResolveX already seeds the demo data required by the challenge:

- merchants across delivery zones
- riders
- customers
- completed historical orders with preparation, pickup, and drop-off timestamps
- rider GPS trails, including a deliberate detour/stationary-stop example
- customer refund histories across low, medium, and high-risk bands
- just-placed "tonight" orders whose future stages and GPS trails are written to `scripts/seed_output/live_orders_plan.json`

## 1. Seed the mock dataset

From the repository root:

```bash
python scripts/seed_data.py
```

This populates Supabase and generates the live replay plan.

## 2. Apply the reassignment audit migration

Run the Supabase migration:

```text
supabase/migrations/20260912_rider_reassignments.sql
```

The replay still runs if the audit table is not installed, but the reassignment history will only be printed to the terminal rather than persisted.

## 3. Replay a busy evening

```bash
python scripts/replay_feed.py --speed 15
```

The feed advances order stages and rider GPS points on an accelerated clock. It proactively flags orders as late before a complaint exists and reports when a zone-wide delay threshold is reached.

## Automatic rider reassignment

When an open order falls at least 8 simulated minutes beyond its promised delivery time, the replay selects the least-loaded alternative rider in the same zone, updates `orders.rider_id`, and routes subsequent GPS points under the new rider. The event is also written to `rider_reassignments` when the migration is installed.

Change the threshold:

```bash
python scripts/replay_feed.py --speed 15 --reassign-after 5
```

Disable the stretch feature for comparison:

```bash
python scripts/replay_feed.py --speed 15 --no-auto-reassign
```

The terminal prints `🔁 AUTO-REASSIGN` whenever the system moves an order to another rider, making the stretch requirement visible during the demo.
