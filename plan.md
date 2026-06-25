# Plan: Convert Kapruka Concierge → Fashion Shopping Agent

Inspired by [gca-americas/fashion-app-demo](https://github.com/gca-americas/fashion-app-demo) (Fitting Room / Stylist / Catalog agents), but keeping the existing **Python stack**: google-adk 2.1.0, Gemini 2.5 Flash, FastAPI SSE server, single-file `static/index.html`. Cart + checkout stay as-is. The backend folder structure is reorganized to mirror the demo's `adk_backend/` layout (one package per agent + shared `tools/`).

## Verified facts (don't re-derive)

- Root `ecommerce_agent` delegates via `sub_agents=[catalog_agent, checkout_agent]` (currently agents.py:301) — transfer delegation, **not** AgentTool (CLAUDE.md is stale on this).
- Callbacks are keyword-only: `force_json_before_tool(*, tool, args, tool_context)` and `capture_products_after_tool(*, tool, args, tool_context, tool_response)` (currently tools.py:115, 128).
- `.venv` already has `google-genai 1.75.0` and `httpx 0.28.1` — **no new installs needed**. `GOOGLE_API_KEY` in `.env` is picked up by `genai.Client()` automatically.
- Demo backend structure (Go): `adk_backend/{rootagent, catalog, stylist, fittingroom, tools}/` + `main.go` + `example.env` + `run.sh`.
- Kapruka MCP has real fashion categories (usable as the `category` search filter — embed names **exactly**, two contain literal backticks):
  - **Clothing**: Kids Clothing, Mens Clothing, Saree, Saree Blouse, Sportswear, Unisex Clothing, Women Activewear, Womens Clothing, Clothing Gift Sets, Mens Activewear
  - **Fashion**: Belts, Eyewear Accessories, Gents Shoes, Handbags and Travel Accessories, Headwear, Kids Accessories, Kids Shoes, Ladies Shoes, Men`s Accessories, Umbrellas, Unisex Shoes, Women`s Accessories, Fashion Gift Sets

---

## Feature 0 — Restructure backend to mirror the demo (pure refactor, no behavior change) ✅ DONE

Target layout (Python mirror of `adk_backend/`):

```
kapruka/
├── main.py                    # FastAPI entrypoint (stays at root, like main.go)
├── rootagent/
│   ├── __init__.py            # re-exports root_agent
│   └── agent.py               # ecommerce_agent (root) — routing rules, wires sub_agents
├── catalog/
│   ├── __init__.py
│   └── agent.py               # catalog_agent + instructions
├── checkout/                  # extra vs demo — we keep cart/checkout
│   ├── __init__.py
│   └── agent.py               # checkout_agent + logistics_agent + checkout callbacks
├── stylist/                   # created in Feature 2
│   ├── __init__.py
│   └── agent.py
├── fittingroom/               # created in Feature 3
│   ├── __init__.py
│   ├── agent.py
│   └── tryon.py               # try_on tool implementation + photo store
├── tools/                     # shared, replaces tools.py
│   ├── __init__.py            # re-export the public names so imports stay short
│   ├── mcp.py                 # _toolset(), search_toolset, delivery_toolset, order_toolset
│   ├── callbacks.py           # _normalize_search_params, force_json_before_tool, capture_products_after_tool (+ stylist variant later)
│   ├── sinks.py               # product_sink (+ image_sink, current_session_id later)
│   ├── cart.py                # manage_cart, save_delivery_details, save_user_info, _order_fingerprint
│   └── persona.py             # shared VOICE / LANGUAGE blocks
├── static/index.html
├── kapruka_concierge/agent.py # adk web wrapper — now imports from rootagent
├── example.env                # template: GOOGLE_API_KEY=..., TRYON_MODEL=... (like the demo)
├── run.sh                     # .venv/bin/uvicorn main:app --reload (like the demo)
└── plan.md / CLAUDE.md
```

Steps:
1. Create the packages and **move** code out of `agents.py` / `tools.py` (split, don't rewrite — instructions and logic stay byte-identical in this step):
   - `tools.py` → `tools/mcp.py` (toolset builders), `tools/callbacks.py` (normalize + before/after callbacks), `tools/sinks.py` (`product_sink`), `tools/cart.py` (cart + save_* + checkout before/after callbacks can live here or in `checkout/agent.py` — put `before_checkout_tool`/`after_checkout_tool`/`_order_fingerprint` in `checkout/agent.py` since only checkout uses them).
   - `agents.py` → `catalog/agent.py` (catalog_agent), `checkout/agent.py` (checkout_agent + logistics_agent), `rootagent/agent.py` (ecommerce_agent), shared VOICE/LANGUAGE → `tools/persona.py`.
2. `tools/__init__.py` re-exports (`product_sink`, `search_toolset`, `manage_cart`, callbacks…) so agent modules use `from tools import ...`.
3. Update importers:
   - `main.py`: `from rootagent import root_agent`, `from tools.sinks import product_sink`.
   - `kapruka_concierge/agent.py`: keep the sys.path + dotenv bootstrap, change to `from rootagent.agent import ecommerce_agent as root_agent`.
   - `workflow.py`: either delete it or reduce to `from rootagent import root_agent` (keep as a one-line back-compat alias; delete if nothing imports it — grep first).
4. Delete the now-empty `agents.py` / `tools.py`. Add `example.env` and `run.sh`.
5. **Gotcha**: a top-level package named `tools/` shadows nothing in stdlib, but make sure the old `tools.py` is gone before creating `tools/` (a file and package with the same name can't coexist). Also `adk web` discovers every subfolder containing `agent.py` — `rootagent/`, `catalog/`, `checkout/` etc. would each show up as separate apps in the adk web dropdown. To keep discovery clean, EITHER name the per-agent module something other than `agent.py` (e.g. `catalog/catalog_agent.py`) OR accept multiple entries. Recommended: keep `agent.py` filenames (mirrors the demo) and treat the extra adk-web entries as harmless; `kapruka_concierge` remains the canonical entry.

**Verify**: `.venv/bin/uvicorn main:app` boots; a chat search returns cards exactly as before; checkout flow works; `.venv/bin/adk web` still serves `kapruka_concierge`. No instruction/behavior diffs.

---

## Feature 1 — Fashion-focused catalog agent (smallest functional change) ✅ DONE

**Files: `catalog/agent.py`, `static/index.html`.**

1. Rewrite `catalog_agent`'s instruction body (keep VOICE/LANGUAGE prefix from `tools/persona.py`, tools, callbacks, temperature unchanged):
   - Fashion-first identity (still able to handle any Kapruka product).
   - FIND step: steer the `category` filter to the exact Clothing/Fashion subcategory lists above.
   - CURATE step: speak fashion — fit, size availability (via `kapruka_get_product` variants), color, material, occasion suitability.
   - Keep cart wording and checkout hand-off untouched (no checkout regression).
2. Rebrand `static/index.html` header/greeting/placeholder ("Kapruka Fashion Stylist", "Find me a saree for a wedding under 15,000…"). Keep the dark theme.

**Verify**: "Find me a red saree under 10,000 LKR" → search chip, product cards, fashion-flavored prose. Then "mata saree ekak one" → Singlish reply. Then checkout regression: add to cart → checkout flow still works.

---

## Feature 2 — AI Stylist agent (outfits by occasion/style/budget) ✅ DONE

**Files: `tools/callbacks.py`, new `stylist/agent.py`, `rootagent/agent.py`, `main.py`, `static/index.html`.**

1. **`tools/callbacks.py`**:
   - `stylist_capture_after_tool(*, tool, args, tool_context, tool_response)` — same parse logic as `capture_products_after_tool` (refactor to share), but tags each item `it["_group"] = (args.get("params") or {}).get("category") or "Outfit"` before appending to `product_sink`. Used **only** by the stylist so normal searches keep today's untagged behavior.
2. **New `stylist/agent.py`** — `stylist_agent`:
   - `model="gemini-2.5-flash"`, temp 0.8, `tools=[search_toolset, manage_cart]`, `before_tool_callback=force_json_before_tool`, `after_tool_callback=stylist_capture_after_tool`, VOICE/LANGUAGE prefix.
   - Instructions: infer occasion/style/budget/gender-presentation (ask at most ONE clarifying question); plan 3–4 outfit slots (main garment / shoes / bag / accessory) mapped to exact category names; ONE `kapruka_search_products` per slot with `category=<exact>`, `limit=4`, `max_price` from a budget split (~45% main, 25% shoes, 20% bag, 10% accessory); **hard cap 4 searches/turn** (free public tier rate-limits) — if a slot is empty, broaden once (drop max_price) then skip, never retry-loop; present the outfit as a story with total-vs-budget; offer "add the whole outfit to cart" and try-on hand-off.
3. **`rootagent/agent.py`**: `sub_agents=[catalog_agent, stylist_agent, checkout_agent]` + routing rule (outfit / "what should I wear" / occasion dressing → stylist). **Keep root persona-free** (documented PROHIBITED_CONTENT regression).
4. **`main.py`**: `_card()` gains `"group": item.get("_group")` (null for normal searches).
5. **`static/index.html`**: track `currentGroup` alongside `currentGrid`; when `item.group` changes, close the grid, append an accent-colored label ("👗 Womens Clothing"), start a new grid. Ungrouped products behave exactly as today.

**Verify**: "Style me an outfit for a beach wedding, budget 25,000" → 3–4 search chips, cards under labeled groups, total-vs-budget summary, add-all-to-cart works.

---

## Feature 3 — Virtual try-on (Fitting Room agent) ✅ DONE

**Files: `tools/callbacks.py`, `tools/sinks.py`, new `fittingroom/tryon.py` + `fittingroom/agent.py`, `rootagent/agent.py`, `main.py`, `static/index.html`.**

1. **`tools/callbacks.py`** — `_remember_products(tool_context, items)`: persist captured products into `state["seen_products"]` (dict `id → {name, image_url, price, url}`, capped ~60, **copy-mutate-reassign** like the cart or deltas won't persist). Call from both after-tool callbacks. This lets `try_on` resolve `product_id → image_url` across turns.
2. **`tools/sinks.py`** — add alongside `product_sink`:
   ```python
   image_sink: ContextVar[list | None]              # mirrors product_sink pattern
   current_session_id: ContextVar[str | None]
   ```
3. **New `fittingroom/tryon.py`** (must NOT import FastAPI, so `adk web` still works):
   ```python
   USER_PHOTOS: dict[str, tuple[bytes, str]] = {}   # session_id -> (bytes, mime); in-memory, cleared by --reload (fine for demo)
   TRYON_MODEL = os.getenv("TRYON_MODEL", "gemini-2.5-flash-image")
   GENERATED_DIR = static/generated                 # mkdir(parents=True, exist_ok=True) at import
   ```
   `async def try_on(tool_context: ToolContext, product_id: str) -> dict` (async keeps it in the request asyncio context so contextvars work; only ever **append/read** contextvars, never `.set()`):
   - No photo for `current_session_id.get()` → `{"status": "no_photo", "message": "Ask the user to upload a photo using the camera button first."}`
   - Garment not in `state["seen_products"]` → `{"status": "unknown_product", "message": "Look it up with kapruka_get_product first, then retry."}`
   - Download `image_url` via `httpx.AsyncClient` (10s timeout, browser User-Agent — Kapruka CDN may 403 bare clients; non-200 → error status, never raise).
   - `await genai.Client().aio.models.generate_content(model=TRYON_MODEL, contents=[Part.from_bytes(user_photo), Part.from_bytes(garment), "<prompt: photorealistic, keep face/pose/background, replace only the clothing>"])`
   - Check `candidates[0].content.parts` for `inline_data` — model can return text-only or be safety-blocked for real-person photos → `{"status": "generation_failed", ...}`; catch 429 → "fitting room is busy".
   - Save PNG to `static/generated/{uuid}.png`; append `{"url": "/static/generated/...", "product_id", "product_name"}` to `image_sink`; return `{"status": "ok", "image_url", "product_name"}`.
4. **New `fittingroom/agent.py`** — `fitting_room_agent`: temp 0.6, `tools=[try_on, search_toolset, manage_cart]`, standard callbacks (`capture_products_after_tool` populates `seen_products`). Instructions per status: `no_photo` → warmly ask for upload; `unknown_product` → `kapruka_get_product` then retry; success → one-line styling comment + add-to-cart offer; **never claim an image was generated on error**.
5. **`rootagent/agent.py`**: add `fitting_room_agent` to `sub_agents` + routing rule ("try on" / "Try on product <id>" → fitting_room).
6. **`main.py`**:
   - `POST /upload_photo` — `Form(session_id)` + `UploadFile`; reject non-jpeg/png/webp or >8 MB; store in `USER_PHOTOS[session_id]`.
   - In `/chat`'s `event_stream()`: alongside `product_sink.set(...)`, do `current_session_id.set(request.session_id)` and `image_sink.set([])`; add a `drain_images()` twin of `drain_products()` emitting `{"type": "tryon_image", "url", "product_id", "product_name"}` at the same drain points (per-event + post-loop catch-up).
7. **`static/index.html`**:
   - Camera button + hidden `<input type="file" accept="image/*">` in footer → `fetch("/upload_photo", FormData with session_id)` → status chip + small thumbnail.
   - "Try on" button per card in `addProduct()` — attach via `addEventListener` + `dataset.id`/`dataset.name` (no inline-onclick name interpolation); click sets `input.value = "Try on product ${id} (${name})"` and `form.requestSubmit()`.
   - Handle `{"type":"tryon_image"}` → bot-styled bubble with `<img>` (~320px, rounded, click-to-open) + caption "You, wearing <product_name>"; reset `currentGrid`.
   - Tool chip special-case `try_on` → "Creating your try-on look… (can take ~20s)".

**Verify**: (a) click Try on **before** uploading → agent asks for photo, no crash; (b) upload JPEG → chip + thumbnail, `/upload_photo` 200; (c) click Try on → `try_on` chip → image bubble, file exists in `static/generated/`; (d) fresh session "try on product 12345" → agent recovers via `kapruka_get_product` or explains gracefully; (e) `.venv/bin/adk web` still discovers `kapruka_concierge`.

---

## Final — CLAUDE.md update ✅ DONE

Rewrite for the new layout: per-agent packages (`rootagent/`, `catalog/`, `stylist/`, `fittingroom/`, `checkout/`) + shared `tools/` package (mcp, callbacks, sinks, cart, persona) mirroring the fashion-app-demo's adk_backend; fix the stale `concierge_agent`/AgentTool description → `ecommerce_agent` + `sub_agents` transfer with four specialists + routing; document `fittingroom/tryon.py` (USER_PHOTOS, image_sink/current_session_id mirroring product_sink, gemini-2.5-flash-image, per-image billing); `seen_products` state cache and why `try_on` depends on it; full SSE contract incl. `tryon_image` frame + `group` card field; `/upload_photo`; optional `TRYON_MODEL` env var; `example.env`/`run.sh`; `static/generated/` is runtime output; rule "card fields or SSE frames change → update `_card()` AND index.html"; convention update: "agent logic lives in each agent package's `agent.py`; shared toolsets/callbacks in `tools/`".

## SSE frame contract after all features

- `{"type":"tool","name"}` — unchanged (also fires for `try_on`)
- `{"type":"product","item":{id,name,summary,price,currency,image_url,in_stock,stock_level,url,group}}` — `group` new, null unless stylist
- `{"type":"tryon_image","url","product_id","product_name"}` — new
- `{"type":"text"|"error"|"done"}` — unchanged

## Risks

- Restructure: old `tools.py` must be deleted before creating the `tools/` package (same import name); `adk web` will list each per-agent package containing an `agent.py` — `kapruka_concierge` stays the canonical entry.
- Image model: 10–30s latency, low free-tier quota, may safety-block real-person photos — always check `inline_data`, return structured errors.
- Stylist multi-search vs Kapruka free-tier rate limits — hard cap 4 searches/turn, skip slots instead of retrying.
- New callbacks must match keyword-only signatures exactly or ADK raises at call time.
- `seen_products`/cart state need copy-mutate-reassign or deltas won't persist.
- `USER_PHOTOS` is cleared by `--reload` mid-session — acceptable for demo.
