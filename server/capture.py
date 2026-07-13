"""Per-turn capture of structured tool output, via the contextvar sinks.

Every conversational endpoint (/chat, /live, /voice_sinhala, /live_sinhala)
needs the same plumbing: fresh lists installed into the contextvar sinks in
tools/sinks.py so the tool callbacks can append products / try-on images /
placed orders / tracking cards while the LLM speaks prose, then an incremental
drain that turns anything new into wire frames BEFORE the prose. TurnCapture
bundles that so each endpoint no longer repeats the setup and four drain loops.
"""

from dataclasses import dataclass, field
from typing import Iterator

from tools.sinks import (
    current_role,
    current_session_id,
    image_sink,
    order_sink,
    product_sink,
    search_counter,
    tracking_sink,
)

from server.streaming import product_card


@dataclass
class TurnCapture:
    """One conversation turn's (or one live connection's) captured output."""

    products: list = field(default_factory=list)
    images: list = field(default_factory=list)
    orders: list = field(default_factory=list)
    tracking: list = field(default_factory=list)
    _drained: dict = field(
        default_factory=lambda: {"products": 0, "images": 0, "orders": 0,
                                 "tracking": 0}
    )

    @classmethod
    def bind(cls, session_id: str, *, role: str | None = None) -> "TurnCapture":
        """Install fresh sinks into the CURRENT context and return the capture.

        Must run in the coroutine that will execute the agent — or, for the
        WebSocket paths, before the pump tasks are spawned so they inherit the
        context. Downstream, callbacks mutate the held lists in place; a later
        `.set()` would fork a binding they'd never see (see tools/sinks.py).
        """
        capture = cls()
        product_sink.set(capture.products)
        image_sink.set(capture.images)
        order_sink.set(capture.orders)
        tracking_sink.set(capture.tracking)
        search_counter.set({"n": 0})  # per-turn search budget (stylist)
        current_session_id.set(session_id)  # photo lookup + audit
        if role is not None:
            current_role.set(role)
        return capture

    def drain(self) -> Iterator[dict]:
        """Yield a wire frame for everything captured since the last drain,
        in render order: product cards, try-on images, order links, tracking."""
        d = self._drained
        while d["products"] < len(self.products):
            yield {"type": "product",
                   "item": product_card(self.products[d["products"]])}
            d["products"] += 1
        while d["images"] < len(self.images):
            yield {"type": "tryon_image", **self.images[d["images"]]}
            d["images"] += 1
        while d["orders"] < len(self.orders):
            yield {"type": "order", **self.orders[d["orders"]]}
            d["orders"] += 1
        while d["tracking"] < len(self.tracking):
            yield {"type": "tracking", **self.tracking[d["tracking"]]}
            d["tracking"] += 1


def reset_search_budget() -> None:
    """Reset the stylist's per-turn search budget at a live-turn boundary.

    Unlike /chat and /voice_sinhala, the live WebSocket loops are one long run
    with no per-turn re-entry, so the budget set once at connect would otherwise
    climb across the whole session and lock the stylist out after ~6 searches.
    Mutate the HELD dict in place (not search_counter.set): the callbacks read
    the object the downstream task inherited at connect time, and a .set() here
    forks a new binding they'd never see (see the contextvar note in CLAUDE.md).
    """
    counter = search_counter.get()
    if counter is not None:
        counter["n"] = 0


def searches_this_turn() -> int:
    """How many product searches ran since the last budget reset."""
    return (search_counter.get() or {}).get("n", 0)
