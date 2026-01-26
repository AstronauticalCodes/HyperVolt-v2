'use client'

import { useRef, useMemo } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, PerspectiveCamera } from '@react-three/drei'
import * as THREE from 'three'

interface DigitalTwinProps {
  lightIntensity: number // 0-100 from LDR sensor
  activeSource: 'solar' | 'battery' | 'grid'
  className?: string
}

function Room({ lightIntensity, activeSource }: { lightIntensity: number; activeSource: string }) {
  const roomRef = useRef<THREE.Group>(null)
  const lightRef = useRef<THREE.PointLight>(null)

  // Source colors
  const sourceColors = {
    solar: '#FDB022', // Yellow for solar
    battery: '#FF6B35', // Orange for battery
    grid: '#EF4444', // Red for grid
  }

  // Normalize light intensity (0-100) to (0.3-1.5) for visual effect
  const normalizedIntensity = 0.3 + (lightIntensity / 100) * 1.2

  useFrame((state) => {
    const time = state.clock.getElapsedTime()
    
    // Gentle pulsing effect based on active source
    if (roomRef.current) {
      const pulseFactor = Math.sin(time * 2) * 0.02 + 1
      roomRef.current.scale.set(pulseFactor, pulseFactor, pulseFactor)
    }

    // Update light intensity smoothly
    if (lightRef.current) {
      lightRef.current.intensity = normalizedIntensity + Math.sin(time) * 0.1
    }
  })

  // Floor color based on power source
  const floorColor = sourceColors[activeSource as keyof typeof sourceColors] || sourceColors.grid

  return (
    <group ref={roomRef}>
      {/* Room walls - wireframe style */}
      <lineSegments>
        <edgesGeometry args={[new THREE.BoxGeometry(5, 3, 5)]} />
        <lineBasicMaterial color="#4A5568" transparent opacity={0.6} />
      </lineSegments>

      {/* Floor with source color */}
      <mesh position={[0, -1.5, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[5, 5]} />
        <meshStandardMaterial 
          color={floorColor}
          transparent 
          opacity={0.2}
          emissive={floorColor}
          emissiveIntensity={0.3}
        />
      </mesh>

      {/* Ceiling light representation */}
      <mesh position={[0, 1.3, 0]}>
        <sphereGeometry args={[0.15, 16, 16]} />
        <meshStandardMaterial 
          color="#FFF"
          emissive="#FFF"
          emissiveIntensity={normalizedIntensity * 2}
        />
      </mesh>

      {/* Light source */}
      <pointLight 
        ref={lightRef}
        position={[0, 1.3, 0]} 
        intensity={normalizedIntensity}
        color="#FFFFFF"
        distance={7}
        decay={2}
      />

      {/* Energy particles flowing upward */}
      <EnergyParticles activeSource={activeSource} />

      {/* Ambient light for base visibility */}
      <ambientLight intensity={0.3} />
    </group>
  )
}

function EnergyParticles({ activeSource }: { activeSource: string }) {
  const particlesRef = useRef<THREE.Points>(null)

  const sourceColors = {
    solar: '#FDB022',
    battery: '#FF6B35',
    grid: '#EF4444',
  }

  // Create particles
  const particles = useMemo(() => {
    const count = 50
    const positions = new Float32Array(count * 3)
    
    for (let i = 0; i < count; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 4 // x
      positions[i * 3 + 1] = Math.random() * 3 - 1.5 // y
      positions[i * 3 + 2] = (Math.random() - 0.5) * 4 // z
    }
    
    return positions
  }, [])

  useFrame((state) => {
    if (particlesRef.current) {
      const positions = particlesRef.current.geometry.attributes.position.array as Float32Array
      
      for (let i = 0; i < positions.length; i += 3) {
        positions[i + 1] += 0.01 // Move upward
        
        // Reset to bottom when reaching top
        if (positions[i + 1] > 1.5) {
          positions[i + 1] = -1.5
        }
      }
      
      particlesRef.current.geometry.attributes.position.needsUpdate = true
      particlesRef.current.rotation.y += 0.001
    }
  })

  const particleColor = sourceColors[activeSource as keyof typeof sourceColors] || sourceColors.grid

  return (
    <points ref={particlesRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={particles.length / 3}
          array={particles}
          itemSize={3}
          args={[particles, 3]}
        />
      </bufferGeometry>
      <pointsMaterial
        size={0.05}
        color={particleColor}
        transparent
        opacity={0.6}
        sizeAttenuation
      />
    </points>
  )
}

export default function DigitalTwin({ lightIntensity, activeSource, className }: DigitalTwinProps) {
  return (
    <div className={className} style={{ width: '100%', height: '100%' }}>
      <Canvas>
        <PerspectiveCamera makeDefault position={[4, 2, 4]} />
        <OrbitControls 
          enableZoom={true}
          enablePan={true}
          minDistance={3}
          maxDistance={15}
          autoRotate
          autoRotateSpeed={0.5}
        />
        <Room lightIntensity={lightIntensity} activeSource={activeSource} />
      </Canvas>
    </div>
  )
}
