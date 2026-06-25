"""Per-request contextvar sinks carrying structured data out-of-band from prose.

`product_sink` is a per-request list: main.py sets a fresh one at the start of
each /chat request (contextvars carry it through the agent/tool nesting), and
the after-tool callbacks append parsed products to it.
"""

import contextvars

product_sink: "contextvars.ContextVar[list | None]" = contextvars.ContextVar(
    "product_sink", default=None
)

# Per-request search budget. main.py sets {"n": 0} at the start of each /chat
# request; the stylist's before-tool callback increments it and short-circuits
# searches past the cap (the LLM ignores instruction-only caps when it keeps
# getting empty results). Mutating the dict in place works through contextvar
# copies; only `.set()` would not propagate.
search_counter: "contextvars.ContextVar[dict | None]" = contextvars.ContextVar(
    "search_counter", default=None
)

# Generated try-on images, mirroring product_sink: the try_on tool appends
# {"url", "product_id", "product_name"} dicts; main.py drains them into
# `tryon_image` SSE frames.
image_sink: "contextvars.ContextVar[list | None]" = contextvars.ContextVar(
    "image_sink", default=None
)

# The /chat session id, so the try_on tool can find the photo uploaded for
# this session (uploads happen on a separate endpoint, outside the run).
current_session_id: "contextvars.ContextVar[str | None]" = contextvars.ContextVar(
    "current_session_id", default=None
)

# Placed orders, mirroring product_sink: the checkout after-tool callback appends
# {"checkout_url", "order_ref", "grand_total", "currency", "expires_at"} dicts.
# The payment link lives only in the agent's prose otherwise — which the live
# voice model drops/garbles — so we surface it as a structured `order` frame the
# UI renders as a clickable Pay button.
order_sink: "contextvars.ContextVar[list | None]" = contextvars.ContextVar(
    "order_sink", default=None
)

# Order-tracking lookups, mirroring product_sink: the tracking agent's after-tool
# callback appends one shaped dict per kapruka_track_order call (order_number,
# status, delivery_date, amount, a progress[] timeline, …); main.py drains them
# into `tracking` SSE frames the UI renders as a status + timeline card.
tracking_sink: "contextvars.ContextVar[list | None]" = contextvars.ContextVar(
    "tracking_sink", default=None
)

# The live session's LiveRequestQueue (set only on the /live Gemini path). It lets
# a slow background job — confirming an order with Kapruka's MCP, which is too slow
# to await inside a live tool call without the session aborting (1008) — speak a
# follow-up turn AFTER the tool already returned a quick "please wait" line.
live_request_queue_var: "contextvars.ContextVar" = contextvars.ContextVar(
    "live_request_queue_var", default=None
)
