"use client";

import * as THREE from "three";
import { useTexture, MeshReflectorMaterial, Text } from "@react-three/drei";
import { ROOM } from "@/lib/scene";

const W = ROOM.maxX - ROOM.minX;
const D = ROOM.maxZ - ROOM.minZ;
const H = ROOM.height;
const CX = (ROOM.minX + ROOM.maxX) / 2;
const CZ = (ROOM.minZ + ROOM.maxZ) / 2;

// Minimalist boutique shell: warm plaster walls, polished concrete floor, a
// clay accent wall behind the displays.
const PLASTER = "#ece6dc";
const PLASTER_SOFT = "#e6dfd3";
const CONCRETE = "#c7c3ba";
const CEILING = "#f4f0e9";
const CLAY = "#d7c3b3"; // accent wall (back, where products hang)

function Wall(props: {
  position: [number, number, number];
  args: [number, number, number];
  color?: string;
}) {
  return (
    <mesh position={props.position} receiveShadow>
      <boxGeometry args={props.args} />
      <meshStandardMaterial color={props.color || PLASTER} roughness={1} />
    </mesh>
  );
}

// The Kapruka wordmark logo (public/kapruka-logo.png, 625×110) — the only brand
// mark on the back wall. It's a light logo, so we mount it on a slim dark sign
// plate to read against the clay wall, centred on the wall.
function BrandLogo() {
  const tex = useTexture("/kapruka-logo.png");
  tex.colorSpace = THREE.SRGBColorSpace;
  const logoH = 0.7;
  const logoW = logoH * (625 / 110); // keep the logo's aspect ratio
  const y = H - 0.6; // high on the back wall
  const x = 0; // centred
  const zPlate = ROOM.minZ + 0.13;
  return (
    <group position={[x, y, 0]}>
      {/* dark sign plate (front face at minZ+0.16) */}
      <mesh position={[0, 0, zPlate]} castShadow>
        <boxGeometry args={[logoW + 0.34, logoH + 0.3, 0.06]} />
        <meshStandardMaterial color="#2e2a24" roughness={0.5} metalness={0.2} />
      </mesh>
      {/* logo plane sits clearly IN FRONT of the plate (avoid z-fighting) */}
      <mesh position={[0, 0, zPlate + 0.09]}>
        <planeGeometry args={[logoW, logoH]} />
        <meshBasicMaterial map={tex} transparent toneMapped={false} />
      </mesh>
    </group>
  );
}

// Store wordmark running along a side wall. `side` picks the wall: the left wall
// (x = minX) faces +x, the right wall (x = maxX) faces -x, so each sign is turned
// to read off the inner face. Mounted high like a boutique banner.
function WallSign({ side }: { side: "left" | "right" }) {
  const isLeft = side === "left";
  const x = isLeft ? ROOM.minX + 0.12 : ROOM.maxX - 0.12;
  const rotY = isLeft ? Math.PI / 2 : -Math.PI / 2;
  return (
    <Text
      position={[x, H - 1.0, CZ]}
      rotation={[0, rotY, 0]}
      fontSize={0.8}
      color="#5a5048"
      anchorX="center"
      anchorY="middle"
      letterSpacing={0.18}
    >
      KAPRUKA FASHION STORE
    </Text>
  );
}

export default function Store() {
  return (
    <group>
      {/* soft, even boutique lighting — the procedural Environment (<Lighting/>)
          carries most of the look now, so ambient/hemisphere are dialled back to
          avoid washing the scene out. One directional light keeps a sense of
          direction (and casts the fixtures' shadow). */}
      <hemisphereLight args={["#fbf7f0", "#cdbfa8", 0.5]} />
      <ambientLight intensity={0.22} />
      <directionalLight position={[5, 9, 7]} intensity={0.4} castShadow />

      {/* polished concrete floor — a soft real-time reflection of the garments
          and lights reads as a glossy showroom rather than a matte plane. Kept
          low-res + blurred + rough so it stays a subtle sheen, not a mirror. */}
      <mesh position={[CX, 0, CZ]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[W, D]} />
        <MeshReflectorMaterial
          color={CONCRETE}
          resolution={512}
          blur={[300, 100]}
          mixBlur={1}
          mixStrength={1.2}
          roughness={0.85}
          metalness={0.1}
          depthScale={1}
          minDepthThreshold={0.4}
          maxDepthThreshold={1.2}
          mirror={0}
        />
      </mesh>
      {/* ceiling */}
      <mesh position={[CX, H, CZ]} rotation={[Math.PI / 2, 0, 0]}>
        <planeGeometry args={[W, D]} />
        <meshStandardMaterial color={CEILING} roughness={1} />
      </mesh>

      {/* walls — back wall is the clay accent that the displays sit against */}
      <Wall position={[CX, H / 2, ROOM.minZ]} args={[W, H, 0.2]} color={CLAY} />
      <Wall position={[CX, H / 2, ROOM.maxZ]} args={[W, H, 0.2]} color={PLASTER_SOFT} />
      <Wall position={[ROOM.minX, H / 2, CZ]} args={[0.2, H, D]} />
      <Wall position={[ROOM.maxX, H / 2, CZ]} args={[0.2, H, D]} />

      {/* low plastered divider between the two sections */}
      <mesh position={[0, 0.45, CZ + 2]} castShadow receiveShadow>
        <boxGeometry args={[0.18, 0.9, D - 6]} />
        <meshStandardMaterial color={PLASTER} roughness={1} />
      </mesh>

      {/* the Kapruka logo is the only brand mark on the back wall */}
      <BrandLogo />

      {/* store wordmark on both side walls */}
      <WallSign side="left" />
      <WallSign side="right" />
    </group>
  );
}
