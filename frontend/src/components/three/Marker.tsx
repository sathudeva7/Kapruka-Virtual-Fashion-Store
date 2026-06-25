"use client";

import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Billboard, Text } from "@react-three/drei";
import * as THREE from "three";
import { TALK_SPOT, MARKER_RADIUS } from "@/lib/scene";
import { useStore } from "@/lib/store";

// A GTA-style "stand here to talk" marker: a glowing column of light, a rotating
// floor ring and a floating prompt. Turns green when the player is inside it
// (which is also what enables the mic). Walk into it to talk to the assistant.
export default function Marker() {
  const near = useStore((s) => s.nearAssistant);
  const beam = useRef<THREE.Mesh>(null);
  const ring = useRef<THREE.Mesh>(null);
  const beamMat = useRef<THREE.MeshBasicMaterial>(null);

  useFrame((st) => {
    const t = st.clock.elapsedTime;
    if (beam.current) {
      const s = 1 + Math.sin(t * 2) * 0.05;
      beam.current.scale.set(s, 1, s);
    }
    if (beamMat.current) beamMat.current.opacity = 0.22 + (Math.sin(t * 2) + 1) * 0.06;
    if (ring.current) ring.current.rotation.z = t * 0.6;
  });

  const color = near ? "#39d98a" : "#f3c14b";
  const r = MARKER_RADIUS;

  return (
    <group position={TALK_SPOT}>
      {/* column of light (half height) */}
      <mesh ref={beam} position={[0, 0.65, 0]}>
        <cylinderGeometry args={[r * 0.72, r * 0.72, 1.3, 32, 1, true]} />
        <meshBasicMaterial
          ref={beamMat}
          color={color}
          transparent
          opacity={0.28}
          side={THREE.DoubleSide}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>

      {/* rotating floor ring */}
      <mesh ref={ring} position={[0, 0.04, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[r * 0.66, r, 48]} />
        <meshBasicMaterial color={color} transparent opacity={0.7} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>

      {/* soft inner disc */}
      <mesh position={[0, 0.02, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[r * 0.66, 40]} />
        <meshBasicMaterial color={color} transparent opacity={0.12} depthWrite={false} />
      </mesh>

      {/* floating prompt */}
      <Billboard position={[0, 1.8, 0]}>
        <Text fontSize={0.3} color={color} anchorX="center" anchorY="middle" outlineWidth={0.02} outlineColor="#1a1a1a">
          {near ? "● Tap 🎤 to talk" : "Stand here to talk 💬"}
        </Text>
      </Billboard>
    </group>
  );
}
