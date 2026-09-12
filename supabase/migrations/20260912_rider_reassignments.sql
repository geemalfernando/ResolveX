create table if not exists public.rider_reassignments (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders(id) on delete cascade,
  from_rider_id uuid references public.riders(id) on delete set null,
  to_rider_id uuid references public.riders(id) on delete set null,
  zone_id text,
  reason text not null default 'sla_breach_auto_rebalance',
  minutes_behind numeric(8,2) not null default 0,
  created_at timestamptz not null default now()
);

create index if not exists rider_reassignments_order_created_idx
  on public.rider_reassignments(order_id, created_at desc);

create index if not exists rider_reassignments_zone_created_idx
  on public.rider_reassignments(zone_id, created_at desc);

alter table public.rider_reassignments enable row level security;

-- The app writes this table only through the backend/service client. Read access
-- can be exposed through authenticated FastAPI workflow endpoints when needed.
