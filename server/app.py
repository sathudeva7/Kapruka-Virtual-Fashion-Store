"""Application factory: wires the routers, static mounts and shared resources."""

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server.config import FRONTEND_OUT, STATIC_DIR
from server.routers import chat, commerce, system, voice_live, voice_sinhala


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # One pooled HTTP client for the /img proxy (reused connections, clean
    # close on shutdown) instead of a new client per request.
    app.state.http = httpx.AsyncClient(timeout=15, follow_redirects=True)
    try:
        yield
    finally:
        await app.state.http.aclose()


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO)

    app = FastAPI(title="Kapruka Virtual Fashion Store", lifespan=_lifespan)

    app.include_router(system.router)
    app.include_router(commerce.router)
    app.include_router(chat.router)
    app.include_router(voice_live.router)
    app.include_router(voice_sinhala.router)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # Frontend serving — registered LAST so it doesn't shadow the API routes.
    # In production the 3D store is built to a static export (`frontend/out`)
    # and served here at the site root, same-origin with the API/WS — no CORS,
    # one deploy. In dev the export doesn't exist; run `npm run dev` (Next on
    # :3000, which proxies these endpoints) and "/" here falls back to the
    # legacy chat UI.
    if FRONTEND_OUT.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_OUT, html=True),
                  name="frontend")
    else:
        @app.get("/")
        async def index_fallback():
            return FileResponse(STATIC_DIR / "index.html")

    return app
