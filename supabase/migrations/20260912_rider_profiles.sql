-- Riders need a row in public.user_profiles like every other role.
-- Without it, rider identity exists only in Supabase auth app_metadata, so the
-- server cannot tell which riders are able to work a delivery and
-- auto-assignment falls back to scanning the auth admin API.

alter table public.user_profiles
  add column if not exists rider_id uuid references public.riders(id) on delete set null;

alter table public.user_profiles
  drop constraint if exists user_profiles_role_check;

alter table public.user_profiles
  add constraint user_profiles_role_check
  check (role in ('customer', 'ops', 'partner', 'support', 'admin', 'rider'));

alter table public.user_profiles
  drop constraint if exists rider_requires_rider_id;

alter table public.user_profiles
  add constraint rider_requires_rider_id
  check (role <> 'rider' or rider_id is not null);

create index if not exists user_profiles_rider_idx on public.user_profiles(rider_id);

create or replace view public.resolve_x_role_summary as
select user_id, email, display_name, role, customer_id, merchant_id, rider_id, created_at, updated_at
from public.user_profiles;

-- Backfill existing rider logins from trusted auth app_metadata.
insert into public.user_profiles (user_id, email, display_name, role, rider_id)
select
  u.id,
  u.email,
  coalesce(u.raw_app_meta_data ->> 'display_name', split_part(u.email, '@', 1)),
  'rider',
  (u.raw_app_meta_data ->> 'rider_id')::uuid
from auth.users u
where u.raw_app_meta_data ->> 'role' = 'rider'
  and u.raw_app_meta_data ->> 'rider_id' is not null
  and exists (select 1 from public.riders r where r.id = (u.raw_app_meta_data ->> 'rider_id')::uuid)
on conflict (user_id) do update
set role = 'rider',
    rider_id = excluded.rider_id,
    email = excluded.email,
    display_name = excluded.display_name;
