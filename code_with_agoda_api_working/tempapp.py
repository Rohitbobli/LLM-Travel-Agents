import gradio as gr
import asyncio
import uuid
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
)

def format_message(item):
    if isinstance(item, MessageOutputItem):
        text = ItemHelpers.text_message_output(item)
        if text:
            return text
    elif isinstance(item, HandoffOutputItem):
        return f"Handed off from {item.source_agent.name} to {item.target_agent.name}"
    elif isinstance(item, ToolCallItem):
        return f"{item.agent.name}: Calling a tool"
    elif isinstance(item, ToolCallOutputItem):
        return f"{item.agent.name}: Tool call output: {item.output}"
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

        bot_response = bot_response.strip()
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