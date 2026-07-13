"""Wire-format helpers shared by the SSE and WebSocket paths."""

import json


def sse(payload: dict) -> str:
    """Encode one event as an SSE frame with a JSON body."""
    return f"data: {json.dumps(payload)}\n\n"


def friendly_error(detail: str) -> str:
    """Map a raw backend error to a calm, actionable message — or "" if we don't
    recognise it (caller falls back to the raw detail).

    Covers the infra failures that otherwise reach the user as scary stack-y
    text: the Kapruka MCP catalog being unreachable (which strands the agent
    with no search tool, so Gemini hallucinates a tool name → "Tool ... not
    found"), Gemini overload (503), and free-tier rate limits (429).
    """
    d = detail.lower()
    if "not found" in d and "available tools" in d:
        # The MCP toolset failed to load, so a search tool the model expected
        # isn't registered. The catalog, not the model, is the real problem.
        return ("The Kapruka catalog is temporarily unavailable, so I couldn't run "
                "that search. Please try again in a moment.")
    if "mcp session" in d or ("mcp" in d and "connect" in d):
        return ("Can't reach the Kapruka catalog right now (connection failed). "
                "Please try again shortly.")
    if "resource_exhausted" in d or "429" in d:
        return ("We've hit the free-tier usage limit for a moment. Please wait a "
                "minute and try again.")
    if "503" in d or "unavailable" in d or "overloaded" in d:
        return ("The AI service is briefly busy. Please send your message again in "
                "a few seconds.")
    return ""


def product_card(item: dict) -> dict:
    """Trim a raw Kapruka product to the fields the frontend renders."""
    price = item.get("price") or {}
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "summary": item.get("summary"),
        "price": price.get("amount"),
        "currency": price.get("currency"),
        "image_url": item.get("image_url"),
        "in_stock": item.get("in_stock"),
        "stock_level": item.get("stock_level"),
        "url": item.get("url"),
        # Outfit slot label set by the stylist's capture callback; null for
        # plain catalog searches (frontend renders a grouped section when set).
        "group": item.get("_group"),
    }
