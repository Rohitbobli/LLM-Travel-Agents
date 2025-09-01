import asyncio
import json
import uuid
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Load environment variables early
load_dotenv()

# Reuse existing agents and helpers
from main import (
    user_preferences_agent,
    destination_research_agent,
    itinerary_agent,
    booking_agent,
    summary_agent,
    TripPlannerContext,
    Runner,
    trace,
    ItemHelpers,
    MessageOutputItem,
    HandoffOutputItem,
    ToolCallItem,
    ToolCallOutputItem,
    read_itinerary_json_tool,
    populate_accommodations_from_agoda_tool,
    format_itinerary_for_display,
)


# ---------- Simple in-memory session store ----------
class _Session:
    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        self.current_agent = user_preferences_agent
        self.items: list[Dict[str, Any]] = []
        self.context = TripPlannerContext(conversation_id=conversation_id)
        self.lock = asyncio.Lock()


_sessions: Dict[str, _Session] = {}


def _get_or_create_session(conversation_id: Optional[str]) -> _Session:
    conv_id = conversation_id or uuid.uuid4().hex[:16]
    if conv_id not in _sessions:
        _sessions[conv_id] = _Session(conv_id)
    return _sessions[conv_id]


# ---------- Schemas ----------
class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    conversation_id: Optional[str] = Field(None, description="Existing conversation id to continue; new if omitted")


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    current_agent: str


class PopulateRequest(BaseModel):
    conversation_id: str


# ---------- Utilities ----------
def _format_message(item: Any) -> str:
    # Mirrors app.format_message but avoids importing gradio in the API
    if isinstance(item, MessageOutputItem):
        text = ItemHelpers.text_message_output(item)
        if not text:
            return ""
        # Try to parse JSON and pretty print itinerary if present
        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        if isinstance(parsed, dict) and {
            "destination",
            "start_date",
            "end_date",
            "itinerary",
        }.issubset(parsed.keys()):
            try:
                return format_itinerary_for_display(json.dumps(parsed))
            except Exception:
                return "Itinerary updated."
        return text
    elif isinstance(item, HandoffOutputItem):
        return f"Handed off from {item.source_agent.name} to {item.target_agent.name}"
    elif isinstance(item, ToolCallItem):
        return f"{item.agent.name}: Calling a tool"
    elif isinstance(item, ToolCallOutputItem):
        try:
            parsed = json.loads(item.output)
        except Exception:
            parsed = None
        if isinstance(parsed, dict) and {
            "destination",
            "start_date",
            "end_date",
            "itinerary",
        }.issubset(parsed.keys()):
            try:
                return format_itinerary_for_display(json.dumps(parsed))
            except Exception:
                return f"{item.agent.name}: Itinerary updated."
        return f"{item.agent.name}: Tool completed."
    return ""


# ---------- FastAPI app ----------
app = FastAPI(title="Travel Co-pilot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    session = _get_or_create_session(req.conversation_id)
    async with session.lock:
        # Ensure context carries conversation id
        if not getattr(session.context, "conversation_id", None):
            session.context.conversation_id = session.conversation_id

        agent_by_key = {
            "user_preferences": user_preferences_agent,
            "destination_research": destination_research_agent,
            "itinerary": itinerary_agent,
            "booking": booking_agent,
            "summary": summary_agent,
        }

        with trace("Trip Planner", group_id=session.conversation_id):
            session.items.append({"content": req.message, "role": "user"})
            response = await Runner.run(session.current_agent, session.items, context=session.context)

        bot_response = []
        new_current_agent = session.current_agent
        for item in response.new_items:
            formatted = _format_message(item)
            if formatted:
                bot_response.append(formatted)
            if isinstance(item, HandoffOutputItem):
                new_current_agent = item.target_agent
            elif isinstance(item, MessageOutputItem):
                text = ItemHelpers.text_message_output(item) or ""
                stripped = text.strip()
                if stripped.upper().startswith("HANDOFF:"):
                    target_key = stripped.split(":", 1)[1].strip().lower()
                    if target_key in agent_by_key:
                        new_current_agent = agent_by_key[target_key]
                        session.items.append({"content": f"Conversation ID: {session.conversation_id}", "role": "system"})

        # Update session state for next turn
        session.current_agent = new_current_agent
        session.items = response.to_input_list()

        reply_text = ("\n".join(bot_response)).strip() or "Noted."
        return ChatResponse(
            conversation_id=session.conversation_id,
            reply=reply_text,
            current_agent=session.current_agent.name,
        )


@app.get("/itineraries/{conversation_id}")
async def get_itinerary(conversation_id: str):
    # Use the existing tool helper to read from file storage
    session = _get_or_create_session(conversation_id)
    try:
        # create a lightweight RunContextWrapper-like effect by ensuring context has the conv id
        if not getattr(session.context, "conversation_id", None):
            session.context.conversation_id = conversation_id
        class _Wrapper:
            def __init__(self, ctx):
                self.context = ctx
        itinerary_json = await read_itinerary_json_tool(context=_Wrapper(session.context), conversation_id=conversation_id)  # type: ignore
        return json.loads(itinerary_json)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/itineraries/{conversation_id}/populate-accommodations")
async def populate_accommodations(conversation_id: str):
    session = _get_or_create_session(conversation_id)
    async with session.lock:
        try:
            if not getattr(session.context, "conversation_id", None):
                session.context.conversation_id = conversation_id
            # Provide a minimal wrapper exposing `.context` as expected by the tool
            class _Wrapper:
                def __init__(self, ctx):
                    self.context = ctx

            updated_json = await populate_accommodations_from_agoda_tool(context=_Wrapper(session.context), conversation_id=conversation_id)  # type: ignore
            try:
                return json.loads(updated_json)
            except Exception:
                return {"raw": updated_json}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
