import asyncio
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from agents import (
    Agent, Runner, trace, ItemHelpers, MessageOutputItem, TResponseInputItem,
    RunContextWrapper, HandoffOutputItem, ToolCallItem, ToolCallOutputItem,
    WebSearchTool, function_tool
)
from pydantic import BaseModel
from typing import List
import uuid
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Create folder for itineraries
ITINERARY_FOLDER = "itineraries"
os.makedirs(ITINERARY_FOLDER, exist_ok=True)
logger.info("Itinerary folder set up at %s", ITINERARY_FOLDER)

# --- Pydantic Models ---
class ItineraryDay(BaseModel):
    date: str
    day_number: int
    location: str
    activities: List[str]
    transportation: str
    accommodation: List[str]
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
    file_path = os.path.join(ITINERARY_FOLDER, f"itinerary_{conv_id}.json")
    with open(file_path, "w") as f:
        f.write(itinerary_json)
    logger.info("Itinerary saved to %s", file_path)
    
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
    file_path = os.path.join(ITINERARY_FOLDER, f"itinerary_{conv_id}.json")
    
    if not os.path.exists(file_path):
        raise ValueError(f"No itinerary found for conversation ID: {conv_id}")
    
    json.loads(updated_itinerary)  # validate JSON
    
    with open(file_path, "w") as f:
        f.write(updated_itinerary)
    logger.info("Itinerary updated at %s", file_path)
    
    return updated_itinerary

@function_tool
async def read_itinerary_json_tool(
    context: RunContextWrapper[TripPlannerContext],
    conversation_id: str | None = None,
) -> str:
    """Read and return the itinerary JSON string for the given or current conversation."""
    conv_id = conversation_id or context.context.conversation_id
    if not conv_id:
        raise ValueError("conversation_id not provided and not set in context")
    file_path = os.path.join(ITINERARY_FOLDER, f"itinerary_{conv_id}.json")
    if not os.path.exists(file_path):
        raise ValueError(f"No itinerary found for conversation ID: {conv_id}")
    with open(file_path, "r") as f:
        data = f.read()
    logger.info("Itinerary loaded from %s", file_path)
    return data

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
        output += f"  Accommodation: {', '.join(day['accommodation']) or 'None'}\n"
        output += f"  Notes: {day['notes']}\n\n"
    return output

# --- Agents with Prompts ---
summary_agent = Agent[TripPlannerContext](
    name="summary_agent",
    instructions="""
You are the summary agent. Provide a clear summary of the itinerary including
destination, dates, activities, transportation, accommodations, and notes.
Output JSON and formatted text.

If the user requests modifications, do NOT use a built-in handoff. Instead, emit a single line:
    HANDOFF: <target>
Where <target> is one of: user_preferences, destination_research, itinerary, booking.
After emitting the HANDOFF line, stop and wait.
""",
    handoff_description="Final itinerary summary agent",
    tools=[read_itinerary_json_tool, update_itinerary_json_tool, update_context_tool],
        handoffs=[],
)

booking_agent = Agent[TripPlannerContext](
    name="booking_agent",
    instructions="""
You are the booking agent. Review and allow updates to the itinerary.
Use update_itinerary_json_tool to save changes. Then hand off to summary_agent.
""",
    handoff_description="Booking and itinerary update agent",
    tools=[read_itinerary_json_tool, update_itinerary_json_tool],
    handoffs=[],
)

itinerary_agent = Agent[TripPlannerContext](
    name="itinerary_agent",
    instructions="""
You are the itinerary agent. Create a day-by-day itinerary based on user's
preferences and destination info. Use create_itinerary_json_tool to generate JSON.
Then hand off to booking_agent.
""",
    handoff_description="Itinerary creation agent",
    tools=[create_itinerary_json_tool, update_itinerary_json_tool, read_itinerary_json_tool],
    handoffs=[],
)

destination_research_agent = Agent[TripPlannerContext](
    name="destination_research_agent",
    instructions="""
You are the destination research agent. Research destination info based on user
preferences including activities, attractions, transportation, and accommodations.
Use WebSearchTool if needed. Then hand off to itinerary_agent.
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
itinerary_agent.handoffs = [booking_agent]
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
