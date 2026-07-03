# Rate limiting & cost protection

Design doc for bounding AI spend on the public Kapruka app. **Not yet
implemented** — this is the agreed plan. Decisions: **fully open (no login),
IP-based limits, in-memory counters** (single instance).

## Why

The app is public and unauthenticated. Every caller currently hits Gemini (and
Azure, on `/live`) on our budget. Without limits, a script — or a single
runaway loop — can drain tokens or run up an image-generation bill unbounded.

The key constraint: **`session_id` is client-supplied and unauthenticated**
(it arrives in the `/chat` body and the `/live` query param). Any limit keyed
only on `session_id` is bypassed by minting a fresh UUID per request, so it is
**not** a usable quota key. We limit by **client IP** instead.

## Cost surface (not all requests are equal)

| Endpoint | Cost per call | Notes |
|---|---|---|
| `/chat` | Gemini 2.5 Flash text + sub-agent transfers + N MCP calls | Medium cost, high volume |
| `/upload_photo` → `/try_on` | `gemini-2.5-flash-image`, **bills per image**, 10–30s | Highest per-call |
| `/live` (WebSocket) | Gemini Live + Azure STT/TTS, long-lived (~15 min) | Highest per-session |

Limiting by raw request count is wrong: one try-on ≈ dozens of chat turns, one
voice session ≈ hundreds. We use **cost-weighted** limits.

## Architecture (layered)

### Layer 0 — Edge (Caddy)
Coarse per-IP request/connection cap in the Caddyfile (e.g. ~60 req/min/IP) to
absorb crude floods *before* they reach Python. This is flood protection, not
cost control.

### Layer 1 — Identity (client IP)
- uvicorn binds `127.0.0.1:8000` behind Caddy, so the socket peer is always
  Caddy. Derive the real client IP from **`X-Forwarded-For`**, taking the hop
  **Caddy appended** (the rightmost trusted entry) — never the leftmost, which
  clients can forge.
- This trust is only valid because nothing but Caddy can reach `:8000`. **Do
  not expose `:8000` publicly** or IP spoofing becomes trivial.

### Layer 2 — Cost-weighted per-IP quotas (in-memory)
- A process-local `{ip: token-bucket}` map. Use `slowapi` / `limits`
  (in-memory backend) or a hand-rolled sliding window.
- **Reaper required:** evict idle IP entries (unused > ~1 hr) via a background
  task, or the map grows unbounded and becomes its own memory-leak DoS.
- Suggested starting buckets per IP (tune from real traffic):
  - **Chat:** ~20 turns / 10 min, ~150 / day
  - **Try-on:** ~3–5 / day (hard cap) + **global concurrency cap** of ~2
    image generations in flight at once
  - **Live voice:** 1 concurrent WS / IP, server-enforced 15-min cap,
    ~15 min/day total

### Layer 3 — Global daily kill-switch (do this first)
A single process-wide counter approximating spend (image-gens + live-minutes +
chat turns). Past a configured threshold, **degrade gracefully in order**:
disable try-on → disable voice → keep text chat with a "high demand, back
tomorrow" message. This bounds the worst-case bill regardless of how per-IP
logic is gamed. It is the single highest-value piece.

### Layer 4 — Hard caps on the expensive paths
- `/upload_photo` + `/try_on`: strict per-IP daily cap **and** global
  in-flight concurrency cap (slow, bills per image).
- `/live`: per-IP concurrent-connection cap (1), small global concurrent cap,
  and the 15-min limit enforced **server-side** (not just client reconnect).

## Where it plugs into the code

- `main.py:344` is the existing identity seam (`user_role = "customer"`) and
  sits right beside `guardrail_engine.preflight`. Resolve IP → check quota →
  reject **before** `_ensure_session` and any LLM/MCP call, mirroring how the
  input guardrail already short-circuits.
- Reject by emitting the existing SSE `error` frame, plus a `retry_after`
  field so the frontend can show "try again in N min".
- Apply the same gate at the top of the `/live` WS handler and on
  `/try_on` / `/upload_photo`.
- **Keep all counter logic in one module** so the in-memory → Redis swap later
  is a single-file change.

## Accepted trade-offs (consequences of the chosen options)

1. **State resets on restart/redeploy.** Deploy does `docker stop && docker rm`,
   which wipes all counters *including the global kill-switch*. A redeploy or
   reboot resets everyone's quota and the daily budget. Tolerable for a
   manually-deployed app — but don't redeploy as a way to "reset limits", and
   treat the global cap as best-effort, not a hard ledger.
2. **IP rotation bypasses it.** A proxy pool / rotating mobile IPs get fresh
   buckets. IP-based stops casual abuse and single-host bots (~95% of real
   risk). The global kill-switch still protects against organized abuse.

## Rollout order

1. **First (small, huge payoff):** global daily kill-switch (Layer 3) + edge
   IP cap in Caddy (Layer 0). Bounds the bill immediately.
2. **Next:** cost-weighted per-IP quotas + reaper (Layers 2 & 4) at the
   `main.py:344` seam.
3. **Later, if needed:** a lightweight challenge (Cloudflare Turnstile /
   reCAPTCHA) to harden against IP rotation; or swap in-memory → Redis when
   scaling past one container (the *only* change needed for multi-instance).
