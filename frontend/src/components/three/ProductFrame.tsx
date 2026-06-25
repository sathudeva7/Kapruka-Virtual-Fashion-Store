"use client";

import { useState } from "react";
import { Text } from "@react-three/drei";
import { ThreeEvent } from "@react-three/fiber";
import { useImgTexture } from "@/lib/useImgTexture";
import { useStore, type ProductItem } from "@/lib/store";

// One framed product "poster" on a rack. Width/height are decided by the rack
// layout (so the grid always fits the wall). Texture comes through the backend
// /img proxy (CDN has no CORS headers, which a WebGL texture load requires).
// Loaded imperatively so a missing image degrades to a placeholder.
export default function ProductFrame({
  item,
  position,
  w,
  h,
}: {
  item: ProductItem;
  position: [number, number, number];
  w: number;
  h: number;
}) {
  const tex = useImgTexture(item.image_url);
  const [hover, setHover] = useState(false);
  const setSelected = useStore((s) => s.setSelected);

  const price =
    item.price != null
      ? new Intl.NumberFormat("en-LK").format(item.price) + " " + (item.currency || "LKR")
      : "—";

  const onClick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    setSelected(item);
  };

  const nameSize = Math.min(0.13, w * 0.11);
  const priceSize = Math.min(0.15, w * 0.13);

  return (
    <group
      position={position}
      onClick={onClick}
      onPointerOver={(e) => {
        e.stopPropagation();
        setHover(true);
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={() => {
        setHover(false);
        document.body.style.cursor = "auto";
      }}
      scale={hover ? 1.06 : 1}
    >
      {/* frame border — sits behind the picture (front face at z=0.03) */}
      <mesh position={[0, 0, 0]}>
        <boxGeometry args={[w + 0.1, h + 0.1, 0.06]} />
        <meshStandardMaterial color={hover ? "#b8860b" : "#3a2f22"} />
      </mesh>
      {/* picture — clearly in front of the border so they never z-fight */}
      <mesh position={[0, 0, 0.07]}>
        <planeGeometry args={[w, h]} />
        {tex ? (
          <meshBasicMaterial map={tex} toneMapped={false} />
        ) : (
          <meshStandardMaterial color="#cfc6b6" />
        )}
      </mesh>
      {/* name + price plate, below the frame */}
      <Text
        position={[0, -h / 2 - 0.16, 0.1]}
        fontSize={nameSize}
        maxWidth={w + 0.2}
        textAlign="center"
        color="#1d1d1f"
        anchorX="center"
        anchorY="top"
      >
        {(item.name || "Product").slice(0, 44)}
      </Text>
      <Text
        position={[0, -h / 2 - 0.16 - nameSize * 2.4, 0.1]}
        fontSize={priceSize}
        color="#7a5c10"
        anchorX="center"
        anchorY="top"
      >
        {price}
      </Text>
    </group>
  );
}
