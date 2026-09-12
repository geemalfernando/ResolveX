-- Adds the zone_broadcasts table: one row per open order's customer, notified when a
-- ZONE_BROADCAST verdict fires for that zone. Closes the "zone-wide delay triggers a
-- notice to every affected customer" requirement from the brief.
begin;

create table if not exists public.zone_broadcasts (
  id uuid primary key default gen_random_uuid(),
  case_id uuid not null references public.cases(id) on delete cascade,
  zone_id text not null,
  order_id uuid not null references public.orders(id),
  customer_id uuid not null references public.customers(id),
  message text not null,
  created_at timestamptz not null default now()
);

create index if not exists zone_broadcasts_zone_id_idx on public.zone_broadcasts(zone_id);
create index if not exists zone_broadcasts_order_id_idx on public.zone_broadcasts(order_id);
create index if not exists zone_broadcasts_customer_id_idx on public.zone_broadcasts(customer_id);

do $$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'zone_broadcasts'
  ) then
    alter publication supabase_realtime add table public.zone_broadcasts;
  end if;
end;
$$;

commit;
