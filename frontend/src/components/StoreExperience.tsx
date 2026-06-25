"use client";

import { Suspense, useEffect } from "react";
import * as THREE from "three";
import { Canvas } from "@react-three/fiber";
import { KeyboardControls } from "@react-three/drei";
import { SPAWN } from "@/lib/scene";
import { useStore } from "@/lib/store";
import Store from "./three/Store";
import Lighting from "./three/Lighting";
import Decor from "./three/Decor";
import Assistant from "./three/Assistant";
import Marker from "./three/Marker";
import TryOnRoom from "./three/TryOnRoom";
import ProductRack from "./three/ProductRack";
import PlayerControls, { KEYMAP } from "./three/PlayerControls";
import HUD from "./hud/HUD";

export default function StoreExperience() {
  const seedFeatured = useStore((s) => s.seedFeatured);

  // Fill the racks with curated default products on first load so the store is
  // never empty before the visitor talks to the assistant.
  useEffect(() => {
    seedFeatured();
  }, [seedFeatured]);

  return (
    <div style={{ position: "fixed", inset: 0 }}>
      <KeyboardControls map={KEYMAP}>
        <Canvas
          shadows
          camera={{ position: SPAWN, fov: 70 }}
          dpr={[1, 2]}
          gl={{ toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.05 }}
        >
          <color attach="background" args={["#e7e1d6"]} />
          <fog attach="fog" args={["#e7e1d6", 22, 46]} />
          <Suspense fallback={null}>
            <Lighting />
            <Store />
            <Decor />
            <Assistant />
            <Marker />
            <TryOnRoom />
            <ProductRack section="women" />
            <ProductRack section="men" />
          </Suspense>
          <PlayerControls />
        </Canvas>
      </KeyboardControls>
      <HUD />
    </div>
  );
}
