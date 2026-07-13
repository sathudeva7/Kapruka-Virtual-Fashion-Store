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


async def _reset_sessions(session_manager) -> None:
    """Drop the manager's cached MCP sessions so the next call reconnects.

    The Kapruka server expires long-lived streamable-HTTP sessions. When that
    happens the client's local read/write streams stay open, so ADK's
    _is_session_disconnected check keeps handing back the dead session and
    every call fails with McpError("Session terminated") until the process
    restarts. close() clears the session cache; the manager stays usable and
    create_session() builds a fresh session on the next call.
    """
    try:
        await session_manager.close()
    except Exception:
        logger.warning("Failed to reset MCP sessions before retry.", exc_info=True)


def _wrap_retry(tool):
    """Wrap a read-only MCP tool's run_async so a single transient failure
    (timeout / dropped connection / expired session on the free tier) is
    retried once — against a freshly created MCP session."""
    name = getattr(tool, "name", None)
    if name not in _RETRY_SAFE_TOOLS or getattr(tool, "_kapruka_retry_wrapped", False):
        return tool
    original = tool.run_async

    async def run_async(*, args, tool_context):
        try:
            return await original(args=args, tool_context=tool_context)
        except Exception as exc:  # transient: timeout / reset / dead session
            logger.warning("MCP tool %s failed (%s); retrying once.", name, exc)
            await _reset_sessions(tool._mcp_session_manager)
            await asyncio.sleep(_RETRY_DELAY_SECONDS)
            return await original(args=args, tool_context=tool_context)

    tool.run_async = run_async
    tool._kapruka_retry_wrapped = True
    return tool


class _RetryingMcpToolset(McpToolset):
    """McpToolset that retries once on a transient error, recreating the MCP
    session in between (covers both tool listing and tool execution)."""

    async def get_tools(self, readonly_context=None):
        try:
            tools = await super().get_tools(readonly_context)
        except Exception as exc:
            logger.warning("MCP get_tools failed (%s); retrying once.", exc)
            await _reset_sessions(self._mcp_session_manager)
            await asyncio.sleep(_RETRY_DELAY_SECONDS)
            tools = await super().get_tools(readonly_context)
        return [_wrap_retry(t) for t in tools]


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
