# ResolveX authentication and role access

ResolveX uses **Supabase Auth** for login and the `public.user_profiles` table for server-controlled authorization.

## Access matrix

| Role | Customer | Ops Dashboard | Partner Portal | Claim Risk | Admin |
|---|---:|---:|---:|---:|---:|
| `customer` | Yes | No | No | No | No |
| `ops` | No | Yes | No | No | No |
| `partner` | No | No | Yes (own merchant only) | No | No |
| `support` | No | No | No | Yes | No |
| `admin` | Yes | Yes | Yes | Yes | Yes |

The frontend route guard improves UX, but it is **not** the security boundary. FastAPI validates the Supabase access token and enforces roles again for protected endpoints.

## 1. Apply the RBAC migration

Run `supabase/migrations/20260912_rbac_auth.sql` in the Supabase SQL editor or through your normal migration workflow.

Do not execute the `.sql` file directly in zsh. For a quick local copy:

```bash
pbcopy < supabase/migrations/20260912_rbac_auth.sql
```

Paste it into **Supabase -> SQL Editor -> New query -> Run**.

Verify:

```sql
select * from public.user_profiles;
```

## 2. Seed all five demo login accounts automatically

A `400` from `/auth/v1/token?grant_type=password` normally means the Supabase Auth user does not exist yet, the password is wrong, or the account is not confirmed. Creating only a row in `public.user_profiles` does not create an Auth login.

ResolveX therefore includes an idempotent server-side seeder that creates/updates the Auth users, confirms their emails, creates a demo customer and merchant if needed, and links every role in `user_profiles`.

Your root `.env` must contain:

```env
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SECRET_KEY=<server secret key>
```

For the hackathon-only credentials, run:

```bash
python scripts/seed_demo_auth_users.py --demo-passwords
```

It creates/updates:

| Role | Email | Demo password |
|---|---|---|
| Customer | `customer@resolvex.demo` | `ResolveX@Customer26` |
| Ops | `ops@resolvex.demo` | `ResolveX@Ops26` |
| Partner | `partner@resolvex.demo` | `ResolveX@Partner26` |
| Support | `support@resolvex.demo` | `ResolveX@Support26` |
| Admin | `admin@resolvex.demo` | `ResolveX@Admin26` |

These passwords are intentionally public demo credentials. Do not use them for production.

For custom passwords, omit `--demo-passwords` and export:

```bash
export DEMO_CUSTOMER_PASSWORD='...'
export DEMO_OPS_PASSWORD='...'
export DEMO_PARTNER_PASSWORD='...'
export DEMO_SUPPORT_PASSWORD='...'
export DEMO_ADMIN_PASSWORD='...'
python scripts/seed_demo_auth_users.py
```

The script is safe to rerun: existing Auth users are updated rather than duplicated.

## 3. Manual role assignment alternative

If you prefer to create users manually in Supabase **Authentication -> Users**, copy each Auth user UUID and insert a profile from the SQL editor.

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

Backend and the demo-user seeder require a server key (`SUPABASE_SECRET_KEY` or the legacy `SUPABASE_KEY`). Never expose the server key to Vite.

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
3. Sign in as ops -> `/ops` works; `/partner` and `/claims` are inaccessible.
4. Sign in as partner -> only that merchant's cases appear.
5. Sign in as support -> Claim Risk works but Ops demo controls and Partner Portal are inaccessible.
6. Sign in as admin -> all sections are available.

Backend authorization can also be checked by calling a protected endpoint with no `Authorization` header (expect `401`) and then with a valid access token for the wrong role (expect `403`).
