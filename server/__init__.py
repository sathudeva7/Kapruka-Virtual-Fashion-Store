"""HTTP/WebSocket server for the Kapruka fashion agent.

Layout:
    app.py        — application factory (routers, static mounts, lifespan)
    config.py     — process-wide constants
    schemas.py    — request bodies (pydantic)
    runners.py    — the ADK runners + in-memory session registries
    streaming.py  — SSE encoding, error mapping, product-card shaping
    capture.py    — per-turn contextvar sinks (products / try-on / orders / tracking)
    routers/      — one module per concern (system, commerce, chat, voice)

`main.py` at the repo root stays the uvicorn entrypoint (`main:app`).
"""
