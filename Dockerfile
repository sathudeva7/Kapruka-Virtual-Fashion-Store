# Kapruka fashion agent — single image: Next static export + FastAPI backend.
#
# Stage 1 builds the 3D frontend to a static export (`frontend/out`).
# Stage 2 is the Python runtime; it copies the export in and serves everything
# same-origin from one uvicorn process (see main.py: the catch-all "/" mount).
# Deploy ONE instance — sessions, cart and (in memory mode) photos live in-
# process; see CLAUDE.md / the deploy plan before scaling out.

# --- Stage 1: frontend static export ----------------------------------------
FROM node:20-slim AS frontend
WORKDIR /app/frontend

# Install deps against the committed lockfile first (better layer caching).
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Build the static export. BUILD_EXPORT=1 flips next.config.ts to output:'export'
# (no rewrites), emitting ./out — the bundle FastAPI serves at the site root.
COPY frontend/ ./
RUN BUILD_EXPORT=1 npm run build

# --- Stage 2: python runtime -------------------------------------------------
FROM python:3.12-slim AS runtime

# The Azure Speech SDK (Sinhala STT/TTS) links libssl + ALSA at import time even
# when we only use raw PCM; ca-certificates is needed for the HTTPS calls to
# Gemini / Azure / the Kapruka MCP.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        libssl3 \
        libasound2 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Python deps first so code changes don't re-run pip.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code (the agent packages, tools/, static/, main.py). .dockerignore keeps
# .venv, node_modules and the frontend build out of this layer.
COPY . .

# Drop in the built frontend (overrides any stale local frontend/out).
COPY --from=frontend /app/frontend/out ./frontend/out

# Run unprivileged; the app writes generated try-on PNGs under static/generated.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p static/generated \
    && chown -R app:app /app
USER app

EXPOSE 8000

# No --reload in prod. Bind all interfaces so the load balancer can reach it.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
