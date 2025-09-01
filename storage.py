import json
import os
from typing import Optional

from db import get_db_url, get_conn


ITINERARY_FOLDER = "itineraries"


def _ensure_folder():
    os.makedirs(ITINERARY_FOLDER, exist_ok=True)


def use_db() -> bool:
    return bool(get_db_url())


def _file_path(conversation_id: str) -> str:
    return os.path.join(ITINERARY_FOLDER, f"itinerary_{conversation_id}.json")


def read_itinerary_json(conversation_id: str) -> str:
    if use_db():
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select itinerary_json::text from itineraries where conversation_id = %s",
                    (conversation_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise ValueError(f"No itinerary found for conversation ID: {conversation_id}")
                return row[0]
    # Local fallback
    _ensure_folder()
    path = _file_path(conversation_id)
    if not os.path.exists(path):
        raise ValueError(f"No itinerary found for conversation ID: {conversation_id}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_itinerary_json(conversation_id: str, itinerary_json: str) -> str:
    # Validate JSON
    json.loads(itinerary_json)
    if use_db():
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into itineraries (conversation_id, itinerary_json)
                    values (%s, %s::jsonb)
                    on conflict (conversation_id)
                    do update set itinerary_json = excluded.itinerary_json;
                    """,
                    (conversation_id, itinerary_json),
                )
        return itinerary_json
    # Local fallback
    _ensure_folder()
    path = _file_path(conversation_id)
    # Ensure file exists or will be created
    with open(path, "w", encoding="utf-8") as f:
        f.write(itinerary_json)
    return itinerary_json
