"""Direct (no-LLM) commerce endpoints for the 3D UI: virtual try-on, the cart
trolley, the checkout-details form, and typed order tracking."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from fittingroom.tryon import generate_tryon
from liveagent.bridge import (
    cart_add_item,
    cart_remove_item,
    cart_set_quantity,
    cart_view,
    save_checkout_details,
)
from tools.callbacks import _tracking_card
from tools.order_api import track_order_via_mcp

from server.schemas import (
    CartAddRequest,
    CartRemoveRequest,
    CartUpdateRequest,
    CheckoutDetailsRequest,
    TrackOrderRequest,
    TryOnRequest,
)

router = APIRouter()


@router.post("/try_on")
async def try_on_endpoint(req: TryOnRequest):
    """Direct virtual try-on (no LLM): uploaded photo + garment image(s) →
    generated image. Returns {status, image_url, product_name}. The photo must
    have been sent to /upload_photo for this session first."""
    garments = [
        {"id": p.id, "name": p.name, "image_url": p.image_url} for p in req.products
    ]
    return await generate_tryon(req.session_id, garments)


@router.post("/cart")
async def cart_add_endpoint(req: CartAddRequest):
    """Direct add-to-cart for the 3D UI (no LLM). Uses the live-session cart."""
    if not req.product_id or not req.name:
        return JSONResponse(
            {"status": "error", "message": "product_id and name are required."},
            status_code=400,
        )
    return await cart_add_item(
        req.session_id,
        req.product_id,
        req.name,
        req.category,
        req.price,
        req.quantity,
        req.image_url,
    )


@router.post("/cart/remove")
async def cart_remove_endpoint(req: CartRemoveRequest):
    """Remove a line from the live-session cart for the 3D UI's trolley."""
    if not req.product_id:
        return JSONResponse(
            {"status": "error", "message": "product_id is required."},
            status_code=400,
        )
    return await cart_remove_item(req.session_id, req.product_id)


@router.post("/cart/update")
async def cart_update_endpoint(req: CartUpdateRequest):
    """Set a line's quantity in the live-session cart for the 3D UI's trolley
    (no LLM). A quantity of 0 or less removes the line."""
    if not req.product_id:
        return JSONResponse(
            {"status": "error", "message": "product_id is required."},
            status_code=400,
        )
    return await cart_set_quantity(req.session_id, req.product_id, req.quantity)


@router.get("/cart")
async def cart_view_endpoint(session_id: str):
    """Read the current live-session cart for the 3D UI's trolley widget."""
    return await cart_view(session_id)


@router.post("/checkout_details")
async def checkout_details_endpoint(req: CheckoutDetailsRequest):
    """Save typed buyer + delivery details so the assistant never has to
    transcribe a name/address/phone by ear (3D UI's details form).

    Saving does NOT place the order — order placement is driven entirely by the
    AI agent (so it can confirm with the shopper first); placing here too caused
    a duplicate order."""
    return await save_checkout_details(
        req.session_id,
        req.name,
        req.phone,
        req.address,
        req.city,
        req.date,
        req.instructions,
    )


@router.post("/track_order")
async def track_order_endpoint(req: TrackOrderRequest):
    """Direct order tracking (no LLM): look up an order by the EXACT number the
    shopper typed and return the shaped tracking card. Used by the 3D UI's "Track
    an order" box so a mis-heard voice number can't break the lookup.

    Returns {status:"ok", item:<tracking card>} or {status:"error", message}."""
    data = await track_order_via_mcp(req.order_number)
    if isinstance(data, dict) and data.get("order_number"):
        return {"status": "ok", "item": _tracking_card(data)}
    message = (
        (data.get("message") if isinstance(data, dict) else None)
        or "We couldn't find that order. Please check the number and try again."
    )
    return JSONResponse({"status": "error", "message": message}, status_code=404)
