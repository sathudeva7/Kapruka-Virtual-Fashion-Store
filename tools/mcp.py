"""Kapruka MCP toolsets — one purpose-built subset per agent."""

import asyncio
import logging

from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams

logger = logging.getLogger(__name__)

# Kapruka's MCP server is a remote streamable-HTTP endpoint.
KAPRUKA_MCP_URL = "https://mcp.kapruka.com/mcp"

# The public free tier flakes intermittently (slow / rate-limited): a call can
# time out or drop the connection even though an immediate retry succeeds (we've
# observed an identical search succeed then time out back-to-back). We retry such
# failures ONCE — but only for read-only tools, never for order placement, which
# isn't idempotent (a retried create_order could place a duplicate).
_RETRY_SAFE_TOOLS = {
    "kapruka_search_products",
    "kapruka_get_product",
    "kapruka_list_categories",
    "kapruka_check_delivery",
    "kapruka_list_delivery_cities",
    "kapruka_track_order",
}
_RETRY_DELAY_SECONDS = 0.6


def _wrap_retry(tool):
    """Wrap a read-only MCP tool's run_async so a single transient failure
    (timeout / dropped connection on the free tier) is retried once."""
    name = getattr(tool, "name", None)
    if name not in _RETRY_SAFE_TOOLS or getattr(tool, "_kapruka_retry_wrapped", False):
        return tool
    original = tool.run_async

    async def run_async(*, args, tool_context):
        try:
            return await original(args=args, tool_context=tool_context)
        except Exception as exc:  # transient: timeout / connection reset
            logger.warning("MCP tool %s failed (%s); retrying once.", name, exc)
            await asyncio.sleep(_RETRY_DELAY_SECONDS)
            return await original(args=args, tool_context=tool_context)

    tool.run_async = run_async
    tool._kapruka_retry_wrapped = True
    return tool


class _RetryingMcpToolset(McpToolset):
    """McpToolset that retries read-only tool calls once on a transient error."""

    async def get_tools(self, readonly_context=None):
        return [_wrap_retry(t) for t in await super().get_tools(readonly_context)]


def _toolset(*tool_names: str) -> McpToolset:
    """An MCP toolset connected to Kapruka, limited to the named tools.

    Passing no names exposes every tool the server offers.
    """
    return _RetryingMcpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=KAPRUKA_MCP_URL,
            # Default is 5s — too tight for the public tier when it's slow or
            # rate-limiting, which surfaces as "Failed to get tools / TimeoutError".
            timeout=30.0,
        ),
        tool_filter=list(tool_names) or None,
    )


# Full toolset (all Kapruka tools) plus purpose-built subsets per agent.
kapruka_toolset = _toolset()
# Shopper: full product-discovery set — browse categories, search the catalog,
# and pull full details (price, variants, images, stock) for a specific product.
search_toolset = _toolset(
    "kapruka_search_products",
    "kapruka_get_product",
    "kapruka_list_categories",
)
delivery_toolset = _toolset(
    "kapruka_check_delivery",
    "kapruka_list_delivery_cities",
)
order_toolset = _toolset("kapruka_create_order")
# Post-sale: look up an existing order's status + delivery progress by order number.
tracking_toolset = _toolset("kapruka_track_order")
