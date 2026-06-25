"""Before/after tool callbacks for the product-discovery tools.

The shopper agent turns MCP results into prose, which loses image URLs and
clean fields. To render real product cards in the frontend we capture the
raw structured products here, out-of-band from the chat text (see sinks.py).
"""

import json
import os
import re

from google.genai import types

from tools.sinks import product_sink, search_counter

_PRODUCT_TOOLS = {"kapruka_search_products", "kapruka_get_product"}

# --- Wearables-only filter ---------------------------------------------------
# Kapruka is a broad gift marketplace: a keyword search (e.g. "dress") leaks in
# books ("New Dress" the children's book → id BOOK00527), gift sets (a saree
# gift box → GIFTSET00572), etc. The per-product `category` field is useless
# (always "General"), but the real category is encoded in the product id PREFIX
# (CLOTHING06672, FASHION…, BOOK00527, GIFTSET00572) and echoed in the summary
# breadcrumb ("shop - Clothing, Saree, ..." / "... Fashion, Ladiesshoes ...").
# We keep only Clothing (garments) and Fashion (shoes, bags, belts, eyewear).
#
# Set RESTRICT_TO_CLOTHING=false in .env to disable (show all categories again).
RESTRICT_TO_CLOTHING = os.getenv("RESTRICT_TO_CLOTHING", "true").strip().lower() not in (
    "false", "0", "no",
)

# First-party id prefixes we keep (the category code leads the id).
_KEEP_PREFIXES = ("CLOTHING", "FASHION")
# Partner-central ids look like EF_PC_<CATCODE>... e.g. EF_PC_CLOT…, EF_PC_FASHION…
_PARTNER_ID_RE = re.compile(r"^EF[_-]?PC[_-]?([A-Z]+)", re.I)
_PARTNER_KEEP = ("CLOT", "FASHION")
# Category words that confirm scope when found in the summary breadcrumb.
_KEEP_WORDS = ("clothing", "fashion", "saree")


def _is_wearable(item: dict) -> bool:
    """True if the product is a garment or fashion accessory. Primary signal is
    the id prefix; falls back to the summary breadcrumb for odd partner ids."""
    if not isinstance(item, dict):
        return False
    pid = str(item.get("id") or "").upper()
    if pid.startswith(_KEEP_PREFIXES):
        return True
    m = _PARTNER_ID_RE.match(pid)
    if m and m.group(1).startswith(_PARTNER_KEEP):
        return True
    # Fallback: the category breadcrumb sits at the start of the summary
    # ("shop - Clothing, Saree, ..."). Check only that head, not the whole blurb.
    summary = str(item.get("summary") or "").lower()
    head = summary.split(" - ", 1)[-1][:60]
    return any(word in head for word in _KEEP_WORDS)

# Mirrors only the values the normalizer needs from the server's validators —
# not the full schema (the MCP server remains the source of truth that validates).
SUPPORTED_CURRENCIES = {"LKR", "USD", "GBP", "AUD", "CAD", "EUR"}
ALLOWED_SORTS = {"relevance", "price_asc", "price_desc", "newest", "bestseller"}
DEFAULT_CURRENCY = "LKR"
DEFAULT_LIMIT = 8
MAX_LIMIT = 12  # keep the product-card grid manageable


def _items_from_tool_response(tool_response) -> list[dict]:
    """Pull product dicts out of an MCP tool's JSON response."""
    try:
        content = tool_response.get("content") if isinstance(tool_response, dict) else None
        text = content[0].get("text") if content else None
        data = json.loads(text)
    except Exception:
        return []
    if isinstance(data, dict) and isinstance(data.get("results"), list):
        # The server sometimes returns the same product twice in one page —
        # dedupe by id so the card grid doesn't show doubles. Also drop any
        # non-clothing leak-ins (books, gift sets, …) when the filter is on.
        seen: set = set()
        items = []
        for item in data["results"]:
            if RESTRICT_TO_CLOTHING and not _is_wearable(item):
                continue
            key = item.get("id") if isinstance(item, dict) else None
            if key is None or key not in seen:
                seen.add(key)
                items.append(item)
        return items                    # search → list of products
    if isinstance(data, dict) and data.get("id"):
        return [data]                   # get_product → single product
    return []


def _normalize_search_params(params: dict) -> None:
    """Make search args satisfy the server's validators and keep the UI sane.

    The LLM chooses the *semantics* (query, filters, sort); this just enforces
    invariants so a slightly-off arg can't fail validation or flood the grid.
    Mutates `params` in place.
    """
    # Always JSON so we can extract images / structured fields for the cards.
    params["response_format"] = "json"

    # Currency: server requires uppercase + a supported value.
    currency = str(params.get("currency") or DEFAULT_CURRENCY).upper()
    params["currency"] = currency if currency in SUPPORTED_CURRENCIES else DEFAULT_CURRENCY

    # Limit: sane default, clamped — avoids over-fetch and huge card grids.
    try:
        limit = int(params.get("limit", DEFAULT_LIMIT))
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    params["limit"] = max(1, min(limit, MAX_LIMIT))

    # Sort: drop unknown values so the server falls back to relevance.
    if params.get("sort") not in ALLOWED_SORTS:
        params.pop("sort", None)

    # Never enumerate the catalog with stub/category-landing pages.
    params["include_stubs"] = False

    # Strip None/empty optionals so we never send invalid values.
    for key in ("category", "cursor", "min_price", "max_price"):
        if params.get(key) in (None, ""):
            params.pop(key, None)


# --- Session-scoped search cache --------------------------------------------
# The free public MCP tier is slow (often several seconds, 30s timeout). A
# shopper refining a query ("red shirt" -> "red shirt under 5000" -> back to
# "red shirt"), or the live voice model re-issuing the same search across turns,
# otherwise re-pays that round-trip every time. We cache a well-formed search
# response per session keyed by the result-affecting params, and return it from
# the before-tool callback to skip the MCP call. The after-tool callback still
# runs on a cache hit (verified in ADK's function flow), so product cards are
# captured from the cached response exactly as on a live call. Mirrors the
# delivery-check cache in checkout/agent.py.
_SEARCH_CACHE_KEY = "search_cache"
MAX_SEARCH_CACHE = 24
_SEARCH_KEY_FIELDS = ("q", "currency", "limit", "sort", "category", "min_price", "max_price")


def _search_cache_key(params: dict) -> str:
    keep = {k: params.get(k) for k in _SEARCH_KEY_FIELDS if params.get(k) not in (None, "")}
    return json.dumps(keep, sort_keys=True)


def _cached_search(tool_context, params: dict):
    """Return a cached search response for these params this session, or None."""
    cache = tool_context.state.get(_SEARCH_CACHE_KEY)
    if isinstance(cache, dict):
        return cache.get(_search_cache_key(params))
    return None


def _store_search(tool_context, params: dict, tool_response) -> None:
    """Cache a search response — but only if it's a well-formed results page, so a
    transient timeout/error is never cached (and re-served) for the session."""
    try:
        data = json.loads(tool_response["content"][0]["text"])
    except Exception:
        return
    if not isinstance(data, dict) or "results" not in data:
        return
    cache = dict(tool_context.state.get(_SEARCH_CACHE_KEY) or {})
    cache[_search_cache_key(params)] = tool_response
    if len(cache) > MAX_SEARCH_CACHE:
        cache = dict(list(cache.items())[-MAX_SEARCH_CACHE:])
    tool_context.state[_SEARCH_CACHE_KEY] = cache


def _fold_flat_args(args: dict) -> dict:
    """Gemini sometimes passes tool args flat instead of nested under `params`
    (the Kapruka MCP schema's single wrapper field) — the server then rejects
    the call with `params.<field>: Field required`. Fold stray top-level keys
    into params so either calling style validates server-side."""
    params = args.get("params")
    if not isinstance(params, dict):
        params = {}
    for key in [k for k in list(args) if k != "params"]:
        params.setdefault(key, args.pop(key))
    args["params"] = params
    return params


def force_json_before_tool(*, tool, args, tool_context):
    """Normalize/validate product-tool args before the call (see _normalize…)."""
    name = getattr(tool, "name", None)
    if name in _PRODUCT_TOOLS:
        params = _fold_flat_args(args)
        if name == "kapruka_search_products":
            _normalize_search_params(params)
            cached = _cached_search(tool_context, params)
            if cached is not None:
                return cached  # skip the slow MCP call; after-callback still captures
        else:  # kapruka_get_product — only JSON matters
            params["response_format"] = "json"
    return None  # proceed with the (mutated) args


MAX_SEEN_PRODUCTS = 60


def _remember_products(tool_context, items: list[dict]) -> None:
    """Persist captured products into session state so other agents — the
    fitting room's try_on in particular — can resolve product_id → image_url
    across turns. Copy-mutate-reassign so ADK records the state delta."""
    if not items:
        return
    seen = dict(tool_context.state.get("seen_products") or {})
    for item in items:
        pid = item.get("id")
        if pid:
            seen[str(pid)] = {
                "name": item.get("name"),
                "image_url": item.get("image_url"),
                "price": (item.get("price") or {}).get("amount"),
                "url": item.get("url"),
            }
    if len(seen) > MAX_SEEN_PRODUCTS:
        seen = dict(list(seen.items())[-MAX_SEEN_PRODUCTS:])
    tool_context.state["seen_products"] = seen


def capture_products_after_tool(*, tool, args, tool_context, tool_response):
    """Stash structured products into the per-request sink, if one is set."""
    name = getattr(tool, "name", None)
    if name in _PRODUCT_TOOLS:
        # Record that a product search actually executed this turn (even if it
        # returned nothing) so the voice paths can tell "searched, found nothing"
        # apart from "never searched" and avoid leaving a stale wall on screen.
        if name == "kapruka_search_products":
            counter = search_counter.get()
            if counter is not None:
                counter["n"] += 1
            params = args.get("params") if isinstance(args.get("params"), dict) else {}
            _store_search(tool_context, params, tool_response)
        items = _items_from_tool_response(tool_response)
        _remember_products(tool_context, items)
        sink = product_sink.get()
        if sink is not None:
            sink.extend(items)
    return None  # leave the tool response unchanged


# 4 outfit slots + a couple of broadened retries; past this the stylist must
# present what it has instead of hammering the rate-limited free tier.
MAX_STYLIST_SEARCHES = 6


def stylist_before_tool(*, tool, args, tool_context):
    """force_json_before_tool plus a hard, code-enforced per-turn search budget
    for the stylist (it composes multi-slot outfits, so left unchecked it can
    burn a dozen searches retrying sparse slots)."""
    if getattr(tool, "name", None) == "kapruka_search_products":
        counter = search_counter.get()
        if counter is not None:
            counter["n"] += 1
            if counter["n"] > MAX_STYLIST_SEARCHES:
                return {
                    "status": "error",
                    "message": "Search limit for this turn reached. STOP searching "
                               "now — present the best outfit you can from what you "
                               "already found and clearly say which slots you "
                               "couldn't fill.",
                }
    return force_json_before_tool(tool=tool, args=args, tool_context=tool_context)


def stylist_capture_after_tool(*, tool, args, tool_context, tool_response):
    """Like capture_products_after_tool, but tags each product with the outfit
    slot it was searched for (so the UI renders grouped outfit sections).

    The slot label comes from the search args: the category filter when used,
    otherwise the title-cased query — the stylist is instructed to keep `q` a
    clean slot-shaped phrase ("batik saree", "ladies heels")."""
    if getattr(tool, "name", None) not in _PRODUCT_TOOLS:
        return None
    items = _items_from_tool_response(tool_response)
    params = args.get("params") if isinstance(args.get("params"), dict) else {}
    if getattr(tool, "name", None) == "kapruka_search_products":
        _store_search(tool_context, params, tool_response)
    raw = params.get("category") or str(params.get("q") or "Outfit")
    # capitalize() per word, not str.title() — the latter mangles apostrophes
    # ("women's" -> "Women'S").
    group = " ".join(word.capitalize() for word in raw.split())
    for item in items:
        item["_group"] = group
    _remember_products(tool_context, items)
    _remember_styled(tool_context, items)
    sink = product_sink.get()
    if sink is not None:
        sink.extend(items)
    return None  # leave the tool response unchanged


# --- Fresh-outfit memory (after the demo stylist's InjectPreviousProducts /
# --- SaveSelectedProducts callbacks) -----------------------------------------
#
# Products surfaced by one styling turn are committed to state when the turn
# ends; on the next stylist turn they're re-injected as a reminder so "style
# me again" produces a fresh look instead of the same pieces. Split across two
# keys so the reminder never covers products found *earlier in the same turn*
# (the demo avoids this by parsing only the final response).

MAX_STYLED_MEMORY = 24

_STYLED_KEY = "styled_products"          # committed: previous turns' outfits
_STYLED_PENDING_KEY = "styled_pending"   # this turn's finds, not yet committed


def _remember_styled(tool_context, items: list[dict]) -> None:
    """Queue this turn's captured products for the cross-turn styled memory."""
    if not items:
        return
    pending = list(tool_context.state.get(_STYLED_PENDING_KEY) or [])
    known = {p.get("id") for p in pending}
    for item in items:
        pid = item.get("id")
        if pid and str(pid) not in known:
            known.add(str(pid))
            pending.append({"id": str(pid), "name": item.get("name")})
    tool_context.state[_STYLED_PENDING_KEY] = pending


def stylist_after_agent(callback_context):
    """AfterAgentCallback: fold this turn's pending finds into the committed
    styled-products memory once the stylist has finished responding."""
    pending = callback_context.state.get(_STYLED_PENDING_KEY) or []
    if not pending:
        return None
    styled = list(callback_context.state.get(_STYLED_KEY) or [])
    known = {p.get("id") for p in styled}
    styled.extend(p for p in pending if p.get("id") not in known)
    callback_context.state[_STYLED_KEY] = styled[-MAX_STYLED_MEMORY:]
    callback_context.state[_STYLED_PENDING_KEY] = []
    return None  # don't replace the agent's response


def stylist_before_model(callback_context, llm_request):
    """BeforeModelCallback: remind the model which products it already styled
    in earlier turns, so a repeat request composes a fresh outfit."""
    styled = callback_context.state.get(_STYLED_KEY) or []
    names = ", ".join(
        f"{p['name']} (id {p['id']})" for p in styled if p.get("name") and p.get("id")
    )
    if not names:
        return None
    reminder = (
        "REMINDER: you previously suggested these products: "
        f"{names}. Vary your search queries and pick DIFFERENT items this time "
        "so the user gets a fresh outfit. Do not reuse those product ids."
    )
    for content in reversed(llm_request.contents):
        if content.role == "user" and content.parts is not None:
            content.parts.append(types.Part.from_text(text=reminder))
            break
    return None  # proceed with the (mutated) request
