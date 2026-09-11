"""Inspect then apply the narrow EXTERNAL migration using configured SQL access.

Credentials are read locally; never printed or passed on command lines.
Management endpoint: https://supabase.com/docs/reference/api/v1-run-a-query
"""
import json
import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
INSPECT = """select a.attname, format_type(a.atttypid, a.atttypmod) as column_type,
 c.conname, pg_get_constraintdef(c.oid) as definition
 from pg_attribute a join pg_constraint c on c.conrelid = a.attrelid and a.attnum = any(c.conkey)
 where a.attrelid = 'public.verdicts'::regclass and a.attname = 'fault_party' and c.contype = 'c';"""


def main():
    config = {**dotenv_values(ROOT / '.env'), **os.environ}
    sql = (ROOT / 'supabase/migrations/20260912_external_fault.sql').read_text()
    if config.get('DATABASE_URL'):
        env = {**os.environ, 'PGDATABASE': config['DATABASE_URL']}
        # libpq accepts a connection URI via PGDATABASE. No credentials in argv/logs.
        for query in [INSPECT, sql, INSPECT]:
            result = subprocess.run(['psql', '-X', '-v', 'ON_ERROR_STOP=1'], input=query, text=True, env=env, capture_output=True)
            if result.returncode:
                raise SystemExit('Database inspection/migration failed; check the configured connection and privileges.')
            print(result.stdout)
    elif config.get('SUPABASE_ACCESS_TOKEN'):
        ref = urlparse(config['SUPABASE_URL']).hostname.split('.')[0]
        with httpx.Client(timeout=30) as client:
            for query in [INSPECT, sql, INSPECT]:
                response = client.post(f'https://api.supabase.com/v1/projects/{ref}/database/query',
                    headers={'Authorization': 'Bearer ' + config['SUPABASE_ACCESS_TOKEN']}, json={'query': query})
                if not response.is_success:
                    raise SystemExit(f'Management SQL request failed (HTTP {response.status_code}); check token permissions.')
                print(json.dumps(response.json(), indent=2))
    else:
        raise SystemExit('Cannot apply migration: DATABASE_URL or SUPABASE_ACCESS_TOKEN is not configured. The Supabase table API key cannot execute this schema migration.')


if __name__ == '__main__':
    main()
