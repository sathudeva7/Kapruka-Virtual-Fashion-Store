"use client";

import { Text } from "@react-three/drei";
import { ROOM, SECTIONS } from "@/lib/scene";
import { useStore, type Section } from "@/lib/store";
import ProductFrame from "./ProductFrame";

const WALL_Z = ROOM.minZ + 0.18; // sit just in front of the back wall

// Vertical band the gallery occupies on the wall: below the section sign,
// above the floor.
const BAND_TOP = ROOM.height - 1.3;
const BAND_BOTTOM = 0.6;
const BAND_H = BAND_TOP - BAND_BOTTOM;

// Lays the section's products out as a grid of framed posters on the back wall
// of that half of the store. Frames are sized to fit the section width and wall
// height (max 2 rows), so a search of any size stays on the wall — no clipping
// behind the ceiling. Products land in the section the player is standing in
// (see store.addProduct).
export default function ProductRack({ section }: { section: Section }) {
  const items = useStore((s) => s.productsBySection[section]);
  const def = SECTIONS[section];

  const sectionW = Math.abs(def.maxX - def.minX) - 1.4; // usable width
  const n = items.length;

  return (
    <group>
      {/* shelf back-panel accent for the section */}
      <mesh position={[def.centerX, BAND_TOP + 0.15, WALL_Z - 0.05]}>
        <boxGeometry args={[Math.abs(def.maxX - def.minX) - 0.8, 0.05, 0.05]} />
        <meshStandardMaterial color={def.color} />
      </mesh>

      {n === 0 ? (
        <Text
          position={[def.centerX, (BAND_TOP + BAND_BOTTOM) / 2, WALL_Z + 0.1]}
          fontSize={0.24}
          maxWidth={6}
          textAlign="center"
          color="#9a9388"
          anchorX="center"
          anchorY="middle"
        >
          {`Ask the assistant for ${section}'s pieces…`}
        </Text>
      ) : (
        (() => {
          const rows = n <= 5 ? 1 : 2;
          const cols = Math.ceil(n / rows);
          const cellW = sectionW / cols;
          const cellH = BAND_H / rows;
          const frameW = Math.min(cellW * 0.82, 1.5);
          const frameH = Math.min(cellH * 0.62, frameW * 1.25, 1.7);

          return items.map((item, i) => {
            const row = Math.floor(i / cols);
            const col = i % cols;
            const x = def.centerX - ((cols - 1) * cellW) / 2 + col * cellW;
            const cellTop = BAND_TOP - row * cellH;
            const y = cellTop - frameH / 2 - 0.05;
            return (
              <ProductFrame
                key={item.id || `${section}-${i}`}
                item={item}
                position={[x, y, WALL_Z + 0.1]}
                w={frameW}
                h={frameH}
              />
            );
          });
        })()
      )}
    </group>
  );
}
