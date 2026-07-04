"use client";

import { CSSProperties, useEffect } from "react";
import { useState } from "react";

// Shown once on first load (gated by localStorage); reopenable from the "?" button.
const SEEN_KEY = "kapruka_welcome_seen";
const SERIF = "Georgia, 'Iowan Old Style', 'Times New Roman', serif";

const FEATURES: { icon: string; title: string; body: string }[] = [
  {
    icon: "🚶",
    title: "Explore the 3D store",
    body: "Walk with WASD, drag to look around, and walk up to the assistant to start talking.",
  },
  {
    icon: "🎙️",
    title: "Talk to a voice stylist",
    body: "Hands-free voice shopping in English, Tamil, and Sinhala — or just type.",
  },
  {
    icon: "🔍",
    title: "Find products",
    body: "Describe what you want — “a red shirt for men under 5,000” — and see live Kapruka product cards.",
  },
  {
    icon: "👗",
    title: "Get a full outfit styled",
    body: "e.g. “style me for a beach wedding under 20,000” → a complete coordinated look: saree/garment · shoes · bag · accessory.",
  },
  {
    icon: "🪞",
    title: "Virtually try it on",
    body: "Upload your photo and see yourself wearing any garment.",
  },
];

export default function WelcomeModal() {
  const [open, setOpen] = useState(false);

  // Open automatically the first time (no persisted "seen" flag). Read after mount
  // (not in render/useState) to stay SSR-safe: the static export prerenders it
  // closed, and this one-time open avoids a hydration mismatch. try/catch so a
  // locked-down localStorage (private mode) still shows it.
  useEffect(() => {
    try {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time external (localStorage) read on mount
      if (!localStorage.getItem(SEEN_KEY)) setOpen(true);
    } catch {
      setOpen(true);
    }
  }, []);

  // Close + remember, so it doesn't reappear on the next visit.
  function dismiss() {
    setOpen(false);
    try {
      localStorage.setItem(SEEN_KEY, "1");
    } catch {
      /* private mode — it'll just show again next load */
    }
  }

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") dismiss();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      {/* Always-available reopen affordance. */}
      <button
        onClick={() => setOpen(true)}
        style={helpBtn}
        title="How it works"
        aria-label="How it works"
      >
        ?
      </button>

      {open && (
        <div style={backdrop} onClick={dismiss}>
          <div style={card} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <button onClick={dismiss} style={closeBtn} aria-label="Close">
              ✕
            </button>

            <div style={eyebrow}>Kapruka · Welcome</div>
            <div style={title}>Your personal fashion stylist</div>
            <div style={subtitle}>Here’s what you can do in the store:</div>

            <ul style={list}>
              {FEATURES.map((f) => (
                <li key={f.title} style={row}>
                  <span style={iconWrap} aria-hidden>
                    {f.icon}
                  </span>
                  <span>
                    <span style={rowTitle}>{f.title}</span>
                    <span style={rowBody}>{f.body}</span>
                  </span>
                </li>
              ))}
            </ul>

            <button onClick={dismiss} style={cta}>
              Start shopping
            </button>
          </div>
        </div>
      )}
    </>
  );
}

// --- styles (match the HUD's boutique palette: ivory, brass, ink, magenta) ---
const helpBtn: CSSProperties = {
  position: "fixed",
  bottom: 20,
  right: 20,
  width: 38,
  height: 38,
  borderRadius: 999,
  border: "1px solid #efe7d5",
  background: "rgba(255,253,249,0.92)",
  backdropFilter: "blur(8px)",
  color: "#9b3463",
  fontSize: 18,
  fontWeight: 700,
  cursor: "pointer",
  boxShadow: "0 4px 16px rgba(0,0,0,0.14)",
  zIndex: 40,
  lineHeight: 1,
};

const backdrop: CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(28,22,16,0.5)",
  backdropFilter: "blur(3px)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: 16,
  zIndex: 60,
};

const card: CSSProperties = {
  position: "relative",
  background: "rgba(255,253,249,0.98)",
  border: "1px solid #efe7d5",
  borderRadius: 18,
  padding: "26px 26px 24px",
  width: "min(460px, calc(100% - 32px))",
  maxHeight: "86vh",
  overflowY: "auto",
  boxShadow: "0 24px 70px rgba(0,0,0,0.35)",
};

const closeBtn: CSSProperties = {
  position: "absolute",
  top: 14,
  right: 16,
  border: "none",
  background: "transparent",
  cursor: "pointer",
  fontSize: 15,
  color: "#8a7f70",
  lineHeight: 1,
  padding: 4,
};

const eyebrow: CSSProperties = {
  fontSize: 9.5,
  fontWeight: 700,
  letterSpacing: "1.4px",
  textTransform: "uppercase",
  color: "#b9a06a",
  marginBottom: 6,
};

const title: CSSProperties = {
  fontFamily: SERIF,
  fontSize: 23,
  color: "#211c16",
  lineHeight: 1.2,
};

const subtitle: CSSProperties = {
  fontSize: 13.5,
  color: "#8a7f70",
  marginTop: 6,
  marginBottom: 18,
};

const list: CSSProperties = {
  listStyle: "none",
  margin: 0,
  padding: 0,
  display: "flex",
  flexDirection: "column",
  gap: 14,
};

const row: CSSProperties = {
  display: "flex",
  gap: 13,
  alignItems: "flex-start",
};

const iconWrap: CSSProperties = {
  flex: "0 0 auto",
  width: 34,
  height: 34,
  borderRadius: 10,
  background: "#f6efe2",
  border: "1px solid #ece2cd",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  fontSize: 17,
};

const rowTitle: CSSProperties = {
  display: "block",
  fontSize: 14.5,
  fontWeight: 700,
  color: "#211c16",
  marginBottom: 2,
};

const rowBody: CSSProperties = {
  display: "block",
  fontSize: 13,
  lineHeight: 1.5,
  color: "#6a6153",
};

const cta: CSSProperties = {
  marginTop: 22,
  width: "100%",
  border: "none",
  borderRadius: 999,
  background: "#9b3463",
  color: "#fff",
  fontSize: 15,
  fontWeight: 700,
  padding: "12px 16px",
  cursor: "pointer",
  boxShadow: "0 8px 20px rgba(155,52,99,0.26)",
};
