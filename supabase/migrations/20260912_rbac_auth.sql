-- ResolveX role-based access control.
-- Authentication is handled by Supabase Auth. Authorization is stored here,
-- separately from user-editable auth metadata.

create table if not exists public.user_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  email text,
  display_name text,
  role text not null check (role in ('customer', 'ops', 'partner', 'support', 'admin')),
  customer_id uuid references public.customers(id) on delete set null,
  merchant_id uuid references public.merchants(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint partner_requires_merchant check (role <> 'partner' or merchant_id is not null),
  constraint customer_link_consistency check (role = 'customer' or customer_id is null)
);

create index if not exists user_profiles_role_idx on public.user_profiles(role);
create index if not exists user_profiles_customer_idx on public.user_profiles(customer_id);
create index if not exists user_profiles_merchant_idx on public.user_profiles(merchant_id);

alter table public.user_profiles enable row level security;

-- A signed-in user may read only their own authorization profile. Inserts and
-- updates remain backend/SQL-admin only; no client-side mutation policy exists.
drop policy if exists "user_profiles_read_own" on public.user_profiles;
create policy "user_profiles_read_own"
on public.user_profiles
for select
to authenticated
using (auth.uid() = user_id);

create or replace function public.set_user_profiles_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists user_profiles_set_updated_at on public.user_profiles;
create trigger user_profiles_set_updated_at
before update on public.user_profiles
for each row execute function public.set_user_profiles_updated_at();

-- Optional convenience view for administrators using the SQL editor/service role.
create or replace view public.resolve_x_role_summary as
select user_id, email, display_name, role, customer_id, merchant_id, created_at, updated_at
from public.user_profiles;

-- Example role assignments after creating users in Supabase Auth:
-- insert into public.user_profiles(user_id,email,display_name,role)
-- values ('<auth-user-uuid>','ops@example.com','Ops User','ops');
--
-- insert into public.user_profiles(user_id,email,display_name,role,merchant_id)
-- values ('<auth-user-uuid>','partner@example.com','Merchant Partner','partner','<merchant-uuid>');
