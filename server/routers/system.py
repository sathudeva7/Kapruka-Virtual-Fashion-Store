"""Infrastructure endpoints: health probe, legacy UI, image proxy, photo upload."""

import asyncio
from urllib.parse import urlparse

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from tools.photostore import photo_store

from server.config import (
    ALLOWED_PHOTO_TYPES,
    BROWSER_UA,
    MAX_PHOTO_BYTES,
    STATIC_DIR,
)

router = APIRouter()


@router.get("/healthz")
async def healthz():
    """Liveness probe for the load balancer / orchestrator. Stays cheap on
    purpose: returns 200 without touching Gemini, Azure or the MCP catalog, so a
    transient upstream outage never marks the container unhealthy."""
    return {"status": "ok"}


@router.get("/legacy")
async def legacy_index():
    """The original single-file chat UI (kept as a fallback)."""
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/img")
async def img_proxy(u: str, request: Request):
    """Same-origin image proxy for product photos (see BROWSER_UA in config.py).
    Uses the shared pooled client created in the app lifespan."""
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https"):
        return JSONResponse({"error": "invalid url"}, status_code=400)
    try:
        r = await request.app.state.http.get(u, headers={"User-Agent": BROWSER_UA})
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


@router.post("/upload_photo")
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
            {"status": "error", "message": "The uploaded file is empty."},
            status_code=400,
        )
    if len(data) > MAX_PHOTO_BYTES:
        return JSONResponse(
            {"status": "error", "message": "Photo is too large (max 8 MB)."},
            status_code=413,
        )
    # Off-thread: the S3 backend does a blocking network PUT (memory is instant).
    await asyncio.to_thread(photo_store.put, session_id, data, content_type)
    return {"status": "ok"}
