import asyncio
import json
import os
import time
import csv
from datetime import datetime, timedelta
from dotenv import load_dotenv
from agents import (
    Agent, Runner, trace, ItemHelpers, MessageOutputItem, TResponseInputItem,
    RunContextWrapper, HandoffOutputItem, ToolCallItem, ToolCallOutputItem,
    WebSearchTool, function_tool
)
from pydantic import BaseModel
from typing import List, Dict, Any, Tuple
import uuid
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Storage: file or Supabase
from storage import read_itinerary_json as storage_read_itinerary_json
from storage import write_itinerary_json as storage_write_itinerary_json
logger.info("Storage initialized (DB=%s)", bool(os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL")))

# Agoda config from environment
# Support either AGODA_BASE_URL or AGODA_API_BASE_URL in .env
AGODA_BASE_URL = (os.getenv("AGODA_BASE_URL") or os.getenv("AGODA_API_BASE_URL") or "").rstrip("/")
AGODA_API_KEY = os.getenv("AGODA_API_KEY", "")
# Optional: override the POST endpoint path if your affiliate API uses a specific route
# Default to '/hotels/search' to match typical affiliate search
AGODA_SEARCH_PATH = os.getenv("AGODA_SEARCH_PATH", "")
CITY_MAPPING_CSV = os.path.join(os.getcwd(), "city_mapping.csv")
logger.info("Agoda config loaded: base_url=%s, search_path=%s, csv=%s", AGODA_BASE_URL or "<unset>", AGODA_SEARCH_PATH or "<default>", CITY_MAPPING_CSV)

# Simple in-memory cache for city mapping
_CITY_NAME_TO_ID: Dict[str, int] = {}

def _normalize_city_name(name: str) -> str:
    return (name or "").strip().casefold()

def load_city_mapping() -> Dict[str, int]:
    global _CITY_NAME_TO_ID
    if _CITY_NAME_TO_ID:
        return _CITY_NAME_TO_ID
    mapping: Dict[str, int] = {}
    if os.path.exists(CITY_MAPPING_CSV):
        logger.debug("Loading city mapping from %s", CITY_MAPPING_CSV)
        with open(CITY_MAPPING_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    city_id = int(row.get("city_id") or row.get("cityId") or 0)
                except Exception:
                    continue
                city_name = row.get("city") or row.get("city_name") or ""
                if city_id and city_name:
                    mapping[_normalize_city_name(city_name)] = city_id
    _CITY_NAME_TO_ID = mapping
    logger.info("Loaded %d city mappings", len(mapping))
    return mapping

def map_city_to_id(city_name: str) -> int | None:
    mapping = load_city_mapping()
    return mapping.get(_normalize_city_name(city_name))

def infer_rate_range(budget: str | None) -> Tuple[int, int]:
    # Map simple budget labels to nightly USD ranges
    if not budget:
        return (20, 500)
    b = budget.strip().lower()
    if b in {"budget", "cheap", "low"}:
        return (20, 80)
    if b in {"mid", "mid-range", "medium"}:
        return (80, 200)
    if b in {"luxury", "high", "premium"}:
        return (200, 800)
    # fallback if numeric string like "150"
    try:
        val = int(float(b))
        return (max(20, int(val * 0.5)), max(40, int(val * 1.25)))
    except Exception:
        return (20, 500)

# Simple rate limiting (1 req/sec) and retries
RATE_LIMIT_SECONDS = 1.0
_LAST_CALL_TIME = 0.0
MAX_RETRIES = 3

def _rate_limit():
    global _LAST_CALL_TIME
    now = time.time()
    elapsed = now - _LAST_CALL_TIME
    if elapsed < RATE_LIMIT_SECONDS:
        sleep_for = RATE_LIMIT_SECONDS - elapsed
        logger.debug("Rate limiting Agoda request: sleeping %.2fs", sleep_for)
        time.sleep(sleep_for)
    _LAST_CALL_TIME = time.time()

# --- Pydantic Models ---
class ItineraryDay(BaseModel):
    date: str
    day_number: int
    location: str
    activities: List[str]
    transportation: str
    accommodation: Any  # Can be full Agoda response (dict), list, or strings
    notes: str

class ItineraryOutput(BaseModel):
    destination: str
    description: str
    start_date: str
    end_date: str
    duration_days: int
    itinerary: List[ItineraryDay]

class TripPlannerContext(BaseModel):
    destination: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    budget: str | None = None
    travel_style: str | None = None
    number_of_people: int | None = None
    conversation_id: str | None = None

# --- Tools ---
def _read_itinerary_json(conv_id: str) -> str:
    data = storage_read_itinerary_json(conv_id)
    logger.info("Itinerary loaded for %s (storage)", conv_id)
    return data

def _update_itinerary_json(conv_id: str, updated_itinerary: str) -> str:
    storage_write_itinerary_json(conv_id, updated_itinerary)
    logger.info("Itinerary updated for %s (storage)", conv_id)
    return updated_itinerary

@function_tool
async def update_context_tool(
    context: RunContextWrapper[TripPlannerContext],
    destination: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    budget: str | None = None,
    travel_style: str | None = None,
    number_of_people: int | None = None,
    conversation_id: str | None = None,
) -> None:
    logger.info(
        "Updating context (partial allowed): dest=%s, %s->%s, budget=%s, style=%s, people=%s, conv_id=%s",
        destination,
        start_date,
        end_date,
        budget,
        travel_style,
        number_of_people,
        conversation_id,
    )
    if destination is not None:
        context.context.destination = destination
    if start_date is not None:
        context.context.start_date = start_date
    if end_date is not None:
        context.context.end_date = end_date
    if budget is not None:
        context.context.budget = budget
    if travel_style is not None:
        context.context.travel_style = travel_style
    if number_of_people is not None:
        context.context.number_of_people = number_of_people
    if conversation_id is not None:
        context.context.conversation_id = conversation_id

@function_tool
async def create_itinerary_json_tool(
    context: RunContextWrapper[TripPlannerContext],
    activities_per_day: List[List[str]],
    transportation: List[str],
    accommodations: List[List[str]],
    notes: List[str],
    description: str,
    conversation_id: str | None = None
) -> str:
    logger.info("Creating itinerary JSON for conversation ID: %s", conversation_id)
    
    if not (context.context.start_date and context.context.end_date and context.context.destination):
        raise ValueError("Missing required context: destination, start_date, or end_date")
    
    start_date = datetime.strptime(context.context.start_date, "%Y-%m-%d")
    end_date = datetime.strptime(context.context.end_date, "%Y-%m-%d")
    duration_days = (end_date - start_date).days + 1
    
    itinerary_days = []
    for i in range(duration_days):
        day_date = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
        activities = activities_per_day[i] if i < len(activities_per_day) else []
        transport = transportation[i] if i < len(transportation) else "None"
        stay = accommodations[i] if i < len(accommodations) else []
        note = notes[i] if i < len(notes) else ""
        
        itinerary_days.append(
            ItineraryDay(
                date=day_date,
                day_number=i + 1,
                location=context.context.destination,
                activities=activities,
                transportation=transport,
                accommodation=stay,
                notes=note
            )
        )
    
    itinerary_output = ItineraryOutput(
        destination=context.context.destination,
        description=description,
        start_date=context.context.start_date,
        end_date=context.context.end_date,
        duration_days=duration_days,
        itinerary=itinerary_days
    )
    
    itinerary_json = json.dumps(itinerary_output.dict(), indent=2)
    conv_id = conversation_id or context.context.conversation_id or uuid.uuid4().hex[:16]
    # Ensure context knows the conv_id for subsequent calls
    context.context.conversation_id = conv_id
    storage_write_itinerary_json(conv_id, itinerary_json)
    logger.info("Itinerary saved for %s (storage)", conv_id)
    
    return itinerary_json

@function_tool
async def update_itinerary_json_tool(
    context: RunContextWrapper[TripPlannerContext],
    updated_itinerary: str,
    conversation_id: str | None = None,
) -> str:
    conv_id = conversation_id or context.context.conversation_id
    if not conv_id:
        raise ValueError("conversation_id not provided and not set in context")
    return _update_itinerary_json(conv_id, updated_itinerary)

@function_tool
async def read_itinerary_json_tool(
    context: RunContextWrapper[TripPlannerContext],
    conversation_id: str | None = None,
) -> str:
    """Read and return the itinerary JSON string for the given or current conversation."""
    conv_id = conversation_id or context.context.conversation_id
    if not conv_id:
        raise ValueError("conversation_id not provided and not set in context")
    return _read_itinerary_json(conv_id)

@function_tool
async def populate_accommodations_from_agoda_tool(
    context: RunContextWrapper[TripPlannerContext],
    conversation_id: str | None = None,
) -> str:
    """Populate accommodations in the itinerary JSON using Agoda affiliate API and return updated JSON.

    Uses city_mapping.csv to map city names to city IDs. Respects context budget and number_of_people.
    """
    conv_id = conversation_id or context.context.conversation_id
    if not conv_id:
        raise ValueError("conversation_id not provided and not set in context")
    # Preconditions
    if not AGODA_BASE_URL or not AGODA_API_KEY:
        raise RuntimeError("AGODA_BASE_URL or AGODA_API_KEY not configured in environment")
    logger.info("[Agoda] Start populate: conv_id=%s, base_url=%s, search_path=%s", conv_id, AGODA_BASE_URL, AGODA_SEARCH_PATH or "<default>")

    # Read itinerary
    # Use internal helper to avoid nested tool invocation
    itinerary_json = _read_itinerary_json(conv_id)
    itinerary = json.loads(itinerary_json)

    # Compute occupancy
    adults = max(1, int(context.context.number_of_people or 2))
    children = 0
    childrenAges: List[int] = []

    min_rate, max_rate = infer_rate_range(context.context.budget)
    # If budget looks like a total trip budget (numeric and large), derive nightly range from nights
    try:
        budget_val = float(context.context.budget) if context.context.budget is not None else None
    except Exception:
        budget_val = None
    if budget_val and budget_val > 500:
        nights = max(1, len(itinerary.get("itinerary", [])))
        nightly_base = budget_val / nights
        # Use a reasonable band around nightly average
        min_rate = max(20, int(nightly_base * 0.5))
        max_rate = max(min_rate + 20, int(nightly_base * 1.5))
        logger.info(
            "[Agoda] Recalculated nightly range from total budget: nights=%s, base=%.2f -> $%s-$%s",
            nights,
            nightly_base,
            min_rate,
            max_rate,
        )
    logger.info("[Agoda] Using occupancy: adults=%s children=%s ages=%s; nightly range: $%s-$%s", adults, children, childrenAges, min_rate, max_rate)

    # Iterate days and fetch accommodations per night
    updated_days: List[Dict[str, Any]] = []
    for i, day in enumerate(itinerary.get("itinerary", [])):
        day_dict = dict(day)
        city_name = day_dict.get("location") or itinerary.get("destination")
        city_id = map_city_to_id(city_name or "")
        # Determine check-in/out per night
        check_in = day_dict.get("date")
        # Checkout is next day if available
        if i + 1 < len(itinerary["itinerary"]):
            check_out = itinerary["itinerary"][i + 1]["date"]
        else:
            # fallback to same day + 1
            try:
                dt = datetime.strptime(check_in, "%Y-%m-%d") + timedelta(days=1)
                check_out = dt.strftime("%Y-%m-%d")
            except Exception:
                check_out = check_in

        logger.info("[Agoda][Day %s] date=%s city='%s' -> city_id=%s, stay %s -> %s", i + 1, check_in, city_name, city_id, check_in, check_out)

        agoda_response: Any = None
        if city_id:
            try:
                import httpx
                payload = {
                    "criteria": {
                        "additional": {
                            "currency": "USD",
                            "dailyRate": {
                                "maximum": max_rate,
                                "minimum": min_rate,
                            },
                            "discountOnly": False,
                            "language": "en-us",
                            "maxResult": 3,
                            "minimumReviewScore": 0,
                            "minimumStarRating": 0,
                            "occupancy": {
                                "numberOfAdult": adults,
                                "numberOfChildren": children,
                                "childrenAges": childrenAges,
                            },
                            "sortBy": "PriceAsc",
                        },
                        "checkInDate": check_in,
                        "checkOutDate": check_out,
                        "cityId": city_id,
                    }
                }

                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip,deflate",
                    # Some affiliate gateways expect different auth header/casing
                    "Authorization": AGODA_API_KEY,
                    "apiKey": AGODA_API_KEY,
                    "ApiKey": AGODA_API_KEY,
                }
                # Build endpoint list:
                # - If AGODA_SEARCH_PATH is provided, try that first then a couple fallbacks.
                # - If not provided, post directly to the base URL only (to match Postman usage).
                candidate_paths = []
                if AGODA_SEARCH_PATH:
                    p = AGODA_SEARCH_PATH if AGODA_SEARCH_PATH.startswith("/") else f"/{AGODA_SEARCH_PATH}"
                    candidate_paths.append(p)
                    for fb in ("/hotels/search", "/search"):
                        if fb not in candidate_paths:
                            candidate_paths.append(fb)
                else:
                    candidate_paths.append("")
                logger.debug("[Agoda][Day %s] Candidate paths: %s", i + 1, ", ".join(candidate_paths))
                resp_json = None
                resp_error: Dict[str, Any] | None = None
                with httpx.Client(timeout=20.0) as client:
                    for path in candidate_paths:
                        url = f"{AGODA_BASE_URL}{path}"
                        logger.info(
                            "[Agoda][Day %s] POST %s (cityId=%s, %s->%s, maxResult=%s)",
                            i + 1,
                            url,
                            city_id,
                            check_in,
                            check_out,
                            payload["criteria"]["additional"]["maxResult"],
                        )
                        for attempt in range(1, MAX_RETRIES + 1):
                            try:
                                _rate_limit()
                                # Affiliate search is a POST endpoint
                                t0 = time.time()
                                r = client.post(url, headers=headers, json=payload)
                                dt_ms = int((time.time() - t0) * 1000)
                                if r.status_code == 200:
                                    resp_json = r.json()
                                    logger.info("[Agoda][Day %s] 200 OK in %sms, parsing response", i + 1, dt_ms)
                                    break
                                else:
                                    logger.warning("[Agoda][Day %s] POST %s -> %s in %sms", i + 1, url, r.status_code, dt_ms)
                                    preview = r.text[:300]
                                    logger.debug("[Agoda][Day %s] Response preview: %s", i + 1, preview)
                                    # Capture non-200 body for storage
                                    try:
                                        body_json = r.json()
                                    except Exception:
                                        body_json = r.text
                                    resp_error = {
                                        "status": r.status_code,
                                        "body": body_json if isinstance(body_json, (dict, list)) else str(body_json)[:2000],
                                        "path": path,
                                    }
                            except Exception as e:
                                logger.warning("[Agoda][Day %s] Request error at %s (attempt %s): %s", i + 1, path, attempt, e)
                            # Backoff between retries
                            time.sleep(min(2 ** attempt, 8))
                        # If we got a response but no items or explicit no-result error, try a permissive fallback once
                        if isinstance(resp_json, dict):
                            items = resp_json.get("results") or resp_json.get("hotels") or resp_json.get("properties") or []
                            no_items = hasattr(items, "__len__") and len(items) == 0
                            explicit_no_result = isinstance(resp_json.get("error"), dict) and resp_json["error"].get("id") == 911
                            if no_items or explicit_no_result:
                                try:
                                    fallback_payload = json.loads(json.dumps(payload))  # deep copy
                                    # Remove price constraints to broaden results
                                    try:
                                        fallback_payload["criteria"]["additional"].pop("dailyRate", None)
                                        fallback_payload["criteria"]["additional"]["maxResult"] = 10
                                        fallback_payload["criteria"]["additional"]["sortBy"] = "Popularity"
                                    except Exception:
                                        pass
                                    logger.info("[Agoda][Day %s] Fallback search (no price filters)", i + 1)
                                    _rate_limit()
                                    t1 = time.time()
                                    r2 = client.post(url, headers=headers, json=fallback_payload)
                                    dt2_ms = int((time.time() - t1) * 1000)
                                    if r2.status_code == 200:
                                        resp_json = r2.json()
                                        logger.info("[Agoda][Day %s] Fallback 200 OK in %sms", i + 1, dt2_ms)
                                    else:
                                        logger.warning("[Agoda][Day %s] Fallback POST %s -> %s in %sms", i + 1, url, r2.status_code, dt2_ms)
                                    # If still empty or explicit no-results, try minimal payload
                                    if isinstance(resp_json, dict):
                                        items2 = resp_json.get("results") or resp_json.get("hotels") or resp_json.get("properties") or []
                                        no_items2 = hasattr(items2, "__len__") and len(items2) == 0
                                        explicit_no_result2 = isinstance(resp_json.get("error"), dict) and resp_json["error"].get("id") == 911
                                        if no_items2 or explicit_no_result2:
                                            minimal_payload = {
                                                "criteria": {
                                                    "checkInDate": check_in,
                                                    "checkOutDate": check_out,
                                                    "cityId": city_id,
                                                }
                                            }
                                            logger.info("[Agoda][Day %s] Second fallback (minimal payload)", i + 1)
                                            _rate_limit()
                                            t2 = time.time()
                                            r3 = client.post(url, headers=headers, json=minimal_payload)
                                            dt3_ms = int((time.time() - t2) * 1000)
                                            if r3.status_code == 200:
                                                resp_json = r3.json()
                                                logger.info("[Agoda][Day %s] Second fallback 200 OK in %sms", i + 1, dt3_ms)
                                            else:
                                                logger.warning("[Agoda][Day %s] Second fallback POST %s -> %s in %sms", i + 1, url, r3.status_code, dt3_ms)
                                except Exception as e:
                                    logger.warning("[Agoda][Day %s] Fallback error: %s", i + 1, e)
                        if resp_json is not None:
                            break
                # Store response or error in accommodation if available
                if isinstance(resp_json, (dict, list)):
                    agoda_response = resp_json
                    # Log a brief summary if dict
                    try:
                        if isinstance(resp_json, dict):
                            items = resp_json.get("results") or resp_json.get("hotels") or resp_json.get("properties") or []
                            logger.info(
                                "[Agoda][Day %s] Items in response: %s",
                                i + 1,
                                len(items) if hasattr(items, "__len__") else "unknown",
                            )
                    except Exception:
                        pass
                elif resp_error is not None:
                    agoda_response = {"agoda_error": resp_error}
            except Exception as e:
                logger.warning("Failed to fetch Agoda hotels for city_id=%s: %s", city_id, e)
        else:
            logger.info("No city_id found for '%s' in city_mapping.csv; skipping Agoda lookup", city_name)
            # Store a helpful hint if accommodation is empty/missing
            try:
                existing_acc = day_dict.get("accommodation")
                if not existing_acc:
                    day_dict["accommodation"] = {
                        "agoda_error": {
                            "reason": "no_city_id",
                            "city": city_name,
                        }
                    }
            except Exception:
                pass

        # If we received a response, store it; otherwise leave as-is
        if agoda_response is not None:
            day_dict["accommodation"] = agoda_response
            logger.info("[Agoda][Day %s] Stored full Agoda response in accommodation", i + 1)
        updated_days.append(day_dict)

    itinerary["itinerary"] = updated_days
    updated_json = json.dumps(itinerary, indent=2)
    # Persist
    _update_itinerary_json(conv_id, updated_json)
    logger.info("[Agoda] Itinerary updated and saved for conv_id=%s", conv_id)
    return updated_json

def format_itinerary_for_display(itinerary_json: str) -> str:
    itinerary = json.loads(itinerary_json)
    output = f"Trip to {itinerary['destination']}\n"
    output += f"Description: {itinerary['description']}\n"
    output += f"Dates: {itinerary['start_date']} to {itinerary['end_date']} ({itinerary['duration_days']} days)\n\n"
    output += "Itinerary:\n"
    for day in itinerary['itinerary']:
        output += f"Day {day['day_number']} ({day['date']}):\n"
        output += f"  Location: {day['location']}\n"
        output += f"  Activities: {', '.join(day['activities'])}\n"
        output += f"  Transportation: {day['transportation']}\n"
        acc = day.get('accommodation')
        if isinstance(acc, list) and all(isinstance(x, str) for x in acc):
            acc_str = ', '.join(acc)
        elif isinstance(acc, dict):
            # Summarize dict: show count of results if available
            items = acc.get('results') or acc.get('hotels') or acc.get('properties') or []
            acc_str = f"Agoda response with {len(items) if hasattr(items, '__len__') else 'unknown'} items"
        elif isinstance(acc, list):
            acc_str = f"Agoda response list with {len(acc)} entries"
        else:
            acc_str = str(acc) if acc is not None else 'None'
        output += f"  Accommodation: {acc_str}\n"
        output += f"  Notes: {day['notes']}\n\n"
    return output

# --- Agents with Prompts ---
summary_agent = Agent[TripPlannerContext](
    name="summary_agent",
    instructions="""
You are the summary agent. Provide a clear summary of the itinerary including
destination, dates, activities, transportation, accommodations, and notes.
output formatted text.

If the user requests modifications, do NOT use a built-in handoff. Instead, emit a single line:
    HANDOFF: <target>
Where <target> is one of: user_preferences, destination_research, itinerary, booking.
After emitting the HANDOFF line, stop and wait.
""",
    handoff_description="Final itinerary summary agent",
    tools=[read_itinerary_json_tool, update_itinerary_json_tool, update_context_tool, populate_accommodations_from_agoda_tool],
        handoffs=[],
)

booking_agent = Agent[TripPlannerContext](
    name="booking_agent",
    instructions="""
You are the booking agent. Review and allow updates to the itinerary.
Use update_itinerary_json_tool to save changes. Then hand off to summary_agent.
Location field in the json must be the city name and not the country name

""",
    handoff_description="Booking and itinerary update agent",
    tools=[read_itinerary_json_tool, update_itinerary_json_tool, populate_accommodations_from_agoda_tool],
    handoffs=[],
)

itinerary_agent = Agent[TripPlannerContext](
    name="itinerary_agent",
    instructions="""
You are the itinerary agent. Create a day-by-day itinerary based on user's
preferences and destination info. Use create_itinerary_json_tool to generate JSON.
Then hand off to booking_agent.
After creating json itinerary , populate accomodations from agoda. use populate_accomodations_from_agoda_tool
After any update on itinerary,populate accomodations from agoda. use populate_accomodations_from_agoda_tool and save it. Use update_itinerary_json_tool to save changes.
Location field in the json must be the city name and not the country name
After updation of the itinerary then hand off to summary_agent
""",
    handoff_description="Itinerary creation agent",
    tools=[create_itinerary_json_tool, update_itinerary_json_tool, read_itinerary_json_tool, populate_accommodations_from_agoda_tool],
    handoffs=[],
)

destination_research_agent = Agent[TripPlannerContext](
    name="destination_research_agent",
    instructions="""
You are the destination research agent. Research destination info based on user
preferences including activities, attractions, transportation, and accommodations.
Use WebSearchTool if needed. Then hand off to itinerary_agent.
Location field in the json must be the city name and not the country name

""",
    handoff_description="Destination research agent",
    tools=[WebSearchTool()],
    handoffs=[],
)

user_preferences_agent = Agent[TripPlannerContext](
    name="user_preferences_agent",
    instructions="""
You are the first agent. Collect user preferences: destination, start/end dates,
number of people, budget, and travel style. Update context with update_context_tool.
Then hand off to destination_research_agent.
""",
    handoff_description="User preference collection agent",
    tools=[update_context_tool],
    handoffs=[],
)

# Wire handoffs after all agents are defined to avoid forward-reference issues
user_preferences_agent.handoffs = [destination_research_agent]
destination_research_agent.handoffs = [itinerary_agent]
itinerary_agent.handoffs = [booking_agent,summary_agent]
booking_agent.handoffs = [summary_agent]
summary_agent.handoffs = []  # prevent cycles; use custom HANDOFF: routing instead

# --- Main Loop ---
async def main():
    current_agent: Agent[TripPlannerContext] = user_preferences_agent
    input_items: list[TResponseInputItem] = []
    context = TripPlannerContext()
    conversation_id = uuid.uuid4().hex[:16]
    context.conversation_id = conversation_id
    logger.info("Starting trip planner with conversation ID: %s", conversation_id)

    # Map for custom HANDOFF routing
    agent_by_key = {
        "user_preferences": user_preferences_agent,
        "destination_research": destination_research_agent,
        "itinerary": itinerary_agent,
        "booking": booking_agent,
        "summary": summary_agent,
    }

    while True:
        msg = input("Enter your message: ")
        input_items.append({"content": msg, "role": "user"})

        print(f"\n>>> Currently active agent: {current_agent.name}\n")

        with trace("Trip Planner", group_id=conversation_id):
            try:
                response = await Runner.run(current_agent, input_items, context=context)
            except Exception as e:
                print(f"Error running {current_agent.name}: {str(e)}")
                continue
            
            for item in response.new_items:
                if isinstance(item, MessageOutputItem):
                    text = ItemHelpers.text_message_output(item)
                    if text:
                        # Custom HANDOFF protocol
                        stripped = text.strip()
                        if stripped.upper().startswith("HANDOFF:"):
                            target_key = stripped.split(":", 1)[1].strip().lower()
                            if target_key in agent_by_key:
                                current_agent = agent_by_key[target_key]
                                print(f"\n>>> HANDOFF (custom) to {current_agent.name}\n")
                                input_items.append({"content": f"Conversation ID: {conversation_id}", "role": "system"})
                                # Stop processing remaining items for this turn
                                break
                        # Otherwise, print or format itinerary
                        try:
                            json.loads(text)
                            print("Updated Itinerary:")
                            print(format_itinerary_for_display(text))
                        except json.JSONDecodeError:
                            print(text)
                elif isinstance(item, HandoffOutputItem):
                    current_agent = item.target_agent
                    print(f"\n>>> Handed off to {current_agent.name}\n")
                    input_items.append({"content": f"Conversation ID: {conversation_id}", "role": "system"})
                elif isinstance(item, ToolCallItem):
                    print(f"{item.agent.name}: Calling a tool...")
                elif isinstance(item, ToolCallOutputItem):
                    print(f"{item.agent.name}: Tool call output")
                    try:
                        json.loads(item.output)
                        print("Itinerary Updated:")
                        print(format_itinerary_for_display(item.output))
                    except json.JSONDecodeError:
                        pass
            
            input_items = response.to_input_list()

if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
