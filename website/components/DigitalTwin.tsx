'use client'

import React, { useRef, useState, useEffect, Suspense } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, PerspectiveCamera, useGLTF, Html } from '@react-three/drei'
import * as THREE from 'three'
import { motion, AnimatePresence } from 'framer-motion'
import { Loader2, AlertCircle, Home as HomeIcon } from 'lucide-react'

interface DigitalTwinProps {
  lightIntensity: number
  activeSource: 'solar' | 'battery' | 'grid'
  brightnessThreshold: number
  weatherCondition?: string
  className?: string
  onLoadingComplete?: (success: boolean) => void
}

type ModelLoadState = 'loading' | 'success' | 'error'

function GeometricHouse({
  lightIntensity,
  brightnessThreshold,
  needsArtificialLight,
  artificialLightIntensity
}: {
  lightIntensity: number
  brightnessThreshold: number
  needsArtificialLight: boolean
  artificialLightIntensity: number
}) {
  const groupRef = useRef<THREE.Group>(null)

  return (
    <group ref={groupRef} position={[0, -1, 0]}>
      
      <mesh position={[0, 0.5, 0]} castShadow receiveShadow>
        <boxGeometry args={[4, 2, 4]} />
        <meshStandardMaterial color="#2D3748" />
      </mesh>
      
      <mesh position={[0, 2.0, 0]} castShadow>
        <coneGeometry args={[3.5, 1.5, 4]} />
        <meshStandardMaterial color="#1F2937"/>
      </mesh>
      
      <mesh position={[0, 0.5, 2.01]}>
        <boxGeometry args={[0.8, 1.2, 0.1]} />
        <meshStandardMaterial color="#8B4513" />
      </mesh>
      
      <mesh position={[-1.2, 0.8, 2.01]}>
        <planeGeometry args={[0.8, 0.8]} />
        <meshStandardMaterial color={needsArtificialLight ? "#F6E05E" : "#4A5568"} emissive={needsArtificialLight ? "#F6E05E" : "#000000"} />
      </mesh>
      <mesh position={[1.2, 0.8, 2.01]}>
        <planeGeometry args={[0.8, 0.8]} />
        <meshStandardMaterial color={needsArtificialLight ? "#F6E05E" : "#4A5568"} emissive={needsArtificialLight ? "#F6E05E" : "#000000"} />
      </mesh>

      
      {needsArtificialLight && (
        <pointLight
          position={[0, 1.5, 0]}
          intensity={artificialLightIntensity}
          color="#FFE5B4"
          distance={10}
          decay={2}
        />
      )}
    </group>
  )
}

function GLTFModel({
  onLoad,
  lightIntensity,
  brightnessThreshold
}: {
  onLoad: () => void,
  lightIntensity: number,
  brightnessThreshold: number
}) {
  const gltf = useGLTF('/models/isometric_room_school.glb')

  const darknessFactor = Math.max(0, Math.min(1, (brightnessThreshold - lightIntensity) / brightnessThreshold))

  useEffect(() => {
    onLoad()

    gltf.scene.traverse((child) => {
      if ((child as THREE.Mesh).isMesh) {
        const mesh = child as THREE.Mesh
        const material = mesh.material as THREE.MeshStandardMaterial

        if (mesh.name.toLowerCase().includes('window') || mesh.name.toLowerCase().includes('glass')) {
          material.emissive = new THREE.Color("#F6E05E")
          material.emissiveIntensity = darknessFactor * 2
        }
      }
    })
  }, [gltf, lightIntensity, darknessFactor, onLoad])

  return (
    <primitive
      object={gltf.scene}
      position={[0, -1, 0]}
      scale={0.02}
    />
  )
}

class ModelErrorBoundary extends React.Component<
  { fallback: React.ReactNode; onError: () => void; children: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: any) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error: any) {
    console.error("3D Model Load Failed:", error)
    this.props.onError()
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback
    }
    return this.props.children
  }
}

function Scene({
  lightIntensity,
  brightnessThreshold,
  onLoadStateChange
}: {
  lightIntensity: number
  brightnessThreshold: number
  onLoadStateChange: (state: ModelLoadState) => void
}) {
  const needsArtificialLight = lightIntensity < brightnessThreshold
  const artificialLightIntensity = needsArtificialLight
    ? ((brightnessThreshold - lightIntensity) / 100) * 5
    : 0

  const dynamicAmbient = Math.max(0.5, (lightIntensity / 100) * 3.0)

  const [sunPosition, setSunPosition] = useState<[number, number, number]>([10, 10, 5])

  useEffect(() => {
    const updateSunPosition = () => {
      const now = new Date();
      const utc = now.getTime() + (now.getTimezoneOffset() * 60000);
      const istDate = new Date(utc + (3600000 * 5.5));

      const hours = istDate.getHours();
      const minutes = istDate.getMinutes();
      const timeDecimal = hours + minutes / 60;

      let x = 10, y = 10, z = 5;

      if (timeDecimal >= 6 && timeDecimal <= 18) {
        const dayProgress = (timeDecimal - 6) / 12;
        const angle = dayProgress * Math.PI;

        x = Math.cos(angle) * 20 * -1;
        y = Math.sin(angle) * 20;
        z = 10;
      } else {
        x = -10;
        y = -5;
        z = -10;
      }

      setSunPosition([x, y, z]);
    };

    updateSunPosition();
    const interval = setInterval(updateSunPosition, 60000);
    return () => clearInterval(interval);
  }, []);

  return (
    <>
      <ambientLight intensity={dynamicAmbient} />
      <directionalLight
        position={sunPosition}
        intensity={lightIntensity > brightnessThreshold ? 1.5 : 0.3}
        castShadow
        shadow-mapSize={[1024, 1024]}
      />

      <ModelErrorBoundary
        onError={() => onLoadStateChange('error')}
        fallback={
          <GeometricHouse
            lightIntensity={lightIntensity}
            brightnessThreshold={brightnessThreshold}
            needsArtificialLight={needsArtificialLight}
            artificialLightIntensity={artificialLightIntensity}
          />
        }
      >
        <Suspense fallback={null}>
          <group>
            <GLTFModel
              onLoad={() => onLoadStateChange('success')}
              lightIntensity={lightIntensity}
              brightnessThreshold={brightnessThreshold}
            />
            {needsArtificialLight && (
              <pointLight
                position={[0, 2, 0]}
                intensity={artificialLightIntensity}
                color="#FFE5B4"
                distance={15}
                castShadow
              />
            )}
          </group>
        </Suspense>
      </ModelErrorBoundary>
    </>
  )
}

function Environment() {
  return (
    <mesh scale={100}>
      <sphereGeometry args={[1, 64, 64]} />
      <meshBasicMaterial color="#111" side={THREE.BackSide} />
    </mesh>
  )
}

export default function DigitalTwin({
  lightIntensity,
  activeSource,
  brightnessThreshold,
  weatherCondition = 'sunny',
  className,
  onLoadingComplete
}: DigitalTwinProps) {
  const [modelState, setModelState] = useState<ModelLoadState>('loading')
  const [showContent, setShowContent] = useState(false)

  const handleLoadStateChange = (state: ModelLoadState) => {
    if (modelState !== state) {
      setModelState(state)
      setTimeout(() => {
        setShowContent(true)
        onLoadingComplete?.(state === 'success')
      }, 500)
    }
  }

  return (
    <div className={className} style={{ width: '100%', height: '100%', position: 'relative', overflow: 'hidden' }}>

      
      <AnimatePresence>
        {!showContent && (
          <motion.div
            initial={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5 }}
            className="absolute inset-0 z-10 flex items-center justify-center bg-gray-900 rounded-lg"
          >
            {modelState === 'loading' && (
              <div className="flex flex-col items-center gap-4">
                <Loader2 className="w-10 h-10 text-blue-500 animate-spin" />
                <p className="text-white font-medium">Loading Digital Twin...</p>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      
      {showContent && modelState === 'error' && (
        <div className="absolute top-4 left-4 z-10 bg-yellow-500/20 backdrop-blur-md border border-yellow-500/30 px-3 py-1.5 rounded-full flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-yellow-500" />
          <span className="text-xs text-yellow-200">Using Fallback Model</span>
        </div>
      )}

      
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: showContent ? 1 : 0 }}
        transition={{ duration: 1 }}
        style={{ width: '100%', height: '100%' }}
      >
        <Canvas shadows dpr={[1, 2]}>
          <PerspectiveCamera makeDefault position={[15, 10, 15]} fov={55} />
          <OrbitControls
            enablePan={false}
            minDistance={10}
            maxDistance={25}
            autoRotate
            autoRotateSpeed={0.5}
            target={[0, 0, 0]}
          />
          <Scene
            lightIntensity={lightIntensity}
            brightnessThreshold={brightnessThreshold}
            onLoadStateChange={handleLoadStateChange}
          />
        </Canvas>
      </motion.div>
    </div>
  )
}