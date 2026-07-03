"""Bridge: run the text agent graph from *inside* the live voice agent.

Spike A finding: a nested `AgentTool` -> remote Kapruka MCP `create_session`
fails/hangs inside `run_live`'s TaskGroup (it works fine under `run_async`). So
the live voice agent does NOT call the specialists directly. Instead it calls the
`shop` function tool below, which runs the proven text graph via `run_async`
(MCP works there) and returns a short text answer to speak. Product/try-on
capture still flows through the shared contextvar sinks, so the cards/images
stream over the WebSocket exactly as in the text and Sinhala paths.

One shared runner (over the same `rootagent` graph) is used for the whole live
session so cart state persists across find -> style -> try-on -> checkout. It is
keyed by the live session id (the `current_session_id` contextvar the /live
handler sets), which also matches the uploaded photo's key for try-on.
"""

from google.adk.events.event import Event
from google.adk.runners import InMemoryRunner
from google.genai import types

import asyncio

from checkout.agent import _order_fingerprint  # shared idempotency signature
from rootagent import root_agent
from tools.cart import _cart_summary, cart_add_line
from tools.order_api import create_order_via_mcp
from tools.sinks import current_session_id, order_sink, live_request_queue_var

_APP = "kapruka"
_USER = "web-user"

# Separate runner from main.py's `runner` (different session store) — that's the
# already-accepted voice/text cart split. Within a live session it keeps state.
_runner = InMemoryRunner(agent=root_agent, app_name=_APP)
_known: set[str] = set()


async def _ensure(session_id: str) -> None:
    if session_id in _known:
        return
    await _runner.session_service.create_session(
        app_name=_APP, user_id=_USER, session_id=session_id
    )
    _known.add(session_id)


async def cart_add_item(
    session_id: str,
    product_id: str,
    name: str,
    category: str = "",
    price: int = 0,
    quantity: int = 1,
    image_url: str = "",
) -> dict:
    """Add a product to the live-session cart (no LLM)."""
    await _ensure(session_id)
    session = await _runner.session_service.get_session(
        app_name=_APP, user_id=_USER, session_id=session_id
    )
    if session is None:
        return {"status": "error", "message": "Session not found."}
    cart = session.state.get("cart", [])
    new_cart, err = cart_add_line(cart, product_id, name, category, price, quantity, image_url)
    if err:
        return err
    await _runner.session_service.append_event(
        session, Event(author="cart_api", state={"cart": new_cart})
    )
    return _cart_summary(new_cart)


async def save_checkout_details(
    session_id: str,
    name: str,
    phone: str,
    address: str,
    city: str,
    date: str = "",
    instructions: str = "",
) -> dict:
    """Write typed buyer + delivery details into the live-session state (no LLM).

    Uses the exact state keys before_checkout_tool reads, so a form entry is
    indistinguishable from details the agent saved — and avoids the assistant
    mishearing names/addresses. Only non-empty fields are written, so a partial
    form never clears something already captured by voice.
    """
    await _ensure(session_id)
    session = await _runner.session_service.get_session(
        app_name=_APP, user_id=_USER, session_id=session_id
    )
    if session is None:
        return {"status": "error", "message": "Session not found."}
    delta: dict = {}
    if name.strip():
        delta["name"] = name.strip()
    if phone.strip():
        delta["mobile"] = phone.strip()
    if address.strip():
        delta["delivery_address"] = address.strip()
    if city.strip():
        delta["delivery_city"] = city.strip()
    if date.strip():
        delta["delivery_date"] = date.strip()
    if instructions.strip():
        delta["delivery_instructions"] = instructions.strip()
    if not delta:
        return {"status": "error", "message": "No details provided."}
    await _runner.session_service.append_event(
        session, Event(author="checkout_form", state=delta)
    )
    return {"status": "ok", "saved": list(delta.keys())}


async def cart_remove_item(session_id: str, product_id: str) -> dict:
    """Remove a product line from the live-session cart (no LLM)."""
    await _ensure(session_id)
    session = await _runner.session_service.get_session(
        app_name=_APP, user_id=_USER, session_id=session_id
    )
    if session is None:
        return {"status": "error", "message": "Session not found."}
    cart = session.state.get("cart", [])
    new_cart = [line for line in cart if line.get("product_id") != product_id]
    await _runner.session_service.append_event(
        session, Event(author="cart_api", state={"cart": new_cart})
    )
    return _cart_summary(new_cart)


async def cart_set_quantity(session_id: str, product_id: str, quantity: int) -> dict:
    """Set a cart line's quantity to an absolute value (no LLM).

    quantity <= 0 removes the line, matching manage_cart's "update" action.
    """
    await _ensure(session_id)
    session = await _runner.session_service.get_session(
        app_name=_APP, user_id=_USER, session_id=session_id
    )
    if session is None:
        return {"status": "error", "message": "Session not found."}
    cart = session.state.get("cart", [])
    new_cart = [dict(line) for line in cart]
    for line in new_cart:
        if line.get("product_id") == product_id:
            break
    else:
        return {"status": "error", "message": f"{product_id} is not in the cart."}
    if quantity <= 0:
        new_cart = [l for l in new_cart if l.get("product_id") != product_id]
    else:
        line["quantity"] = quantity
    await _runner.session_service.append_event(
        session, Event(author="cart_api", state={"cart": new_cart})
    )
    return _cart_summary(new_cart)


async def cart_view(session_id: str) -> dict:
    """Return the current live-session cart contents and total (no LLM)."""
    await _ensure(session_id)
    session = await _runner.session_service.get_session(
        app_name=_APP, user_id=_USER, session_id=session_id
    )
    cart = session.state.get("cart", []) if session else []
    return _cart_summary(cart)


# Required session-state keys for a placeable order, with shopper-facing labels.
_REQUIRED_FOR_ORDER = [
    ("name", "your name"),
    ("mobile", "your phone number"),
    ("delivery_address", "delivery address"),
    ("delivery_city", "delivery city"),
    ("delivery_date", "delivery date"),
]


# Background order-confirmation tasks are kept here so they aren't garbage-collected
# mid-flight (asyncio holds only a weak reference to bare create_task results).
_pending_orders: set = set()


def _order_params(state: dict, cart: list) -> dict:
    """Assemble the kapruka_create_order params from authoritative state."""
    params = {
        "cart": [
            {"product_id": line["product_id"], "quantity": int(line.get("quantity", 1))}
            for line in cart
        ],
        "recipient": {"name": state["name"], "phone": state["mobile"]},
        "sender": {"name": state["name"], "anonymous": False},
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
    return params


def _speak_followup(live_queue, text: str) -> None:
    """Push a follow-up spoken turn into the live session (text, so it makes the
    assistant talk again without showing as a 'you said' caption). The bracketed
    SYSTEM note steers the line; the model must NOT call a tool in response."""
    if live_queue is None:
        return
    try:
        live_queue.send_content(
            types.Content(role="user", parts=[types.Part(text=text)])
        )
    except Exception:
        pass  # session may have closed while we were confirming; nothing to do


async def _confirm_order_in_background(session_id, fingerprint, params, orders_sink, live_queue):
    """Place the order with Kapruka (the slow part), THEN — only once confirmed —
    reveal the Pay now card and have the assistant speak the result. Runs detached
    from the live tool call so the live turn never blocks long enough to abort."""
    try:
        data = await create_order_via_mcp(params)
    except Exception as exc:  # defensive: never let the task die silently
        data = {"status": "error", "message": str(exc)}

    if not isinstance(data, dict) or not data.get("checkout_url"):
        msg = (data.get("message") if isinstance(data, dict) else None) or "please try again"
        _speak_followup(live_queue,
            f"[SYSTEM: The order could NOT be confirmed by Kapruka — reason: {msg}. "
            "Do not call any tool.] Briefly and warmly tell the shopper it didn't go "
            "through, say why in one line, and offer to try placing it again.")
        return

    summary = data.get("summary") or {}
    order = {
        "order_ref": data.get("order_ref"),
        "checkout_url": data.get("checkout_url"),
        "expires_at": data.get("expires_at"),
        "grand_total": summary.get("grand_total"),
        "currency": summary.get("currency"),
    }
    session = await _runner.session_service.get_session(
        app_name=_APP, user_id=_USER, session_id=session_id
    )
    if session is not None:
        await _runner.session_service.append_event(
            session,
            Event(author="order_api", state={"last_order": {"fingerprint": fingerprint, **order}}),
        )
    # Reveal the Pay now card ONLY now that Kapruka has confirmed the order.
    if orders_sink is not None:
        orders_sink.append(order)
    total, currency = order.get("grand_total"), order.get("currency") or "LKR"
    total_line = f" The total is {total} {currency}." if total is not None else ""
    _speak_followup(live_queue,
        f"[SYSTEM: The order is now CONFIRMED by Kapruka.{total_line} The Pay now button "
        "is on the shopper's screen. Do not call any tool.] Warmly tell the shopper their "
        "order is confirmed and ask them to tap the Pay now button to complete payment.")


async def place_order() -> str:
    """Confirm the shopper's order with Kapruka and reveal the payment button.

    Call this the MOMENT the shopper confirms they want to buy / checkout / pay.
    It validates the saved cart + delivery details instantly, then confirms the
    order with Kapruka IN THE BACKGROUND (that round-trip is too slow to await
    here without the live session aborting). So return RIGHT AWAY with the status
    below; when the background confirmation finishes you'll automatically be told
    to speak the result and the Pay now button will appear.

    Returns one of:
      "ORDER_CONFIRMING. ..."  — accepted; tell them to please wait while we confirm.
                                  Do NOT say it's done or mention Pay now yet.
      "MISSING_DETAILS: ..."   — ask them to tap 📝 and type the listed fields, then retry.
      "ORDER_PLACED. ..."      — already confirmed earlier; tell them to tap Pay now.
    Idempotent: the same cart+delivery won't be ordered twice.
    """
    session_id = current_session_id.get() or "live-default"
    await _ensure(session_id)
    session = await _runner.session_service.get_session(
        app_name=_APP, user_id=_USER, session_id=session_id
    )
    if session is None:
        return "MISSING_DETAILS: session not found — please try again."
    state = session.state
    cart = state.get("cart") or []

    missing = ([] if cart else ["an item in the cart"]) + [
        label for key, label in _REQUIRED_FOR_ORDER if not state.get(key)
    ]
    if missing:
        return "MISSING_DETAILS: " + ", ".join(missing)

    fingerprint = _order_fingerprint(state)
    last = state.get("last_order")
    # Already confirmed (same cart+delivery): reuse the link and show the card now.
    if isinstance(last, dict) and last.get("fingerprint") == fingerprint:
        order = {k: last.get(k) for k in
                 ("order_ref", "checkout_url", "expires_at", "grand_total", "currency")}
        sink = order_sink.get()
        if sink is not None and order.get("checkout_url"):
            sink.append(order)
        total, currency = order.get("grand_total"), order.get("currency") or "LKR"
        tail = f" Total {total} {currency}." if total is not None else ""
        return f"ORDER_PLACED. The Pay now button is on screen.{tail}"

    # New order: confirm with Kapruka in the background and return immediately.
    params = _order_params(state, cart)
    task = asyncio.create_task(_confirm_order_in_background(
        session_id, fingerprint, params, order_sink.get(), live_request_queue_var.get()))
    _pending_orders.add(task)
    task.add_done_callback(_pending_orders.discard)
    return ("ORDER_CONFIRMING. Tell the shopper to please hold on a moment while we "
            "confirm their order with Kapruka. Do NOT say it's done and do NOT mention "
            "the Pay now button yet — you'll be told the moment it's confirmed.")


# Public handles so the Sinhala voice path can run its turns on THIS runner — the
# same session store the /cart endpoints (cart_view/cart_add_item) read — instead of
# main.py's separate text `runner`. Otherwise Sinhala voice-added cart items land in a
# store the 3D UI cart widget never reads, so the panel shows nothing (see the
# already-accepted voice/text cart split at the top of this module).
shared_runner = _runner


async def ensure_shared_session(session_id: str) -> None:
    """Create the shared-runner session if absent (idempotent)."""
    await _ensure(session_id)


async def shop(request: str) -> str:
    """Handle a Kapruka shopping request and return a short answer to speak.

    Use this for ANYTHING the shopper wants to do: find products, ask prices or
    availability, compose a full outfit, virtually try a garment on, manage the
    cart, or place an order. Pass the shopper's request in their OWN words (e.g.
    "a red shirt for men under 5000", "style me for a wedding", "try on product
    123", "checkout"). Product cards and try-on images appear on screen
    automatically — your job is just to speak the returned summary briefly.
    """
    session_id = current_session_id.get() or "live-default"
    await _ensure(session_id)
    message = types.Content(role="user", parts=[types.Part(text=request)])

    final = ""
    async for event in _runner.run_async(
        user_id=_USER, session_id=session_id, new_message=message
    ):
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) or []
        text = "".join(p.text for p in parts if getattr(p, "text", None))
        if text and not getattr(event, "partial", False):
            final = text  # keep the last non-partial aggregate
    return final or "Sorry, I couldn't find anything for that just now."
