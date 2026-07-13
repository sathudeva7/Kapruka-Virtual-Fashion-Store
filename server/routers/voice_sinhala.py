"""Sinhala voice — via Azure Speech (Gemini Live can't speak Sinhala).

Two paths share the same building blocks:

POST /voice_sinhala (push-to-talk): audio in → Azure STT (si-LK) → the existing
text agent graph (run_async) → Azure TTS (si-LK-ThiliniNeural) → audio + cards
back in one JSON response.

WS /live_sinhala (hands-free): holds a WebSocket open and streams mic audio into
Azure's continuous recogniser. Azure's own VAD decides when the shopper finished
talking and fires a transcript; we run the agent graph, stream the
product/try-on/order cards, then synthesise the Sinhala reply as raw 24 kHz PCM
streamed back as binary frames (same shape the /live Gemini path uses, so the
browser plays it through the same scheduler).

FULL-DUPLEX with barge-in: the recogniser is fed continuously, even while the
assistant talks, so the shopper can interrupt. Azure's `speech_start_detected`
fires `barge_in()` → the TTS send-loops stop, an `interrupted` frame tells the
client to drop queued audio, and the shopper's utterance becomes the next turn.
This relies on BROWSER ECHO CANCELLATION (getUserMedia) to keep the bot's own
voice out of the mic feed; without it (or with loud speakers) Azure may hear the
bot and self-interrupt — headphones are the safest. The frame protocol mirrors
/live: server→client JSON {product,tryon_image,order,tool,user_text,user_partial,
text,turn_complete,interrupted,error} plus binary audio; client→server binary mic
PCM (16 kHz mono).
"""

import asyncio
import base64
import json
import logging
import re
import time

from fastapi import APIRouter, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from google.genai import types

from liveagent.bridge import ensure_shared_session, shared_runner
from tools import azure_speech

from server.capture import TurnCapture, reset_search_budget, searches_this_turn
from server.config import TTS_FRAME_BYTES, USER_ID
from server.runners import ensure_chat_session
from server.streaming import friendly_error, product_card

logger = logging.getLogger(__name__)

router = APIRouter()

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

    Assumes the caller has already bound a TurnCapture (sinks + session id) so
    product cards, try-on images and orders are captured as a side effect.
    """
    message = types.Content(
        role="user", parts=[types.Part(text=_sinhala_voice_prompt(transcript))]
    )
    # Run on the SHARED bridge runner (same session store the /cart widget reads),
    # so a Sinhala voice "add to cart" is visible to the 3D UI just like the Gemini
    # live and click-to-add paths — not stranded in the separate text runner.
    await ensure_shared_session(session_id)
    streamed_final = ""
    async for event in shared_runner.run_async(
        user_id=USER_ID, session_id=session_id, new_message=message
    ):
        if getattr(event, "error_code", None):
            detail = getattr(event, "error_message", None) or event.error_code
            raise RuntimeError(friendly_error(str(detail)) or str(detail))
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) or []
        text = "".join(p.text for p in parts if getattr(p, "text", None))
        if text and not getattr(event, "partial", False):
            streamed_final = text  # last non-partial aggregate wins
    return streamed_final


@router.post("/voice_sinhala")
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
    await ensure_chat_session(session_id)
    capture = TurnCapture.bind(session_id)

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
    logger.info(
        "[voice_sinhala] STT=%.1fs  agent=%.1fs  TTS=%.1fs  reply_chars=%d",
        _t_stt - _t0, _t_agent - _t_stt, _t_tts - _t_agent, len(reply_text),
    )

    return {
        "status": "ok",
        "transcript": transcript,
        "reply_text": reply_text,
        "audio_mp3_base64": audio_b64,
        "products": [product_card(p) for p in capture.products],
        "tryon_images": capture.images,
        "orders": capture.orders,
        "tracking": capture.tracking,
    }


@router.websocket("/live_sinhala")
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
    await ensure_chat_session(session_id)

    # Per-connection capture sinks (bound once; turns drain the new tail each time).
    capture = TurnCapture.bind(session_id)

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
        """Forward newly captured frames to the client; return how many were
        product cards (so the caller can detect an empty search result)."""
        new_products = 0
        for frame in capture.drain():
            await send_json(frame)
            if frame["type"] == "product":
                new_products += 1
        return new_products

    async def speak_pcm(pcm: bytes) -> float:
        """Stream ready PCM bytes (e.g. a cached greeting/ack) to the client and
        return its play length in seconds. PCM is 24 kHz/16-bit mono = 48000 B/s.
        Stops early if the shopper barges in."""
        for off in range(0, len(pcm), TTS_FRAME_BYTES):
            if interrupt.is_set():
                await signal_interrupt_once()
                break
            await websocket.send_bytes(pcm[off:off + TTS_FRAME_BYTES])
        return len(pcm) / 48000.0

    async def _stream_tts(text: str) -> int:
        """Synthesise `text` and forward PCM chunks to the client AS they arrive
        (Azure streaming synthesis). Returns total bytes sent. Raises
        AzureSpeechError if synthesis fails."""
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
            # Per-turn reset: the search counter doubles as this turn's
            # "did a product search actually run?" flag
            # (see capture_products_after_tool).
            reset_search_budget()
            _t0 = time.perf_counter()
            try:
                reply = await _run_sinhala_turn(session_id, transcript)
            except RuntimeError as exc:
                await send_json({"type": "error", "content": str(exc)})
                speaking["on"] = False
                continue
            logger.info("[live_sinhala] agent=%.1fs  reply_chars=%d",
                        time.perf_counter() - _t0, len(reply))
            new_products = await drain_cards()
            # A search ran this turn but surfaced no products: tell the client so
            # the stale (seeded/previous) wall isn't left implying a fresh result.
            if searches_this_turn() > 0 and new_products == 0:
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
                             "content": friendly_error(f"{type(exc).__name__}: {exc}")
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
