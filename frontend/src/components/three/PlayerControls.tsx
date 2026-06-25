"use client";

import { useEffect, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { useKeyboardControls } from "@react-three/drei";
import * as THREE from "three";
import { ROOM, EYE_HEIGHT, SPAWN, TALK_SPOT, MARKER_RADIUS, ASSISTANT_POS, sectionForX } from "@/lib/scene";
import { useStore } from "@/lib/store";

export type Controls = "forward" | "back" | "turnL" | "turnR" | "strafeL" | "strafeR";

export const KEYMAP = [
  { name: "forward", keys: ["ArrowUp", "KeyW"] },
  { name: "back", keys: ["ArrowDown", "KeyS"] },
  { name: "turnL", keys: ["ArrowLeft"] },
  { name: "turnR", keys: ["ArrowRight"] },
  { name: "strafeL", keys: ["KeyA"] },
  { name: "strafeR", keys: ["KeyD"] },
];

const MOVE_SPEED = 4.2; // metres / second
const TURN_SPEED = 2.0; // radians / second
const DRAG_SENS = 0.005;

export default function PlayerControls() {
  const camera = useThree((s) => s.camera);
  const gl = useThree((s) => s.gl);
  const [, getKeys] = useKeyboardControls<Controls>();

  const yaw = useRef(0); // yaw 0 => camera looks down -z, into the store
  const pos = useRef(new THREE.Vector3(...SPAWN));
  const lastSection = useRef<"men" | "women" | null>(null);
  const lastNear = useRef<boolean | null>(null);

  // Mouse-drag to look around (in addition to the arrow-key turn).
  useEffect(() => {
    const el = gl.domElement;
    let dragging = false;
    let lastX = 0;
    const down = (e: PointerEvent) => {
      dragging = true;
      lastX = e.clientX;
    };
    const move = (e: PointerEvent) => {
      if (!dragging) return;
      yaw.current -= (e.clientX - lastX) * DRAG_SENS;
      lastX = e.clientX;
    };
    const up = () => {
      dragging = false;
    };
    el.addEventListener("pointerdown", down);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      el.removeEventListener("pointerdown", down);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, [gl]);

  useFrame((_, dt) => {
    // consume a one-shot teleport (e.g. into the fitting room)
    const tp = useStore.getState().teleport;
    if (tp) {
      pos.current.set(tp.x, EYE_HEIGHT, tp.z);
      yaw.current = tp.yaw;
      useStore.getState().clearTeleport();
    }

    const k = getKeys();
    const mv = useStore.getState().move; // analog joystick (touch)
    if (k.turnL) yaw.current += TURN_SPEED * dt;
    if (k.turnR) yaw.current -= TURN_SPEED * dt;
    if (mv.x) yaw.current -= mv.x * TURN_SPEED * dt; // joystick: left/right turns

    const y = yaw.current;
    // camera forward (local -Z) and right (local +X) in world space
    const fwd = new THREE.Vector3(-Math.sin(y), 0, -Math.cos(y));
    const right = new THREE.Vector3(Math.cos(y), 0, -Math.sin(y));

    const dir = new THREE.Vector3();
    if (k.forward) dir.add(fwd);
    if (k.back) dir.sub(fwd);
    if (k.strafeR) dir.add(right);
    if (k.strafeL) dir.sub(right);
    if (mv.y) dir.addScaledVector(fwd, mv.y); // joystick: forward/back (analog)
    if (dir.lengthSq() > 0) {
      // Clamp (not normalize) so a half-pushed joystick walks at half speed,
      // while diagonal keyboard input still tops out at full speed.
      if (dir.lengthSq() > 1) dir.normalize();
      dir.multiplyScalar(MOVE_SPEED * dt);
      pos.current.x += dir.x;
      pos.current.z += dir.z;
    }

    // clamp inside the room (can't walk through walls)
    const m = ROOM.margin;
    pos.current.x = THREE.MathUtils.clamp(pos.current.x, ROOM.minX + m, ROOM.maxX - m);
    pos.current.z = THREE.MathUtils.clamp(pos.current.z, ROOM.minZ + m, ROOM.maxZ - m);
    pos.current.y = EYE_HEIGHT;

    // soft collision so you bump into the assistant instead of clipping through
    const adx = pos.current.x - ASSISTANT_POS[0];
    const adz = pos.current.z - ASSISTANT_POS[2];
    const ad = Math.hypot(adx, adz);
    const BLOCK = 1.5;
    if (ad < BLOCK && ad > 1e-4) {
      pos.current.x = ASSISTANT_POS[0] + (adx / ad) * BLOCK;
      pos.current.z = ASSISTANT_POS[2] + (adz / ad) * BLOCK;
    }

    camera.position.copy(pos.current);
    camera.rotation.set(0, y, 0, "YXZ");

    // section the player is standing in -> drives where products appear
    const section = sectionForX(pos.current.x);
    if (section !== lastSection.current) {
      lastSection.current = section;
      useStore.getState().setSection(section);
    }

    // inside the marker "talk spot" -> enable the talk prompt
    const near =
      Math.hypot(pos.current.x - TALK_SPOT[0], pos.current.z - TALK_SPOT[2]) < MARKER_RADIUS;
    if (near !== lastNear.current) {
      lastNear.current = near;
      useStore.getState().setNear(near);
    }
  });

  return null;
}
