"""Deterministic (no-LLM) Kapruka order placement over MCP.

The text/Sinhala agents place orders through the McpToolset *inside* the agent
loop. The live voice path instead calls this directly (via bridge.place_order)
so the final, money-creating step does not depend on the live model correctly
driving the checkout agent and not fabricating success. The order args are
assembled by the caller from authoritative session state, never by a model —
mirroring before_checkout_tool exactly.
"""

import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from tools.mcp import KAPRUKA_MCP_URL

# The free public tier is slow / rate-limited; match the McpToolset's 30s budget.
_TIMEOUT = 30.0


def _text_from_result(result) -> str | None:
    """Pull the first text block out of an MCP CallToolResult."""
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            return text
    return None


async def create_order_via_mcp(params: dict) -> dict:
    """Call kapruka_create_order once over MCP and return the parsed JSON body.

    `params` is the full CreateOrderInput dict (cart / recipient / sender /
    delivery / ...) with response_format="json". Returns the decoded order dict
    (which contains checkout_url / order_ref / summary on success), or
    {"status": "error", "message": ...} on a transport or parse failure.

    NOT retried: create_order is not idempotent server-side (a fresh idempotency
    key is generated per call), so a blind retry could place a duplicate.
    """
    try:
        async with streamablehttp_client(KAPRUKA_MCP_URL, timeout=_TIMEOUT) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "kapruka_create_order", arguments={"params": params}
                )
    except Exception as exc:  # transport / timeout / connection reset
        return {"status": "error", "message": f"Could not reach Kapruka ({exc})."}

    text = _text_from_result(result)
    if not text:
        return {"status": "error", "message": "Empty response from Kapruka."}
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return {"status": "error", "message": "Unexpected response from Kapruka."}
