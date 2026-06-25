import type { NextConfig } from "next";

// Two modes, one config:
//  - dev (`next dev`): proxy the backend HTTP endpoints through Next so the
//    browser talks same-origin (no CORS). The /live WebSocket is NOT proxied
//    here — the client connects straight to the backend (WS isn't subject to
//    CORS); see src/lib/api.ts wsUrl() + .env.local NEXT_PUBLIC_WS_BASE.
//  - prod (`BUILD_EXPORT=1 next build`): emit a static export to `out/`, served
//    by FastAPI at the same origin, so every path is relative — no rewrites, no
//    CORS. NOTE: `output: 'export'` forbids rewrites (they error under it), which
//    is exactly why the export flag is conditional.
const isExport = process.env.BUILD_EXPORT === "1";
const BACKEND = process.env.BACKEND_ORIGIN || "http://localhost:8000";

const nextConfig: NextConfig = isExport
  ? { output: "export" }
  : {
      async rewrites() {
        return [
          { source: "/chat", destination: `${BACKEND}/chat` },
          { source: "/try_on", destination: `${BACKEND}/try_on` },
          { source: "/cart", destination: `${BACKEND}/cart` },
          { source: "/cart/remove", destination: `${BACKEND}/cart/remove` },
          { source: "/checkout_details", destination: `${BACKEND}/checkout_details` },
          { source: "/upload_photo", destination: `${BACKEND}/upload_photo` },
          { source: "/voice_sinhala", destination: `${BACKEND}/voice_sinhala` },
          { source: "/img", destination: `${BACKEND}/img` },
          { source: "/static/:path*", destination: `${BACKEND}/static/:path*` },
        ];
      },
    };

export default nextConfig;
