"use client";

import { useEffect, useRef, useState } from "react";
import { Text } from "@react-three/drei";
import { ThreeEvent } from "@react-three/fiber";
import * as THREE from "three";
import { TRYON_ROOM } from "@/lib/scene";
import { useStore } from "@/lib/store";

const WALL = "#e6dfd3";
const STEEL = "#9a9a9a";
const TIMBER = "#b48a5a";

// Load a raw URL (blob: object-URL for the photo, same-origin /static for the
// result) as a texture. NOT through the /img proxy — these are already loadable.
function useRawTexture(url: string | null): THREE.Texture | null {
  const [tex, setTex] = useState<THREE.Texture | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    setTex(null);
    if (!url) return;
    const loader = new THREE.TextureLoader();
    loader.load(
      url,
      (t) => {
        t.colorSpace = THREE.SRGBColorSpace;
        if (mounted.current) setTex(t);
      },
      undefined,
      () => {}
    );
    return () => {
      mounted.current = false;
    };
  }, [url]);
  return tex;
}

// The functional fitting room. The back wall is a "mirror" that shows the
// generated try-on result; a side wall shows the shopper's uploaded photo.
export default function TryOnRoom() {
  const h = TRYON_ROOM.half;
  const H = TRYON_ROOM.height;
  const tryOn = useStore((s) => s.tryOn);
  const setEnlarge = useStore((s) => s.setEnlarge);

  const photoTex = useRawTexture(tryOn.userPhotoUrl);
  const resultTex = useRawTexture(tryOn.resultUrl);

  const onResultClick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    if (tryOn.resultUrl) setEnlarge(tryOn.resultUrl);
  };

  return (
    <group position={TRYON_ROOM.position} rotation={[0, TRYON_ROOM.rotation, 0]}>
      {/* floor pad */}
      <mesh position={[0, 0.015, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[h * 2, h * 2]} />
        <meshStandardMaterial color="#bdb4a3" roughness={0.8} />
      </mesh>
      {/* back + side walls + ceiling */}
      <mesh position={[0, H / 2, -h]} receiveShadow castShadow>
        <boxGeometry args={[h * 2, H, 0.1]} />
        <meshStandardMaterial color={WALL} roughness={1} />
      </mesh>
      <mesh position={[-h, H / 2, 0]} receiveShadow castShadow>
        <boxGeometry args={[0.1, H, h * 2]} />
        <meshStandardMaterial color={WALL} roughness={1} />
      </mesh>
      <mesh position={[h, H / 2, 0]} receiveShadow castShadow>
        <boxGeometry args={[0.1, H, h * 2]} />
        <meshStandardMaterial color={WALL} roughness={1} />
      </mesh>
      <mesh position={[0, H, 0]}>
        <boxGeometry args={[h * 2, 0.06, h * 2]} />
        <meshStandardMaterial color="#efe9df" roughness={1} />
      </mesh>
      {/* booth light */}
      <pointLight position={[0, H - 0.3, 0.2]} intensity={6} distance={5} color="#fff3e0" />

      {/* curtain rail + parted panels at the opening */}
      <mesh position={[0, H - 0.15, h]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.02, 0.02, h * 2, 8]} />
        <meshStandardMaterial color={STEEL} metalness={0.6} />
      </mesh>
      <mesh position={[-h + 0.35, H / 2, h]} castShadow>
        <boxGeometry args={[0.55, H - 0.3, 0.04]} />
        <meshStandardMaterial color="#8a7d6a" roughness={0.95} />
      </mesh>
      <mesh position={[h - 0.35, H / 2, h]} castShadow>
        <boxGeometry args={[0.55, H - 0.3, 0.04]} />
        <meshStandardMaterial color="#8a7d6a" roughness={0.95} />
      </mesh>

      {/* ---- MIRROR / RESULT on the back wall (straight ahead) ----
           The picture plane sits clearly IN FRONT of the frame box, otherwise
           the solid frame occludes it (it's bigger than the picture). */}
      <group position={[0, 1.45, -h + 0.09]}>
        {/* frame (behind: front face at local +0.0) */}
        <mesh position={[0, 0, -0.06]}>
          <boxGeometry args={[1.5, 2.0, 0.12]} />
          <meshStandardMaterial color="#6b5b46" roughness={0.6} />
        </mesh>
        {/* surface: result texture when ready, else a mirror look. The `key`
            forces a fresh material when the texture arrives — swapping material
            props/types in place doesn't reliably re-apply the map in R3F. */}
        <mesh position={[0, 0, 0.04]} onClick={onResultClick}>
          <planeGeometry args={[1.36, 1.86]} />
          <meshBasicMaterial
            key={resultTex ? "result-tex" : "result-mirror"}
            map={resultTex || null}
            color={resultTex ? "#ffffff" : "#cfd6da"}
            toneMapped={false}
          />
        </mesh>
        {!resultTex && (
          <Text position={[0, 0, 0.08]} fontSize={0.12} maxWidth={1.2} textAlign="center" color="#5a6b72" anchorX="center" anchorY="middle">
            {tryOn.status === "error"
              ? tryOn.error || "Try-on failed"
              : tryOn.status === "generating"
              ? "Generating your look…"
              : "Your try-on will appear here"}
          </Text>
        )}
        <Text position={[0, -1.06, 0.08]} fontSize={0.1} color="#5a5048" anchorX="center" anchorY="middle" letterSpacing={0.1}>
          {resultTex ? "TRY-ON · tap to enlarge" : "MIRROR"}
        </Text>
      </group>

      {/* ---- YOUR PHOTO on the left side wall ---- */}
      <group position={[-h + 0.09, 1.45, 0]} rotation={[0, Math.PI / 2, 0]}>
        <mesh position={[0, 0, -0.06]}>
          <boxGeometry args={[1.12, 1.6, 0.12]} />
          <meshStandardMaterial color="#3a2f22" />
        </mesh>
        <mesh position={[0, 0, 0.04]}>
          <planeGeometry args={[1.0, 1.48]} />
          <meshBasicMaterial
            key={photoTex ? "photo-tex" : "photo-ph"}
            map={photoTex || null}
            color={photoTex ? "#ffffff" : "#cfc6b6"}
            toneMapped={false}
          />
        </mesh>
        <Text position={[0, -0.86, 0.08]} fontSize={0.1} color="#5a5048" anchorX="center" anchorY="middle" letterSpacing={0.12}>
          YOU
        </Text>
      </group>

      {/* stool */}
      <mesh position={[h - 0.45, 0.32, -h + 0.45]} castShadow>
        <cylinderGeometry args={[0.18, 0.18, 0.06, 16]} />
        <meshStandardMaterial color={TIMBER} roughness={0.7} />
      </mesh>
      <mesh position={[h - 0.45, 0.16, -h + 0.45]}>
        <cylinderGeometry args={[0.03, 0.03, 0.32, 8]} />
        <meshStandardMaterial color={STEEL} metalness={0.5} />
      </mesh>

      {/* sign above the opening */}
      <Text position={[0, H + 0.15, h]} fontSize={0.16} color="#5a5048" anchorX="center" anchorY="middle" letterSpacing={0.1}>
        FITTING ROOM
      </Text>
    </group>
  );
}
