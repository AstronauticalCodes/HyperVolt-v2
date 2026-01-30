'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import dynamic from 'next/dynamic'
import { Activity, Zap, Sun, Battery, Plug, AlertTriangle, Clock, RefreshCw } from 'lucide-react'
import { motion } from 'framer-motion'
import { useWebSocket } from '@/hooks/useWebSocket'
import apiService from '@/lib/api-service'
import { StrategyLogEntry, WebSocketMessage, ForecastPrediction } from '@/lib/types'
import StatsGrid from '@/components/StatsGrid'
import EnergyChart from '@/components/EnergyChart'
import PowerDistribution from '@/components/PowerDistribution'
import LogsViewer from '@/components/LogsViewer'

// Constants
const MAX_HISTORY_ENTRIES = 20
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Dynamic imports for 3D components (client-side only)
const EnergyFlow = dynamic(() => import('@/components/EnergyFlow'), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex items-center justify-center bg-gray-900/50 rounded-lg">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-4 border-purple-500 border-t-transparent rounded-full animate-spin" />
        <div className="text-gray-400">Loading Energy Flow...</div>
      </div>
    </div>
  ),
})

// Types for AI Decision
interface AIDecision {
  timestamp: string
  forecast: ForecastPrediction[]
  peak_hours: ForecastPrediction[]
  current_conditions: {
    hour: number
    temperature: number
    humidity: number
    ldr: number
    current: number
    voltage: number
    carbon_intensity: number
    source: string
  }
  current_decision: {
    predicted_demand_kwh: number
    source_allocation: [string, number][]
    cost: number
    carbon: number
    battery_charge: number
    battery_percentage: number
    solar_available: number
    primary_source: string
  }
  recommendation: string
  available: boolean
}

export default function Dashboard() {
  // State management
  const [activeSource, setActiveSource] = useState<'solar' | 'battery' | 'grid'>('grid')
  const [strategyLogs, setStrategyLogs] = useState<StrategyLogEntry[]>([])
  const [forecastData, setForecastData] = useState<ForecastPrediction[]>([])
  const [peakHours, setPeakHours] = useState<ForecastPrediction[]>([])
  const [aiAvailable, setAiAvailable] = useState(false)
  const [lastUpdate, setLastUpdate] = useState<string>('')
  const [isLoading, setIsLoading] = useState(true)
  
  // Sensor data from ESP32/simulation
  const [sensorData, setSensorData] = useState({
    temperature: 25,
    humidity: 50,
    ldr: 2000,
    current: 1.0,
    voltage: 230,
  })
  
  // AI Decision data
  const [decision, setDecision] = useState<AIDecision | null>(null)
  
  const [stats, setStats] = useState({
    carbonSavings: 0,
    costSavings: 0,
    powerConsumption: 1.2,
    efficiency: 85,
  })
  
  const [energyOutputs, setEnergyOutputs] = useState({
    solar: 0,
    battery: 0,
    grid: 0,
    home: 1.2,
  })

  // WebSocket connection for real-time updates
  const { isConnected, lastMessage } = useWebSocket(undefined, {
    onMessage: handleWebSocketMessage,
    autoReconnect: true,
  })

  function handleWebSocketMessage(message: WebSocketMessage) {
    console.log('WebSocket message:', message)

    if (message.type === 'sensor_update' && message.data) {
      const { sensor_type, value } = message.data
      setSensorData(prev => ({
        ...prev,
        [sensor_type]: value
      }))
      
      addLog({
        id: Date.now().toString(),
        timestamp: new Date().toISOString(),
        type: 'info',
        message: `Sensor update: ${sensor_type} = ${value}`,
      })
    }

    if (message.type === 'ai_decision' && message.data) {
      const source = message.data.source || message.data.payload?.source
      if (source) {
        setActiveSource(source as 'solar' | 'battery' | 'grid')
      }
      addLog({
        id: Date.now().toString(),
        timestamp: new Date().toISOString(),
        type: 'success',
        message: `AI Decision: Switch to ${source?.toUpperCase()}`,
        details: message.data.reasoning || message.data.payload?.details?.recommendation
      })
    }
  }

  const addLog = useCallback((log: StrategyLogEntry) => {
    setStrategyLogs(prev => [...prev.slice(-50), log])
  }, [])

  // Fetch AI Decision - this is the main function that gets AI data
  const fetchAIDecision = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/ai/decide/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })
      
      if (!response.ok) throw new Error('AI decision failed')
      
      const data: AIDecision = await response.json()
      
      if (data.available) {
        setDecision(data)
        setAiAvailable(true)
        setForecastData(data.forecast || [])
        setPeakHours(data.peak_hours || [])
        setLastUpdate(new Date().toLocaleTimeString())
        
        // Update active source from AI decision
        const primarySource = data.current_decision?.primary_source
        if (primarySource) {
          setActiveSource(primarySource as 'solar' | 'battery' | 'grid')
        }
        
        // Update sensor data from conditions
        if (data.current_conditions) {
          setSensorData({
            temperature: data.current_conditions.temperature || 25,
            humidity: data.current_conditions.humidity || 50,
            ldr: data.current_conditions.ldr || 2000,
            current: data.current_conditions.current || 1.0,
            voltage: data.current_conditions.voltage || 230,
          })
        }
        
        // Update energy outputs from allocation
        if (data.current_decision?.source_allocation) {
          const allocation = data.current_decision.source_allocation
          setEnergyOutputs({
            solar: allocation.find(a => a[0] === 'solar')?.[1] || 0,
            battery: allocation.find(a => a[0] === 'battery')?.[1] || 0,
            grid: allocation.find(a => a[0] === 'grid')?.[1] || 0,
            home: data.current_decision.predicted_demand_kwh || 1.2,
          })
        }
        
        // Update stats
        setStats(prev => ({
          carbonSavings: prev.carbonSavings + (500 - (data.current_decision?.carbon || 500)) / 1000,
          costSavings: prev.costSavings + (6 - (data.current_decision?.cost || 6)) / 10,
          powerConsumption: data.current_decision?.predicted_demand_kwh || 1.2,
          efficiency: Math.min(100, 75 + (data.current_decision?.solar_available || 0) * 10),
        }))
        
        addLog({
          id: Date.now().toString(),
          timestamp: new Date().toISOString(),
          type: 'success',
          message: `AI Decision: ${data.recommendation}`,
          details: `Source: ${primarySource}, Demand: ${data.current_decision?.predicted_demand_kwh?.toFixed(2)} kWh`
        })
      }
    } catch (error) {
      console.warn('AI decision fetch failed:', error)
      addLog({
        id: Date.now().toString(),
        timestamp: new Date().toISOString(),
        type: 'warning',
        message: 'AI service unavailable - using fallback',
      })
    }
  }, [addLog])

  // Check AI Status on load
  useEffect(() => {
    const checkAIStatus = async () => {
      setIsLoading(true)
      try {
        const response = await fetch(`${API_BASE_URL}/api/ai/status/`)
        if (response.ok) {
          const status = await response.json()
          setAiAvailable(status.available)
          
          addLog({
            id: Date.now().toString(),
            timestamp: new Date().toISOString(),
            type: status.available ? 'success' : 'warning',
            message: status.available 
              ? '✅ AI Engine Online - Ready for predictions'
              : '⚠️ AI Engine starting up...',
          })
          
          // Fetch initial AI decision
          await fetchAIDecision()
        }
      } catch (error) {
        console.warn('Failed to check AI status')
        addLog({
          id: Date.now().toString(),
          timestamp: new Date().toISOString(),
          type: 'warning',
          message: 'Backend not connected - Start Django server',
          details: `Run: cd api && python manage.py runserver`
        })
      }
      setIsLoading(false)
    }
    
    checkAIStatus()
  }, [addLog, fetchAIDecision])

  // Periodic AI decision updates
  useEffect(() => {
    const interval = setInterval(() => {
      fetchAIDecision()
    }, 10000) // Every 10 seconds

    return () => clearInterval(interval)
  }, [fetchAIDecision])

  // Get source icon
  const getSourceIcon = (source: string) => {
    switch (source) {
      case 'solar': return <Sun className="w-6 h-6 text-yellow-400" />
      case 'battery': return <Battery className="w-6 h-6 text-green-400" />
      default: return <Plug className="w-6 h-6 text-blue-400" />
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900">
      {/* Header */}
      <header className="border-b border-gray-700/50 bg-gray-900/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg">
                <Zap className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-white">HyperVolt</h1>
                <p className="text-xs text-gray-400">AI-Driven Energy Orchestrator</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              {/* AI Status Badge */}
              <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border ${
                aiAvailable 
                  ? 'bg-green-500/10 border-green-500/50 text-green-400' 
                  : 'bg-yellow-500/10 border-yellow-500/50 text-yellow-400'
              }`}>
                <div className={`w-2 h-2 rounded-full ${aiAvailable ? 'bg-green-500 animate-pulse' : 'bg-yellow-500'}`} />
                <span className="text-xs font-medium">
                  AI {aiAvailable ? 'Online' : 'Offline'}
                </span>
              </div>
              
              {/* WebSocket Status */}
              <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-800 rounded-full border border-gray-700">
                <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
                <span className="text-xs text-gray-300">
                  {isConnected ? 'Live' : 'Offline'}
                </span>
              </div>
              
              {/* Current Power */}
              <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-800 rounded-full border border-gray-700">
                <Activity className="w-4 h-4 text-blue-400" />
                <span className="text-xs text-gray-300">
                  {energyOutputs.home.toFixed(2)} kW
                </span>
              </div>
              
              {/* Manual Refresh Button */}
              <button 
                onClick={fetchAIDecision}
                className="p-2 rounded-lg bg-gray-800 border border-gray-700 hover:bg-gray-700 transition-colors"
                title="Refresh AI Decision"
              >
                <RefreshCw className="w-4 h-4 text-gray-400" />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Dashboard */}
      <main className="container mx-auto px-6 py-8">
        {/* Loading State */}
        {isLoading ? (
          <div className="flex items-center justify-center h-64">
            <div className="flex flex-col items-center gap-4">
              <div className="w-12 h-12 border-4 border-purple-500 border-t-transparent rounded-full animate-spin" />
              <p className="text-gray-400">Connecting to AI Engine...</p>
            </div>
          </div>
        ) : (
          <>
            {/* Current Energy Source - Big Display */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-8"
            >
              <div className="bg-gradient-to-r from-gray-800/50 to-gray-900/50 rounded-xl border border-gray-700/50 p-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-6">
                    <div className={`p-4 rounded-xl ${
                      activeSource === 'solar' ? 'bg-yellow-500/20' :
                      activeSource === 'battery' ? 'bg-green-500/20' : 'bg-blue-500/20'
                    }`}>
                      {getSourceIcon(activeSource)}
                    </div>
                    <div>
                      <h2 className="text-lg text-gray-400 mb-1">Current Energy Source</h2>
                      <p className="text-3xl font-bold text-white capitalize">{activeSource}</p>
                      <p className="text-sm text-gray-500 mt-1">
                        {decision?.recommendation || 'Waiting for AI decision...'}
                      </p>
                    </div>
                  </div>
                  
                  {/* Quick Stats */}
                  <div className="flex gap-8">
                    <div className="text-center">
                      <p className="text-2xl font-bold text-green-400">
                        {decision?.current_decision?.battery_percentage?.toFixed(0) || 70}%
                      </p>
                      <p className="text-xs text-gray-400">Battery</p>
                    </div>
                    <div className="text-center">
                      <p className="text-2xl font-bold text-yellow-400">
                        {decision?.current_decision?.solar_available?.toFixed(1) || 0} kW
                      </p>
                      <p className="text-xs text-gray-400">Solar</p>
                    </div>
                    <div className="text-center">
                      <p className="text-2xl font-bold text-blue-400">
                        {decision?.current_decision?.predicted_demand_kwh?.toFixed(2) || 1.2} kW
                      </p>
                      <p className="text-xs text-gray-400">Demand</p>
                    </div>
                  </div>
                </div>
              </div>
            </motion.div>

            {/* Stats Grid */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
              className="mb-8"
            >
              <StatsGrid
                carbonSavings={stats.carbonSavings}
                costSavings={stats.costSavings}
                powerConsumption={stats.powerConsumption}
                efficiency={stats.efficiency}
              />
            </motion.div>

            {/* Peak Hours Warning */}
            {peakHours.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.15 }}
                className="mb-8"
              >
                <div className="bg-orange-500/10 border border-orange-500/30 rounded-xl p-4">
                  <div className="flex items-center gap-3">
                    <AlertTriangle className="w-6 h-6 text-orange-400" />
                    <div>
                      <h3 className="text-lg font-semibold text-orange-400">Peak Hours Detected</h3>
                      <p className="text-sm text-gray-300">
                        High demand expected at: {peakHours.slice(0, 3).map(p => 
                          `${p.hour_of_day || new Date(p.timestamp).getHours()}:00`
                        ).join(', ')}
                      </p>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {/* Sensor Data from ESP32/Simulation */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="mb-8"
            >
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Activity className="w-5 h-5 text-blue-400" />
                Hardware Sensor Data
                <span className="text-xs text-gray-500 ml-2">
                  (Source: {decision?.current_conditions?.source || 'simulation'})
                </span>
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                {[
                  { label: 'Temperature', value: `${sensorData.temperature.toFixed(1)}°C`, color: 'text-red-400' },
                  { label: 'Humidity', value: `${sensorData.humidity.toFixed(0)}%`, color: 'text-blue-400' },
                  { label: 'Light (LDR)', value: sensorData.ldr.toFixed(0), color: 'text-yellow-400' },
                  { label: 'Current', value: `${sensorData.current.toFixed(2)}A`, color: 'text-green-400' },
                  { label: 'Voltage', value: `${sensorData.voltage.toFixed(0)}V`, color: 'text-purple-400' },
                ].map((sensor, idx) => (
                  <div key={idx} className="bg-gray-800/50 rounded-lg p-4 border border-gray-700/50">
                    <p className="text-xs text-gray-400 mb-1">{sensor.label}</p>
                    <p className={`text-2xl font-bold ${sensor.color}`}>{sensor.value}</p>
                  </div>
                ))}
              </div>
            </motion.div>

            {/* Main Grid Layout */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8"
            >
              {/* Energy Flow Visualization */}
              <div className="h-[400px]">
                <EnergyFlow
                  activeSource={activeSource}
                  solarOutput={energyOutputs.solar}
                  batteryOutput={energyOutputs.battery}
                  gridOutput={energyOutputs.grid}
                  homeConsumption={energyOutputs.home}
                />
              </div>
              
              {/* Power Distribution */}
              <div>
                <PowerDistribution
                  solarOutput={energyOutputs.solar}
                  batteryOutput={energyOutputs.battery}
                  gridOutput={energyOutputs.grid}
                />
                
                {/* Source Allocation Details */}
                <div className="mt-4 bg-gray-800/50 rounded-lg p-4 border border-gray-700/50">
                  <h4 className="text-sm font-semibold text-gray-300 mb-3">AI Source Allocation</h4>
                  <div className="space-y-2">
                    {decision?.current_decision?.source_allocation?.map(([source, power], idx) => (
                      <div key={idx} className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          {getSourceIcon(source)}
                          <span className="text-gray-300 capitalize">{source}</span>
                        </div>
                        <span className="text-white font-medium">{power.toFixed(3)} kW</span>
                      </div>
                    )) || (
                      <p className="text-gray-500 text-sm">Waiting for AI decision...</p>
                    )}
                  </div>
                </div>
              </div>
            </motion.div>

            {/* Energy Forecast Chart */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 }}
              className="mb-8"
            >
              <EnergyChart forecastData={forecastData} />
            </motion.div>

            {/* Last Update Time */}
            <div className="text-center text-sm text-gray-500 mb-4">
              <Clock className="w-4 h-4 inline mr-1" />
              Last AI Update: {lastUpdate || 'Never'}
            </div>
          </>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-700/50 bg-gray-900/80 backdrop-blur-sm mt-12">
        <div className="container mx-auto px-6 py-4">
          <div className="text-center text-sm text-gray-400">
            <p>HyperVolt - SMVIT Sustainergy Hackathon 2026</p>
            <p className="text-xs mt-1">Built with ❤️ by HyperHawks Team</p>
          </div>
        </div>
      </footer>

      {/* Floating Logs Viewer */}
      <LogsViewer logs={strategyLogs} />
    </div>
  )
}
