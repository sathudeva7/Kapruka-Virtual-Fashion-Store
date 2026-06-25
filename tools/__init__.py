"""Shared toolsets, callbacks, sinks, cart and persona for all agent packages.

Mirrors the fashion-app-demo's `adk_backend/tools` layout. Public names are
re-exported here so agent packages can simply `from tools import ...`.
"""

from tools.persona import VOICE, LANGUAGE
from tools.mcp import (
    KAPRUKA_MCP_URL,
    kapruka_toolset,
    search_toolset,
    delivery_toolset,
    order_toolset,
    tracking_toolset,
)
from tools.sinks import product_sink
from tools.callbacks import (
    SUPPORTED_CURRENCIES,
    ALLOWED_SORTS,
    _fold_flat_args,
    force_json_before_tool,
    capture_products_after_tool,
    stylist_before_tool,
    stylist_capture_after_tool,
    stylist_before_model,
    stylist_after_agent,
    before_tracking_tool,
    capture_tracking_after_tool,
)
from tools.cart import manage_cart

__all__ = [
    "VOICE",
    "LANGUAGE",
    "KAPRUKA_MCP_URL",
    "kapruka_toolset",
    "search_toolset",
    "delivery_toolset",
    "order_toolset",
    "tracking_toolset",
    "product_sink",
    "SUPPORTED_CURRENCIES",
    "ALLOWED_SORTS",
    "force_json_before_tool",
    "capture_products_after_tool",
    "stylist_before_tool",
    "stylist_capture_after_tool",
    "stylist_before_model",
    "stylist_after_agent",
    "before_tracking_tool",
    "capture_tracking_after_tool",
    "manage_cart",
]
