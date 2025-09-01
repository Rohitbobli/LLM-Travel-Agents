# 🧳 Travel Co-pilot with Agoda Integration

This project is an **Travel Co-Pilot** that helps users:
- Collect travel preferences (destination, dates, budget, people).
- Research destinations and suggest activities.
- Generate day-by-day itineraries.
- Populate accommodations using the **Agoda Affiliate API**.
- Save itineraries as JSON files and display them in a human-friendly format.

---

## ✨ Features

- 🤖 **Multi-agent pipeline**
  - `user_preferences_agent` → collects preferences
  - `destination_research_agent` → researches activities & attractions
  - `itinerary_agent` → builds itineraries + calls Agoda for hotels
  - `booking_agent` → allows edits & updates
  - `summary_agent` → final summary output

- 🏨 **Agoda API Integration**
  - Hotel results fetched by city ID, dates, and budget
  - Automatic retry, rate-limiting, and fallback queries

- 📂 **Persistent Itineraries**
  - Stored as JSON in `itineraries/`
  - Read, update, and re-save during conversation

- 📊 **Budget-Aware Planning**
  - Maps budget labels (budget/mid-range/luxury) → nightly price ranges
  - Supports numeric budgets (either per night or total trip)

---

## ⚙️ Requirements

- Python 3.10+
- Dependencies:
  ```bash
  pip install -r requirements.txt
  ```
  (Make sure you include `httpx`, `pydantic`, `python-dotenv`, and your `agents` framework in `requirements.txt`.)

---


Follow these steps to set up and run the project locally:

---

## ⚙️ 1. Create a Python Environment
```bash
python -m venv venv
```

---

## 📦 2. Install Dependencies
Activate your virtual environment and install required packages:
```bash
# On Windows
venv\Scripts\activate

# On macOS/Linux
source venv/bin/activate

# Then install dependencies
pip install -r requirements.txt
```

---

## 🔑 3. Add API Keys
Create a `.env` file in the project root and add your Agoda credentials:
```env
AGODA_BASE_URL=https://affiliate-api.agoda.com/api/v1
AGODA_API_KEY=your_api_key_here
AGODA_SEARCH_PATH=/hotels/search
```

---

## ▶️ 4. Activate Virtual Environment (Windows)
If not already activated, run:
```bash
venv\Scripts\activate.bat
```

---

## 🚀 5. Run the Application
```bash
python app.py
```

---

## 📜 6. Logs
Execution logs will be visible directly in the terminal.


## 🔑 Environment Variables

Create a `.env` file in the project root:

```env
AGODA_BASE_URL=https://affiliate-api.agoda.com/api/v1
AGODA_API_KEY=your_api_key_here
OPENAI_API_KEY=
SUPABASE_DB_URL=postgresql://postgres:[YOUR-PASSWORD]@db.mwesfopjhpfjjvcedsre.supabase.co:5432/postgres
```

### Required Files
- `city_mapping.csv` → CSV with `city_id` and `city` name mappings
- `itineraries/` → Folder where generated itineraries are saved

---

## 🏗️ How It Works

1. User starts conversation → `user_preferences_agent` collects travel details
2. Research agent suggests activities & logistics
3. Itinerary agent generates JSON itinerary (day-by-day)
4. Agoda API populates accommodations automatically
5. Booking agent allows edits
6. Summary agent outputs final formatted itinerary

---

## 📂 Data Models

### `TripPlannerContext`
Stores the context of the trip:
```python
{
  "destination": "Paris",
  "start_date": "2025-10-10",
  "end_date": "2025-10-15",
  "budget": "mid-range",
  "travel_style": "romantic",
  "number_of_people": 2,
  "conversation_id": "abcd1234"
}
```

### `ItineraryOutput`
Represents the final trip plan:
```json
{
  "destination": "Paris",
  "description": "Romantic trip for 2",
  "start_date": "2025-10-10",
  "end_date": "2025-10-15",
  "duration_days": 6,
  "itinerary": [
    {
      "date": "2025-10-10",
      "day_number": 1,
      "location": "Paris",
      "activities": ["Visit Eiffel Tower", "Seine River cruise"],
      "transportation": "Metro",
      "accommodation": {
        "results": [ ... Agoda API response ... ]
      },
      "notes": "Start trip with light activities"
    }
  ]
}
```

---

## 📌 Example Usage

```bash
python app.py
```

Example conversation:
```
Enter your message: I want to go to Paris from Oct 10–15 with my partner, budget mid-range.

>>> Currently active agent: user_preferences_agent

>>> HANDOFF (custom) to destination_research_agent

>>> HANDOFF (custom) to itinerary_agent

Itinerary Updated:
Trip to Paris
Description: Romantic trip for 2
Dates: 2025-10-10 to 2025-10-15 (6 days)

Itinerary:
Day 1 (2025-10-10):
  Location: Paris
  Activities: Visit Eiffel Tower, Seine River cruise
  Transportation: Metro
  Accommodation: Agoda response with 3 items
  Notes: Start trip with light activities
```

---

## ✅ Reliability Features
- **Rate limiting** → max 1 request/sec to Agoda
- **Retries** → up to 3 retries with exponential backoff
- **Fallback queries** → progressively broadens Agoda search if no results
- **Logging** → detailed logs for troubleshooting

---

## 🗄️ Supabase Storage (Postgres)

This project now supports storing itineraries in Supabase Postgres. If `SUPABASE_DB_URL` (or `DATABASE_URL`) is set, itineraries are read/written to the `itineraries` table. If not set, it falls back to local files in `itineraries/`.

### Initialize the database table

1. Set the env var or pass the URL as an argument.
2. Run the init script:

```powershell
# Using env var
$env:SUPABASE_DB_URL = "postgresql://postgres:[YOUR-PASSWORD]@db.mwesfopjhpfjjvcedsre.supabase.co:5432/postgres"
python scripts/init_supabase_db.py

# Or pass as an argument
python scripts/init_supabase_db.py "postgresql://postgres:[YOUR-PASSWORD]@db.mwesfopjhpfjjvcedsre.supabase.co:5432/postgres"
```

Table schema:

- conversation_id (text, PK)
- itinerary_json (jsonb)
- created_at (timestamptz, default now())
- updated_at (timestamptz, default now(); auto-updated on UPDATE via trigger)

No code changes are required in your API usage—`api.py` and the agents continue to function, now persisting to Supabase when configured.


