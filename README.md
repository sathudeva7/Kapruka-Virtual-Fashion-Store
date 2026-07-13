# Kapruka Fashion Shopping Agent

A Sri Lankan **fashion shopping assistant** built on [Google ADK](https://github.com/google/adk-python). A team of LLM agents (Gemini 2.5 Flash) shops Kapruka's remote MCP server for real products and delivery, renders a **virtual try-on** of the user's photo wearing a chosen garment (`gemini-2.5-flash-image`), and places real orders via a checkout link. Multilingual (Sinhala / Tamil / English + romanized mixes), with text chat, streaming product cards, and realtime voice.

> Modeled on Google's [fashion-app-demo](https://github.com/gca-americas/fashion-app-demo) (catalog / stylist / fitting-room agents), reimplemented on a Python + FastAPI stack.

---

## Demo
<img width="1680" height="807" alt="Screenshot 2026-07-13 at 13 39 16" src="https://github.com/user-attachments/assets/9503b1e7-9b70-4d21-b2e2-d5c067836b3a" />
<img width="1680" height="807" alt="Screenshot 2026-07-13 at 13 43 35" src="https://github.com/user-attachments/assets/dd284699-97e5-4129-a394-d8e0893c10af" />
<img width="1680" height="807" alt="Screenshot 2026-07-13 at 13 45 01" src="https://github.com/user-attachments/assets/eece4e58-c9be-45db-980e-d3ba2cfd4c64" />



- **Live demo:** https://13-206-93-47.sslip.io/
- **Video walkthrough:** https://www.loom.com/share/6bd7f897f5ac451ba90c7f7b1c7ed93f

---

## Features

- **Conversational shopping** over Kapruka's live catalog (search, browse, cart).
- **Outfit styling** — composes a coordinated look across garment / shoes / bag / accessory slots with a budget split.
- **Virtual try-on** — uploads a user photo + garment image to an image model and returns a photoreal image of the user wearing the item (single item or full outfit).
- **Real checkout** — collects buyer/delivery details, verifies delivery feasibility, places the order, and returns a time-limited payment link (with duplicate-order protection).
- **Voice** — realtime English/Tamil via Gemini Live, plus a Sinhala voice path via Azure Speech.
- **Two frontends** — a 3D Next.js UI (default) and a legacy single-file SSE chat UI.

---

## Architecture

### Agent graph (`sub_agents` transfer delegation)

A thin router delegates to exactly one specialist per turn via `transfer_to_agent`:

| Agent | Package | Responsibility |
|---|---|---|
| `ecommerce_agent` | `rootagent/` | Router. Persona-free by design (a long persona on the root trips Gemini's content filter). |
| `catalog_agent` | `catalog/` | Fashion-first product discovery + cart. Carries the full VOICE/LANGUAGE persona. |
| `stylist_agent` | `stylist/` | Composes one coordinated outfit (3–4 slots), one search per slot, hard per-turn search budget. |
| `fitting_room_agent` | `fittingroom/` | Drives the `try_on` tool and its status codes. |
| `checkout_agent` / `logistics_agent` | `checkout/` | Places orders (assembled entirely from session state, with an idempotency fingerprint) / checks delivery feasibility. |

`kapruka_concierge/` is the `adk web` wrapper that re-exports the root agent.

### Shared `tools/` package

- `mcp.py` — builds filtered `McpToolset`s over the remote streamable-HTTP MCP endpoint (`https://mcp.kapruka.com/mcp`).
- `callbacks.py` — before/after tool callbacks: arg normalization (folds flat args into the schema's `params` wrapper, forces JSON), product capture, stylist grouping, search-budget enforcement.
- `sinks.py` — per-request `contextvars` (`product_sink`, `image_sink`, `search_counter`, `current_session_id`) that carry capture state through the agent nesting into callbacks.
- `cart.py` — `manage_cart`; cart lives in `state["cart"]` (copy → modify → reassign so ADK records the delta).
- `persona.py` — shared VOICE / LANGUAGE blocks.
- `order_api.py`, `photostore.py`, `azure_speech.py` — order placement, in-memory user-photo store, and the Sinhala STT/TTS bridge.

### Try-on (`fittingroom/tryon.py`)

`try_on(tool_context, product_id)`: user photo (in-memory, keyed by session) + garment image (downloaded with a browser User-Agent — the CDN rejects bare clients) → image model → PNG saved to `static/generated/` → streamed to the UI. Backend is `gemini-2.5-flash-image` by default; an optional Grok (xAI) backend can be enabled for single-item try-on. Strict identity-preserving prompt (only the clothes change). **Does not import FastAPI** (the agent graph is imported by `adk web`).

### Server (`main.py`)

A single process-wide `InMemoryRunner` (sessions, cart, and uploaded photos live in-process — **deploy one instance**). The `/chat` SSE stream drains the product/image sinks before the prose.

---

## Tech stack

- **Python 3.12**, FastAPI + Uvicorn, `google-adk`, `google-genai`, `mcp`
- **Gemini 2.5 Flash** (agents), `gemini-2.5-flash-image` (try-on), Gemini Live (voice)
- **Azure Cognitive Services Speech** (Sinhala voice, optional)
- **Next.js 16 / React 19 / three.js / @react-three/fiber** (3D frontend), Tailwind CSS
- Docker (multi-stage: Next static export + Python runtime)

---

## Project layout

```
.
├── main.py                # FastAPI entrypoint (chat SSE, voice WS, direct endpoints)
├── rootagent/             # router agent
├── catalog/ stylist/ fittingroom/ checkout/   # specialist agents
├── kapruka_concierge/     # `adk web` wrapper
├── liveagent/             # realtime voice agent + bridge
├── tools/                 # shared toolsets, callbacks, sinks, cart, persona
├── static/                # legacy single-file chat UI + generated/ (runtime try-on PNGs)
├── frontend/              # Next.js 3D frontend (static-exported in prod)
├── requirements.txt
├── Dockerfile
├── run.sh
└── example.env
```

---

## Getting started

### Prerequisites

- Python 3.12
- A **Google AI Studio API key** (`GOOGLE_API_KEY`)
- Node.js 20+ (only if you want to run/build the `frontend/` Next.js app)
- *(Optional)* Azure Speech resource for the Sinhala voice path; xAI key for the Grok try-on backend

### 1. Backend setup

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp example.env .env        # then edit .env and add your GOOGLE_API_KEY
```

### 2. Configure environment

Copy `example.env` to `.env` and fill in at minimum:

| Variable | Required | Purpose |
|---|---|---|
| `GOOGLE_API_KEY` | ✅ | Gemini agents + try-on image model |
| `TRYON_MODEL` | optional | Override the try-on image model (default `gemini-2.5-flash-image`) |
| `TRYON_PROVIDER` / `XAI_API_KEY` | optional | Switch try-on to the Grok backend |
| `RESTRICT_TO_CLOTHING` | optional | Restrict results to wearables (default on) |
| `LIVE_MODEL` | optional | Gemini Live model for English/Tamil voice |
| `AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION` / `AZURE_TTS_VOICE` / `AZURE_STT_LANG` | optional | Sinhala voice path |

See `example.env` for the full annotated list.

### 3. Run

```bash
./run.sh                              # chat UI + SSE at http://127.0.0.1:8000
.venv/bin/uvicorn main:app --reload   # same thing, by hand
.venv/bin/adk web                     # ADK dev UI — use the `kapruka_concierge` app
```

### 4. Frontend (optional, for local dev of the 3D UI)

```bash
cd frontend
npm install
npm run dev        # Next dev server (proxies API to the backend)
npm run build      # production build; `npm run export` emits ./out for same-origin serving
```

In production the frontend is **static-exported** and served at `/` by the same Uvicorn process (see the Dockerfile).

---

## HTTP / WebSocket API

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | 3D frontend (static export) |
| `GET` | `/legacy` | Legacy single-file SSE chat UI (`static/index.html`) |
| `GET` | `/healthz` | Health check |
| `POST` | `/chat` | Chat (Server-Sent Events: `tool`, `product`, `tryon_image`, `text`, `error`, `done` frames) |
| `POST` | `/upload_photo` | Multipart photo upload (JPEG/PNG/WebP, 8 MB cap) → in-memory photo store |
| `POST` | `/try_on` | Direct (non-AI) try-on for the 3D frontend |
| `POST` | `/cart`, `/cart/remove`, `GET /cart` | Direct cart operations |
| `POST` | `/checkout_details` | Submit buyer/delivery details |
| `GET` | `/img` | Image proxy |
| `WS` | `/live` | Realtime English/Tamil voice (Gemini Live) |
| `WS` | `/live_sinhala` | Realtime Sinhala voice (Azure) |
| `POST` | `/voice_sinhala` | Turn-based Sinhala voice |

---

## Docker

```bash
docker build -t kapruka-agent .
docker run -p 8000:8000 --env-file .env kapruka-agent
```

The multi-stage build compiles the Next.js static export, then serves it plus the FastAPI app from a single Uvicorn process. **Run a single instance** — sessions, cart, and uploaded photos are in-process.

---

## Notes & gotchas

- **Content filter:** a long persona *plus* long instruction on a sub-agent deterministically trips Gemini's `PROHIBITED_CONTENT` filter (empty turn, no error frame). Only `catalog`/`checkout` carry the full persona; `root`/`stylist`/`fittingroom` are kept short.
- **MCP coverage:** the Kapruka MCP server is the source of truth for arg validation. The `category` filter has patchy coverage — agents prefer keyword queries and drop `category` on empty results. The index returns duplicates/fuzzy matches (deduped by id in capture).
- **Rate limits:** the public MCP tier and free Gemini tier both rate-limit; per-turn tool calls are bounded (stylist search budget, "stop after two errors"). Keep manual verification runs few — live runs cost Gemini quota.
- **Privacy:** uploaded user photos live only in memory for the session and are never written under `static/`.
- There are no automated tests; verification is manual (run the server and exercise `/chat`).
