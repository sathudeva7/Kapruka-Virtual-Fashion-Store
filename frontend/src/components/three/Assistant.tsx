"use client";

import { Component, ReactNode, Suspense, useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Billboard, Text, useGLTF, useAnimations } from "@react-three/drei";
import * as THREE from "three";
import { ASSISTANT_POS } from "@/lib/scene";
import { useStore } from "@/lib/store";

// Drop a rigged humanoid avatar here to make the assistant a realistic human.
// Any .glb works (Ready Player Me, Mixamo, etc.). See README for the 2-minute
// Ready Player Me path to get the exact business-attire look.
const AVATAR_URL = "/assistant.glb";
const TARGET_HEIGHT = 1.7; // metres — auto-scaled to this regardless of source

function NameTag() {
  return (
    <Billboard position={[0, 2.1, 0]}>
      <Text
        fontSize={0.16}
        color="#1d1d1f"
        anchorX="center"
        anchorY="middle"
        outlineWidth={0.012}
        outlineColor="#ffffff"
      >
        Tharushi · Your Stylist
      </Text>
    </Billboard>
  );
}

// --- the glTF human avatar -------------------------------------------------
function HumanAssistant() {
  const group = useRef<THREE.Group>(null);
  const { scene, animations } = useGLTF(AVATAR_URL);

  // Use the loaded scene directly (single instance) so the skinned-mesh ↔
  // skeleton binding stays intact and animations actually play. Cloning a
  // skinned glTF with scene.clone() breaks that binding (it shows the T-pose).
  // Auto-fit is applied to a wrapper <group>, not the cached scene.
  const { fitScale, yOffset } = useMemo(() => {
    const box = new THREE.Box3().setFromObject(scene);
    const size = new THREE.Vector3();
    box.getSize(size);
    const s = TARGET_HEIGHT / (size.y || 1);
    scene.traverse((o) => {
      o.castShadow = true;
    });
    return { fitScale: s, yOffset: -box.min.y * s };
  }, [scene]);

  const { actions, names } = useAnimations(animations, group);

  useEffect(() => {
    const idle = names.find((n) => /idle/i.test(n)) || names[0];
    if (idle && actions[idle]) {
      actions[idle].reset().fadeIn(0.3).play();
      return () => {
        actions[idle]?.fadeOut(0.3);
      };
    }
  }, [actions, names]);

  // gentle sway if the model has no animation at all
  useFrame((st) => {
    if (group.current && names.length === 0) {
      group.current.rotation.y = Math.sin(st.clock.elapsedTime * 0.6) * 0.05;
    }
  });

  return (
    <group ref={group} position={ASSISTANT_POS} rotation={[0, 0, 0]}>
      <group scale={fitScale} position={[0, yOffset, 0]}>
        <primitive object={scene} />
      </group>
      {/* podium */}
      <mesh position={[0, 0.04, 0]} receiveShadow>
        <cylinderGeometry args={[0.65, 0.75, 0.08, 28]} />
        <meshStandardMaterial color="#d9d2c4" />
      </mesh>
      <NameTag />
    </group>
  );
}

// --- a primitive stylist (fallback if the .glb is missing or fails) --------
function PrimitiveAssistant() {
  const body = useRef<THREE.Group>(null);
  const connection = useStore((s) => s.connection);
  const active = connection === "live" || connection === "recording" || connection === "thinking";
  useFrame((state) => {
    if (body.current) body.current.position.y = Math.sin(state.clock.elapsedTime * 1.6) * 0.04;
  });
  return (
    <group position={ASSISTANT_POS}>
      <group ref={body}>
        <mesh position={[0, 1.62, 0]} castShadow>
          <sphereGeometry args={[0.22, 24, 24]} />
          <meshStandardMaterial color="#e8c9a0" />
        </mesh>
        <mesh position={[0, 1.72, -0.02]} castShadow>
          <sphereGeometry args={[0.235, 24, 24, 0, Math.PI * 2, 0, Math.PI / 1.7]} />
          <meshStandardMaterial color="#2b2018" />
        </mesh>
        <mesh position={[0, 1.12, 0]} castShadow>
          <capsuleGeometry args={[0.22, 0.5, 6, 16]} />
          <meshStandardMaterial color={active ? "#c8447a" : "#9b3463"} />
        </mesh>
        <mesh position={[0, 0.55, 0]} castShadow>
          <coneGeometry args={[0.42, 0.95, 24]} />
          <meshStandardMaterial color={active ? "#c8447a" : "#9b3463"} />
        </mesh>
      </group>
      <mesh position={[0, 0.06, 0]} receiveShadow>
        <cylinderGeometry args={[0.6, 0.7, 0.12, 28]} />
        <meshStandardMaterial color="#cdbb9a" />
      </mesh>
      <NameTag />
    </group>
  );
}

// --- error boundary: fall back to the primitive if the avatar can't load ---
class AvatarBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

export default function Assistant() {
  return (
    <AvatarBoundary fallback={<PrimitiveAssistant />}>
      <Suspense fallback={<PrimitiveAssistant />}>
        <HumanAssistant />
      </Suspense>
    </AvatarBoundary>
  );
}

useGLTF.preload(AVATAR_URL);
