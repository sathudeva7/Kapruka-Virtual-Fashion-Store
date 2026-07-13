"""The text chat endpoint: POST /chat → SSE stream (see CLAUDE.md for frames)."""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from google.genai import types

from tools.guardrails import engine as guardrail_engine

from server.capture import TurnCapture
from server.runners import USER_ID, ensure_chat_session, runner
from server.schemas import ChatRequest
from server.streaming import friendly_error, sse

router = APIRouter()


@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    async def event_stream():
        try:
            await ensure_chat_session(request.session_id)

            # No real auth yet (see CLAUDE.md): every caller is a "customer".
            # This is the single seam to swap when identity is wired in. Set
            # before the guardrail runs so audit entries and the Layer-2 RBAC
            # callbacks see the right role.
            user_role = "customer"

            # Fresh per-request sinks that the tool callbacks fill with
            # structured output (carried through the agent nesting via
            # contextvars).
            capture = TurnCapture.bind(request.session_id, role=user_role)

            # LAYER 1 — Input guardrail. Reject prompt-injection / forbidden
            # keywords BEFORE any MCP query or LLM call. Nothing downstream
            # runs if this fails.
            preflight = guardrail_engine.preflight(request.message, user_role=user_role)
            if not preflight["allowed"]:
                yield sse({
                    "type": "error",
                    "content": "Sorry — I can't help with that request.",
                })
                return  # the finally block emits the terminal "done" frame

            message = types.Content(
                role="user", parts=[types.Part(text=request.message)]
            )

            # LAYER 3 needs the COMPLETE reply (and every product captured this
            # turn) to redact + grounding-check it as a unit, so we buffer the
            # assistant prose here instead of streaming raw deltas. Tool /
            # product / image / order / tracking frames still stream live
            # below, so perceived latency stays low.
            assistant_text = ""
            streamed_partial = False
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
                    friendly = friendly_error(str(detail))
                    yield sse({
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
                        yield sse({"type": "tool", "name": call.name})

                # Emit captured product cards / try-on images / order links /
                # tracking cards (before prose).
                for frame in capture.drain():
                    yield sse(frame)

                text = "".join(p.text for p in parts if getattr(p, "text", None))
                if not text:
                    continue

                if getattr(event, "partial", False):
                    streamed_partial = True
                    assistant_text += text
                else:
                    # Final aggregated message: it's the authoritative full
                    # version of whatever we streamed in deltas, so replace
                    # rather than append.
                    if streamed_partial:
                        assistant_text = text
                        streamed_partial = False
                    else:
                        assistant_text += text

            # Catch anything captured after the last event (cards before prose).
            for frame in capture.drain():
                yield sse(frame)

            # LAYER 3 — Output guardrail over the complete reply: PII redaction
            # + factual grounding against this turn's retrieved products.
            # Emitted as one final text frame (or a safe fallback if grounding
            # fails).
            safe_text = guardrail_engine.finalize(
                assistant_text, source_contexts=capture.products
            )
            if safe_text:
                yield sse({"type": "text", "content": safe_text})
        except Exception as exc:  # surface backend errors to the UI
            detail = f"{type(exc).__name__}: {exc}"
            yield sse({"type": "error", "content": friendly_error(detail) or detail})
        finally:
            yield sse({"type": "done"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
