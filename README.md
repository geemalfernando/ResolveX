# ResolveX

Real-time last-mile delivery problem detection and fair dispute resolution.
Built for CodeArena'26, Topic 3 — "Managing last-mile delivery problems in real time."

ResolveX watches live deliveries, flags problems before customers even complain, assembles
a full case (order, timestamps, rider GPS trail, merchant, refund history), runs it through
five checks, predicts responsibility with a local trained classifier, and applies resolution rules for an instant
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
                                       |--> 5 CHECKS (evidence from the Case)
                                       |      - PHOTO         (AI: Gemini 3.6 Flash, multimodal)
                                       |      - TIMING        (local ETA model + timestamps)
                                       |      - RIDER_ROUTE   (plain code geometry)
                                       |      - ZONE          (plain code)
                                       |      - CLAIM_HISTORY (plain code / rules)
                                       |
                                       |--> FAULT CLASSIFIER + FAIRNESS RULES
                                       |      strict JSON verdict: claim_valid, fault_party,
                                       |      confidence, outcome, reasons[]
                                       |      predict + predict_proba -> resolution constraints
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
│       ├── aggregator/     aggregator.py (fault inference + resolution constraints)
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

### Training and verifying the models

See [the training and inference guide](docs/fault_inference.md) for local dataset paths,
reproducible commands and model evaluation. Both datasets are installed locally; the
fault classifier uses controlled noisy scenarios derived from those operational rows.
They do not provide historical fault labels. Model metadata and the UI disclose this.

`GET /api/model/status` reports ETA/fault loading state. The API returns predicted
responsibility, model probabilities and resolution separately. Missing photos only
block photo-relevant complaints. Run the saved-artifact API tests to exercise all four
fault classes; model confidence and business constraints determine the final outcome.

### Photo evidence

`backend/app/checks/photo.py` uses Gemini when configured with `GEMINI_API_KEY`.
Unavailable photo analysis is marked inconclusive. Final fault inference runs locally.

## Contracts

See [`docs/case_contract.md`](docs/case_contract.md) and
[`docs/aggregator_contract.md`](docs/aggregator_contract.md) for the exact JSON shapes
passed between the Case Builder, the five checks, and the Fairness Aggregator — read these
before changing any check's output shape, since model features are extracted from them.
