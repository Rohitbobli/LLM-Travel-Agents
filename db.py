import os
from typing import Optional, Tuple

# Try psycopg (v3) first, then psycopg2 as a fallback
_driver = None  # type: Optional[Tuple[str, object]]
try:
    import psycopg as _psycopg  # type: ignore

    _driver = ("psycopg", _psycopg)
except Exception:
    try:
        import psycopg2 as _psycopg  # type: ignore

        _driver = ("psycopg2", _psycopg)
    except Exception:
        _driver = None


def get_db_url() -> Optional[str]:
    url = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
    if url:
        # Trim whitespace and surrounding quotes that can sneak into .env
        url = url.strip().strip('"').strip("'")
    return url


def get_conn():
    db_url = get_db_url()
    if not db_url:
        raise RuntimeError("SUPABASE_DB_URL or DATABASE_URL is not set in environment")
    if not _driver:
        raise RuntimeError(
            "No Postgres driver found. Install either 'psycopg[binary]' (v3) or 'psycopg2-binary'."
        )
    name, mod = _driver
    if name == "psycopg":  # v3
        return mod.connect(db_url, autocommit=True)
    else:  # psycopg2
        conn = mod.connect(db_url)
        try:
            conn.autocommit = True
        except Exception:
            pass
        return conn


def init_db() -> None:
    """Create itineraries table if it doesn't exist."""
    with get_conn() as conn:
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
            # Ensure the function exists (use distinct dollar-quoting to avoid nesting issues)
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
            # Ensure trigger exists
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
