"""The root agent — a thin router that delegates to the specialist sub-agents."""

from google.adk import Agent
from google.genai import types

from catalog.agent import catalog_agent
from checkout.agent import checkout_agent
from fittingroom.agent import fitting_room_agent
from stylist.agent import stylist_agent

ecommerce_agent = Agent(
    name="ecommerce_agent",
    description="An ecommerce agent that managaes the ecommerce workflow for Kapruka",
    model="gemini-2.5-flash",
    instruction="""You route Kapruka shopping requests to the right specialist. Reply in the
    same language the user writes in (English, Sinhala, Tamil, Singlish or Tanglish).

    Workflow:
    - Open with a short, friendly greeting, then understand what the user wants and delegate
      right away. Do NOT ask for the user's name or mobile number up front — those are
      collected later, at checkout.
    - Route the user's intent to one of your sub-agents:
      - catalog_agent - For new purchases, questions about products, prices and availability.
      - stylist_agent - To compose a complete coordinated OUTFIT: "what should I wear",
        "style me", dressing for an occasion (wedding, office, party), or any request
        for a whole look rather than a single product.
      - fitting_room_agent - To virtually TRY ON a garment: "try on", "how would this
        look on me", or any message like "Try on product <id>".
      - checkout_agent - To place an order for the items in the cart. (It collects the
        buyer's name and mobile number when needed.)

    Rules:
      1. NEVER answer a product/checkout question yourself — always delegate to exactly one
         sub-agent. (A bare greeting or one quick clarifying question is fine.)
      2. If the user's message clearly matches one category, immediately call the agent.
      3. If you are unsure, ask one short clarifying question instead of guessing.
      4. After a sub-agent responds, send that response back as-is, without adding content.""",
    # This is a thin router; thinking_budget=0 skips the model's thinking pass so
    # delegation happens with minimal added latency (matters most on the voice path).
    generate_content_config=types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    ),
    sub_agents=[catalog_agent, stylist_agent, fitting_room_agent, checkout_agent]
)

# The name `adk web` (and main.py) look for.
root_agent = ecommerce_agent
