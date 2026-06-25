"use client";

import { Environment, Lightformer, ContactShadows } from "@react-three/drei";
import { ROOM } from "@/lib/scene";

const CX = (ROOM.minX + ROOM.maxX) / 2;
const CZ = (ROOM.minZ + ROOM.maxZ) / 2;

// Procedural image-based lighting for the boutique. We build the environment
// from a handful of Lightformer panels instead of drei's `preset` (which would
// fetch an HDRI from a CDN) — this keeps the static export self-contained and
// deterministic. The Environment gives the steel rails, mirror, POS and the
// reflective floor something real to reflect; ContactShadows grounds the
// fixtures so they don't look like they're floating.
export default function Lighting() {
  return (
    <>
      {/* baked once (static scene) — soft warm key overhead + cooler side fills */}
      <Environment resolution={256} frames={1}>
        <color attach="background" args={["#101012"]} />
        {/* broad warm ceiling key */}
        <Lightformer
          form="rect"
          intensity={2.2}
          color="#fff2dc"
          position={[0, 9, 0]}
          rotation={[Math.PI / 2, 0, 0]}
          scale={[16, 24, 1]}
        />
        {/* cooler fills down each long wall — give garments shape */}
        <Lightformer
          form="rect"
          intensity={1.1}
          color="#dbe6f0"
          position={[-11, 4, 0]}
          rotation={[0, Math.PI / 2, 0]}
          scale={[20, 6, 1]}
        />
        <Lightformer
          form="rect"
          intensity={1.1}
          color="#dbe6f0"
          position={[11, 4, 0]}
          rotation={[0, -Math.PI / 2, 0]}
          scale={[20, 6, 1]}
        />
        {/* gentle front bounce so the back-wall product posters aren't flat */}
        <Lightformer
          form="rect"
          intensity={0.8}
          color="#fbf6ec"
          position={[0, 4, 13]}
          rotation={[0, Math.PI, 0]}
          scale={[18, 6, 1]}
        />
      </Environment>

      {/* soft grounding shadow under the fixtures */}
      <ContactShadows
        position={[CX, 0.02, CZ]}
        scale={Math.max(ROOM.maxX - ROOM.minX, ROOM.maxZ - ROOM.minZ) + 2}
        resolution={1024}
        far={6}
        blur={2.6}
        opacity={0.38}
        color="#2a241c"
      />
    </>
  );
}
