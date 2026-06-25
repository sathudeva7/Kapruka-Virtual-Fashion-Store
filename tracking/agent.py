"""The Tracking Agent — looks up an existing order's status and delivery
progress by its Kapruka order number (the post-sale "where is my order?" step).

Deliberately compact and persona-free: the content filter is cumulative, so —
like the stylist and fitting-room agents — this carries no VOICE block (see
CLAUDE.md "Gemini content filter"). The structured timeline is captured into a
`tracking` card by capture_tracking_after_tool; this agent only narrates."""

from google.adk import Agent
from google.genai import types

from tools import (
    tracking_toolset,
    before_tracking_tool,
    capture_tracking_after_tool,
)

tracking_agent = Agent(
    name="tracking_agent",
    description="Tracks an existing Kapruka order by its order number.",
    model="gemini-2.5-flash",
    instruction="""You track an existing Kapruka order and report where it is.
    Reply in the same language the user writes in (English, Sinhala, Tamil, Singlish
    or Tanglish).

    The order NUMBER is the code from the customer's order-confirmation email or the
    order-complete page (e.g. VPAY827982BA, VIMP34456CB2). It is NOT the pre-payment
    checkout / pay reference — do not reuse a checkout ref as the order number.

    Steps:
    - If the user has not given an order number, ask for it in one short sentence
      (mention it's the number from their confirmation email / order page). Do not
      guess or invent one.
    - Once you have a number, call kapruka_track_order with it exactly ONCE.
    - On success, tell the user the current status, the delivery date, and the latest
      progress step in one or two warm sentences. The full timeline appears on screen
      as a card, so don't list every step in prose.
    - If the lookup fails or the order isn't found, say so kindly and ask them to
      double-check the number — do NOT retry the tool in a loop.""",
    tools=[tracking_toolset],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.4,
        thinking_config=types.ThinkingConfig(thinking_budget=0),  # lower latency
    ),
    before_tool_callback=before_tracking_tool,
    after_tool_callback=capture_tracking_after_tool,
)
