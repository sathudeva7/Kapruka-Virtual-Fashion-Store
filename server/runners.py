"""The process-wide ADK runners and their in-memory session registries."""

from google.adk.runners import InMemoryRunner

from liveagent import live_concierge
from rootagent import root_agent

from server.config import APP_NAME, USER_ID

# One runner per graph for the whole process; both keep session state in memory.
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


async def _ensure(rnr: InMemoryRunner, known: set[str], session_id: str) -> None:
    if session_id in known:
        return
    await rnr.session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id
    )
    known.add(session_id)


async def ensure_chat_session(session_id: str) -> None:
    await _ensure(runner, _known_sessions, session_id)


async def ensure_live_session(session_id: str) -> None:
    await _ensure(live_runner, _live_known_sessions, session_id)
