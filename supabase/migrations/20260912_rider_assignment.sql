-- Rider assignment lifecycle: offer, accept, decline, reassign.
--
-- A packed order is offered to the nearest available rider. The rider accepts or
-- declines. A declined order is never offered back to the same rider, and an
-- offer nobody answers is re-offered so the order is not stranded.

alter table public.orders
  add column if not exists rider_assigned_at timestamptz;

alter table public.orders
  add column if not exists rider_accepted_at timestamptz;

comment on column public.orders.rider_assigned_at is
  'When the current rider was offered this delivery. Resets on every reassignment.';
comment on column public.orders.rider_accepted_at is
  'When the assigned rider accepted. Null while an offer is outstanding.';

create table if not exists public.rider_reassignments (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders(id) on delete cascade,
  from_rider_id uuid references public.riders(id) on delete set null,
  to_rider_id uuid references public.riders(id) on delete set null,
  reason text not null check (reason in ('auto_assigned', 'rider_rejected', 'offer_expired')),
  created_at timestamptz not null default now()
);

create index if not exists rider_reassignments_order_idx
  on public.rider_reassignments(order_id);

alter table public.rider_reassignments enable row level security;

-- Orders packed before this migration were assigned without an offer timestamp.
update public.orders
set rider_assigned_at = coalesce(ready_at, placed_at),
    rider_accepted_at = coalesce(picked_up_at, rider_accepted_at)
where rider_id is not null
  and rider_assigned_at is null;
