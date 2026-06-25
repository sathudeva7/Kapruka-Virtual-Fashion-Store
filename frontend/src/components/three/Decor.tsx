"use client";

import { Text } from "@react-three/drei";
import { ROOM } from "@/lib/scene";

const H = ROOM.height;

// Minimalist boutique palette (concrete / plaster / timber / brushed steel,
// muted garments). No product photos on the walls.
const GARMENTS = ["#c9bca6", "#a7b0a0", "#c2a18a", "#9a9089", "#6f7b74", "#b9a78f", "#d6c0b1", "#8d9a93"];
const TIMBER = "#b48a5a";
const LIMESTONE = "#d9d2c4";
const STEEL = "#9a9a9a";
const FIXTURE = "#2b2b2b";

// --- garments on hangers (real clothing silhouettes) ----------------------
function HangerHook() {
  return (
    <mesh position={[0, 0.04, 0]} rotation={[Math.PI / 2, 0, 0]}>
      <torusGeometry args={[0.035, 0.006, 8, 14, Math.PI]} />
      <meshStandardMaterial color={STEEL} metalness={0.6} roughness={0.3} />
    </mesh>
  );
}

function HangingDress({ color }: { color: string }) {
  return (
    <group>
      <HangerHook />
      {/* straps */}
      <mesh position={[0, -0.13, 0]}>
        <boxGeometry args={[0.26, 0.05, 0.05]} />
        <meshPhysicalMaterial color={color} roughness={0.85} sheen={0.6} sheenRoughness={0.5} sheenColor="#fff4e6" />
      </mesh>
      {/* bodice */}
      <mesh position={[0, -0.36, 0]} castShadow>
        <cylinderGeometry args={[0.15, 0.2, 0.42, 18]} />
        <meshPhysicalMaterial color={color} roughness={0.85} sheen={0.6} sheenRoughness={0.5} sheenColor="#fff4e6" />
      </mesh>
      {/* A-line skirt */}
      <mesh position={[0, -0.82, 0]} castShadow>
        <cylinderGeometry args={[0.2, 0.42, 0.74, 22]} />
        <meshPhysicalMaterial color={color} roughness={0.85} sheen={0.6} sheenRoughness={0.5} sheenColor="#fff4e6" />
      </mesh>
    </group>
  );
}

function HangingShirt({ color }: { color: string }) {
  return (
    <group>
      <HangerHook />
      {/* shoulders */}
      <mesh position={[0, -0.16, 0]} castShadow>
        <boxGeometry args={[0.5, 0.1, 0.13]} />
        <meshPhysicalMaterial color={color} roughness={0.85} sheen={0.6} sheenRoughness={0.5} sheenColor="#fff4e6" />
      </mesh>
      {/* sleeves */}
      <mesh position={[-0.28, -0.28, 0]} rotation={[0, 0, 0.5]} castShadow>
        <boxGeometry args={[0.24, 0.09, 0.11]} />
        <meshPhysicalMaterial color={color} roughness={0.85} sheen={0.6} sheenRoughness={0.5} sheenColor="#fff4e6" />
      </mesh>
      <mesh position={[0.28, -0.28, 0]} rotation={[0, 0, -0.5]} castShadow>
        <boxGeometry args={[0.24, 0.09, 0.11]} />
        <meshPhysicalMaterial color={color} roughness={0.85} sheen={0.6} sheenRoughness={0.5} sheenColor="#fff4e6" />
      </mesh>
      {/* body */}
      <mesh position={[0, -0.52, 0]} castShadow>
        <boxGeometry args={[0.42, 0.62, 0.1]} />
        <meshPhysicalMaterial color={color} roughness={0.85} sheen={0.6} sheenRoughness={0.5} sheenColor="#fff4e6" />
      </mesh>
    </group>
  );
}

// --- a clean free-standing clothing rail ----------------------------------
function Rail({
  position,
  rotation = 0,
  count = 5,
  start = 0,
}: {
  position: [number, number, number];
  rotation?: number;
  count?: number;
  start?: number;
}) {
  const len = 2.2;
  const step = len / (count - 1);
  return (
    <group position={position} rotation={[0, rotation, 0]}>
      {/* feet + posts + bar */}
      <mesh position={[-len / 2, 0.02, 0]}>
        <boxGeometry args={[0.5, 0.04, 0.5]} />
        <meshStandardMaterial color={FIXTURE} />
      </mesh>
      <mesh position={[len / 2, 0.02, 0]}>
        <boxGeometry args={[0.5, 0.04, 0.5]} />
        <meshStandardMaterial color={FIXTURE} />
      </mesh>
      <mesh position={[-len / 2, 0.85, 0]}>
        <cylinderGeometry args={[0.022, 0.022, 1.7, 10]} />
        <meshStandardMaterial color={STEEL} metalness={0.7} roughness={0.3} />
      </mesh>
      <mesh position={[len / 2, 0.85, 0]}>
        <cylinderGeometry args={[0.022, 0.022, 1.7, 10]} />
        <meshStandardMaterial color={STEEL} metalness={0.7} roughness={0.3} />
      </mesh>
      <mesh position={[0, 1.68, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[0.02, 0.02, len, 10]} />
        <meshStandardMaterial color={STEEL} metalness={0.7} roughness={0.3} />
      </mesh>
      {/* garments hung on the bar */}
      {Array.from({ length: count }).map((_, i) => {
        const x = -len / 2 + i * step;
        const c = GARMENTS[(i + start) % GARMENTS.length];
        return (
          <group key={i} position={[x, 1.64, 0]}>
            {(i + start) % 2 === 0 ? <HangingDress color={c} /> : <HangingShirt color={c} />}
          </group>
        );
      })}
    </group>
  );
}

// --- a display plinth with folded garment stacks --------------------------
function Plinth({
  position,
  size,
  stacks = [],
}: {
  position: [number, number, number];
  size: [number, number, number];
  stacks?: { color: string; dx: number }[];
}) {
  const [w, h, d] = size;
  return (
    <group position={position}>
      <mesh position={[0, h / 2, 0]} castShadow receiveShadow>
        <boxGeometry args={[w, h, d]} />
        <meshStandardMaterial color={LIMESTONE} roughness={0.95} />
      </mesh>
      {stacks.map((s, i) => (
        <group key={i} position={[s.dx, h, 0]}>
          {[0, 1, 2].map((j) => (
            <mesh key={j} position={[0, 0.05 + j * 0.08, 0]} castShadow>
              <boxGeometry args={[0.5 - j * 0.06, 0.07, 0.5 - j * 0.06]} />
              <meshStandardMaterial color={s.color} roughness={0.9} />
            </mesh>
          ))}
        </group>
      ))}
    </group>
  );
}

// --- a slim pedestal showing a single folded piece ------------------------
function Pedestal({ position, h, color }: { position: [number, number, number]; h: number; color: string }) {
  return (
    <group position={position}>
      <mesh position={[0, h / 2, 0]} castShadow>
        <cylinderGeometry args={[0.28, 0.3, h, 24]} />
        <meshStandardMaterial color={LIMESTONE} roughness={0.95} />
      </mesh>
      <mesh position={[0, h + 0.06, 0]} castShadow>
        <boxGeometry args={[0.36, 0.12, 0.36]} />
        <meshStandardMaterial color={color} roughness={0.9} />
      </mesh>
    </group>
  );
}

// --- a headless boutique mannequin wearing a dress or a suit ---------------
function Mannequin({
  position,
  color,
  rotation = 0,
  kind = "dress",
}: {
  position: [number, number, number];
  color: string;
  rotation?: number;
  kind?: "dress" | "suit";
}) {
  return (
    <group position={position} rotation={[0, rotation, 0]}>
      {/* base */}
      <mesh position={[0, 0.05, 0]} castShadow>
        <cylinderGeometry args={[0.3, 0.34, 0.1, 24]} />
        <meshStandardMaterial color={FIXTURE} metalness={0.3} />
      </mesh>

      {kind === "dress" ? (
        <>
          {/* A-line gown */}
          <mesh position={[0, 0.75, 0]} castShadow>
            <cylinderGeometry args={[0.2, 0.5, 1.3, 28]} />
            <meshPhysicalMaterial color={color} roughness={0.85} sheen={0.6} sheenRoughness={0.5} sheenColor="#fff4e6" />
          </mesh>
          {/* bodice */}
          <mesh position={[0, 1.55, 0]} castShadow>
            <cylinderGeometry args={[0.17, 0.2, 0.45, 18]} />
            <meshPhysicalMaterial color={color} roughness={0.85} sheen={0.6} sheenRoughness={0.5} sheenColor="#fff4e6" />
          </mesh>
          {/* straps */}
          <mesh position={[0, 1.78, 0]}>
            <boxGeometry args={[0.26, 0.05, 0.05]} />
            <meshPhysicalMaterial color={color} roughness={0.85} sheen={0.6} sheenRoughness={0.5} sheenColor="#fff4e6" />
          </mesh>
        </>
      ) : (
        <>
          {/* stand pole */}
          <mesh position={[0, 0.5, 0]}>
            <cylinderGeometry args={[0.03, 0.03, 0.8, 10]} />
            <meshStandardMaterial color={STEEL} metalness={0.6} />
          </mesh>
          {/* trousers */}
          <mesh position={[-0.11, 1.0, 0]} castShadow>
            <capsuleGeometry args={[0.1, 0.7, 4, 10]} />
            <meshStandardMaterial color="#3a3833" roughness={0.95} />
          </mesh>
          <mesh position={[0.11, 1.0, 0]} castShadow>
            <capsuleGeometry args={[0.1, 0.7, 4, 10]} />
            <meshStandardMaterial color="#3a3833" roughness={0.95} />
          </mesh>
          {/* jacket / shirt torso */}
          <mesh position={[0, 1.6, 0]} castShadow>
            <boxGeometry args={[0.46, 0.7, 0.26]} />
            <meshPhysicalMaterial color={color} roughness={0.85} sheen={0.6} sheenRoughness={0.5} sheenColor="#fff4e6" />
          </mesh>
          {/* shoulders */}
          <mesh position={[0, 1.92, 0]} castShadow>
            <boxGeometry args={[0.56, 0.12, 0.28]} />
            <meshPhysicalMaterial color={color} roughness={0.85} sheen={0.6} sheenRoughness={0.5} sheenColor="#fff4e6" />
          </mesh>
        </>
      )}

      {/* neck stub (headless) */}
      <mesh position={[0, kind === "dress" ? 1.86 : 2.04, 0]}>
        <cylinderGeometry args={[0.05, 0.07, 0.12, 12]} />
        <meshStandardMaterial color={LIMESTONE} />
      </mesh>
    </group>
  );
}

// --- a timber bench --------------------------------------------------------
function Bench({ position, rotation = 0 }: { position: [number, number, number]; rotation?: number }) {
  return (
    <group position={position} rotation={[0, rotation, 0]}>
      <mesh position={[0, 0.42, 0]} castShadow>
        <boxGeometry args={[1.8, 0.12, 0.5]} />
        <meshStandardMaterial color={TIMBER} roughness={0.7} />
      </mesh>
      {[-0.75, 0.75].map((x) => (
        <mesh key={x} position={[x, 0.2, 0]}>
          <boxGeometry args={[0.12, 0.4, 0.46]} />
          <meshStandardMaterial color={TIMBER} roughness={0.7} />
        </mesh>
      ))}
    </group>
  );
}

// --- the cash / checkout counter -------------------------------------------
function CashCounter({ position, rotation = 0 }: { position: [number, number, number]; rotation?: number }) {
  return (
    <group position={position} rotation={[0, rotation, 0]}>
      {/* counter body */}
      <mesh position={[0, 0.5, 0]} castShadow receiveShadow>
        <boxGeometry args={[2.6, 1.0, 0.8]} />
        <meshStandardMaterial color={LIMESTONE} roughness={0.95} />
      </mesh>
      {/* timber countertop (overhangs the customer side) */}
      <mesh position={[0, 1.04, 0.06]} castShadow>
        <boxGeometry args={[2.8, 0.08, 1.0]} />
        <meshStandardMaterial color={TIMBER} roughness={0.6} />
      </mesh>
      {/* back display cabinet */}
      <mesh position={[0, 0.9, -0.7]} castShadow>
        <boxGeometry args={[2.6, 1.8, 0.3]} />
        <meshStandardMaterial color="#e6dfd3" roughness={1} />
      </mesh>
      {[0.6, 1.2].map((y) => (
        <mesh key={y} position={[0, y, -0.54]}>
          <boxGeometry args={[2.4, 0.04, 0.05]} />
          <meshStandardMaterial color={TIMBER} roughness={0.7} />
        </mesh>
      ))}
      {/* POS terminal */}
      <group position={[0.75, 1.08, 0]}>
        <mesh position={[0, 0.06, 0]} castShadow>
          <boxGeometry args={[0.3, 0.06, 0.22]} />
          <meshStandardMaterial color="#3a3a3a" />
        </mesh>
        <mesh position={[0, 0.26, -0.02]} rotation={[-0.3, 0, 0]}>
          <boxGeometry args={[0.32, 0.24, 0.02]} />
          <meshStandardMaterial color="#1b1b1b" />
        </mesh>
      </group>
      {/* card machine */}
      <mesh position={[-0.7, 1.13, 0.1]} rotation={[-0.4, 0, 0]} castShadow>
        <boxGeometry args={[0.12, 0.22, 0.03]} />
        <meshStandardMaterial color="#2c2c2c" />
      </mesh>
      {/* stool behind */}
      <mesh position={[0, 0.5, -0.95]}>
        <cylinderGeometry args={[0.2, 0.2, 0.08, 18]} />
        <meshStandardMaterial color={TIMBER} roughness={0.7} />
      </mesh>
      <mesh position={[0, 0.26, -0.95]}>
        <cylinderGeometry args={[0.03, 0.03, 0.46, 8]} />
        <meshStandardMaterial color={STEEL} metalness={0.5} />
      </mesh>
      {/* sign */}
      <Text position={[0, 2.0, -0.52]} fontSize={0.2} color="#5a5048" anchorX="center" anchorY="middle" letterSpacing={0.18}>
        CHECKOUT
      </Text>
    </group>
  );
}

// --- a fitting room booth (curtain + full-length mirror + stool) -----------
function FittingRoom({ position, rotation = 0 }: { position: [number, number, number]; rotation?: number }) {
  const WALL = "#e6dfd3";
  return (
    <group position={position} rotation={[0, rotation, 0]}>
      {/* floor pad */}
      <mesh position={[0, 0.015, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[1.7, 1.7]} />
        <meshStandardMaterial color="#bdb4a3" roughness={0.8} />
      </mesh>
      {/* back + side walls */}
      <mesh position={[0, 1.15, -0.85]} castShadow receiveShadow>
        <boxGeometry args={[1.7, 2.3, 0.1]} />
        <meshStandardMaterial color={WALL} roughness={1} />
      </mesh>
      <mesh position={[-0.85, 1.15, 0]} castShadow receiveShadow>
        <boxGeometry args={[0.1, 2.3, 1.7]} />
        <meshStandardMaterial color={WALL} roughness={1} />
      </mesh>
      <mesh position={[0.85, 1.15, 0]} castShadow receiveShadow>
        <boxGeometry args={[0.1, 2.3, 1.7]} />
        <meshStandardMaterial color={WALL} roughness={1} />
      </mesh>
      {/* ceiling */}
      <mesh position={[0, 2.3, 0]}>
        <boxGeometry args={[1.7, 0.06, 1.7]} />
        <meshStandardMaterial color="#efe9df" roughness={1} />
      </mesh>
      {/* full-length mirror on the back wall */}
      <group position={[0, 1.1, -0.78]}>
        <mesh position={[0, 0, -0.01]}>
          <boxGeometry args={[0.68, 1.7, 0.05]} />
          <meshStandardMaterial color="#6b5b46" roughness={0.6} />
        </mesh>
        <mesh>
          <planeGeometry args={[0.58, 1.6]} />
          <meshStandardMaterial color="#cfd6da" metalness={0.95} roughness={0.06} />
        </mesh>
      </group>
      {/* curtain rail + two panels (slightly parted) */}
      <mesh position={[0, 2.15, 0.85]} rotation={[0, 0, Math.PI / 2]}>
        <cylinderGeometry args={[0.02, 0.02, 1.7, 8]} />
        <meshStandardMaterial color={STEEL} metalness={0.6} />
      </mesh>
      <mesh position={[-0.55, 1.1, 0.85]} castShadow>
        <boxGeometry args={[0.55, 2.0, 0.04]} />
        <meshStandardMaterial color="#8a7d6a" roughness={0.95} />
      </mesh>
      <mesh position={[0.55, 1.1, 0.85]} castShadow>
        <boxGeometry args={[0.55, 2.0, 0.04]} />
        <meshStandardMaterial color="#8a7d6a" roughness={0.95} />
      </mesh>
      {/* stool */}
      <mesh position={[0.45, 0.32, -0.35]} castShadow>
        <cylinderGeometry args={[0.18, 0.18, 0.06, 16]} />
        <meshStandardMaterial color={TIMBER} roughness={0.7} />
      </mesh>
      <mesh position={[0.45, 0.16, -0.35]}>
        <cylinderGeometry args={[0.03, 0.03, 0.32, 8]} />
        <meshStandardMaterial color={STEEL} metalness={0.5} />
      </mesh>
      {/* sign above the entrance */}
      <Text
        position={[0, 2.45, 0.85]}
        fontSize={0.15}
        color="#5a5048"
        anchorX="center"
        anchorY="middle"
        letterSpacing={0.1}
      >
        FITTING ROOM
      </Text>
    </group>
  );
}

// --- ceiling track light ---------------------------------------------------
function Track({ x, z, len = 8 }: { x: number; z: number; len?: number }) {
  return (
    <group>
      <mesh position={[x, H - 0.08, z]}>
        <boxGeometry args={[0.06, 0.06, len]} />
        <meshStandardMaterial color={FIXTURE} />
      </mesh>
      {Array.from({ length: 4 }).map((_, i) => {
        const lz = z - len / 2 + (i + 0.5) * (len / 4);
        return (
          <group key={i}>
            <mesh position={[x, H - 0.18, lz]}>
              <cylinderGeometry args={[0.06, 0.08, 0.16, 12]} />
              <meshStandardMaterial color={FIXTURE} />
            </mesh>
            <pointLight position={[x, H - 0.4, lz]} intensity={2.2} distance={7} decay={2} color="#fff0db" />
          </group>
        );
      })}
    </group>
  );
}

// --- a single sculptural planter -------------------------------------------
function Planter({ position }: { position: [number, number, number] }) {
  return (
    <group position={position}>
      <mesh position={[0, 0.3, 0]}>
        <cylinderGeometry args={[0.26, 0.2, 0.6, 20]} />
        <meshStandardMaterial color="#cfc7b8" roughness={1} />
      </mesh>
      {[0, 1, 2, 3, 4].map((i) => (
        <mesh key={i} position={[Math.sin(i) * 0.12, 1.1 + i * 0.18, Math.cos(i) * 0.1]} rotation={[0.3 * i, i, 0]}>
          <boxGeometry args={[0.04, 0.7, 0.12]} />
          <meshStandardMaterial color="#6f7b5e" roughness={1} />
        </mesh>
      ))}
    </group>
  );
}

export default function Decor() {
  return (
    <group>
      {/* track lighting */}
      <Track x={-5} z={-2} />
      <Track x={5} z={-2} />

      {/* ---- WOMEN side (x < 0) ---- */}
      <Mannequin position={[-7, 0, 1]} color="#c2a18a" kind="dress" rotation={0.4} />
      <Mannequin position={[-4, 0, -7]} color="#a7b0a0" kind="dress" rotation={-0.2} />
      <Rail position={[-7.5, 0, -3]} rotation={Math.PI / 2} count={5} start={0} />
      <Pedestal position={[-3, 0, -1]} h={0.8} color="#c9bca6" />

      {/* ---- MEN side (x > 0) ---- */}
      <Mannequin position={[7, 0, 1]} color="#6f7b74" kind="suit" rotation={-0.4} />
      <Mannequin position={[4, 0, -7]} color="#33506f" kind="suit" rotation={0.2} />
      <Rail position={[7.5, 0, -3]} rotation={Math.PI / 2} count={5} start={1} />
      <Pedestal position={[3, 0, -1]} h={0.65} color="#9a9089" />

      {/* central display island */}
      <Plinth
        position={[0, 0, -4]}
        size={[2.6, 0.4, 1.1]}
        stacks={[
          { color: "#c9bca6", dx: -0.8 },
          { color: "#a7b0a0", dx: 0 },
          { color: "#c2a18a", dx: 0.8 },
        ]}
      />

      {/* cash counter (front-left, faces the entrance) */}
      <CashCounter position={[-6.6, 0, 7]} rotation={0} />

      {/* decorative fitting booth (the interactive one is <TryOnRoom/>) */}
      <FittingRoom position={[-9.0, 0, -6]} rotation={Math.PI / 2} />

      {/* seating + greenery near the entrance */}
      <Bench position={[2.5, 0, 8.5]} />
      <Planter position={[8.8, 0, 9.4]} />
      <Planter position={[-9.3, 0, -10.5]} />
      <Planter position={[9.3, 0, -10.5]} />
    </group>
  );
}
