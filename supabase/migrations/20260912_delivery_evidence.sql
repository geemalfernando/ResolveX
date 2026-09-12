-- Private delivery evidence bucket and comparison results.
-- Packing, handover, and claim photos are stored as:
--   {order_id}/packing.{ext}
--   {order_id}/handover.{ext}
--   {order_id}/claim.{ext}

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'delivery-evidence',
  'delivery-evidence',
  false,
  10485760,
  array['image/jpeg', 'image/png', 'image/webp']
)
on conflict (id) do update
set public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

create table if not exists public.delivery_evidence (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders(id) on delete cascade,
  kind text not null check (kind in ('packing', 'handover', 'claim')),
  storage_path text not null,
  content_type text not null,
  uploaded_by uuid,
  created_at timestamptz not null default now(),
  unique (order_id, kind)
);

create index if not exists delivery_evidence_order_idx
  on public.delivery_evidence(order_id);

create table if not exists public.photo_comparisons (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders(id) on delete cascade,
  case_id uuid references public.cases(id) on delete set null,
  packing_path text,
  handover_path text,
  claim_path text,
  fault_party text not null check (fault_party in ('MERCHANT', 'RIDER', 'NEITHER', 'INCONCLUSIVE')),
  confidence numeric not null check (confidence >= 0 and confidence <= 1),
  reasons jsonb not null default '[]'::jsonb,
  details jsonb not null default '{}'::jsonb,
  source text not null default 'gemini',
  created_at timestamptz not null default now(),
  unique (order_id)
);

create index if not exists photo_comparisons_case_idx
  on public.photo_comparisons(case_id);

alter table public.delivery_evidence enable row level security;
alter table public.photo_comparisons enable row level security;
