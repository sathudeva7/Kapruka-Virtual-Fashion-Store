"use client";

import { useRef, useState, type CSSProperties } from "react";
import { useStore, type Lang, type ProductItem, type CartState, type CheckoutDetails } from "@/lib/store";
import { getVoiceClient } from "@/lib/voice";
import { uploadPhoto, imgUrl, requestTryOn, addToCart, fetchCart, removeFromCart, saveCheckoutDetails, trackOrder, type CartResult } from "@/lib/api";
import type { TrackingItem } from "@/lib/store";
import { getSessionId } from "@/lib/session";
import { TRYON_ROOM } from "@/lib/scene";
import Joystick from "./Joystick";

const LANGS: { value: Lang; label: string }[] = [
  { value: "en", label: "English" },
  { value: "ta", label: "தமிழ் (Tamil)" },
  { value: "si", label: "සිංහල (Sinhala)" },
];

function fmtPrice(price?: number, currency?: string) {
  return price != null ? new Intl.NumberFormat("en-LK").format(price) + " " + (currency || "LKR") : "—";
}

// Map a product's stock fields to a human label + colour for the detail pill.
function stockInfo(p: ProductItem): { label: string; color: string; bg: string } {
  if (p.in_stock === false) return { label: "Out of stock", color: "#a1352b", bg: "#fbecea" };
  if ((p.stock_level || "").toLowerCase().includes("low")) {
    return { label: "Only a few left", color: "#9a6a12", bg: "#fbf2dd" };
  }
  return { label: "In stock", color: "#1b6b3a", bg: "#e7f3ec" };
}

function cartFrom(out: CartResult): CartState {
  return {
    items: out.items ?? [],
    count: out.item_count ?? 0,
    total: out.total ?? 0,
    currency: out.currency ?? "LKR",
  };
}

export default function HUD() {
  const section = useStore((s) => s.section);
  const near = useStore((s) => s.nearAssistant);
  const lang = useStore((s) => s.lang);
  const connection = useStore((s) => s.connection);
  const userCaption = useStore((s) => s.userCaption);
  const userPartial = useStore((s) => s.userPartial);
  const botCaption = useStore((s) => s.botCaption);
  const toolStatus = useStore((s) => s.toolStatus);
  const captionsHidden = useStore((s) => s.captionsHidden);
  const error = useStore((s) => s.error);
  const selected = useStore((s) => s.selectedProduct);
  const orders = useStore((s) => s.orders);
  const tracking = useStore((s) => s.tracking);
  const tryOn = useStore((s) => s.tryOn);
  const enlarge = useStore((s) => s.enlarge);
  const cart = useStore((s) => s.cart);
  const cartOpen = useStore((s) => s.cartOpen);
  const checkout = useStore((s) => s.checkout);
  const checkoutOpen = useStore((s) => s.checkoutOpen);
  const checkoutSaved = useStore((s) => s.checkoutSaved);

  const setLang = useStore((s) => s.setLang);
  const setError = useStore((s) => s.setError);
  const setSelected = useStore((s) => s.setSelected);
  const setConnection = useStore((s) => s.setConnection);
  const startTryOn = useStore((s) => s.startTryOn);
  const setTryOnResult = useStore((s) => s.setTryOnResult);
  const setTryOnError = useStore((s) => s.setTryOnError);
  const exitTryOn = useStore((s) => s.exitTryOn);
  const requestTeleport = useStore((s) => s.requestTeleport);
  const setEnlarge = useStore((s) => s.setEnlarge);
  const setCart = useStore((s) => s.setCart);
  const setCartOpen = useStore((s) => s.setCartOpen);
  const setCheckout = useStore((s) => s.setCheckout);
  const setCheckoutOpen = useStore((s) => s.setCheckoutOpen);
  const setCheckoutSaved = useStore((s) => s.setCheckoutSaved);
  const setCaptionsHidden = useStore((s) => s.setCaptionsHidden);
  const addTracking = useStore((s) => s.addTracking);
  const removeTracking = useStore((s) => s.removeTracking);

  const fileRef = useRef<HTMLInputElement>(null);
  const tryOnFileRef = useRef<HTMLInputElement>(null);
  const photoUrlRef = useRef<string | null>(null); // persistent blob URL of the photo
  const pendingProductRef = useRef<ProductItem | null>(null);
  const [needPhoto, setNeedPhoto] = useState(false); // show the "upload your photo" step in the modal
  const [addingToCart, setAddingToCart] = useState(false);
  const [savingDetails, setSavingDetails] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [trackOpen, setTrackOpen] = useState(false);
  const [trackNum, setTrackNum] = useState("");
  const [trackBusy, setTrackBusy] = useState(false);
  const [trackErr, setTrackErr] = useState<string | null>(null);
  const client = getVoiceClient();

  const busy = connection === "connecting" || connection === "thinking";
  const listening = connection === "live" || connection === "recording";

  const micLabel = busy
    ? "…"
    : listening
    ? connection === "recording" // push-to-talk (PTT fallback) vs continuous
      ? "■ Stop & send"
      : "■ Stop"
    : "🎤 Talk";

  async function toggleMic() {
    setError(null);
    try {
      if (!client.active) await client.start(lang);
      else await client.stop();
    } catch (e) {
      setConnection("idle");
      setError("Mic error: " + ((e as Error).message || e));
    }
  }

  async function changeLang(next: Lang) {
    if (client.active) await client.stop().catch(() => {});
    setLang(next);
  }

  async function onPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    try {
      await uploadPhoto(getSessionId(), f);
      photoUrlRef.current = URL.createObjectURL(f); // reuse for the fitting-room wall
      setError(null);
      useStore.getState().setToolStatus("Photo uploaded — ask to try on a piece.");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  // --- virtual try-on flow ---
  async function runTryOn(product: ProductItem, photoUrl: string) {
    startTryOn(photoUrl, product.name ?? null);
    requestTeleport({ x: TRYON_ROOM.standSpot.x, z: TRYON_ROOM.standSpot.z, yaw: TRYON_ROOM.standSpot.yaw });
    try {
      const out = await requestTryOn(getSessionId(), product);
      if (out.status === "ok" && out.image_url) setTryOnResult(out.image_url);
      else setTryOnError(out.message || "Try-on failed. Try another photo.");
    } catch (err) {
      setTryOnError((err as Error).message);
    }
  }

  function onVirtualTryOn() {
    const product = selected;
    if (!product) return;
    if (photoUrlRef.current) {
      runTryOn(product, photoUrlRef.current);
    } else {
      pendingProductRef.current = product; // reveal the upload step, then run
      setNeedPhoto(true);
    }
  }

  async function onAddToCart() {
    const product = selected;
    if (!product?.id || addingToCart) return;
    setAddingToCart(true);
    setError(null);
    try {
      const out = await addToCart(getSessionId(), {
        id: product.id,
        name: product.name,
        price: product.price,
      });
      if (out.status !== "ok") {
        throw new Error(out.message || "Could not add to cart.");
      }
      setCart(cartFrom(out));
      useStore.getState().setToolStatus(
        `Added to cart — ${out.item_count ?? 1} item${(out.item_count ?? 1) === 1 ? "" : "s"}, ` +
          `${fmtPrice(out.total, out.currency)} total`
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setAddingToCart(false);
    }
  }

  // Refresh from the server (captures items the voice assistant added too) and
  // toggle the trolley panel open/closed.
  async function refreshCart() {
    try {
      const out = await fetchCart(getSessionId());
      if (out.status === "ok") setCart(cartFrom(out));
    } catch {
      /* leave the last-known cart in place */
    }
  }

  function toggleCart() {
    const open = !cartOpen;
    setCartOpen(open);
    if (open) refreshCart();
  }

  async function onRemoveFromCart(productId: string) {
    if (removingId) return;
    setRemovingId(productId);
    setError(null);
    try {
      const out = await removeFromCart(getSessionId(), productId);
      if (out.status !== "ok") throw new Error(out.message || "Could not remove item.");
      setCart(cartFrom(out));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRemovingId(null);
    }
  }

  // --- typed checkout details ---
  function setField<K extends keyof CheckoutDetails>(key: K, value: CheckoutDetails[K]) {
    setCheckout({ ...checkout, [key]: value });
    if (checkoutSaved) setCheckoutSaved(false); // edits invalidate the saved badge
  }

  async function onSaveDetails(e: React.FormEvent) {
    e.preventDefault();
    if (savingDetails) return;
    setSavingDetails(true);
    setError(null);
    try {
      const out = await saveCheckoutDetails(getSessionId(), checkout);
      if (out.status !== "ok") throw new Error(out.message || "Could not save details.");
      setCheckoutSaved(true);
      setCheckoutOpen(false);
      useStore.getState().setToolStatus(
        "Details saved — tell the assistant you're ready to pay."
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSavingDetails(false);
    }
  }

  async function submitTrack(e: React.FormEvent) {
    e.preventDefault();
    const num = trackNum.trim();
    if (!num || trackBusy) return;
    setTrackBusy(true);
    setTrackErr(null);
    try {
      const out = await trackOrder(num);
      if (out.status !== "ok" || !out.item) {
        throw new Error(out.message || "We couldn't find that order.");
      }
      addTracking(out.item as TrackingItem);
      setTrackNum("");
      setTrackOpen(false);
    } catch (err) {
      setTrackErr((err as Error).message);
    } finally {
      setTrackBusy(false);
    }
  }

  async function onTryOnPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    const url = URL.createObjectURL(f);
    photoUrlRef.current = url;
    setNeedPhoto(false);
    try {
      await uploadPhoto(getSessionId(), f);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      if (tryOnFileRef.current) tryOnFileRef.current.value = "";
    }
    const product = pendingProductRef.current;
    pendingProductRef.current = null;
    if (product) runTryOn(product, url);
  }

  function closeProduct() {
    setSelected(null);
    setNeedPhoto(false);
    pendingProductRef.current = null;
  }

  function exitFitting() {
    exitTryOn();
    requestTeleport({ x: 0, z: 9, yaw: 0 }); // back to the entrance
  }

  return (
    <>
      {/* top-left: where am I + controls hint */}
      <div style={panel({ top: 16, left: 16 })}>
        <div style={{ fontWeight: 700, fontSize: 15 }}>
          {section === "men" ? "👔 Men's section" : "👗 Women's section"}
        </div>
        <div style={{ fontSize: 12, opacity: 0.7, marginTop: 4, lineHeight: 1.5 }}>
          Arrows / WASD to walk · drag to look
          <br />
          Walk up to the assistant and tap 🎤
        </div>
      </div>

      {/* top-right: language + photo */}
      <div style={{ ...panel({ top: 16, right: 16 }), display: "flex", gap: 8, alignItems: "center" }}>
        <select
          value={lang}
          onChange={(e) => changeLang(e.target.value as Lang)}
          style={{ padding: "6px 8px", borderRadius: 8, border: "1px solid #ddd", fontSize: 13 }}
        >
          {LANGS.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </select>
        <button onClick={() => fileRef.current?.click()} style={iconBtn} title="Upload a photo for try-on">
          📷
        </button>
        <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={onPhoto} />
        <button
          onClick={toggleCart}
          style={{ ...iconBtn, position: "relative", fontSize: 18 }}
          title="View your cart"
          aria-label="Cart"
        >
          🛒
          {cart.count > 0 && <span style={cartBadge}>{cart.count}</span>}
        </button>
        <button
          onClick={() => setCheckoutOpen(true)}
          style={{ ...iconBtn, position: "relative", fontSize: 18 }}
          title="Type your delivery details"
          aria-label="Delivery details"
        >
          📝
          {checkoutSaved && <span style={{ ...cartBadge, background: "#196b3a" }}>✓</span>}
        </button>
        <button
          onClick={() => { setTrackErr(null); setTrackOpen((v) => !v); }}
          style={{ ...iconBtn, fontSize: 18, opacity: trackOpen ? 1 : 0.85 }}
          title="Track an order"
          aria-label="Track an order"
        >
          📦
        </button>
        <button
          onClick={() => setCaptionsHidden(!captionsHidden)}
          style={{ ...iconBtn, fontSize: 18, opacity: captionsHidden ? 0.4 : 1 }}
          title={captionsHidden ? "Show subtitles" : "Hide subtitles"}
          aria-label={captionsHidden ? "Show subtitles" : "Hide subtitles"}
        >
          💬
        </button>
      </div>

      {/* expandable cart trolley */}
      {cartOpen && (
        <div style={{ ...panel({ top: 64, right: 16 }), width: 300, maxWidth: "calc(100% - 32px)", padding: 0, overflow: "hidden" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 14px", borderBottom: "1px solid #eee" }}>
            <div style={{ fontWeight: 700 }}>🛒 Your cart{cart.count > 0 ? ` · ${cart.count}` : ""}</div>
            <button onClick={() => setCartOpen(false)} style={iconBtn} aria-label="Close cart">
              ✕
            </button>
          </div>
          {cart.items.length === 0 ? (
            <div style={{ padding: "18px 14px", fontSize: 13, opacity: 0.65 }}>
              Your cart is empty. Open a product and tap “🛒 Add to cart”.
            </div>
          ) : (
            <>
              <div style={{ maxHeight: 300, overflowY: "auto" }}>
                {cart.items.map((line) => (
                  <div
                    key={line.product_id}
                    style={{ display: "flex", justifyContent: "space-between", gap: 10, padding: "10px 14px", borderBottom: "1px solid #f2f2f2" }}
                  >
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {line.name}
                      </div>
                      <div style={{ fontSize: 12, opacity: 0.6, marginTop: 2 }}>
                        {line.quantity} × {fmtPrice(line.unit_price, cart.currency)}
                      </div>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, whiteSpace: "nowrap" }}>
                        {fmtPrice(line.unit_price * line.quantity, cart.currency)}
                      </div>
                      <button
                        onClick={() => onRemoveFromCart(line.product_id)}
                        disabled={removingId === line.product_id}
                        style={{ ...iconBtn, fontSize: 15, color: "#a12", opacity: removingId === line.product_id ? 0.4 : 1 }}
                        title="Remove from cart"
                        aria-label={`Remove ${line.name}`}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", padding: "12px 14px", fontWeight: 700, borderTop: "1px solid #eee" }}>
                <span>Total</span>
                <span style={{ color: "#7a5c10" }}>{fmtPrice(cart.total, cart.currency)}</span>
              </div>
              <div style={{ padding: "0 14px 14px" }}>
                <button
                  onClick={() => { setCartOpen(false); setCheckoutOpen(true); }}
                  style={{ ...payBtn, width: "100%", textAlign: "center", background: checkoutSaved ? "#196b3a" : "#9b3463" }}
                >
                  {checkoutSaved ? "✓ Delivery details saved — edit" : "📝 Type delivery details"}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* typed buyer + delivery details form */}
      {checkoutOpen && (
        <div style={modalBackdrop} onClick={() => setCheckoutOpen(false)}>
          <form style={modal} onClick={(e) => e.stopPropagation()} onSubmit={onSaveDetails}>
            <button type="button" onClick={() => setCheckoutOpen(false)} style={{ ...iconBtn, position: "absolute", top: 8, right: 8 }}>
              ✕
            </button>
            <h3 style={{ margin: "0 0 4px", fontSize: 18 }}>📝 Your delivery details</h3>
            <p style={{ fontSize: 12.5, opacity: 0.7, lineHeight: 1.5, margin: "0 0 14px" }}>
              Type these in so the spelling is exactly right — the assistant won&apos;t have to
              guess your name or address by ear. Used for both recipient and sender.
            </p>
            <label style={fieldLabel}>
              Full name
              <input style={fieldInput} value={checkout.name} onChange={(e) => setField("name", e.target.value)} placeholder="e.g. Nimal Perera" required />
            </label>
            <label style={fieldLabel}>
              Mobile number
              <input style={fieldInput} value={checkout.phone} onChange={(e) => setField("phone", e.target.value)} placeholder="e.g. 0771234567" inputMode="tel" required />
            </label>
            <label style={fieldLabel}>
              Delivery address
              <textarea style={{ ...fieldInput, minHeight: 56, resize: "vertical" }} value={checkout.address} onChange={(e) => setField("address", e.target.value)} placeholder="House / street, area" required />
            </label>
            <div style={{ display: "flex", gap: 10 }}>
              <label style={{ ...fieldLabel, flex: 1 }}>
                City
                <input style={fieldInput} value={checkout.city} onChange={(e) => setField("city", e.target.value)} placeholder="e.g. Colombo" required />
              </label>
              <label style={{ ...fieldLabel, flex: 1 }}>
                Delivery date
                <input type="date" style={fieldInput} value={checkout.date} min={new Date().toISOString().slice(0, 10)} onChange={(e) => setField("date", e.target.value)} required />
              </label>
            </div>
            <label style={fieldLabel}>
              Delivery note (optional)
              <input style={fieldInput} value={checkout.instructions ?? ""} onChange={(e) => setField("instructions", e.target.value)} placeholder="e.g. leave at reception" />
            </label>
            <button type="submit" disabled={savingDetails} style={{ ...payBtn, width: "100%", textAlign: "center", marginTop: 6, opacity: savingDetails ? 0.7 : 1 }}>
              {savingDetails ? "Saving…" : "Save details"}
            </button>
          </form>
        </div>
      )}

      {/* error toast */}
      {error && (
        <div style={{ ...panel({ top: 16 }), left: "50%", transform: "translateX(-50%)", background: "#fdecec", color: "#a12", maxWidth: 420 }}>
          ⚠️ {error}
          <button onClick={() => setError(null)} style={{ ...iconBtn, marginLeft: 8 }}>
            ✕
          </button>
        </div>
      )}

      {/* placed orders -> Pay now */}
      {orders.length > 0 && (
        <div style={{ ...panel({ bottom: 150, left: 16 }), maxWidth: 280 }}>
          {orders.map((o, i) => (
            <div key={i} style={{ marginBottom: i < orders.length - 1 ? 10 : 0 }}>
              <div style={{ fontWeight: 700 }}>✅ Order placed{o.order_ref ? " · " + o.order_ref : ""}</div>
              {o.grand_total != null && (
                <div style={{ fontSize: 13, margin: "4px 0" }}>
                  Total: <b>{fmtPrice(o.grand_total, o.currency)}</b>
                </div>
              )}
              {o.checkout_url && (
                <a href={o.checkout_url} target="_blank" rel="noopener" style={payBtn}>
                  💳 Pay now
                </a>
              )}
              {o.expires_at && <div style={{ fontSize: 11, opacity: 0.6, marginTop: 4 }}>Link expires: {o.expires_at}</div>}
            </div>
          ))}
        </div>
      )}

      {/* track-an-order input box (typed number — avoids voice mis-hearing) */}
      {trackOpen && (
        <div style={{ ...panel({ top: 70, right: 16 }), width: 250 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
            <div style={{ fontWeight: 700 }}>📦 Track an order</div>
            <button onClick={() => setTrackOpen(false)} style={iconBtn} aria-label="Close">
              ✕
            </button>
          </div>
          <form onSubmit={submitTrack}>
            <input
              autoFocus
              value={trackNum}
              onChange={(e) => { setTrackNum(e.target.value); setTrackErr(null); }}
              placeholder="Order number, e.g. VPAY827982BA"
              style={fieldInput}
            />
            {trackErr && <div style={{ color: "#a12", fontSize: 12, marginTop: 6 }}>{trackErr}</div>}
            <button
              type="submit"
              disabled={trackBusy || !trackNum.trim()}
              style={{ ...payBtn, width: "100%", textAlign: "center", marginTop: 8, opacity: trackBusy || !trackNum.trim() ? 0.6 : 1 }}
            >
              {trackBusy ? "Checking…" : "Track order"}
            </button>
            <div style={{ fontSize: 11, opacity: 0.6, marginTop: 6 }}>
              The number from your order confirmation email.
            </div>
          </form>
        </div>
      )}

      {/* order tracking -> status + delivery timeline */}
      {tracking.length > 0 && (
        <div style={{ ...panel({ bottom: 150, right: 16 }), maxWidth: 300, maxHeight: "52vh", overflowY: "auto" }}>
          {tracking.map((t, i) => {
            const done = ["delivered", "shipped", "out for delivery"].includes(
              String(t.status || "").toLowerCase()
            );
            const amt = t.amount == null || t.amount === "" ? null : Number(t.amount);
            const steps = t.progress ?? [];
            return (
              <div key={i} style={{ marginBottom: i < tracking.length - 1 ? 14 : 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 700 }}>
                  <span>📦 {t.order_number || "Order"}</span>
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 700,
                      padding: "2px 8px",
                      borderRadius: 999,
                      color: done ? "#1b6b3a" : "#9a6a12",
                      background: done ? "#e7f3ec" : "#fbf2dd",
                    }}
                  >
                    {t.status_display || t.status || "Unknown"}
                  </span>
                  <button
                    onClick={() => removeTracking(t.order_number)}
                    style={{ ...iconBtn, marginLeft: "auto", fontSize: 14, opacity: 0.6 }}
                    title="Dismiss"
                    aria-label="Dismiss tracking card"
                  >
                    ✕
                  </button>
                </div>
                {(amt != null || t.delivery_date) && (
                  <div style={{ fontSize: 13, margin: "5px 0" }}>
                    {amt != null && Number.isFinite(amt) && (
                      <>
                        Total: <b>{fmtPrice(amt, t.currency)}</b>
                      </>
                    )}
                    {amt != null && t.delivery_date ? " · " : ""}
                    {t.delivery_date && (
                      <>
                        Delivery: <b>{t.delivery_date}</b>
                      </>
                    )}
                  </div>
                )}
                {t.recipient_name && (
                  <div style={{ fontSize: 12, opacity: 0.65 }}>
                    To: {t.recipient_name}
                    {t.recipient_city ? " · " + t.recipient_city : ""}
                  </div>
                )}
                {steps.length > 0 && (
                  <div style={{ marginTop: 8, borderLeft: "2px solid #cfe6d8", paddingLeft: 12 }}>
                    {steps.map((p, j) => {
                      const last = j === steps.length - 1;
                      return (
                        <div key={j} style={{ position: "relative", padding: "3px 0" }}>
                          <span
                            style={{
                              position: "absolute",
                              left: -17,
                              top: 7,
                              width: 7,
                              height: 7,
                              borderRadius: "50%",
                              background: last ? "#196b3a" : "#b9c8bf",
                              border: "2px solid #fff",
                            }}
                          />
                          <div
                            style={{
                              fontSize: 12.5,
                              fontWeight: last ? 700 : 400,
                              color: last ? "#196b3a" : "#333",
                            }}
                          >
                            {p.step}
                          </div>
                          {p.timestamp && <div style={{ fontSize: 10.5, opacity: 0.55 }}>{p.timestamp}</div>}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* captions (dismissable — they can cover the small mobile screen) */}
      {!captionsHidden && (userCaption || userPartial || botCaption || toolStatus) && (
        <div style={{ ...panel({ bottom: 110 }), left: "50%", transform: "translateX(-50%)", maxWidth: 560, width: "calc(100% - 32px)", paddingRight: 30 }}>
          <button
            onClick={() => setCaptionsHidden(true)}
            style={{ ...iconBtn, position: "absolute", top: 4, right: 6, fontSize: 14, opacity: 0.6 }}
            title="Hide subtitles"
            aria-label="Hide subtitles"
          >
            ✕
          </button>
          {userPartial ? (
            // in-progress utterance takes priority over the last completed one
            <div style={{ fontSize: 13, opacity: 0.4, fontStyle: "italic" }}>You: {userPartial}…</div>
          ) : (
            userCaption && <div style={{ fontSize: 13, opacity: 0.6 }}>You: {userCaption}</div>
          )}
          {toolStatus && <div style={{ fontSize: 12, color: "#7a5c10", margin: "2px 0" }}>🔎 {toolStatus}</div>}
          {botCaption && <div style={{ fontSize: 15, marginTop: 2 }}>{botCaption}</div>}
        </div>
      )}

      {/* on-screen movement joystick (touch devices only) */}
      <Joystick />

      {/* mic (hidden while inside the fitting room) */}
      <div
        style={{
          position: "fixed",
          bottom: 28,
          left: "50%",
          transform: "translateX(-50%)",
          textAlign: "center",
          display: tryOn.active ? "none" : "block",
        }}
      >
        <button
          onClick={toggleMic}
          disabled={busy}
          style={{
            ...micBtn,
            background: listening ? "#d33" : near ? "#b8860b" : "#1d1d1f",
            boxShadow: near && !listening ? "0 0 0 6px rgba(184,134,11,0.25)" : micBtn.boxShadow,
            cursor: busy ? "wait" : "pointer",
          }}
        >
          {micLabel}
        </button>
      </div>

      {/* product detail */}
      {selected && (() => {
        const stock = stockInfo(selected);
        return (
        <div style={modalBackdrop} onClick={closeProduct}>
          <div style={productCard} onClick={(e) => e.stopPropagation()}>
            {/* image stage with floating close */}
            <div style={imageStage}>
              {selected.image_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={imgUrl(selected.image_url) || undefined}
                  alt={selected.name || "product"}
                  style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }}
                />
              ) : (
                <span style={{ fontSize: 44, opacity: 0.25 }}>👗</span>
              )}
              <button onClick={closeProduct} style={closeFab} aria-label="Close">
                ✕
              </button>
            </div>

            {/* content */}
            <div style={{ padding: "18px 22px 22px" }}>
              <h3 style={productTitle}>{selected.name || "Product"}</h3>

              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, marginTop: 10 }}>
                <div style={priceText}>
                  {selected.price != null ? new Intl.NumberFormat("en-LK").format(selected.price) : "—"}
                  <span style={priceCurrency}>{selected.currency || "LKR"}</span>
                </div>
                <span style={{ ...stockPill, color: stock.color, background: stock.bg }}>
                  <span style={{ width: 6, height: 6, borderRadius: 99, background: stock.color, display: "inline-block" }} />
                  {stock.label}
                </span>
              </div>

              <div style={goldRule} />

              <p style={descText}>
                {selected.summary?.trim()
                  ? selected.summary
                  : "Full details for this piece are on Kapruka — tap “View on Kapruka” below."}
              </p>

              {needPhoto ? (
                <div style={{ marginTop: 16, padding: 16, background: "#faf3f7", borderRadius: 14, border: "1px solid #f0dbe6" }}>
                  <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4, color: "#7a2750" }}>📸 Upload your photo</div>
                  <div style={{ fontSize: 12.5, color: "#8a6478", lineHeight: 1.55, marginBottom: 14 }}>
                    Use a clear, front-facing full-body photo. We&apos;ll dress you in this piece and show the result on the
                    fitting-room mirror. Your photo is never saved publicly.
                  </div>
                  <div style={{ display: "flex", gap: 10 }}>
                    <button onClick={() => tryOnFileRef.current?.click()} style={{ ...primaryBtn, flex: 1, background: "#9b3463", boxShadow: "0 6px 18px rgba(155,52,99,0.28)" }}>
                      📷  Choose photo
                    </button>
                    <button onClick={() => { setNeedPhoto(false); pendingProductRef.current = null; }} style={{ ...secondaryBtn, flex: "0 0 auto", padding: "11px 18px" }}>
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div style={{ marginTop: 16 }}>
                  {selected.id && selected.in_stock !== false && (
                    <button
                      onClick={onAddToCart}
                      disabled={addingToCart}
                      style={{ ...primaryBtn, opacity: addingToCart ? 0.7 : 1, cursor: addingToCart ? "wait" : "pointer" }}
                    >
                      {addingToCart ? "Adding…" : "🛒  Add to cart"}
                    </button>
                  )}
                  <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
                    <button onClick={onVirtualTryOn} style={{ ...secondaryBtn, color: "#9b3463", borderColor: "#eccfdd" }}>
                      👗  Virtual try-on
                    </button>
                    {selected.url && (
                      <a href={selected.url} target="_blank" rel="noopener" style={{ ...secondaryBtn, color: "#2a241c", borderColor: "#e4ded2" }}>
                        View on Kapruka ↗
                      </a>
                    )}
                  </div>
                </div>
              )}
              <input
                ref={tryOnFileRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                hidden
                onChange={onTryOnPhoto}
              />
            </div>
          </div>
        </div>
        );
      })()}

      {/* fitting-room overlay (shown while inside the try-on experience) */}
      {tryOn.active && (
        <div
          style={{
            ...panel({ bottom: 28 }),
            left: "50%",
            transform: "translateX(-50%)",
            textAlign: "center",
            maxWidth: 440,
            width: "calc(100% - 32px)",
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 4 }}>
            🪞 Fitting room{tryOn.productName ? " · " + tryOn.productName : ""}
          </div>
          <div style={{ fontSize: 13, opacity: 0.85, marginBottom: 10 }}>
            {tryOn.status === "generating"
              ? "Generating your look… (10–30s). Drag to look around."
              : tryOn.status === "ready"
              ? "Here's your look — tap the mirror to enlarge."
              : tryOn.status === "error"
              ? "⚠️ " + (tryOn.error || "Try-on failed.")
              : ""}
          </div>
          <button onClick={exitFitting} style={{ ...payBtn, background: "#1d1d1f" }}>
            ✕ Exit fitting room
          </button>
        </div>
      )}

      {/* full-screen enlarged try-on image */}
      {enlarge && (
        <div
          onClick={() => setEnlarge(null)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.85)",
            zIndex: 60,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={enlarge}
            alt="Your virtual try-on"
            style={{ maxWidth: "92%", maxHeight: "92%", borderRadius: 12, boxShadow: "0 10px 50px rgba(0,0,0,0.6)" }}
          />
          <button onClick={() => setEnlarge(null)} style={{ ...iconBtn, position: "fixed", top: 18, right: 22, color: "#fff", fontSize: 26 }}>
            ✕
          </button>
        </div>
      )}
    </>
  );
}

// --- inline styles ------------------------------------------------------
function panel(pos: CSSProperties): CSSProperties {
  return {
    position: "fixed",
    background: "rgba(255,255,255,0.92)",
    backdropFilter: "blur(8px)",
    borderRadius: 12,
    padding: "10px 14px",
    boxShadow: "0 4px 20px rgba(0,0,0,0.15)",
    fontSize: 14,
    zIndex: 10,
    ...pos,
  };
}

const iconBtn: CSSProperties = {
  border: "none",
  background: "transparent",
  cursor: "pointer",
  fontSize: 16,
  lineHeight: 1,
  padding: 4,
};

const fieldLabel: CSSProperties = {
  display: "block",
  fontSize: 12.5,
  fontWeight: 600,
  color: "#444",
  marginBottom: 10,
};

const fieldInput: CSSProperties = {
  display: "block",
  width: "100%",
  marginTop: 4,
  padding: "9px 10px",
  borderRadius: 9,
  border: "1px solid #ddd",
  fontSize: 14,
  fontWeight: 400,
  boxSizing: "border-box",
  fontFamily: "inherit",
};

const cartBadge: CSSProperties = {
  position: "absolute",
  top: -6,
  right: -6,
  minWidth: 16,
  height: 16,
  padding: "0 4px",
  borderRadius: 999,
  background: "#196b3a",
  color: "#fff",
  fontSize: 10,
  fontWeight: 700,
  lineHeight: "16px",
  textAlign: "center",
};

const micBtn: CSSProperties = {
  color: "#fff",
  border: "none",
  borderRadius: 999,
  padding: "16px 32px",
  fontSize: 17,
  fontWeight: 700,
  boxShadow: "0 6px 24px rgba(0,0,0,0.3)",
  zIndex: 10,
};

const payBtn: CSSProperties = {
  display: "inline-block",
  background: "#196b3a",
  color: "#fff",
  textDecoration: "none",
  padding: "9px 16px",
  borderRadius: 9,
  fontSize: 14,
  fontWeight: 600,
  border: "none",
  cursor: "pointer",
};

const modalBackdrop: CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.45)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 50,
};

const modal: CSSProperties = {
  position: "relative",
  background: "#fff",
  borderRadius: 16,
  padding: 20,
  width: "min(440px, calc(100% - 32px))",
  maxHeight: "85vh",
  overflowY: "auto",
  boxShadow: "0 20px 60px rgba(0,0,0,0.4)",
};

// --- product detail card (editorial-boutique treatment) ----------------
const SERIF = "Georgia, 'Iowan Old Style', 'Times New Roman', serif";

const productCard: CSSProperties = {
  position: "relative",
  background: "#fff",
  borderRadius: 18,
  width: "min(420px, calc(100% - 32px))",
  maxHeight: "88vh",
  overflowY: "auto",
  boxShadow: "0 24px 70px rgba(40,30,15,0.45)",
};

const imageStage: CSSProperties = {
  position: "relative",
  width: "100%",
  height: 280,
  background: "#f2eee6",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  borderRadius: "18px 18px 0 0",
  overflow: "hidden",
};

const closeFab: CSSProperties = {
  position: "absolute",
  top: 12,
  right: 12,
  width: 32,
  height: 32,
  borderRadius: 999,
  border: "none",
  cursor: "pointer",
  background: "rgba(255,255,255,0.92)",
  boxShadow: "0 2px 8px rgba(0,0,0,0.18)",
  fontSize: 13,
  color: "#5a5248",
  lineHeight: 1,
};

const productTitle: CSSProperties = {
  margin: 0,
  fontFamily: SERIF,
  fontSize: 22,
  lineHeight: 1.25,
  fontWeight: 600,
  color: "#211c16",
  letterSpacing: "0.2px",
};

const priceText: CSSProperties = {
  fontFamily: SERIF,
  fontSize: 24,
  fontWeight: 700,
  color: "#a87c28",
};

const priceCurrency: CSSProperties = {
  fontFamily: "inherit",
  fontSize: 12,
  fontWeight: 600,
  color: "#b9a06a",
  marginLeft: 6,
  letterSpacing: "0.5px",
};

const stockPill: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  padding: "4px 10px",
  borderRadius: 999,
  fontSize: 11.5,
  fontWeight: 700,
  whiteSpace: "nowrap",
};

const goldRule: CSSProperties = {
  height: 1,
  background: "linear-gradient(90deg,#d8c79a,rgba(216,199,154,0))",
  margin: "14px 0",
};

const descText: CSSProperties = {
  margin: 0,
  fontSize: 13.5,
  lineHeight: 1.6,
  color: "#5f574c",
};

const primaryBtn: CSSProperties = {
  display: "block",
  width: "100%",
  textAlign: "center",
  background: "#1b6b3a",
  color: "#fff",
  border: "none",
  padding: "13px 16px",
  borderRadius: 11,
  fontSize: 15,
  fontWeight: 700,
  cursor: "pointer",
  boxShadow: "0 6px 18px rgba(27,107,58,0.28)",
};

const secondaryBtn: CSSProperties = {
  flex: 1,
  textAlign: "center",
  textDecoration: "none",
  background: "#fff",
  border: "1.5px solid #e2ddd2",
  padding: "11px 12px",
  borderRadius: 11,
  fontSize: 13.5,
  fontWeight: 700,
  cursor: "pointer",
};
