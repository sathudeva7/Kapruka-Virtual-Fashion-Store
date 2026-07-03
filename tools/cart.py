"""The session shopping cart — a local tool shared by catalog and checkout."""

from google.adk.tools import ToolContext

# --- Session cart ----------------------------------------------------------
#
# The cart is a list of line items under a single session-state key, `cart`.
# ADK records state changes as a delta, and an in-place `.append(...)` on the
# stored list may not be detected — so every tool below follows the same safe
# pattern: copy the list (and each line dict), modify the copy, then REASSIGN
# `state["cart"]`. Totals are always computed, never stored, to avoid drift.

def _cart_summary(cart: list) -> dict:
  """A structured snapshot the model can read back and confirm to the user."""
  return {
    "status": "ok",
    "items": cart,
    "item_count": sum(line["quantity"] for line in cart),
    "total": sum(line["unit_price"] * line["quantity"] for line in cart),
    "currency": "LKR",
  }


def _load_cart(tool_context: ToolContext) -> list:
  """Return an editable copy of the cart (copies each line so stored state
  is never mutated in place before we reassign it)."""
  return [dict(line) for line in tool_context.state.get("cart", [])]


def cart_add_line(
    cart: list,
    product_id: str,
    name: str,
    category: str = "",
    price: int = 0,
    quantity: int = 1,
    image_url: str = "",
) -> tuple[list | None, dict | None]:
  """Add a product to a cart copy. Returns (new_cart, None) or (None, error)."""
  if not product_id or not name:
    return None, {"status": "error", "message": "add requires product_id and name."}
  if quantity < 1:
    return None, {"status": "error", "message": "quantity must be at least 1."}
  if price < 0:
    return None, {"status": "error", "message": "price cannot be negative."}
  cart = [dict(line) for line in cart]
  for line in cart:
    if line["product_id"] == product_id:
      line["quantity"] += quantity
      # Backfill a thumbnail if this line was first added without one (e.g. via voice).
      if image_url and not line.get("image_url"):
        line["image_url"] = image_url
      break
  else:
    cart.append({
      "product_id": product_id,
      "name": name,
      "category": category,
      "unit_price": price,
      "quantity": quantity,
      "image_url": image_url,
    })
  return cart, None


def manage_cart(
    tool_context: ToolContext,
    action: str,
    product_id: str = "",
    name: str = "",
    category: str = "",
    price: int = 0,
    quantity: int = 1,
    image_url: str = "",
) -> dict:
  """Manage the session shopping cart. Returns the updated cart and total.

  action:
    - "add":    add a product (needs product_id, name, category, price; quantity
                defaults to 1). Re-adding a product INCREMENTS its quantity —
                never warn that it is "already in the cart".
    - "view":   return the current cart contents and total.
    - "update": set product_id's quantity to an absolute value (0 removes the line).
    - "remove": delete product_id from the cart.
    - "clear":  empty the cart.
  """
  action = (action or "").lower()
  cart = _load_cart(tool_context)  # copy so the delta is recorded on reassign

  if action == "view":
    return _cart_summary(cart)

  if action == "clear":
    tool_context.state["cart"] = []
    return _cart_summary([])

  if action == "add":
    # Voice adds go through the LLM, which fills these args and reliably omits the
    # long CDN image_url — so the cart line would render as a bare letter monogram.
    # Backfill it from seen_products (the same product_id -> image_url map try_on
    # uses), so a thumbnail shows regardless of whether the LLM supplied one.
    if not image_url and product_id:
      info = (tool_context.state.get("seen_products") or {}).get(product_id)
      if info:
        image_url = info.get("image_url") or ""
    cart, err = cart_add_line(cart, product_id, name, category, price, quantity, image_url)
    if err:
      return err
    tool_context.state["cart"] = cart  # reassign so ADK persists the change
    return _cart_summary(cart)

  if action == "update":
    if not product_id:
      return {"status": "error", "message": "update requires product_id."}
    for line in cart:
      if line["product_id"] == product_id:
        if quantity <= 0:
          cart.remove(line)
        else:
          line["quantity"] = quantity
        tool_context.state["cart"] = cart
        return _cart_summary(cart)
    return {"status": "error", "message": f"{product_id} is not in the cart."}

  if action == "remove":
    if not product_id:
      return {"status": "error", "message": "remove requires product_id."}
    cart = [l for l in cart if l["product_id"] != product_id]
    tool_context.state["cart"] = cart
    return _cart_summary(cart)

  return {"status": "error",
          "message": f"unknown action '{action}'. Use add/view/update/remove/clear."}
