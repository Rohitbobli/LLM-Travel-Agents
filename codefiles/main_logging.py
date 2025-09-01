import asyncio
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from agents import Agent, Runner, trace, ItemHelpers, MessageOutputItem, TResponseInputItem, RunContextWrapper, HandoffOutputItem, ToolCallItem, ToolCallOutputItem, WebSearchTool, function_tool
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

# Create a folder for storing itineraries
ITINERARY_FOLDER = "itineraries"
os.makedirs(ITINERARY_FOLDER, exist_ok=True)
logger.info("Itinerary folder set up at %s", ITINERARY_FOLDER)

# Pydantic models for JSON itinerary
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

# --- Tools ---
@function_tool
async def update_context_tool(context: RunContextWrapper[TripPlannerContext], destination: str, start_date: str, end_date: str, budget: str, travel_style: str, number_of_people: int) -> None:
    logger.info("Updating context with destination=%s, start_date=%s, end_date=%s, budget=%s, travel_style=%s, number_of_people=%s",
                destination, start_date, end_date, budget, travel_style, number_of_people)
    context.context.destination = destination
    context.context.start_date = start_date
    context.context.end_date = end_date
    context.context.budget = budget
    context.context.travel_style = travel_style
    context.context.number_of_people = number_of_people

@function_tool
async def create_itinerary_json_tool(
    context: RunContextWrapper[TripPlannerContext],
    activities_per_day: List[List[str]],
    transportation: List[str],
    accommodations: List[List[str]],
    notes: List[str],
    description: str,
    conversation_id: str
) -> str:
    logger.info("Creating itinerary JSON for conversation ID: %s", conversation_id)
    
    if not (context.context.start_date and context.context.end_date and context.context.destination):
        logger.error("Missing required context: destination=%s, start_date=%s, end_date=%s",
                     context.context.destination, context.context.start_date, context.context.end_date)
        raise ValueError("Missing required context: destination, start_date, or end_date")
    
    start_date = datetime.strptime(context.context.start_date, "%Y-%m-%d")
    end_date = datetime.strptime(context.context.end_date, "%Y-%m-%d")
    duration_days = (end_date - start_date).days + 1
    logger.info("Trip duration calculated: %d days", duration_days)
    
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
        logger.debug("Added day %d: %s", i + 1, itinerary_days[-1].dict())
    
    itinerary_output = ItineraryOutput(
        destination=context.context.destination,
        description=description,
        start_date=context.context.start_date,
        end_date=context.context.end_date,
        duration_days=duration_days,
        itinerary=itinerary_days
    )
    
    # Save to file
    itinerary_json = json.dumps(itinerary_output.dict(), indent=2)
    file_path = os.path.join(ITINERARY_FOLDER, f"itinerary_{conversation_id}.json")
    with open(file_path, "w") as f:
        f.write(itinerary_json)
    logger.info("Itinerary saved to %s", file_path)
    
    return itinerary_json

@function_tool
async def update_itinerary_json_tool(
    conversation_id: str,
    updated_itinerary: str
) -> str:
    logger.info("Updating itinerary for conversation ID: %s", conversation_id)
    file_path = os.path.join(ITINERARY_FOLDER, f"itinerary_{conversation_id}.json")
    
    if not os.path.exists(file_path):
        logger.error("No itinerary found for conversation ID: %s", conversation_id)
        raise ValueError(f"No itinerary found for conversation ID: {conversation_id}")
    
    try:
        json.loads(updated_itinerary)
        logger.debug("Updated itinerary JSON validated successfully")
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON for itinerary update: %s", str(e))
        raise ValueError("Invalid JSON provided for itinerary update")
    
    with open(file_path, "w") as f:
        f.write(updated_itinerary)
    logger.info("Itinerary updated at %s", file_path)
    
    return updated_itinerary

def read_itinerary_json(conversation_id: str) -> dict:
    logger.info("Reading itinerary for conversation ID: %s", conversation_id)
    file_path = os.path.join(ITINERARY_FOLDER, f"itinerary_{conversation_id}.json")
    
    if not os.path.exists(file_path):
        logger.error("No itinerary found for conversation ID: %s", conversation_id)
        raise ValueError(f"No itinerary found for conversation ID: {conversation_id}")
    
    with open(file_path, "r") as f:
        data = json.load(f)
    
    logger.debug("Itinerary data loaded: %s", data)
    return data

def format_itinerary_for_display(itinerary_json: str) -> str:
    try:
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
        logger.info("Formatted itinerary for display")
        return output
    except json.JSONDecodeError:
        logger.error("Invalid itinerary JSON format")
        return "Error: Invalid itinerary JSON format"

# --- Agents ---
summary_agent = Agent[TripPlannerContext](
    name="summary_agent",
    instructions="""You are the final agent in the sequence...""",
    handoff_description="A summary agent",
)

booking_agent = Agent[TripPlannerContext](
    name="booking_agent",
    instructions="""You are the fourth agent in the sequence...""",
    handoff_description="A booking agent",
    tools=[update_itinerary_json_tool],
    handoffs=[summary_agent],
)

itinerary_agent = Agent[TripPlannerContext](
    name="itinerary_agent",
    instructions="""You are the third agent in the sequence...""",
    handoff_description="An itinerary agent",
    tools=[create_itinerary_json_tool, update_itinerary_json_tool],
    handoffs=[booking_agent],
)

destination_research_agent = Agent[TripPlannerContext](
    name="destination_research_agent",
    instructions="""You are the second agent in the sequence...""",
    handoff_description="A destination research agent",
    tools=[WebSearchTool()],
    handoffs=[itinerary_agent],
)

user_preferences_agent = Agent[TripPlannerContext](
    name="user_preferences_agent",
    instructions="""You are the first agent in the trip planning sequence...""",
    handoff_description="A user preferences and constraints collector agent",
    tools=[update_context_tool],
    handoffs=[destination_research_agent],
)

# --- Main loop ---
async def main():
    current_agent: Agent[TripPlannerContext] = user_preferences_agent
    input_items: list[TResponseInputItem] = []
    context = TripPlannerContext()
    conversation_id = uuid.uuid4().hex[:16]
    logger.info("Starting trip planner with conversation ID: %s", conversation_id)

    while True:
        msg = input("Enter your message: ")
        logger.info("User input: %s", msg)

        # Log active agent
        logger.info("🔹 Active agent: %s", current_agent.name)
        print(f"\n>>> Currently active agent: {current_agent.name}\n")

        with trace("Trip Planner", group_id=conversation_id):
            input_items.append({"content": msg, "role": "user"})
            try:
                response = await Runner.run(current_agent, input_items, context=context)
                logger.info("Agent %s processed input successfully", current_agent.name)
            except Exception as e:
                logger.exception("Error running agent %s", current_agent.name)
                print(f"Error running {current_agent.name}: {str(e)}")
                continue
            
            for item in response.new_items:
                if isinstance(item, MessageOutputItem):
                    text = ItemHelpers.text_message_output(item)
                    if text:
                        try:
                            json.loads(text)
                            logger.info("Received itinerary JSON from %s", current_agent.name)
                            print("Updated Itinerary:")
                            print(format_itinerary_for_display(text))
                        except json.JSONDecodeError:
                            logger.info("Received message output from %s: %s", current_agent.name, text)
                            print(text)
                elif isinstance(item, HandoffOutputItem):
                    logger.info("➡️ Handoff: %s → %s", item.source_agent.name, item.target_agent.name)
                    print(f"\n>>> Handed off from {item.source_agent.name} to {item.target_agent.name}")
                    current_agent = item.target_agent
                    logger.info("🔹 Now active agent: %s", current_agent.name)
                    print(f">>> Now active agent: {current_agent.name}\n")
                    input_items.append({"content": f"Conversation ID: {conversation_id}", "role": "system"})
                elif isinstance(item, ToolCallItem):
                    logger.info("%s is calling a tool", item.agent.name)
                    print(f"{item.agent.name}: Calling a tool")
                elif isinstance(item, ToolCallOutputItem):
                    logger.info("%s tool call output: %s", item.agent.name, item.output)
                    print(f"{item.agent.name}: Tool call output: {item.output}")
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
