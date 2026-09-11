-- Live REST schema: public.verdicts.fault_party is text.
-- Live PostgreSQL error 23514 confirms constraint verdicts_fault_party_check.
-- Inspect its definition in pg_catalog before replacing it; retain existing parties.
begin;
set local lock_timeout = '5s';
do $$
declare
  definition text;
  column_type text;
begin
  select data_type into column_type from information_schema.columns
  where table_schema = 'public' and table_name = 'verdicts' and column_name = 'fault_party';
  if column_type is distinct from 'text' then
    raise exception 'Unexpected verdict fault_party type: %', column_type;
  end if;
  select pg_get_constraintdef(oid) into definition from pg_constraint
  where conrelid = 'public.verdicts'::regclass and conname = 'verdicts_fault_party_check' and contype = 'c';
  if definition is null or definition not like '%merchant%' or definition not like '%rider%'
     or definition not like '%neither%' or definition not like '%customer_abuse%' then
    raise exception 'Unexpected verdict fault constraint: %', definition;
  end if;
  raise notice 'Existing verdict constraint: %', definition;
  if position('external' in definition) = 0 then
    alter table public.verdicts drop constraint verdicts_fault_party_check;
    alter table public.verdicts add constraint verdicts_fault_party_check
      check (fault_party in ('merchant', 'rider', 'external', 'neither', 'customer_abuse'));
  end if;
end $$;
commit;
