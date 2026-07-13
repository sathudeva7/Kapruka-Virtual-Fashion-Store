"""Realtime voice (English + Tamil) — Gemini Live over a WebSocket.

Protocol (one WebSocket per turn-taking session):
  client → server : binary frames = mic audio, PCM 16-bit mono 16 kHz
                    text frames   = JSON control, e.g. {"type":"text","content":..}
  server → client : binary frames = assistant audio, PCM 16-bit mono 24 kHz
                    text frames   = JSON (same shapes as /chat: product,
                                    tryon_image, text, tool) + turn_complete /
                                    interrupted / error / go_away

transfer_to_agent is broken under run_live, so this drives `live_concierge`
(specialists exposed as AgentTool). Product/try-on cards are drained from the
same contextvar sinks the SSE path uses.
"""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from google.adk.agents.live_request_queue import LiveRequestQueue
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.genai import types

from tools.sinks import live_request_queue_var

from server.capture import TurnCapture, reset_search_budget
from server.config import LANG_TO_LOCALE, USER_ID
from server.runners import ensure_live_session, live_runner
from server.streaming import friendly_error

router = APIRouter()


def _live_run_config(locale: str) -> RunConfig:
    return RunConfig(
        streaming_mode=StreamingMode.BIDI,
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            language_code=locale,
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")
            ),
        ),
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
                # Shorter end-of-speech silence → the model takes its turn
                # ~300ms sooner after the shopper stops talking (snappier
                # replies). Too low would cut people off mid-sentence; 500ms is
                # a safe floor.
                silence_duration_ms=500,
            ),
            activity_handling=types.ActivityHandling.START_OF_ACTIVITY_INTERRUPTS,
        ),
        # NOTE: session_resumption is Vertex-only on older ADK; ADK 2.3.0 only
        # enables transparent resumption on Vertex, so the AI Studio backend no
        # longer crashes. The ~15 min cap is handled by the client reconnecting
        # on the `go_away` frame.
    )


def _greeting_kickoff(lang: str) -> types.Content:
    """A one-off text turn sent the moment the shopper connects, BEFORE they
    speak. The live agent is reactive — without a kickoff it stays silent until
    the user talks, and then jumps straight to a `shop` search with no greeting.
    It's TEXT (not audio), so it produces no input transcription and never shows
    as a "you said" caption."""
    greet_lang = "Tamil" if lang == "ta" else "English"
    return types.Content(
        role="user",
        parts=[types.Part(text=(
            "[The shopper just walked up to your counter in the store.] "
            f"Greet them warmly in {greet_lang} in ONE short, friendly "
            "sentence, introduce yourself as their Kapruka stylist, and ask "
            "what they're looking for today. Do NOT call any tool yet."
        ))],
    )


@router.websocket("/live")
async def live_endpoint(websocket: WebSocket):
    await websocket.accept()
    session_id = websocket.query_params.get("session_id") or f"live-{id(websocket)}"
    lang = websocket.query_params.get("lang", "en")
    locale = LANG_TO_LOCALE.get(lang, "en-US")
    await ensure_live_session(session_id)

    # Per-connection capture sinks (bound before the tasks below so each
    # inherits the context; callbacks mutate the held objects in place).
    capture = TurnCapture.bind(session_id)

    live_request_queue = LiveRequestQueue()
    # Expose the queue so a slow background order-confirmation can post a
    # follow-up spoken turn after place_order has already returned its quick
    # "please wait".
    live_request_queue_var.set(live_request_queue)
    run_config = _live_run_config(locale)

    # Proactively greet the moment the shopper connects.
    live_request_queue.send_content(_greeting_kickoff(lang))

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
                                 "content": friendly_error(str(detail)) or str(detail)})
                continue

            # Drain captured product cards / try-on images / orders / tracking.
            for frame in capture.drain():
                await send_json(frame)

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
            # streams the transcription as incremental deltas during the turn
            # AND repeats the FULL text as a final aggregate at the end —
            # forwarding every event verbatim rendered the caption twice. Send
            # only the NEW suffix each time: a delta is appended; the cumulative
            # aggregate starts with what we've already sent, so its suffix is
            # empty.
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
                reset_search_budget()  # barge-in begins a fresh user turn
                await send_json({"type": "interrupted"})
            if getattr(event, "turn_complete", None):
                spoken = ""
                reset_search_budget()  # next turn starts with a full stylist budget
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
                             "content": friendly_error(f"{type(exc).__name__}: {exc}")
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
