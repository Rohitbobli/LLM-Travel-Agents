import os
import sys
from dotenv import load_dotenv

# Load .env so SUPABASE_DB_URL/DATABASE_URL from the file are available
load_dotenv()

# Allow overriding via CLI arg; else read from env
DB_URL = None
if len(sys.argv) > 1:
    DB_URL = sys.argv[1]
else:
    DB_URL = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")

if not DB_URL:
    print("ERROR: Provide SUPABASE_DB_URL/DATABASE_URL env var or pass it as first argument.")
    print("Hint: Add to .env -> SUPABASE_DB_URL=postgresql://... ?sslmode=require")
    sys.exit(1)

# Try importing drivers; or reuse our db helper
try:
    from db import get_conn
    _USE_HELPER = True
except Exception:
    _USE_HELPER = False
    try:
        import psycopg as _psycopg  # type: ignore
        _DRIVER = ("psycopg", _psycopg)
    except Exception:
        import psycopg2 as _psycopg  # type: ignore
        _DRIVER = ("psycopg2", _psycopg)

print("Connecting to:", DB_URL.split('@')[-1])
if _USE_HELPER:
    conn = get_conn()
else:
    name, mod = _DRIVER
    if name == "psycopg":
        conn = mod.connect(DB_URL, autocommit=True)
    else:
        conn = mod.connect(DB_URL)
        try:
            conn.autocommit = True
        except Exception:
            pass

with conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists itineraries (
                conversation_id text primary key,
                itinerary_json jsonb not null,
                created_at timestamptz not null default now(),
                updated_at timestamptz not null default now()
            );
            """
        )
        # Create or replace function, then conditionally create trigger
        cur.execute(
            """
            create or replace function set_updated_at()
            returns trigger as $fn$
            begin
                new.updated_at = now();
                return new;
            end;
            $fn$ language plpgsql;
            """
        )
        cur.execute(
            """
            do $do$
            begin
                if not exists (
                    select 1 from pg_trigger where tgname = 'itineraries_set_updated_at'
                ) then
                    create trigger itineraries_set_updated_at
                    before update on itineraries
                    for each row
                    execute function set_updated_at();
                end if;
            end
            $do$;
            """
        )

print("Supabase table 'itineraries' is ready.")
