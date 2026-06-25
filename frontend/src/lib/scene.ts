// Shared world geometry — used by the player controller (movement clamp +
// section detection), the room mesh, and product-rack placement so they all
// agree on where things are.
import type { Section } from "./store";

export const ROOM = {
  minX: -10,
  maxX: 10,
  minZ: -12,
  maxZ: 12,
  height: 5.5, // tall enough for a 2-row gallery wall under the section sign
  // keep the camera this far off the walls
  margin: 0.6,
};

export const EYE_HEIGHT = 1.6;

// The store is split left/right at x = 0: Women on the left (-x), Men on the
// right (+x). The divider has a small dead-band so the active section doesn't
// flicker when you stand exactly on the line.
export const DIVIDER_X = 0;

export interface SectionDef {
  key: Section;
  label: string;
  color: string; // accent for signage / floor strip
  centerX: number; // middle of this half (for racks/signage)
  minX: number;
  maxX: number;
}

export const SECTIONS: Record<Section, SectionDef> = {
  women: {
    key: "women",
    label: "WOMEN",
    color: "#e0608a",
    centerX: -5,
    minX: ROOM.minX,
    maxX: DIVIDER_X,
  },
  men: {
    key: "men",
    label: "MEN",
    color: "#4a90d9",
    centerX: 5,
    minX: DIVIDER_X,
    maxX: ROOM.maxX,
  },
};

export function sectionForX(x: number): Section {
  return x < DIVIDER_X ? "women" : "men";
}

// The assistant stands centre-stage; the player spawns near the entrance facing
// it. The GTA-style marker is a "talk spot" just in front of the assistant —
// stand in it to start talking.
export const ASSISTANT_POS: [number, number, number] = [0, 0, 3];
export const TALK_SPOT: [number, number, number] = [0, 0, 5.6];
export const MARKER_RADIUS = 1.7; // walk inside this radius of the talk spot to talk
export const SPAWN: [number, number, number] = [0, EYE_HEIGHT, 10];

// The functional fitting room — the player is teleported here for virtual try-on.
// Axis-aligned (opening faces +z, toward the entrance), placed in the open front-
// right so it doesn't sit in front of the back-wall product racks. `standSpot` is
// just inside the opening, looking -z into the booth (yaw 0 = camera faces -z).
export const TRYON_ROOM = {
  position: [6.5, 0, 6] as [number, number, number],
  rotation: 0,
  half: 1.15, // interior half-width/depth
  height: 2.6,
  standSpot: { x: 6.5, z: 7.0, yaw: 0 },
};
