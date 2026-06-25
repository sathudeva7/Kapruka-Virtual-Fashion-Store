"""The Checkout Agent — collects delivery details and places the order —
plus the logistics (delivery-feasibility) specialist and the order-placement
callbacks that only this agent uses."""

import json
from datetime import datetime, timedelta, timezone

from google.adk import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools import ToolContext
from google.genai import types

from tools import (
    VOICE,
    LANGUAGE,
    manage_cart,
    delivery_toolset,
    order_toolset,
    _fold_flat_args,
)
from tools.sinks import order_sink


def save_user_info(tool_context: ToolContext, name: str, mobile: str) -> dict:
  """Save the buyer's name and mobile number to session state (used as both
  recipient and sender at checkout)."""
  tool_context.state["name"] = name
  tool_context.state["mobile"] = mobile
  return {"status": "ok", "name": name, "mobile": mobile}


def save_delivery_details(
    tool_context: ToolContext, address: str, city: str, date: str
) -> dict:
  """Save the delivery address, city and date (YYYY-MM-DD) to session state."""
  tool_context.state["delivery_address"] = address
  tool_context.state["delivery_city"] = city
  tool_context.state["delivery_date"] = date
  return {"status": "ok", "address": address, "city": city, "date": date}


# --- Order placement -------------------------------------------------------
#
# kapruka_create_order is an outward-facing, hard-to-reverse action: it creates
# a real order and returns a 60-minute click-to-pay link. We never let the LLM
# assemble its arguments freely. Instead the before-callback builds the entire
# order from authoritative SESSION STATE (cart + buyer + saved delivery), so a
# wrong product id / price / quantity from the model can't reach Kapruka. The
# model's only freedom is optional gift_message / anonymous flag.

CREATE_ORDER_TOOL = "kapruka_create_order"


def _json_from_tool_response(tool_response) -> dict | None:
    """Parse the JSON body out of an MCP tool response, or None."""
    try:
        content = tool_response.get("content") if isinstance(tool_response, dict) else None
        text = content[0].get("text") if content else None
        return json.loads(text)
    except Exception:
        return None


def _order_fingerprint(state) -> str:
    """Stable signature of the orderable state (cart + delivery). Two create_order
    calls with the same fingerprint are the same order — used for idempotency."""
    cart = state.get("cart") or []
    items = sorted(
        (str(line.get("product_id")), int(line.get("quantity", 1))) for line in cart
    )
    delivery = (
        state.get("delivery_address"),
        state.get("delivery_city"),
        state.get("delivery_date"),
    )
    return json.dumps({"items": items, "delivery": delivery}, sort_keys=True)


_DELIVERY_TOOLS = {"kapruka_check_delivery", "kapruka_list_delivery_cities"}
CHECK_DELIVERY_TOOL = "kapruka_check_delivery"


def _delivery_args_key(args) -> str:
    """Cache key for a delivery check: the (city, date) being validated. Reads
    from the folded `params` (or flat args) and tolerates a couple of likely
    field names — returns "" if neither is present, which disables caching for
    that call rather than risking a false hit."""
    params = args.get("params") if isinstance(args.get("params"), dict) else args
    if not isinstance(params, dict):
        return ""
    city = str(params.get("city") or params.get("delivery_city") or "").strip().lower()
    date = str(params.get("date") or params.get("delivery_date") or "").strip()
    if not city and not date:
        return ""
    return json.dumps({"city": city, "date": date}, sort_keys=True)


def before_checkout_tool(*, tool, args, tool_context):
    """For kapruka_create_order only: validate, assemble params from state, and
    short-circuit duplicate orders. Delivery tools get their args re-nested
    under `params` (Gemini sometimes passes them flat); others proceed
    untouched."""
    name = getattr(tool, "name", None)
    if name in _DELIVERY_TOOLS:
        _fold_flat_args(args)
        # Serve a repeat delivery check for the same city+date from cache instead
        # of the slow (~30s) MCP round-trip. The cache is filled by
        # after_checkout_tool and invalidated naturally when the city/date change.
        if name == CHECK_DELIVERY_TOOL:
            key = _delivery_args_key(args)
            cached = tool_context.state.get("delivery_check")
            if key and isinstance(cached, dict) and cached.get("key") == key:
                return cached.get("result")
        return None
    if name != CREATE_ORDER_TOOL:
        return None

    state = tool_context.state
    cart = state.get("cart") or []

    # 1. Required data must be present — otherwise tell the model what's missing
    #    instead of letting Kapruka reject the call.
    missing = []
    if not cart:
        missing.append("cart is empty")
    if not state.get("name"):
        missing.append("buyer name")
    if not state.get("mobile"):
        missing.append("buyer phone")
    if not state.get("delivery_address"):
        missing.append("delivery address")
    if not state.get("delivery_city"):
        missing.append("delivery city")
    if not state.get("delivery_date"):
        missing.append("delivery date")
    if missing:
        return {
            "status": "error",
            "message": "Cannot place the order yet — missing: " + ", ".join(missing),
        }

    # 2. Idempotency: same cart + delivery already ordered → return the saved link
    #    rather than creating a duplicate order (the cart is kept after checkout).
    fingerprint = _order_fingerprint(state)
    last = state.get("last_order")
    if isinstance(last, dict) and last.get("fingerprint") == fingerprint:
        saved = {k: last.get(k) for k in
                 ("order_ref", "checkout_url", "expires_at", "grand_total", "currency")}
        # Re-surface the payment link too — the create_order tool is skipped here,
        # so after_checkout_tool won't fire for this duplicate confirmation.
        sink = order_sink.get()
        if sink is not None and saved.get("checkout_url"):
            sink.append(saved)
        return {"status": "already_placed", **saved}

    # 3. Build the order entirely from state. Buyer is both recipient and sender.
    incoming = args.get("params") if isinstance(args.get("params"), dict) else {}
    sender_in = incoming.get("sender") if isinstance(incoming.get("sender"), dict) else {}
    params = {
        "cart": [
            {"product_id": line["product_id"], "quantity": int(line.get("quantity", 1))}
            for line in cart
        ],
        "recipient": {"name": state["name"], "phone": state["mobile"]},
        "sender": {"name": state["name"], "anonymous": bool(sender_in.get("anonymous", False))},
        "delivery": {
            "address": state["delivery_address"],
            "city": state["delivery_city"],
            "date": state["delivery_date"],
            "location_type": state.get("delivery_location_type", "house"),
        },
        "currency": "LKR",
        "response_format": "json",
    }
    if state.get("delivery_instructions"):
        params["delivery"]["instructions"] = state["delivery_instructions"]
    if incoming.get("gift_message"):
        params["gift_message"] = incoming["gift_message"]

    args["params"] = params  # authoritative — overrides anything the model passed
    return None


def after_checkout_tool(*, tool, args, tool_context, tool_response):
    """Persist the order reference + checkout link so we can detect duplicates,
    and surface the payment link as a structured `order` frame (the link lives
    only in the agent's prose otherwise — which the voice model drops)."""
    name = getattr(tool, "name", None)
    if name == CHECK_DELIVERY_TOOL:
        # Cache a well-formed delivery check so repeat turns (confirmations,
        # "is it still available?") skip the MCP call. Only cache parseable
        # responses, so a transient timeout/error is never cached.
        key = _delivery_args_key(args)
        if key and isinstance(_json_from_tool_response(tool_response), dict):
            tool_context.state["delivery_check"] = {"key": key, "result": tool_response}
        return None
    if name != CREATE_ORDER_TOOL:
        return None
    data = _json_from_tool_response(tool_response)
    if not isinstance(data, dict) or not data.get("checkout_url"):
        return None  # leave failures untouched
    summary = data.get("summary") or {}
    order = {
        "order_ref": data.get("order_ref"),
        "checkout_url": data.get("checkout_url"),
        "expires_at": data.get("expires_at"),
        "grand_total": summary.get("grand_total"),
        "currency": summary.get("currency"),
    }
    tool_context.state["last_order"] = {"fingerprint": _order_fingerprint(tool_context.state), **order}
    # Emit the clickable payment link out-of-band (drained by main.py).
    sink = order_sink.get()
    if sink is not None:
        sink.append(order)
    return None


# The Checkout Agent — collects delivery details and places the order.
# The buyer (already in state) is used as both recipient and sender. The order
# itself is assembled from authoritative state by before_checkout_tool, so this
# agent only needs to gather delivery info, confirm, and trigger create_order.

# Asia/Colombo is a fixed UTC+5:30 offset (no DST), so we can resolve "today"
# without a tz database. The model has no reliable clock of its own, so we inject
# the current date AND the shopper's saved details into the instruction — without
# this it wrongly calls future dates "in the past" and claims it can't see the
# details the form already saved.
_LK_TZ = timezone(timedelta(hours=5, minutes=30))


def _saved(state, key: str) -> str:
    val = state.get(key)
    return str(val) if val else "(not yet entered)"


def checkout_instruction(ctx: ReadonlyContext) -> str:
    state = ctx.state
    today = datetime.now(_LK_TZ).strftime("%Y-%m-%d")
    return f"""{VOICE}
    {LANGUAGE}

    Your job here: get the order placed quickly and warmly. The buyer's name and phone are
    used as both recipient and sender. Keep it light — every step should feel like one easy
    tap, not a form.

    TODAY'S DATE is {today}. A delivery date is only in the past if it is strictly
    BEFORE {today}; {today} or any later date is valid. Never claim a date is in the
    past without comparing it to {today} first.

    The shopper has saved these details on the on-screen form (this is the SOURCE OF
    TRUTH — trust it, read it back when asked, and do not say you "can't see" it):
    - name: {_saved(state, 'name')}
    - mobile: {_saved(state, 'mobile')}
    - delivery address: {_saved(state, 'delivery_address')}
    - city: {_saved(state, 'delivery_city')}
    - delivery date: {_saved(state, 'delivery_date')}

    IMPORTANT — names, phone numbers and addresses are easy to mishear, so do NOT
    collect them by voice. There is an on-screen details form (the 📝 button). When
    you need the buyer's name, mobile, address, city or delivery date, ask the
    shopper to TAP THE 📝 BUTTON AND TYPE THEM IN — never ask them to spell it out
    loud and never call save_user_info / save_delivery_details from dictation.

    Steps:
    - Call manage_cart(action="view"). If it is empty, tell the user and stop.
    - Read the saved details above. If name, mobile, delivery address, city and
      delivery date are all present, re-use them — do NOT re-ask, and do NOT ask the
      shopper to re-enter a detail that is already shown above.
    - If any show "(not yet entered)", warmly ask the shopper to tap the 📝 details
      button and type in the missing ones, then continue once they're saved.
    - Verify the delivery date above against TODAY'S DATE ({today}). Only if it is
      strictly before {today} should you ask the shopper to edit the form with a later
      date — otherwise treat it as valid and move on.
    - Validate delivery by calling kapruka_check_delivery DIRECTLY with the saved
      city and date — do NOT call kapruka_list_delivery_cities first (it's a slow
      extra step). Tell the user the delivery fee and any freshness warning. Only if
      kapruka_check_delivery fails because the city isn't recognised, call
      kapruka_list_delivery_cities once to find the correct spelling and retry; if it
      is genuinely unavailable, ask them to edit the form with an alternative.
    - Offer a gift message — if it's clearly a gift, proactively ask if they'd like a short
      note added, and pass it as gift_message when you place the order.
    - Show a clear order review (items, quantities, delivery address/date, delivery fee)
      and ask the user to confirm before paying.
    - ONLY after the user confirms, call kapruka_create_order. Then give them the
      checkout link, the grand total and when the link expires — reassure them it's a quick
      one-tap payment.
    - Never invent prices or totals — use exactly what the tools return."""


checkout_agent = Agent(
    name="checkout_agent",
    description="Collects delivery details and places the Kapruka order.",
    model="gemini-2.5-flash",
    instruction=checkout_instruction,
    tools=[manage_cart, delivery_toolset, order_toolset, save_delivery_details,
           save_user_info],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.6,
        thinking_config=types.ThinkingConfig(thinking_budget=0),  # lower latency
    ),
    before_tool_callback=before_checkout_tool,
    after_tool_callback=after_checkout_tool,
)


# The Logistics Agent — a delivery-feasibility specialist.
logistics_agent = Agent(
    name="logistics",
    model="gemini-2.5-flash",
    instruction="""You check whether Kapruka can deliver to a city on a date, and the rate.
    - Use kapruka_list_delivery_cities to resolve/validate the city name.
    - Use kapruka_check_delivery for the chosen city and date; report the flat LKR rate,
    availability, and any perishable warning.""",
    tools=[delivery_toolset],
)
