import { Canvas, useFrame } from "@react-three/fiber";
import { Float, PointMaterial, Points } from "@react-three/drei";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import { useMemo, useRef } from "react";
import type { Group } from "three";
import * as THREE from "three";

function Starfield() {
  const positions = useMemo(() => {
    const count = 2200;
    const arr = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      arr[i * 3] = (Math.random() - 0.5) * 28;
      arr[i * 3 + 1] = (Math.random() - 0.5) * 18;
      arr[i * 3 + 2] = (Math.random() - 0.5) * 18;
    }
    return arr;
  }, []);

  return (
    <Points positions={positions} stride={3} frustumCulled={false}>
      <PointMaterial
        transparent
        color="#67e8f9"
        size={0.035}
        sizeAttenuation
        depthWrite={false}
        opacity={0.72}
      />
    </Points>
  );
}

function Core() {
  const group = useRef<Group>(null);
  useFrame((_, delta) => {
    if (!group.current) return;
    group.current.rotation.y += delta * 0.25;
    group.current.rotation.x += delta * 0.08;
  });

  return (
    <group ref={group}>
      <Float speed={1.4} rotationIntensity={0.4} floatIntensity={0.6}>
        <mesh>
          <torusKnotGeometry args={[1.1, 0.32, 180, 24]} />
          <meshStandardMaterial
            color="#8b5cf6"
            emissive="#22d3ee"
            emissiveIntensity={0.55}
            metalness={0.35}
            roughness={0.25}
          />
        </mesh>
        <mesh>
          <torusKnotGeometry args={[1.1, 0.32, 80, 8]} />
          <meshBasicMaterial color="#67e8f9" wireframe transparent opacity={0.35} />
        </mesh>
        <mesh>
          <sphereGeometry args={[0.28, 32, 32]} />
          <meshStandardMaterial
            color="#f472b6"
            emissive="#f472b6"
            emissiveIntensity={1.4}
            toneMapped={false}
          />
        </mesh>
      </Float>
    </group>
  );
}

function ParallaxRig() {
  const group = useRef<Group>(null);
  const target = useRef(new THREE.Vector2());
  useFrame((state) => {
    target.current.lerp(state.pointer, 0.04);
    if (!group.current) return;
    group.current.rotation.y = target.current.x * 0.35;
    group.current.rotation.x = -target.current.y * 0.2;
  });
  return (
    <group ref={group}>
      <Starfield />
      <Core />
    </group>
  );
}

export function Scene3D() {
  return (
    <div className="scene-wrap">
      <Canvas camera={{ position: [0, 0, 6.2], fov: 42 }} dpr={[1, 1.75]}>
        <color attach="background" args={["#050816"]} />
        <ambientLight intensity={0.35} />
        <pointLight position={[4, 3, 5]} intensity={40} color="#67e8f9" />
        <pointLight position={[-4, -2, -3]} intensity={25} color="#8b5cf6" />
        <ParallaxRig />
        <EffectComposer>
          <Bloom intensity={1.15} luminanceThreshold={0.2} luminanceSmoothing={0.3} mipmapBlur />
        </EffectComposer>
      </Canvas>
    </div>
  );
}
