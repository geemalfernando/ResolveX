alter table public.riders
  add column if not exists lat double precision,
  add column if not exists lng double precision,
  add column if not exists last_location_at timestamptz;

create index if not exists riders_zone_location_idx
  on public.riders(zone_id, last_location_at desc);

create table if not exists public.rider_reassignments (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders(id) on delete cascade,
  from_rider_id uuid references public.riders(id),
  to_rider_id uuid references public.riders(id),
  reason text not null,
  created_at timestamptz not null default now()
);

create index if not exists rider_reassignments_order_created_idx
  on public.rider_reassignments(order_id, created_at desc);
