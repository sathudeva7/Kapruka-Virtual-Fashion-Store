# Kapruka — 3D walk-in store (frontend)

A game-like 3D fashion store (Next.js 16 + React 19 + React Three Fiber). The
shopper walks the store with the arrow keys / WASD, walks up to a voice
assistant, and the products the assistant fetches from the Kapruka MCP catalog
appear as framed posters on the racks of the section (Men / Women) they're
standing in. It talks to the existing FastAPI backend (voice over `/live`,
Sinhala over `/voice_sinhala`, photo upload, product images via `/img`).

## Develop

Run the backend and the Next dev server side by side:

```bash
# 1. backend (repo root) — FastAPI on :8000
./run.sh

# 2. frontend (this dir) — Next dev on :3000 with hot reload
npm run dev
```

In dev, Next proxies the HTTP endpoints (`/chat`, `/upload_photo`,
`/voice_sinhala`, `/img`, `/static`) to the backend (see `next.config.ts`), so
the browser stays same-origin. The `/live` WebSocket can't be proxied through
Next, so the client connects straight to the backend using
`NEXT_PUBLIC_WS_BASE` from `.env.development`. If the backend isn't on
`localhost:8000`, set `BACKEND_ORIGIN` (HTTP proxy target) and
`NEXT_PUBLIC_WS_BASE` (WS target).

## Production

Build a static export and let FastAPI serve it at the site root (same origin →
no CORS, the `/live` WebSocket just works, one deploy):

```bash
npm run export          # = BUILD_EXPORT=1 next build  -> ./out
./run.sh                # FastAPI serves ./frontend/out at /, API + WS alongside
```

`main.py` mounts `frontend/out` at `/` when it exists; the old single-file chat
UI stays available at `/legacy`.

## The assistant avatar (realistic human)

The assistant loads a rigged glTF/GLB humanoid from `public/assistant.glb`
(`src/components/three/Assistant.tsx`) — auto-scaled to ~1.7 m, feet on the
floor, idle animation played if the file has one, with a safe fallback to a
primitive figure if the file is missing or fails to load.

The bundled `public/assistant.glb` is a **placeholder** (a rigged sample human).
To get the exact business-attire woman look:

1. Go to **https://readyplayer.me** → create a **full-body** avatar (choose the
   look you want — e.g. blue shirt, black trousers).
2. Get its `.glb`:
   - **Easiest:** download the avatar and save it as `frontend/public/assistant.glb`
     (replace the placeholder), then `npm run export`.
   - **Or** point the loader at the hosted URL: set `AVATAR_URL` in
     `Assistant.tsx` to your `https://models.readyplayer.me/<id>.glb` (RPM serves
     it CORS-enabled, so the browser loads it directly — no rebuild of the model).
3. Ready Player Me avatars come in an A-pose with no animation; the assistant
   shows them standing with a gentle sway. To add a real idle/talk animation,
   merge a Mixamo or RPM animation clip into the `.glb` (optional, later).

Any rigged humanoid `.glb` works (Mixamo, Sketchfab CC0, etc.) — just replace
the file or `AVATAR_URL`.

## Map

- `src/components/StoreExperience.tsx` — the `<Canvas>` + HUD wrapper.
- `src/components/three/` — `Store` (room/sections/signage), `PlayerControls`
  (arrow/WASD + drag-look, wall clamping, section detection), `Assistant`
  (avatar + proximity prompt), `ProductRack`/`ProductFrame` (textured posters).
- `src/components/hud/HUD.tsx` — mic, language, captions, product detail, the
  Pay-now button, photo upload.
- `src/lib/` — `voice` (mic + `/live` WS + Sinhala, ported from the legacy UI),
  `audio` (downsample/WAV), `store` (zustand), `api`, `scene`, `session`.
