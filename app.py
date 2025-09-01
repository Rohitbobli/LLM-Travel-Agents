import gradio as gr
import asyncio
import uuid
import json
import re
from dotenv import load_dotenv

# Load environment variables from a local .env file if present
load_dotenv()

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
    TResponseInputItem,
    HandoffOutputItem,
    ToolCallItem,
    ToolCallOutputItem,
    format_itinerary_for_display,
)

def _try_extract_json(text: str):
    """Try to extract and parse JSON (including fenced ```json blocks). Returns parsed obj or None."""
    if not text:
        return None
    # Look for fenced code blocks first
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```",
                            text, flags=re.DOTALL | re.IGNORECASE)
    candidate = None
    if fence_match:
        candidate = fence_match.group(1).strip()
    else:
        stripped = text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            candidate = stripped
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except Exception:
        return None

def _is_itinerary_like(obj) -> bool:
    if not isinstance(obj, dict):
        return False
    keys = set(obj.keys())
    return {
        "destination",
        "start_date",
        "end_date",
        "itinerary",
    }.issubset(keys) and isinstance(obj.get("itinerary"), list)

def format_message(item):
    if isinstance(item, MessageOutputItem):
        text = ItemHelpers.text_message_output(item)
        if not text:
            return ""
        # If the model emitted an itinerary JSON, suppress raw JSON and show formatted text
        parsed = _try_extract_json(text)
        if parsed is not None:
            if _is_itinerary_like(parsed):
                try:
                    return format_itinerary_for_display(json.dumps(parsed))
                except Exception:
                    return "Itinerary updated."
            # Non-itinerary JSON: don't display raw JSON
            # Try to remove fenced JSON and show any remaining prose
            no_json = re.sub(r"```(?:json)?\s*.*?\s*```", "", text, flags=re.DOTALL | re.IGNORECASE).strip()
            return no_json
        # Plain text message
        return text
    elif isinstance(item, HandoffOutputItem):
        return f"Handed off from {item.source_agent.name} to {item.target_agent.name}"
    elif isinstance(item, ToolCallItem):
        return f"{item.agent.name}: Calling a tool"
    elif isinstance(item, ToolCallOutputItem):
        # Tool outputs often return itinerary JSON; don't show raw output
        parsed = None
        try:
            parsed = json.loads(item.output)
        except Exception:
            parsed = None
        if parsed is not None and _is_itinerary_like(parsed):
            try:
                return format_itinerary_for_display(json.dumps(parsed))
            except Exception:
                return f"{item.agent.name}: Itinerary updated."
        # Non-itinerary output or non-JSON: provide a concise status
        return f"{item.agent.name}: Tool completed."
    return ""

async def respond(message, history, current_agent, input_items, context, conversation_id):
    # Maintain state across turns so the agent advances instead of restarting
    history = history or []
    # Ensure the context carries the conversation id
    if not getattr(context, "conversation_id", None):
        context.conversation_id = conversation_id

    agent_by_key = {
        "user_preferences": user_preferences_agent,
        "destination_research": destination_research_agent,
        "itinerary": itinerary_agent,
        "booking": booking_agent,
        "summary": summary_agent,
    }

    with trace("Trip Planner", group_id=conversation_id):
        input_items.append({"content": message, "role": "user"})
        response = await Runner.run(current_agent, input_items, context=context)

    bot_response = ""
    new_current_agent = current_agent
    for item in response.new_items:
        formatted_message = format_message(item)
        if formatted_message:
            bot_response += formatted_message + "\n"

        if isinstance(item, HandoffOutputItem):
            new_current_agent = item.target_agent
        elif isinstance(item, MessageOutputItem):
            # Support custom text-based handoffs like: "HANDOFF: booking"
            text = ItemHelpers.text_message_output(item) or ""
            stripped = text.strip()
            if stripped.upper().startswith("HANDOFF:"):
                target_key = stripped.split(":", 1)[1].strip().lower()
                if target_key in agent_by_key:
                    new_current_agent = agent_by_key[target_key]
                    # Ensure conversation id is threaded
                    input_items.append({"content": f"Conversation ID: {conversation_id}", "role": "system"})

    bot_response = bot_response.strip() or "Noted."
    # Convert response to input list for the next turn
    input_items = response.to_input_list()

    # Return updated UI history and the updated states
    return history + [(message, bot_response)], new_current_agent, input_items, context

def create_chatbot():
    with gr.Blocks() as demo:
        chatbot = gr.Chatbot(
            label="Trip Planner Assistant",
            height=600,
        )

        msg = gr.Textbox(
            label="Message",
            placeholder="Type your message here...",
            lines=2,
        )

        clear = gr.Button("Clear")

        # Session state to persist agent, items, and context across turns
        conversation_id = uuid.uuid4().hex[:16]
        agent_state = gr.State(user_preferences_agent)
        items_state = gr.State([])
        context_state = gr.State(TripPlannerContext())
        conv_id_state = gr.State(conversation_id)

        # Use async handler directly; Gradio supports coroutine functions
        msg.submit(
            respond,
            inputs=[msg, chatbot, agent_state, items_state, context_state, conv_id_state],
            outputs=[chatbot, agent_state, items_state, context_state],
            queue=True,
        ).then(
            lambda: "",
            None,
            msg,
            queue=False,
        )

        # Clear both UI and state
        def _clear():
            return [], user_preferences_agent, [], TripPlannerContext()

        clear.click(
            _clear,
            inputs=None,
            outputs=[chatbot, agent_state, items_state, context_state],
            queue=False,
        )

    return demo

if __name__ == "__main__":
    demo = create_chatbot()
    demo.launch()