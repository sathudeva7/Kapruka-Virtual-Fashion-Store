"""The Stylist Agent — composes complete, coordinated outfits.

Modeled on the fashion-app-demo's stylist: the instruction lives in
instructions.md (compact, workflow-shaped, persona-free — the full VOICE
block plus a long body reliably trips Gemini's PROHIBITED_CONTENT filter,
verified by bisecting; it's cumulative, not one phrase), and cross-turn
behavior is enforced by state-driven callbacks instead of prompt text.
"""

from pathlib import Path

from google.adk import Agent
from google.genai import types

from tools import (
    search_toolset,
    manage_cart,
    stylist_before_tool,
    stylist_capture_after_tool,
    stylist_before_model,
    stylist_after_agent,
    rbac_before,
    rbac_after,
)

_INSTRUCTIONS = (Path(__file__).parent / "instructions.md").read_text(encoding="utf-8")

stylist_agent = Agent(
    name="stylist_agent",
    description="An AI stylist that composes complete coordinated outfits "
                "(occasion, style, budget) from the Kapruka catalog.",
    model="gemini-2.5-flash",
    instruction=_INSTRUCTIONS,
    tools=[
        search_toolset,
        manage_cart,
    ],
    # A touch more creative than the catalog agent — composing looks, not lists.
    # thinking_budget=0 drops the model's thinking pass for lower voice latency.
    generate_content_config=types.GenerateContentConfig(
        temperature=0.8,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    ),
    # Same arg normalization as the catalog agent plus a hard per-turn search
    # budget; the after-callback variant tags each captured product with its
    # outfit slot for grouped rendering.
    before_tool_callback=rbac_before(stylist_before_tool),
    after_tool_callback=rbac_after(stylist_capture_after_tool),
    # Fresh-outfit memory: previously styled products are committed to state
    # when the turn ends and re-injected as a reminder on later turns, so
    # "style me again" yields different pieces (demo: InjectPreviousProducts).
    before_model_callback=stylist_before_model,
    after_agent_callback=stylist_after_agent,
)
