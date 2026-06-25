# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Sri Lankan **fashion shopping agent** built on **Google ADK** (`google-adk` 2.1.0, Python 3.12), modeled on Google's [fashion-app-demo](https://github.com/gca-americas/fashion-app-demo) (catalog / stylist / fitting-room agents) but on a Python + FastAPI stack. LLM agents (Gemini 2.5 Flash) shop Kapruka's **remote MCP server** (`https://mcp.kapruka.com/mcp`) for products and delivery; a **virtual try-on** renders the user's uploaded photo wearing a chosen garment via `gemini-2.5-flash-image`. Cart and real order placement (checkout link) are included.

## Running

Requires `GOOGLE_API_KEY` in `.env` (template: `example.env`; loaded by both entrypoints via `python-dotenv`). Optional env: `TRYON_MODEL` (defaults to `gemini-2.5-flash-image`). The virtualenv at `.venv` holds all dependencies — there is no `requirements.txt`/`pyproject.toml`, so install new packages into `.venv` and they won't be pinned anywhere.

```bash
./run.sh                              # the primary app: chat UI at /, SSE + product cards
.venv/bin/uvicorn main:app --reload   # same thing, by hand
.venv/bin/adk web                     # ADK dev UI — use the kapruka_concierge app
```

There are no tests, linters, or build steps configured. Verification is manual: run the server and exercise `/chat` (see SSE contract below). Live tests cost Gemini quota — keep them few, and never let an agent retry-loop a failing tool.

## Architecture

One package per agent plus a shared `tools/` package (mirrors the demo's `adk_backend/` layout). `main.py` is the FastAPI entrypoint at the root.

**Agent graph — `sub_agents` transfer delegation (not AgentTool):**
- `rootagent/agent.py` — `ecommerce_agent`, a thin router. It delegates via `transfer_to_agent` to exactly one specialist per turn. **It deliberately carries no persona** — adding the VOICE block to the root reliably trips Gemini's `PROHIBITED_CONTENT` filter (see Gotchas).
- `catalog/agent.py` — `catalog_agent`: fashion-first product discovery + cart. Carries the full VOICE/LANGUAGE persona from `tools/persona.py`.
- `stylist/agent.py` — `stylist_agent`: composes one coordinated outfit (3–4 slots: garment / shoes / bag / accessory) with a budget split, one search per slot. **Instruction is deliberately compact and persona-free** (content filter).
- `fittingroom/agent.py` — `fitting_room_agent`: drives the `try_on` tool and handles its status codes. Also compact/persona-free.
- `checkout/agent.py` — `checkout_agent` (collects buyer + delivery details, places the order — the order args are assembled **entirely from session state** by `before_checkout_tool`, never by the LLM, with an idempotency fingerprint against duplicate orders) and `logistics_agent` (delivery feasibility).
- `tracking/agent.py` — `tracking_agent`: the post-sale "where is my order?" step. Looks up an existing order by its **order number** (from the confirmation email — NOT the `order_ref` that `kapruka_create_order` returns) via `kapruka_track_order`, and narrates status + delivery progress. Compact/persona-free (content filter). Demo/test order number: `VPAY827982BA`.

`kapruka_concierge/agent.py` is the `adk web` wrapper (sys.path + dotenv bootstrap, re-exports the root agent). `adk web` also lists the other packages because they contain an `agent.py`; that's harmless — `kapruka_concierge` is the canonical entry.

**Shared `tools/` package** (public names re-exported in `tools/__init__.py`):
- `mcp.py` — `_toolset(*names)` builds an `McpToolset` over the remote streamable-HTTP endpoint, filtered to named tools (30s timeout — the free public tier is slow/rate-limited). Purpose-built subsets: `search_toolset`, `delivery_toolset`, `order_toolset`, `tracking_toolset` (`kapruka_track_order`).
- `callbacks.py` — before/after tool callbacks (see capture pipeline below).
- `sinks.py` — per-request contextvars: `product_sink`, `image_sink`, `search_counter`, `current_session_id`. `main.py` sets all four at the start of each `/chat` request; contextvars carry them through the agent nesting into tool callbacks. **Only mutate the held objects in place (append/increment) — a `.set()` inside a tool won't propagate across context copies.**
- `cart.py` — `manage_cart`: cart is `state["cart"]`, always **copy → modify → reassign** so ADK records the delta; totals are computed, never stored.
- `persona.py` — shared VOICE / LANGUAGE blocks (Sinhala/Tamil/English/Singlish/Tanglish mirroring).

**Product capture pipeline** — how the frontend renders real cards although the LLM speaks prose:
- `force_json_before_tool` first calls `_fold_flat_args`: **Gemini often passes tool args flat instead of nested under the schema's `params` wrapper**, which the server rejects (`params.q: Field required`) — folding stray top-level keys into `params` fixes both calling styles. Then `_normalize_search_params` forces `response_format="json"` and clamps currency/limit/sort. `before_checkout_tool` applies the same folding to delivery tools.
- `capture_products_after_tool` parses products out of the MCP JSON (deduped by id), appends them to `product_sink`, and writes them into `state["seen_products"]` (`_remember_products`, capped at 60, copy-mutate-reassign) so `try_on` can resolve `product_id → image_url` in later turns.
- `stylist_capture_after_tool` additionally tags each item with `_group` (the outfit slot, derived from the search query) → the card's `group` field → grouped sections in the UI.
- `stylist_before_tool` enforces a **hard 6-searches-per-turn budget** via `search_counter` — instruction-level caps alone get ignored when the model keeps seeing empty results.
- `capture_tracking_after_tool` mirrors the same pattern for tracking: it parses the `kapruka_track_order` JSON, shapes it via `_tracking_card` (sanitizing recipient HTML artifacts like a stray `<BR`), and appends one dict to `tracking_sink` → the `tracking` SSE frame. `before_tracking_tool` folds flat args + forces JSON.

**Virtual try-on (`fittingroom/tryon.py`)** — `async def try_on(tool_context, product_id)`: user photo (from `USER_PHOTOS`, keyed by `current_session_id`) + garment image (from `seen_products`, downloaded with a browser User-Agent — the CDN rejects bare clients) → `gemini-2.5-flash-image` → PNG saved to `static/generated/` (runtime output, served statically) → appended to `image_sink`. Returns structured statuses the agent instruction handles: `ok`, `no_photo`, `unknown_product`, `garment_image_failed`, `generation_failed`. `USER_PHOTOS` is in-memory by design (cleared on `--reload`; raw user photos are never written under `/static`). **This module must not import FastAPI** — `adk web` imports the agent graph. Image generation takes 10–30s and bills per image.

**Streaming server (`main.py`)** — one process-wide `InMemoryRunner` (sessions in memory, tracked in `_known_sessions`). Endpoints: `GET /` (UI), `POST /chat` (SSE), `POST /upload_photo` (multipart: `session_id` + `photo`; JPEG/PNG/WebP, 8 MB cap → `USER_PHOTOS`). The `/chat` stream drains the sinks **before** the prose. SSE frames:

| frame | shape |
|---|---|
| `tool` | `{"type":"tool","name"}` — in-progress chip (UI special-cases `try_on`) |
| `product` | `{"type":"product","item":{id,name,summary,price,currency,image_url,in_stock,stock_level,url,group}}` — `group` is null except for stylist results |
| `tryon_image` | `{"type":"tryon_image","url","product_id","product_name"}` |
| `order` | `{"type":"order","order_ref","checkout_url","grand_total","currency","expires_at"}` — placed-order Pay link (checkout) |
| `tracking` | `{"type":"tracking","order_number","status","status_display","delivery_date","amount","currency","recipient_name","recipient_city","progress":[{step,timestamp}],…}` — order-status + delivery-timeline card |
| `text` | deltas when `event.partial`, else final aggregate (guarded against double-send) |
| `error` / `done` | terminal frames |

`static/index.html` is the single-file frontend: SSE parser, product grids with per-card "Try on" buttons (these submit `Try on product <id> (<name>)` through the normal chat path; the root routes it to the fitting room), outfit group labels, the 📷 upload button, try-on image bubbles, and order-tracking status/timeline cards (`addTracking`).

## Conventions & gotchas

- Agent logic lives in each package's `agent.py`; shared toolsets/callbacks/sinks in `tools/`. `rootagent`, `kapruka_concierge` and `workflow`-era wrappers contain no logic.
- If you change card fields or SSE frames, update **both** `_card()` in `main.py` and the rendering in `static/index.html`.
- **Gemini content filter:** long persona + long instruction on a sub-agent deterministically triggers `PROHIBITED_CONTENT` (empty turn, no error frame — the event has `error_code=PROHIBITED_CONTENT`). It is cumulative, not one phrase. Keep `stylist`/`fittingroom`/root instructions short; only catalog/checkout carry the full persona.
- The Kapruka MCP server is the source of truth for arg validation; `_normalize_search_params` only mirrors the values it needs. The search `category` filter has **patchy coverage** (e.g. "Saree" matches nothing while bare `q="saree"` works) — agents are instructed to prefer keyword queries and drop `category` on empty results.
- The search index also returns duplicates and fuzzy mismatches; dedupe-by-id happens in `_items_from_tool_response`.
- Free-tier rate limits cut both ways (Kapruka MCP and Gemini): keep per-turn tool calls bounded (stylist budget, "stop after two errors" instruction) and keep manual verification chats few.
