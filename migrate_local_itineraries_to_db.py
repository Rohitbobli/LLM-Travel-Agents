import glob
import json
import os
import re
import sys
from dotenv import load_dotenv

# Load .env for SUPABASE_DB_URL/DATABASE_URL
load_dotenv()

# Try importing drivers; or reuse our db helper
try:
    from db import get_conn
    _USE_HELPER = True
except Exception:
    _USE_HELPER = False
    _DRIVER = None
    try:
        import psycopg as _psycopg  # type: ignore
        _DRIVER = ("psycopg", _psycopg)
    except Exception:
        try:
            import psycopg2 as _psycopg  # type: ignore
            _DRIVER = ("psycopg2", _psycopg)
        except Exception:
            _DRIVER = None


DB_URL = os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")
if DB_URL:
    DB_URL = DB_URL.strip().strip('"').strip("'")
if len(sys.argv) > 1:
    DB_URL = sys.argv[1]

if not DB_URL:
    print("ERROR: Provide SUPABASE_DB_URL/DATABASE_URL env var or pass it as first argument.")
    sys.exit(1)

ITINERARY_DIR = os.path.join(os.getcwd(), "itineraries")
pattern = os.path.join(ITINERARY_DIR, "itinerary_*.json")

print("Scanning:", pattern)
files = glob.glob(pattern)
print(f"Found {len(files)} files")

rx = re.compile(r"itinerary_(?P<cid>[^.]+)\.json$")

print("Connecting to:", DB_URL.split('@')[-1])
# Prefer direct connection with the explicit DB_URL to avoid env mismatches
conn = None
if _DRIVER is not None:
    try:
        name, mod = _DRIVER
        if name == "psycopg":
            conn = mod.connect(DB_URL, autocommit=True)
        else:
            conn = mod.connect(DB_URL)
            try:
                conn.autocommit = True
            except Exception:
                pass
    except Exception:
        conn = None
if conn is None:
    if _USE_HELPER:
        conn = get_conn()
    else:
        raise RuntimeError("No Postgres driver found. Install 'psycopg[binary]' or 'psycopg2-binary'.")

with conn:
    with conn.cursor() as cur:
        for path in files:
            base = os.path.basename(path)
            m = rx.search(base)
            if not m:
                print("Skip (no conv id):", base)
                continue
            cid = m.group("cid")
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = fh.read()
                # Validate JSON
                json.loads(data)
            except Exception as e:
                print("Skip (invalid JSON):", base, e)
                continue
            cur.execute(
                """
                insert into itineraries (conversation_id, itinerary_json)
                values (%s, %s::jsonb)
                on conflict (conversation_id)
                do update set itinerary_json = excluded.itinerary_json;
                """,
                (cid, data),
            )
            print("Upserted:", cid)

print("Done.")
