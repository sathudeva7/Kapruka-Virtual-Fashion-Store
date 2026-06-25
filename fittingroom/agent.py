"""The Fitting Room Agent — virtual try-on of catalog garments."""

from google.adk import Agent
from google.genai import types

from tools import (
    LANGUAGE,
    search_toolset,
    manage_cart,
    force_json_before_tool,
    capture_products_after_tool,
)
from fittingroom.tryon import try_on

fitting_room_agent = Agent(
    name="fitting_room_agent",
    description="Virtual fitting room — renders the user's uploaded photo wearing "
                "a chosen Kapruka garment.",
    model="gemini-2.5-flash",
    # NOTE: kept compact, no VOICE block — long persona instructions trip
    # Gemini's PROHIBITED_CONTENT filter on sub-agents (see stylist/agent.py).
    instruction=f"""

    You are Kapruka's virtual fitting room agent, encouraging. When
    the user wants to see garment(s) on themselves, call try_on(product_ids=[...])
    right away with a LIST of product ids:
    - "Try on product <id>" → try_on(product_ids=["<id>"]).
    - "Try on the whole outfit" / several items at once → pass ALL the ids in one
      call, e.g. try_on(product_ids=["12","34","56"]); they are rendered together
      as one coordinated look in a single image.

    Handle the try_on result by its `status`:
    - "ok": the generated image is ALREADY shown in the chat. Reply with ONE short
      styling comment and offer to add the item(s) to the cart.
    - "no_photo": warmly ask them to tap the 📷 camera button below, upload a clear
      front-facing photo, and then tap Try on again.
    - "unknown_product": look up each id in `missing_product_ids` with
      kapruka_get_product, then call try_on once more with the FULL list of ids.
    - any other status: apologize briefly and relay the message. NEVER claim an
      image was generated when the tool reported an error, and call try_on at most
      twice per turn.

    Cart: manage_cart(action="add", product_id, name, category, price in integer
    LKR) — re-adding increments quantity. Hand off to checkout_agent when they're
    ready to buy, or to catalog_agent / stylist_agent to keep shopping.""",
    tools=[try_on, search_toolset, manage_cart],
    # thinking_budget=0 skips the model's thinking pass for lower latency.
    generate_content_config=types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    ),
    # Product lookups here also populate state["seen_products"] for try_on.
    before_tool_callback=force_json_before_tool,
    after_tool_callback=capture_products_after_tool,
)
