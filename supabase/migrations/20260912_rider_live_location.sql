alter table public.riders
  add column if not exists lat double precision,
  add column if not exists lng double precision,
  add column if not exists last_location_at timestamptz;

create index if not exists riders_zone_location_idx
  on public.riders(zone_id, last_location_at desc);

-- Extend RBAC so rider accounts can be represented in user_profiles too.
alter table public.user_profiles
  add column if not exists rider_id uuid references public.riders(id) on delete set null;

alter table public.user_profiles
  drop constraint if exists user_profiles_role_check;

alter table public.user_profiles
  add constraint user_profiles_role_check
  check (role in ('customer', 'ops', 'partner', 'support', 'admin', 'rider'));

create index if not exists user_profiles_rider_idx
  on public.user_profiles(rider_id);

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
