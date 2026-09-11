# ResolveX authentication and role access

ResolveX uses **Supabase Auth** for login and the `public.user_profiles` table for server-controlled authorization.

## Access matrix

| Role | Customer | Ops Dashboard | Partner Portal | Support Queue | Admin |
|---|---:|---:|---:|---:|---:|
| `customer` | Yes | No | No | No | No |
| `ops` | No | Yes | No | No | No |
| `partner` | No | No | Yes (own merchant only) | No | No |
| `support` | No | No | No | Yes | No |
| `admin` | Yes | Yes | Yes | Yes | Yes |

The frontend route guard improves UX, but it is **not** the security boundary. FastAPI validates the Supabase access token and enforces roles again for protected endpoints.

## 1. Apply the RBAC migration

Run `supabase/migrations/20260912_rbac_auth.sql` in the Supabase SQL editor or through your normal migration workflow.

## 2. Create demo users

Create users in Supabase **Authentication -> Users**. For a 24-hour ideathon, create one account for each role, for example:

- `customer@resolvex.demo`
- `ops@resolvex.demo`
- `partner@resolvex.demo`
- `support@resolvex.demo`
- `admin@resolvex.demo`

Use strong demo passwords and do not commit them.

## 3. Assign roles

Copy each Auth user UUID and insert a profile from the SQL editor.

```sql
insert into public.user_profiles(user_id,email,display_name,role)
values ('<ops-auth-user-id>','ops@resolvex.demo','Ops User','ops');

insert into public.user_profiles(user_id,email,display_name,role)
values ('<support-auth-user-id>','support@resolvex.demo','Support Agent','support');

insert into public.user_profiles(user_id,email,display_name,role)
values ('<admin-auth-user-id>','admin@resolvex.demo','System Admin','admin');
```

A partner **must** be linked to one merchant:

```sql
select id, name from public.merchants order by created_at desc;

insert into public.user_profiles(user_id,email,display_name,role,merchant_id)
values (
  '<partner-auth-user-id>',
  'partner@resolvex.demo',
  'Merchant Partner',
  'partner',
  '<merchant-id>'
);
```

A customer can be linked to an existing customer row:

```sql
select id, name, email from public.customers order by created_at desc;

insert into public.user_profiles(user_id,email,display_name,role,customer_id)
values (
  '<customer-auth-user-id>',
  'customer@resolvex.demo',
  'Customer',
  'customer',
  '<customer-id>'
);
```

## 4. Environment

Frontend requires:

```env
VITE_SUPABASE_URL=...
VITE_SUPABASE_ANON_KEY=...
VITE_API_BASE_URL=http://localhost:8000
```

Backend requires a server key (`SUPABASE_SECRET_KEY` or the legacy `SUPABASE_KEY`). Never expose the server key to Vite.

## 5. Security behavior

- Ops endpoints accept only `ops` and `admin`.
- Demo feed controls accept only `ops` and `admin`.
- Partner case listing is automatically scoped to the logged-in partner's `merchant_id`; the client cannot choose another merchant ID.
- Partner decisions are rejected if the case belongs to another merchant.
- Support review accepts only `support` and `admin`.
- Admin endpoints accept only `admin`.
- Customer notification/evidence endpoints are constrained to the linked customer account.
- Operational map positions are fetched through FastAPI, not directly from Supabase with the browser anon key.

## 6. Quick verification

1. Open `/ops` while signed out -> redirected to `/login`.
2. Sign in as customer and enter `/ops` -> redirected to `/`.
3. Sign in as ops -> `/ops` works; `/partner` and `/support` are inaccessible.
4. Sign in as partner -> only that merchant's cases appear.
5. Sign in as support -> Support Queue works but Ops demo controls and Partner Portal are inaccessible.
6. Sign in as admin -> all sections are available.

Backend authorization can also be checked by calling a protected endpoint with no `Authorization` header (expect `401`) and then with a valid access token for the wrong role (expect `403`).
