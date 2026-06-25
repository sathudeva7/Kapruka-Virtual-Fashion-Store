// Backend endpoint helpers. HTTP paths are relative: in dev Next rewrites proxy
// them to the FastAPI backend (no CORS), in the static-export prod build they
// resolve same-origin (FastAPI serves the export). The /live WebSocket can't be
// proxied, so wsUrl() points at NEXT_PUBLIC_WS_BASE in dev and derives the URL
// from window.location in prod.

export function wsUrl(path: string, params: Record<string, string> = {}): string {
  const qs = new URLSearchParams(params).toString();
  const suffix = qs ? `${path}?${qs}` : path;
  const base = process.env.NEXT_PUBLIC_WS_BASE;
  if (base) return base + suffix;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${suffix}`;
}

// Product images come from the Kapruka CDN, which doesn't send CORS headers — a
// WebGL texture load (crossOrigin=anonymous) would fail. Route them through the
// backend /img proxy so they arrive same-origin and texture cleanly.
export function imgUrl(remote: string | null | undefined): string | null {
  if (!remote) return null;
  return `/img?u=${encodeURIComponent(remote)}`;
}

export async function uploadPhoto(sessionId: string, file: File): Promise<void> {
  const fd = new FormData();
  fd.append("session_id", sessionId);
  fd.append("photo", file);
  const res = await fetch("/upload_photo", { method: "POST", body: fd });
  const out = await res.json().catch(() => ({}));
  if (!res.ok || out.status !== "ok") {
    throw new Error(out.message || "Photo upload failed.");
  }
}

export interface SinhalaResult {
  status: string;
  message?: string;
  transcript?: string;
  reply_text?: string;
  audio_mp3_base64?: string | null;
  products?: unknown[];
  tryon_images?: unknown[];
  orders?: unknown[];
}

export interface TryOnResult {
  status: string;
  image_url?: string;
  product_name?: string;
  message?: string;
}

import type { CartLine, CheckoutDetails } from "./store";

export interface CartResult {
  status: string;
  message?: string;
  items?: CartLine[];
  item_count?: number;
  total?: number;
  currency?: string;
}

// Direct virtual try-on (no LLM). image_url must be the RAW product image URL
// (not the /img proxy) — the backend downloads it server-side.
export async function requestTryOn(
  sessionId: string,
  product: { id?: string; name?: string; image_url?: string }
): Promise<TryOnResult> {
  const res = await fetch("/try_on", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      products: [{ id: product.id, name: product.name, image_url: product.image_url }],
    }),
  });
  return res.json();
}

export async function addToCart(
  sessionId: string,
  product: { id: string; name?: string; price?: number; category?: string }
): Promise<CartResult> {
  const res = await fetch("/cart", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      product_id: product.id,
      name: product.name || "Product",
      category: product.category || "",
      price: Math.round(product.price ?? 0),
    }),
  });
  return res.json();
}

// Save typed buyer + delivery details directly to the session (no LLM), so the
// assistant doesn't have to transcribe a name/address/phone by ear.
export async function saveCheckoutDetails(
  sessionId: string,
  details: CheckoutDetails
): Promise<{ status: string; message?: string; saved?: string[] }> {
  const res = await fetch("/checkout_details", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, ...details }),
  });
  return res.json();
}

export async function removeFromCart(sessionId: string, productId: string): Promise<CartResult> {
  const res = await fetch("/cart/remove", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, product_id: productId }),
  });
  return res.json();
}

// Read the current live-session cart (reflects both button and voice additions,
// which share the bridge runner's session). Used to refresh the trolley widget.
export async function fetchCart(sessionId: string): Promise<CartResult> {
  const res = await fetch(`/cart?session_id=${encodeURIComponent(sessionId)}`);
  return res.json();
}

export async function voiceSinhala(sessionId: string, wav: Blob): Promise<SinhalaResult> {
  const fd = new FormData();
  fd.append("session_id", sessionId);
  fd.append("audio", wav, "speech.wav");
  const res = await fetch("/voice_sinhala", { method: "POST", body: fd });
  return res.json();
}
