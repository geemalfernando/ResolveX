# ResolveX

Real-time last-mile delivery problem detection and fair dispute resolution.
Built for CodeArena'26, Topic 3 — "Managing last-mile delivery problems in real time."

ResolveX watches live deliveries, flags problems before customers even complain, assembles
a full case (order, timestamps, rider GPS trail, merchant, refund history), runs it through
five checks, and has a single AI Fairness Aggregator call decide the outcome: an instant
refund, a zone-wide delay notice, one more question for the customer, or a ticket for a human
support agent.

## Architecture

```
                                CUSTOMER APP (React, phone width)
                                        |
                                        | POST /cases (complaint + photo)
                                        v
   mocked live order feed  --->  FASTAPI BACKEND
   (scripts/replay_feed.py)           |
   flags late orders BEFORE           |--> CASE BUILDER
   any complaint arrives              |      pulls: order + items + timestamps,
                                       |      rider GPS trail, merchant, customer,
                                       |      refund history  --> Case object
                                       |
                                       |--> 5 CHECKS (run in parallel over the Case)
                                       |      - PHOTO         (AI: Gemini 2.5 Flash, multimodal)
                                       |      - TIMING        (plain code)
                                       |      - RIDER_ROUTE   (plain code geometry)
                                       |      - ZONE          (plain code)
                                       |      - CLAIM_HISTORY (plain code / rules)
                                       |
                                       |--> FAIRNESS AGGREGATOR (AI: 1 Gemini call)
                                       |      strict JSON verdict: claim_valid, fault_party,
                                       |      confidence, outcome, reasons[]
                                       |      backend enforces: confidence < 0.6 or disputed
                                       |      fault -> outcome forced to SUPPORT_TICKET
                                       |
                                       v
                              4 possible outcomes
                    NEED_MORE_INFO | AUTO_REFUND | ZONE_BROADCAST | SUPPORT_TICKET
                                       |
                        writes cases / check_results / verdicts / support_tickets
                                       |
                                       v
                            SUPABASE (Postgres + Auth + Storage + Realtime)
                                       |
                     Realtime pushes order/GPS/case/verdict changes to:
                                       |
        +------------------+----------+-----------------+
        |                  |                             |
   OPS DASHBOARD      PARTNER PORTAL                SUPPORT QUEUE
   live Leaflet map   merchant sees & responds      agent mediates disputed
   of open/late/       to complaints on their        SUPPORT_TICKET cases
   disputed orders     own orders
```

All AI calls (PHOTO check, Fairness Aggregator) happen **only** in the FastAPI backend —
the frontend never talks to Gemini directly.

## Repo structure

```
resolvex/
├── frontend/        React + Vite + Tailwind. Routes: / (CustomerApp), /ops (OpsDashboard),
│                    /partner (PartnerPortal), /support (SupportQueue). Leaflet + OSM map,
│                    wired to Supabase Realtime.
├── backend/         FastAPI app.
│   └── app/
│       ├── routers/        cases.py, checks.py, aggregator.py, orders.py
│       ├── checks/         timing.py, zone.py, claim_history.py, rider_route.py (real logic),
│       │                   photo.py (Gemini stub)
│       ├── aggregator/     prompt.py, schema.py, aggregator.py (Gemini stub + outcome overrides)
│       ├── case_builder.py Case Builder — assembles the Case object from Supabase
│       ├── models.py       Pydantic schemas shared across the pipeline
│       ├── db.py, config.py
│       └── main.py
├── scripts/
│   ├── seed_data.py     Faker-generated merchants/riders/customers/orders, incl. a deliberate
│   │                    rider detour and a "tonight" order batch for the zone-delay demo
│   ├── replay_feed.py   Plays tonight's orders live on an accelerated timer
│   └── common.py        Shared Supabase client + geo helpers
├── docs/
│   ├── db_schema.md            Postgres schema (all tables + Realtime + Storage setup)
│   ├── case_contract.md        Case object + check result JSON shapes
│   └── aggregator_contract.md  Fairness Aggregator input/output JSON contract
├── .env.example
└── .gitignore
```

## Prerequisites

- Python 3.11+
- Node.js 18+
- A Supabase project (free tier is fine)
- A Gemini API key ([Google AI Studio](https://aistudio.google.com/apikey))

## Setup

### 1. Supabase

1. Create a project at [supabase.com](https://supabase.com).
2. In the SQL editor, run the table definitions from [`docs/db_schema.md`](docs/db_schema.md)
   (all `create table` statements, the Realtime `alter publication` statements, and the
   optional `open_order_positions` view).
3. Create a public Storage bucket named `complaint-photos`.
4. Grab your Project URL, `service_role` key (backend/scripts), and `anon` key (frontend)
   from Project Settings -> API.

### 2. Environment variables

```bash
cp .env.example .env
# fill in SUPABASE_URL, SUPABASE_KEY (service role), GEMINI_API_KEY

cp .env.example frontend/.env
# in frontend/.env, keep only the VITE_* vars, using the anon key for VITE_SUPABASE_ANON_KEY
```

### 3. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API docs at http://localhost:8000/docs once it's running.

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. `/` is the customer complaint form (phone width), `/ops` is the
live ops map, `/partner` is the merchant portal, `/support` is the human agent queue.

### 5. Seed data + live replay

```bash
cd scripts
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python seed_data.py       # merchants, riders, customers, historical + "tonight" orders
python replay_feed.py     # plays tonight's orders live on an accelerated timer (--speed 15 default)
```

`seed_data.py` prints out the ID of the order it deliberately gave a rider detour + long
stationary stop (for demoing the RIDER_ROUTE check / a disputed SUPPORT_TICKET). It also
writes `scripts/seed_output/live_orders_plan.json`, which `replay_feed.py` reads and plays
back — 8 of 10 "tonight" orders in `ZONE_B` are deliberately planned to run late, so partway
through the replay you'll see console lines like:

```
🚨 flagged LATE (elapsed 42m > promised 35m)
⛈️  ZONE-WIDE DELAY in ZONE_B: 3/10 open orders late (30%) -> trigger a zone_delay case for a ZONE_BROADCAST demo
```

### Demoing all four outcomes

| Outcome           | How to trigger it                                                                 |
|--------------------|-------------------------------------------------------------------------------------|
| `ZONE_BROADCAST`   | Run `replay_feed.py`; once `ZONE_B` crosses the late-ratio threshold, `POST /cases` with `trigger: "zone_delay"` for any open `ZONE_B` order. |
| `AUTO_REFUND`      | File a complaint (via the Customer App or `POST /cases`) against a normal, on-time order with a clean claim history and a photo that doesn't match the order — PHOTO + TIMING agree, confidence is high. |
| `SUPPORT_TICKET`   | File a complaint against the seeded rider-detour order — RIDER_ROUTE flags the rider while ZONE may not, or confidence lands under 0.6. |
| `NEED_MORE_INFO`   | File a complaint with no `photo_url` — the PHOTO check has nothing to compare, so the aggregator asks for another photo. |

## Wiring up Gemini

Both AI call sites are stubbed so the rest of the pipeline runs end-to-end without a key:

- [`backend/app/checks/photo.py`](backend/app/checks/photo.py) — `_call_gemini(...)`
- [`backend/app/aggregator/aggregator.py`](backend/app/aggregator/aggregator.py) — `_call_gemini(...)`

Each stub has a `TODO` comment with the exact `google-genai` client call to drop in once
`GEMINI_API_KEY` is set in `.env`. The aggregator's structured-output schema is already
defined in [`backend/app/aggregator/schema.py`](backend/app/aggregator/schema.py).

## Contracts

See [`docs/case_contract.md`](docs/case_contract.md) and
[`docs/aggregator_contract.md`](docs/aggregator_contract.md) for the exact JSON shapes
passed between the Case Builder, the five checks, and the Fairness Aggregator — read these
before changing any check's output shape, since the aggregator prompt embeds them verbatim.
