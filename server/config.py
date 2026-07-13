"""Process-wide constants shared by the server modules."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
FRONTEND_OUT = BASE_DIR / "frontend" / "out"  # Next static export (prod)

APP_NAME = "kapruka"
USER_ID = "web-user"

# Product images come from the Kapruka CDN, which (a) rejects bare clients and
# (b) sends no CORS headers — a browser WebGL texture load would fail. The 3D
# frontend routes every product image through the /img proxy so it arrives
# same-origin with a browser User-Agent. See frontend/src/lib/api.ts imgUrl().
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Realtime voice languages → output voice locale for the Live API speech config.
# (Sinhala is NOT here — Gemini Live can't speak it; it uses the Azure path.)
LANG_TO_LOCALE = {"en": "en-US", "ta": "ta-IN"}

ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_PHOTO_BYTES = 8 * 1024 * 1024

# ~0.67s of 24 kHz/16-bit PCM per binary TTS frame (Sinhala live voice).
TTS_FRAME_BYTES = 32000
