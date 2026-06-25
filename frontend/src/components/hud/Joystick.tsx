"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { useStore } from "@/lib/store";

// On-screen movement joystick for touch devices. Drag the thumb: vertical walks
// forward/back, horizontal turns. Writes an analog vector to the store, which
// PlayerControls applies each frame alongside the keyboard. Drag elsewhere on the
// canvas still looks around (handled in PlayerControls), so the two don't clash.
const BASE = 132; // px diameter of the joystick base
const KNOB = 58; // px diameter of the thumb
const MAX = (BASE - KNOB) / 2; // max thumb travel from centre

export default function Joystick() {
  const setMove = useStore((s) => s.setMove);
  const tryOnActive = useStore((s) => s.tryOn.active);
  const [isTouch, setIsTouch] = useState(false);
  const [knob, setKnob] = useState({ x: 0, y: 0 });
  const activeId = useRef<number | null>(null);
  const baseRef = useRef<HTMLDivElement>(null);

  // Only show on touch / coarse-pointer devices (desktop keeps keyboard + drag).
  useEffect(() => {
    const coarse =
      window.matchMedia?.("(pointer: coarse)").matches || "ontouchstart" in window;
    setIsTouch(!!coarse);
  }, []);

  // Stop sending movement if the joystick unmounts (e.g. entering the fitting room).
  useEffect(() => () => setMove({ x: 0, y: 0 }), [setMove]);

  if (!isTouch || tryOnActive) return null;

  const update = (clientX: number, clientY: number) => {
    const el = baseRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    let dx = clientX - (r.left + r.width / 2);
    let dy = clientY - (r.top + r.height / 2);
    const dist = Math.hypot(dx, dy);
    if (dist > MAX) {
      dx = (dx / dist) * MAX;
      dy = (dy / dist) * MAX;
    }
    setKnob({ x: dx, y: dy });
    setMove({ x: dx / MAX, y: -dy / MAX }); // screen-up (negative y) = forward
  };

  const onDown = (e: React.PointerEvent) => {
    activeId.current = e.pointerId;
    (e.target as Element).setPointerCapture(e.pointerId);
    update(e.clientX, e.clientY);
  };
  const onMove = (e: React.PointerEvent) => {
    if (activeId.current === e.pointerId) update(e.clientX, e.clientY);
  };
  const onUp = (e: React.PointerEvent) => {
    if (activeId.current !== e.pointerId) return;
    activeId.current = null;
    setKnob({ x: 0, y: 0 });
    setMove({ x: 0, y: 0 });
  };

  return (
    <div
      ref={baseRef}
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerCancel={onUp}
      style={base}
      aria-label="Movement joystick"
    >
      <div style={{ ...thumb, transform: `translate(${knob.x}px, ${knob.y}px)` }} />
    </div>
  );
}

const base: CSSProperties = {
  position: "fixed",
  bottom: 28,
  left: 22,
  width: BASE,
  height: BASE,
  borderRadius: "50%",
  background: "rgba(0,0,0,0.18)",
  border: "1.5px solid rgba(255,255,255,0.55)",
  boxShadow: "0 4px 18px rgba(0,0,0,0.25)",
  backdropFilter: "blur(2px)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  touchAction: "none", // we handle the gesture; don't let the page scroll/zoom
  zIndex: 20,
};

const thumb: CSSProperties = {
  width: KNOB,
  height: KNOB,
  borderRadius: "50%",
  background: "rgba(255,255,255,0.88)",
  boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
  pointerEvents: "none",
};
