import asyncio
import base64
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()  # read GOOGLE_API_KEY (and friends) from .env

from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from google.adk.runners import InMemoryRunner
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.genai import types

from rootagent import root_agent
from liveagent import live_concierge
from liveagent.bridge import (
    cart_add_item,
    cart_remove_item,
    cart_view,
    save_checkout_details,
)
from tools import product_sink
from tools.sinks import (
    search_counter,
    image_sink,
    current_session_id,
    order_sink,
    tracking_sink,
    live_request_queue_var,
)
from tools import azure_speech
from tools.callbacks import _tracking_card
from tools.order_api import track_order_via_mcp
from fittingroom.tryon import generate_tryon
from tools.photostore import photo_store

app = FastAPI()

STATIC_DIR = Path(__file__).parent / "static"
FRONTEND_OUT = Path(__file__).parent / "frontend" / "out"  # Next static export (prod)
APP_NAME = "kapruka"
USER_ID = "web-user"

# Product images come from the Kapruka CDN, which (a) rejects bare clients and
# (b) sends no CORS headers — a browser WebGL texture load would fail. The 3D
# frontend routes every product image through this proxy so it arrives same-
# origin with a browser User-Agent. See frontend/src/lib/api.ts imgUrl().
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# One runner for the whole process. It executes the workflow graph and keeps
# session state in memory.
#  - `runner` (transfer graph) serves the text `/chat` and the turn-based Sinhala
#    voice path (`/voice_sinhala`).
#  - `live_runner` (AgentTool orchestration) serves the realtime English/Tamil
#    voice path (`/live`). It needs a separate runner because transfer_to_agent
#    doesn't work under run_live. Voice and text therefore have separate session
#    state (separate carts) — acceptable for Phase 1.
runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
live_runner = InMemoryRunner(agent=live_concierge, app_name=APP_NAME)
_known_sessions: set[str] = set()
_live_known_sessions: set[str] = set()

# Realtime voice languages → output voice locale for the Live API speech config.
# (Sinhala is NOT here — Gemini Live can't speak it; it uses the Azure path.)
LANG_TO_LOCALE = {"en": "en-US", "ta": "ta-IN"}


class ChatRequest(BaseModel):
    message: str
    session_id: str


class TryOnProduct(BaseModel):
    id: str | None = None
    name: str | None = None
    image_url: str


class TryOnRequest(BaseModel):
    session_id: str
    products: list[TryOnProduct]


class CartAddRequest(BaseModel):
    session_id: str
    product_id: str
    name: str
    category: str = ""
    price: int = 0
    quantity: int = 1


class CartRemoveRequest(BaseModel):
    session_id: str
    product_id: str


class CheckoutDetailsRequest(BaseModel):
    session_id: str
    name: str = ""
    phone: str = ""
    address: str = ""
    city: str = ""
    date: str = ""
    instructions: str = ""


class TrackOrderRequest(BaseModel):
    order_number: str


@app.get("/healthz")
async def healthz():
    """Liveness probe for the load balancer / orchestrator. Stays cheap on
    purpose: returns 200 without touching Gemini, Azure or the MCP catalog, so a
    transient upstream outage never marks the container unhealthy."""
    return {"status": "ok"}


@app.get("/legacy")
async def legacy_index():
    """The original single-file chat UI (kept as a fallback)."""
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/try_on")
async def try_on_endpoint(req: TryOnRequest):
    """Direct virtual try-on (no LLM): uploaded photo + garment image(s) →
    generated image. Returns {status, image_url, product_name}. The photo must
    have been sent to /upload_photo for this session first."""
    garments = [
        {"id": p.id, "name": p.name, "image_url": p.image_url} for p in req.products
    ]
    return await generate_tryon(req.session_id, garments)


@app.post("/cart")
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
    )


@app.post("/cart/remove")
async def cart_remove_endpoint(req: CartRemoveRequest):
    """Remove a line from the live-session cart for the 3D UI's trolley."""
    if not req.product_id:
        return JSONResponse(
            {"status": "error", "message": "product_id is required."},
            status_code=400,
        )
    return await cart_remove_item(req.session_id, req.product_id)


@app.get("/cart")
async def cart_view_endpoint(session_id: str):
    """Read the current live-session cart for the 3D UI's trolley widget."""
    return await cart_view(session_id)


@app.post("/checkout_details")
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


@app.post("/track_order")
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


@app.get("/img")
async def img_proxy(u: str):
    """Same-origin image proxy for product photos (see _BROWSER_UA note)."""
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https"):
        return JSONResponse({"error": "invalid url"}, status_code=400)
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(u, headers={"User-Agent": _BROWSER_UA})
    except Exception:
        return Response(status_code=502)
    ctype = r.headers.get("content-type", "")
    if r.status_code != 200 or not ctype.startswith("image/"):
        return Response(status_code=404)
    return Response(
        content=r.content,
        media_type=ctype,
        headers={"Cache-Control": "public, max-age=3600"},
    )


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_PHOTO_BYTES = 8 * 1024 * 1024


@app.post("/upload_photo")
async def upload_photo(session_id: str = Form(...), photo: UploadFile = File(...)):
    """Store the user's try-on photo for this session (via photo_store: in-memory
    by default, S3 in prod — see tools/photostore.py)."""
    content_type = (photo.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_PHOTO_TYPES:
        return JSONResponse(
            {"status": "error", "message": "Please upload a JPEG, PNG or WebP photo."},
            status_code=415,
        )
    data = await photo.read()
    if not data:
        return JSONResponse(
            {"status": "error", "message": "The uploaded file is empty."}, status_code=400
        )
    if len(data) > MAX_PHOTO_BYTES:
        return JSONResponse(
            {"status": "error", "message": "Photo is too large (max 8 MB)."},
            status_code=413,
        )
    # Off-thread: the S3 backend does a blocking network PUT (memory is instant).
    await asyncio.to_thread(photo_store.put, session_id, data, content_type)
    return {"status": "ok"}


def _sse(payload: dict) -> str:
    """Encode one event as an SSE frame with a JSON body."""
    return f"data: {json.dumps(payload)}\n\n"


def _friendly_error(detail: str) -> str:
    """Map a raw backend error to a calm, actionable message — or "" if we don't
    recognise it (caller falls back to the raw detail).

    Covers the infra failures that otherwise reach the user as scary stack-y
    text: the Kapruka MCP catalog being unreachable (which strands the agent
    with no search tool, so Gemini hallucinates a tool name → "Tool ... not
    found"), Gemini overload (503), and free-tier rate limits (429).
    """
    d = detail.lower()
    if "not found" in d and "available tools" in d:
        # The MCP toolset failed to load, so a search tool the model expected
        # isn't registered. The catalog, not the model, is the real problem.
        return ("The Kapruka catalog is temporarily unavailable, so I couldn't run "
                "that search. Please try again in a moment.")
    if "mcp session" in d or ("mcp" in d and "connect" in d):
        return ("Can't reach the Kapruka catalog right now (connection failed). "
                "Please try again shortly.")
    if "resource_exhausted" in d or "429" in d:
        return ("We've hit the free-tier usage limit for a moment. Please wait a "
                "minute and try again.")
    if "503" in d or "unavailable" in d or "overloaded" in d:
        return ("The AI service is briefly busy. Please send your message again in "
                "a few seconds.")
    return ""


def _card(item: dict) -> dict:
    """Trim a raw Kapruka product to the fields the frontend renders."""
    price = item.get("price") or {}
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "summary": item.get("summary"),
        "price": price.get("amount"),
        "currency": price.get("currency"),
        "image_url": item.get("image_url"),
        "in_stock": item.get("in_stock"),
        "stock_level": item.get("stock_level"),
        "url": item.get("url"),
        # Outfit slot label set by the stylist's capture callback; null for
        # plain catalog searches (frontend renders a grouped section when set).
        "group": item.get("_group"),
    }


async def _ensure(rnr: InMemoryRunner, known: set[str], session_id: str) -> None:
    if session_id in known:
        return
    await rnr.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id
    )
    known.add(session_id)


async def _ensure_session(session_id: str) -> None:
    await _ensure(runner, _known_sessions, session_id)


@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    async def event_stream():
        try:
            await _ensure_session(request.session_id)
            message = types.Content(
                role="user", parts=[types.Part(text=request.message)]
            )

            # Fresh per-request sink that the shopper's tool callback fills with
            # structured products (carried through AgentTool via contextvars).
            sink: list = []
            product_sink.set(sink)
            search_counter.set({"n": 0})  # per-turn search budget (stylist)
            images: list = []
            image_sink.set(images)  # generated try-on images (fitting room)
            current_session_id.set(request.session_id)  # for photo lookup in try_on
            orders: list = []
            order_sink.set(orders)  # placed-order payment links (checkout)
            tracking: list = []
            tracking_sink.set(tracking)  # order-tracking status cards (tracking)
            emitted = 0  # how many captured products we've already streamed
            img_emitted = 0  # how many try-on images we've already streamed
            ord_emitted = 0  # how many order links we've already streamed
            trk_emitted = 0  # how many tracking cards we've already streamed

            def drain_products():
                nonlocal emitted
                frames = ""
                while emitted < len(sink):
                    frames += _sse({"type": "product", "item": _card(sink[emitted])})
                    emitted += 1
                return frames

            def drain_images():
                nonlocal img_emitted
                frames = ""
                while img_emitted < len(images):
                    frames += _sse({"type": "tryon_image", **images[img_emitted]})
                    img_emitted += 1
                return frames

            def drain_orders():
                nonlocal ord_emitted
                frames = ""
                while ord_emitted < len(orders):
                    frames += _sse({"type": "order", **orders[ord_emitted]})
                    ord_emitted += 1
                return frames

            def drain_tracking():
                nonlocal trk_emitted
                frames = ""
                while trk_emitted < len(tracking):
                    frames += _sse({"type": "tracking", **tracking[trk_emitted]})
                    trk_emitted += 1
                return frames

            streamed = False
            async for event in runner.run_async(
                user_id=USER_ID,
                session_id=request.session_id,
                new_message=message,
            ):
                # Model-side blocks (safety filter, malformed calls…) arrive as
                # events with an error_code and no content — without this they
                # render as a silent "(no response)" in the UI.
                if getattr(event, "error_code", None):
                    detail = getattr(event, "error_message", None) or event.error_code
                    friendly = _friendly_error(str(detail))
                    yield _sse({
                        "type": "error",
                        "content": friendly or
                                   f"The model couldn't reply ({detail}). "
                                   "Please try rephrasing, or start a new session.",
                    })
                    continue

                content = getattr(event, "content", None)
                parts = getattr(content, "parts", None) or []

                # Surface tool calls so the UI can show a "searching…" chip.
                for part in parts:
                    call = getattr(part, "function_call", None)
                    if call is not None:
                        yield _sse({"type": "tool", "name": call.name})

                # Emit captured product cards / try-on images / order link /
                # tracking card (before prose).
                cards = (drain_products() + drain_images() + drain_orders()
                         + drain_tracking())
                if cards:
                    yield cards

                text = "".join(p.text for p in parts if getattr(p, "text", None))
                if not text:
                    continue

                if getattr(event, "partial", False):
                    streamed = True
                    yield _sse({"type": "text", "content": text})
                else:
                    # Final aggregated message — only send if we didn't already
                    # stream the deltas for this turn.
                    if not streamed:
                        yield _sse({"type": "text", "content": text})
                    streamed = False

            # Catch anything captured after the last event.
            cards = (drain_products() + drain_images() + drain_orders()
                     + drain_tracking())
            if cards:
                yield cards
        except Exception as exc:  # surface backend errors to the UI
            detail = f"{type(exc).__name__}: {exc}"
            yield _sse({"type": "error", "content": _friendly_error(detail) or detail})
        finally:
            yield _sse({"type": "done"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Realtime voice (English + Tamil) — Gemini Live over a WebSocket ---------
#
# Protocol (one WebSocket per turn-taking session):
#   client → server : binary frames = mic audio, PCM 16-bit mono 16 kHz
#                     text frames   = JSON control, e.g. {"type":"text","content":..}
#   server → client : binary frames = assistant audio, PCM 16-bit mono 24 kHz
#                     text frames   = JSON (same shapes as /chat: product,
#                                     tryon_image, text, tool) + turn_complete /
#                                     interrupted / error / go_away
#
# transfer_to_agent is broken under run_live, so this drives `live_concierge`
# (specialists exposed as AgentTool). Product/try-on cards are drained from the
# same contextvar sinks the SSE path uses.

@app.websocket("/live")
async def live_endpoint(websocket: WebSocket):
    await websocket.accept()
    session_id = websocket.query_params.get("session_id") or f"live-{id(websocket)}"
    lang = websocket.query_params.get("lang", "en")
    locale = LANG_TO_LOCALE.get(lang, "en-US")
    await _ensure(live_runner, _live_known_sessions, session_id)

    # Per-connection capture sinks (set before the tasks below so each inherits
    # the context; callbacks mutate the held objects in place).
    sink: list = []
    product_sink.set(sink)
    search_counter.set({"n": 0})
    images: list = []
    image_sink.set(images)
    orders: list = []
    order_sink.set(orders)
    tracking: list = []
    tracking_sink.set(tracking)
    current_session_id.set(session_id)

    live_request_queue = LiveRequestQueue()
    # Expose the queue so a slow background order-confirmation can post a follow-up
    # spoken turn after place_order has already returned its quick "please wait".
    live_request_queue_var.set(live_request_queue)
    run_config = RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(language_code=locale),
        # Give us the text alongside the audio (for on-screen captions).
        output_audio_transcription=types.AudioTranscriptionConfig(),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        # Voice-activity detection: the model must know when the shopper has
        # STOPPED talking to take its turn. Automatic VAD on the streamed mic
        # audio, tuned to commit a turn after a short silence, with start-of-
        # speech interrupting the assistant (barge-in).
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                disabled=False,
                start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                prefix_padding_ms=100,
                # Shorter end-of-speech silence → the model takes its turn ~300ms
                # sooner after the shopper stops talking (snappier replies). Too
                # low would cut people off mid-sentence; 500ms is a safe floor.
                silence_duration_ms=500,
            ),
            activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
        ),
        # NOTE: session_resumption is Vertex-only on older ADK; ADK 2.3.0 only
        # enables transparent resumption on Vertex, so the AI Studio backend no
        # longer crashes. The ~15 min cap is handled by the client reconnecting
        # on the `go_away` frame.
    )

    # Proactively greet the moment the shopper connects, BEFORE they speak. The
    # live agent is reactive — without a kickoff it stays silent until the user
    # talks, and then jumps straight to a `shop` search with no greeting. We send
    # a one-off text turn to trigger the opening line. It's TEXT (not audio), so
    # it produces no input transcription and never shows as a "you said" caption.
    greet_lang = "Tamil" if lang == "ta" else "English"
    live_request_queue.send_content(
        types.Content(
            role="user",
            parts=[types.Part(text=(
                "[The shopper just walked up to your counter in the store.] "
                f"Greet them warmly in {greet_lang} in ONE short, friendly "
                "sentence, introduce yourself as their Kapruka stylist, and ask "
                "what they're looking for today. Do NOT call any tool yet."
            ))],
        )
    )

    async def send_json(payload: dict) -> None:
        await websocket.send_text(json.dumps(payload))

    async def upstream() -> None:
        """Pump the client's mic audio / typed text into the live queue."""
        try:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    live_request_queue.send_realtime(
                        types.Blob(data=msg["bytes"], mime_type="audio/pcm;rate=16000")
                    )
                elif msg.get("text"):
                    try:
                        data = json.loads(msg["text"])
                    except json.JSONDecodeError:
                        continue
                    if data.get("type") == "text" and data.get("content"):
                        live_request_queue.send_content(
                            types.Content(role="user",
                                          parts=[types.Part(text=data["content"])])
                        )
        except WebSocketDisconnect:
            pass
        finally:
            live_request_queue.close()

    async def downstream() -> None:
        """Stream the assistant's audio + card/caption frames back to the client."""
        emitted = 0
        img_emitted = 0
        ord_emitted = 0
        trk_emitted = 0
        spoken = ""  # transcript already sent this turn (see caption block below)
        async for event in live_runner.run_live(
            user_id=USER_ID,
            session_id=session_id,
            live_request_queue=live_request_queue,
            run_config=run_config,
        ):
            if getattr(event, "error_code", None):
                detail = getattr(event, "error_message", None) or event.error_code
                await send_json({"type": "error",
                                 "content": _friendly_error(str(detail)) or str(detail)})
                continue

            # Drain captured product cards / try-on images (same _card shape).
            while emitted < len(sink):
                await send_json({"type": "product", "item": _card(sink[emitted])})
                emitted += 1
            while img_emitted < len(images):
                await send_json({"type": "tryon_image", **images[img_emitted]})
                img_emitted += 1
            while ord_emitted < len(orders):
                await send_json({"type": "order", **orders[ord_emitted]})
                ord_emitted += 1
            while trk_emitted < len(tracking):
                await send_json({"type": "tracking", **tracking[trk_emitted]})
                trk_emitted += 1

            content = getattr(event, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                call = getattr(part, "function_call", None)
                if call is not None:
                    await send_json({"type": "tool", "name": call.name})
                inline = getattr(part, "inline_data", None)
                if inline is not None and inline.data and \
                        (inline.mime_type or "").startswith("audio"):
                    await websocket.send_bytes(inline.data)

            # Spoken-reply captions and the user's own transcript. Gemini Live
            # streams the transcription as incremental deltas during the turn AND
            # repeats the FULL text as a final aggregate at the end — forwarding
            # every event verbatim rendered the caption twice. Send only the NEW
            # suffix each time: a delta is appended; the cumulative aggregate
            # starts with what we've already sent, so its suffix is empty.
            out_tx = getattr(event, "output_transcription", None)
            if out_tx is not None and getattr(out_tx, "text", None):
                t = out_tx.text
                if t.startswith(spoken):
                    delta, spoken = t[len(spoken):], t
                else:
                    delta, spoken = t, spoken + t
                if delta:
                    await send_json({"type": "text", "content": delta})
            in_tx = getattr(event, "input_transcription", None)
            if in_tx is not None and getattr(in_tx, "text", None):
                await send_json({"type": "user_text", "content": in_tx.text})

            if getattr(event, "interrupted", None):
                spoken = ""
                await send_json({"type": "interrupted"})
            if getattr(event, "turn_complete", None):
                spoken = ""
                await send_json({"type": "turn_complete"})
            # The Live session is about to be torn down (time cap) — tell the
            # client to reconnect with the same session_id.
            if getattr(event, "go_away", None):
                await send_json({"type": "go_away"})

    up = asyncio.create_task(upstream())
    down = asyncio.create_task(downstream())
    try:
        await down
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # surface, then fall through to cleanup
        try:
            await send_json({"type": "error",
                             "content": _friendly_error(f"{type(exc).__name__}: {exc}")
                             or "The voice session ended unexpectedly."})
        except Exception:
            pass
    finally:
        up.cancel()
        live_request_queue.close()
        try:
            await websocket.close()
        except Exception:
            pass


# --- Sinhala voice — turn-based via Azure (Gemini Live can't speak Sinhala) ---
#
# Audio in → Azure STT (si-LK) → the existing text agent graph (run_async) →
# Azure TTS (si-LK-ThiliniNeural) → audio + cards back in one JSON response.

# Voice replies are spoken aloud AND synthesised by TTS, so they must stay short:
# long prose here means both slow Sinhala generation and a long TTS tail. The text
# `/chat` graph defaults to verbose card-friendly prose; this steers it back to
# one or two spoken sentences. Shared by both the push-to-talk (/voice_sinhala)
# and the continuous (/live_sinhala) paths.
_SINHALA_VOICE_PREAMBLE = (
    "[Voice turn — reply in 1-2 short spoken Sinhala sentences only. No lists, no "
    "markdown, no product ids or URLs, and don't recite prices or specs unless the "
    "shopper explicitly asked. The product cards appear on screen, so just say what "
    "matters and ask one short next thing. IMPORTANT: only say you found items if "
    "the search tool actually returned products this turn. If the search returns "
    "nothing or fails, say so honestly (e.g. ask to try different words) — never "
    "describe products you did not actually get back. SEARCH IN ENGLISH: the "
    "catalog is indexed in English, so ALWAYS pass English keywords to the search "
    "tool's `q` even though the shopper speaks Sinhala and you reply in Sinhala — "
    "e.g. සාරි → \"saree\", කමිසය → \"shirt\", සපත්තු → \"shoes\", ගවුම → \"dress\", "
    "අත් බෑගය → \"handbag\". Never send Sinhala-script words as the search query.]\n"
)

# A fixed opening line for the live Sinhala session — synthesised directly (no LLM
# call) so the greeting is instant and costs no Gemini quota.
_SINHALA_GREETING = (
    "ආයුබෝවන්! මම ඔබගේ Kapruka විලාසිතා සහායකයා. අද ඔබ සොයන්නේ කුමක්ද?"
)

# A short spoken acknowledgement played the instant the shopper finishes talking —
# while the agent + MCP round-trip runs — so they hear us immediately ("Right,
# let me check…"). Cached PCM, so it costs no per-turn TTS latency.
_SINHALA_ACK = "හරි, මම බලන්නම්."

# Split a reply into sentences so TTS can stream the first one while the rest
# synthesise. Breaks after Latin (.!?) and Sinhala/Devanagari danda (।/॥)
# terminators followed by whitespace; falls back to the whole text.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?।॥])\s+")


def _split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text.strip()) if p.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def _sinhala_voice_prompt(transcript: str) -> str:
    return _SINHALA_VOICE_PREAMBLE + transcript


async def _run_sinhala_turn(session_id: str, transcript: str) -> str:
    """Run one Sinhala utterance through the text agent graph; return the reply.

    Assumes the caller has already set the per-request/connection contextvar sinks
    (product/image/order/search) and `current_session_id` so product cards, try-on
    images and orders are captured into them as a side effect.
    """
    message = types.Content(
        role="user", parts=[types.Part(text=_sinhala_voice_prompt(transcript))]
    )
    streamed_final = ""
    async for event in runner.run_async(
        user_id=USER_ID, session_id=session_id, new_message=message
    ):
        if getattr(event, "error_code", None):
            detail = getattr(event, "error_message", None) or event.error_code
            raise RuntimeError(_friendly_error(str(detail)) or str(detail))
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) or []
        text = "".join(p.text for p in parts if getattr(p, "text", None))
        if text and not getattr(event, "partial", False):
            streamed_final = text  # last non-partial aggregate wins
    return streamed_final


@app.post("/voice_sinhala")
async def voice_sinhala(session_id: str = Form(...), audio: UploadFile = File(...)):
    if not azure_speech.is_configured():
        return JSONResponse(
            {"status": "error",
             "message": "Sinhala voice isn't configured (set AZURE_SPEECH_KEY / "
                        "AZURE_SPEECH_REGION)."},
            status_code=503,
        )

    audio_bytes = await audio.read()
    if not audio_bytes:
        return JSONResponse({"status": "error", "message": "Empty audio."},
                            status_code=400)

    # 1. Sinhala speech → text (Azure runs sync; keep the event loop free).
    _t0 = time.perf_counter()
    try:
        transcript = await asyncio.to_thread(azure_speech.transcribe, audio_bytes)
    except azure_speech.AzureSpeechError as exc:
        return JSONResponse({"status": "error", "message": str(exc)}, status_code=502)
    if not transcript.strip():
        return JSONResponse({"status": "no_speech",
                             "message": "Didn't catch that — please try again."})

    _t_stt = time.perf_counter()

    # 2. Run the transcript through the same agent graph as the text chat.
    await _ensure_session(session_id)
    sink: list = []
    product_sink.set(sink)
    search_counter.set({"n": 0})
    images: list = []
    image_sink.set(images)
    orders: list = []
    order_sink.set(orders)
    tracking: list = []
    tracking_sink.set(tracking)
    current_session_id.set(session_id)

    try:
        reply_text = await _run_sinhala_turn(session_id, transcript)
    except RuntimeError as exc:
        return JSONResponse({"status": "error", "message": str(exc)})
    _t_agent = time.perf_counter()

    # 3. Text reply → Sinhala speech.
    audio_b64 = None
    if reply_text.strip():
        try:
            audio_out = await asyncio.to_thread(azure_speech.synthesize, reply_text)
            audio_b64 = base64.b64encode(audio_out).decode("ascii")
        except azure_speech.AzureSpeechError:
            audio_b64 = None  # still return text + cards even if TTS fails
    _t_tts = time.perf_counter()
    print(
        f"[voice_sinhala] STT={_t_stt - _t0:.1f}s  "
        f"agent={_t_agent - _t_stt:.1f}s  TTS={_t_tts - _t_agent:.1f}s  "
        f"reply_chars={len(reply_text)}",
        flush=True,
    )

    return {
        "status": "ok",
        "transcript": transcript,
        "reply_text": reply_text,
        "audio_mp3_base64": audio_b64,
        "products": [_card(p) for p in sink],
        "tryon_images": images,
        "orders": orders,
        "tracking": tracking,
    }


# --- Sinhala voice — LIVE (hands-free) via Azure continuous recognition --------
#
# Same building blocks as /voice_sinhala, but instead of one record→upload turn it
# holds a WebSocket open and streams mic audio into Azure's continuous recogniser.
# Azure's own VAD decides when the shopper finished talking and fires a transcript;
# we run the agent graph, stream the product/try-on/order cards, then synthesise the
# Sinhala reply as raw 24 kHz PCM streamed back as binary frames (same shape the
# /live Gemini path uses, so the browser plays it through the same scheduler).
#
# FULL-DUPLEX with barge-in: the recogniser is fed continuously, even while the
# assistant talks, so the shopper can interrupt. Azure's `speech_start_detected`
# fires `barge_in()` → the TTS send-loops stop, an `interrupted` frame tells the
# client to drop queued audio, and the shopper's utterance becomes the next turn.
# This relies on BROWSER ECHO CANCELLATION (getUserMedia) to keep the bot's own
# voice out of the mic feed; without it (or with loud speakers) Azure may hear the
# bot and self-interrupt — headphones are the safest. The frame protocol mirrors
# /live: server→client JSON {product,tryon_image,order,tool,user_text,user_partial,
# text,turn_complete,interrupted,error} plus binary audio; client→server binary mic
# PCM (16 kHz mono).
_TTS_FRAME_BYTES = 32000  # ~0.67s of 24 kHz/16-bit PCM per binary frame

@app.websocket("/live_sinhala")
async def live_sinhala_endpoint(websocket: WebSocket):
    await websocket.accept()
    if not azure_speech.is_configured():
        await websocket.send_text(json.dumps({
            "type": "error",
            "content": "Sinhala voice isn't configured (set AZURE_SPEECH_KEY / "
                       "AZURE_SPEECH_REGION).",
        }))
        await websocket.close()
        return

    session_id = websocket.query_params.get("session_id") or f"si-{id(websocket)}"
    await _ensure_session(session_id)

    # Per-connection capture sinks (set once; turns drain the new tail each time).
    sink: list = []
    product_sink.set(sink)
    search_counter.set({"n": 0})
    images: list = []
    image_sink.set(images)
    orders: list = []
    order_sink.set(orders)
    tracking: list = []
    tracking_sink.set(tracking)
    current_session_id.set(session_id)
    emitted = {"p": 0, "i": 0, "o": 0, "k": 0}

    loop = asyncio.get_running_loop()
    transcripts: asyncio.Queue[str] = asyncio.Queue()
    # Interim (still-talking) transcripts → live "we're hearing you" caption.
    partials: asyncio.Queue[str] = asyncio.Queue()
    # While True, the assistant is thinking/speaking: drop inbound mic audio so the
    # recogniser doesn't pick up the bot's own voice (half-duplex guard).
    speaking = {"on": False}
    # Barge-in: set when the shopper starts talking over the bot. The audio-send
    # loops watch it and stop streaming TTS immediately. `intr["sent"]` makes sure
    # the one-shot `interrupted` frame is sent only once per barge-in (all sends
    # happen inside the single `processor` coroutine, so this stays race-free).
    interrupt = asyncio.Event()
    intr = {"sent": False}

    async def send_json(payload: dict) -> None:
        await websocket.send_text(json.dumps(payload))

    async def signal_interrupt_once() -> None:
        """Tell the client to drop queued assistant audio (once per barge-in)."""
        if not intr["sent"]:
            intr["sent"] = True
            await send_json({"type": "interrupted"})

    def barge_in() -> None:
        """Azure detected the shopper speaking while the bot talks → flag it.
        Runs on the event loop (bridged from the Azure SDK thread)."""
        if speaking["on"] and not interrupt.is_set():
            interrupt.set()
            speaking["on"] = False  # let partials/mic flow for the new utterance

    async def drain_cards() -> int:
        new_products = 0
        while emitted["p"] < len(sink):
            await send_json({"type": "product", "item": _card(sink[emitted["p"]])})
            emitted["p"] += 1
            new_products += 1
        while emitted["i"] < len(images):
            await send_json({"type": "tryon_image", **images[emitted["i"]]})
            emitted["i"] += 1
        while emitted["o"] < len(orders):
            await send_json({"type": "order", **orders[emitted["o"]]})
            emitted["o"] += 1
        while emitted["k"] < len(tracking):
            await send_json({"type": "tracking", **tracking[emitted["k"]]})
            emitted["k"] += 1
        return new_products

    async def speak_pcm(pcm: bytes) -> float:
        """Stream ready PCM bytes (e.g. a cached greeting/ack) to the client and
        return its play length in seconds. PCM is 24 kHz/16-bit mono = 48000 B/s.
        Stops early if the shopper barges in."""
        for off in range(0, len(pcm), _TTS_FRAME_BYTES):
            if interrupt.is_set():
                await signal_interrupt_once()
                break
            await websocket.send_bytes(pcm[off:off + _TTS_FRAME_BYTES])
        return len(pcm) / 48000.0

    async def _stream_tts(text: str) -> int:
        """Synthesise `text` and forward PCM chunks to the client AS they arrive
        (Azure streaming synthesis). Returns total bytes sent. Raises
        AzureSpeechError if synthesis fails."""
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()

        def on_chunk(chunk: bytes) -> None:  # Azure SDK thread → hop to the loop
            loop.call_soon_threadsafe(q.put_nowait, chunk)

        def run() -> None:
            try:
                azure_speech.synthesize_pcm_stream(text, on_chunk)
            finally:
                loop.call_soon_threadsafe(q.put_nowait, None)  # end-of-stream sentinel

        task = asyncio.create_task(asyncio.to_thread(run))
        total = 0
        while True:
            chunk = await q.get()
            if chunk is None:
                break
            if interrupt.is_set():
                # barge-in: stop sending audio but keep draining the queue to the
                # sentinel so the synth thread finishes cleanly (no hang/leak).
                await signal_interrupt_once()
                continue
            await websocket.send_bytes(chunk)
            total += len(chunk)
        await task  # surface any synthesis error after the stream drains
        return total

    async def speak(text: str) -> float:
        """Stream Sinhala TTS sentence-by-sentence: the first sentence starts
        playing while later ones are still synthesising (lower time-to-first-audio).
        Returns total play length in seconds for the half-duplex guard."""
        total = 0
        try:
            for sentence in _split_sentences(text):
                if interrupt.is_set():
                    break  # don't start a new sentence after a barge-in
                total += await _stream_tts(sentence)
        except azure_speech.AzureSpeechError:
            pass  # caption already sent; skip remaining audio if TTS fails
        return total / 48000.0

    # Azure fires `recognized`/`recognizing` on its own thread → hop back onto the
    # event loop. `recognized` = final utterance (a turn); `recognizing` = interim
    # partial while still talking (drives a live caption, doesn't start a turn).
    recognizer, push_stream = await asyncio.to_thread(
        azure_speech.start_continuous,
        lambda text: loop.call_soon_threadsafe(transcripts.put_nowait, text),
        on_recognizing=lambda text: loop.call_soon_threadsafe(
            partials.put_nowait, text),
        on_speech_start=lambda: loop.call_soon_threadsafe(barge_in),
    )

    async def partial_pump() -> None:
        """Forward interim transcripts to the client as live partial captions."""
        while True:
            text = await partials.get()
            if not text.strip():
                continue
            await send_json({"type": "user_partial", "content": text})

    async def upstream() -> None:
        """Pump the client's mic PCM into Azure. Always on now (full-duplex): the
        recogniser must hear the shopper even while the bot talks so they can barge
        in. Browser echo cancellation keeps the bot's own voice out of the feed."""
        try:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                data = msg.get("bytes")
                if data:
                    push_stream.write(data)
        except WebSocketDisconnect:
            pass

    async def end_turn(play_secs: float) -> None:
        """Close out a turn. On a clean finish, hold briefly until playback ends
        then discard any echo Azure picked up. On a barge-in, skip both — the
        shopper is already talking and that utterance must NOT be flushed."""
        await send_json({"type": "turn_complete"})
        if interrupt.is_set():
            speaking["on"] = False
            return
        await asyncio.sleep(play_secs + 0.4)
        while not transcripts.empty():
            transcripts.get_nowait()
        speaking["on"] = False

    async def processor() -> None:
        """Greet, then turn each recognised utterance into a spoken reply."""
        interrupt.clear()
        intr["sent"] = False
        speaking["on"] = True
        # Precompute the fixed greeting + acknowledgement PCM once (cached
        # process-wide) so both replay instantly without a TTS round-trip.
        try:
            greeting_pcm = await asyncio.to_thread(
                azure_speech.synthesize_pcm_cached, _SINHALA_GREETING)
            ack_pcm = await asyncio.to_thread(
                azure_speech.synthesize_pcm_cached, _SINHALA_ACK)
        except azure_speech.AzureSpeechError:
            greeting_pcm = ack_pcm = b""
        await send_json({"type": "text", "content": _SINHALA_GREETING})
        await end_turn(await speak_pcm(greeting_pcm))

        while True:
            transcript = await transcripts.get()
            if not transcript.strip():
                continue
            interrupt.clear()  # fresh turn — clear any prior barge-in flag
            intr["sent"] = False
            speaking["on"] = True
            await send_json({"type": "user_text", "content": transcript})
            # Instant cached acknowledgement so the shopper hears us right away,
            # while the agent + MCP round-trip (a few seconds) runs.
            await speak_pcm(ack_pcm)
            await send_json({"type": "tool", "name": "catalog_agent"})
            # Per-turn reset: search_counter doubles as this turn's
            # "did a product search actually run?" flag (see capture_products_after_tool).
            search_counter.set({"n": 0})
            _t0 = time.perf_counter()
            try:
                reply = await _run_sinhala_turn(session_id, transcript)
            except RuntimeError as exc:
                await send_json({"type": "error", "content": str(exc)})
                speaking["on"] = False
                continue
            print(f"[live_sinhala] agent={time.perf_counter() - _t0:.1f}s  "
                  f"reply_chars={len(reply)}", flush=True)
            new_products = await drain_cards()
            # A search ran this turn but surfaced no products: tell the client so
            # the stale (seeded/previous) wall isn't left implying a fresh result.
            searched = (search_counter.get() or {}).get("n", 0) > 0
            if searched and new_products == 0:
                await send_json({"type": "no_results"})
            play_secs = 0.0
            if reply.strip():
                await send_json({"type": "text", "content": reply})
                play_secs = await speak(reply)
            await end_turn(play_secs)

    up = asyncio.create_task(upstream())
    proc = asyncio.create_task(processor())
    pump = asyncio.create_task(partial_pump())
    try:
        await up  # completes on client disconnect
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # surface, then clean up
        try:
            await send_json({"type": "error",
                             "content": _friendly_error(f"{type(exc).__name__}: {exc}")
                             or "The voice session ended unexpectedly."})
        except Exception:
            pass
    finally:
        proc.cancel()
        pump.cancel()
        try:
            await asyncio.to_thread(recognizer.stop_continuous_recognition)
        except Exception:
            pass
        try:
            push_stream.close()
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass


# --- Frontend serving (registered LAST so it doesn't shadow the API routes) ---
#
# In production the 3D store is built to a static export (`frontend/out`) and
# served here at the site root, same-origin with the API/WS — no CORS, one
# deploy. In dev the export doesn't exist; run `npm run dev` (Next on :3000,
# which proxies these endpoints) and "/" here falls back to the legacy chat UI.
if FRONTEND_OUT.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_OUT, html=True), name="frontend")
else:
    @app.get("/")
    async def index_fallback():
        return FileResponse(STATIC_DIR / "index.html")
