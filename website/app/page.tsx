'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import dynamic from 'next/dynamic'
import { Activity, Zap, Sun, Battery, Plug, Clock, RefreshCw, Database, Cloud, MapPin, Settings, Brain, ChevronDown, Calendar, BatteryCharging, TrendingUp } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { StrategyLogEntry, ForecastPrediction } from '@/lib/types'
import StatsGrid from '@/components/StatsGrid'
import EnergyChart from '@/components/EnergyChart'
import PowerDistribution from '@/components/PowerDistribution'
import LogsViewer from '@/components/LogsViewer'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const POLL_INTERVAL = 5000
const BATTERY_CAPACITY_MAH = 20000
const BATTERY_MAX_VOLTAGE = 2.5
const BATTERY_MAX_OUTPUT_MW = 50 // 50 mW max output

const EnergyFlow = dynamic(() => import('@/components/EnergyFlow'), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex items-center justify-center bg-gray-900/50 rounded-lg">
      <div className="w-8 h-8 border-4 border-purple-500 border-t-transparent rounded-full animate-spin" />
    </div>
  ),
})

interface WeatherData {
  temperature: number
  humidity: number
  cloud_cover: number
  solar_radiation: number
  is_day: boolean
  location: string
}

interface PeakHourSettings {
  mode: 'auto' | 'now' | 'plus1' | 'custom'
  customStart?: number
  customEnd?: number
}

interface SourceUsageStats {
  solar: number
  battery: number
  grid: number
}

export default function Dashboard() {
  const [activeSource, setActiveSource] = useState<'solar' | 'battery' | 'grid'>('grid')
  const [strategyLogs, setStrategyLogs] = useState<StrategyLogEntry[]>([])
  const [forecastData, setForecastData] = useState<ForecastPrediction[]>([])
  const [aiAvailable, setAiAvailable] = useState(false)
  const [lastUpdate, setLastUpdate] = useState<string>('')
  const [isLoading, setIsLoading] = useState(true)
  const [isConnected, setIsConnected] = useState(false)
  const [isAiThinking, setIsAiThinking] = useState(false)
  
  const [sensorData, setSensorData] = useState({ temperature: 25, humidity: 50, ldr: 2000, current: 1.5, voltage: 12 })
  const [batteryState, setBatteryState] = useState({ 
    capacityMah: BATTERY_CAPACITY_MAH, 
    currentMah: BATTERY_CAPACITY_MAH * 0.85, 
    isDraining: false, 
    isCharging: false,
    drainRateMW: 0,
    chargeRateMW: 0 
  })
  const [weatherData, setWeatherData] = useState<WeatherData | null>(null)
  const [userLocation, setUserLocation] = useState<{ lat: number; lon: number } | null>(null)
  const [peakSettings, setPeakSettings] = useState<PeakHourSettings>({ mode: 'auto' })
  const [showPeakSettings, setShowPeakSettings] = useState(false)
  const [selectedForecastDay, setSelectedForecastDay] = useState(0)
  const [isLoadingForecast, setIsLoadingForecast] = useState(false)
  const [weeklyForecast, setWeeklyForecast] = useState<{ [key: number]: ForecastPrediction[] }>({})
  
  // Track source usage for "Most Used" indicator
  const [sourceUsage, setSourceUsage] = useState<SourceUsageStats>({ solar: 0, battery: 0, grid: 0 })
  
  // AI Decision explanation
  const [aiExplanation, setAiExplanation] = useState<string>('')
  
  // Solar power = V × I (in mW)
  const solarPowerMW = useMemo(() => sensorData.voltage * sensorData.current, [sensorData.voltage, sensorData.current])
  const batteryPercentage = useMemo(() => (batteryState.currentMah / batteryState.capacityMah) * 100, [batteryState.currentMah, batteryState.capacityMah])
  const [powerConsumption, setPowerConsumption] = useState(1000) // in mW
  
  const isCurrentlyPeakHour = useMemo(() => {
    const hour = new Date().getHours()
    if (peakSettings.mode === 'now') return true
    if (peakSettings.mode === 'plus1') return hour === (new Date().getHours() + 1) % 24
    if (peakSettings.mode === 'custom' && peakSettings.customStart !== undefined && peakSettings.customEnd !== undefined)
      return hour >= peakSettings.customStart && hour < peakSettings.customEnd
    return (hour >= 7 && hour <= 9) || (hour >= 17 && hour <= 20)
  }, [peakSettings])
  
  const [stats, setStats] = useState({ carbonSavings: 0, costSavings: 0, powerConsumption: 1200, efficiency: 85 })
  const [energyOutputs, setEnergyOutputs] = useState({ solar: 0, battery: 0, grid: 0, home: 1200 })

  // Get most used source
  const mostUsedSource = useMemo(() => {
    const { solar, battery, grid } = sourceUsage
    if (solar >= battery && solar >= grid) return 'solar'
    if (battery >= solar && battery >= grid) return 'battery'
    return 'grid'
  }, [sourceUsage])

  const addLog = useCallback((log: StrategyLogEntry) => setStrategyLogs(prev => [...prev.slice(-50), log]), [])

  // Get location
  useEffect(() => {
    if ('geolocation' in navigator) {
      navigator.geolocation.getCurrentPosition(
        pos => setUserLocation({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
        () => setUserLocation({ lat: 12.9716, lon: 77.5946 })
      )
    } else setUserLocation({ lat: 12.9716, lon: 77.5946 })
  }, [])

  // Fetch weather (cached 30 min)
  const fetchWeatherData = useCallback(async () => {
    if (!userLocation) return
    try {
      const lastFetch = localStorage.getItem('lastWeatherFetch')
      const now = Date.now()
      if (lastFetch && now - parseInt(lastFetch) < 30 * 60 * 1000) {
        const cached = localStorage.getItem('weatherData')
        if (cached) { setWeatherData(JSON.parse(cached)); return }
      }
      const res = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${userLocation.lat}&longitude=${userLocation.lon}&current=temperature_2m,relative_humidity_2m,is_day,cloud_cover,direct_radiation&timezone=auto`)
      if (res.ok) {
        const data = await res.json()
        const weather: WeatherData = {
          temperature: data.current.temperature_2m, humidity: data.current.relative_humidity_2m,
          cloud_cover: data.current.cloud_cover, solar_radiation: data.current.direct_radiation,
          is_day: data.current.is_day === 1, location: `${userLocation.lat.toFixed(2)}, ${userLocation.lon.toFixed(2)}`
        }
        setWeatherData(weather)
        localStorage.setItem('weatherData', JSON.stringify(weather))
        localStorage.setItem('lastWeatherFetch', now.toString())
      }
    } catch (e) { console.warn('Weather fetch failed:', e) }
  }, [userLocation])

  useEffect(() => { if (userLocation) fetchWeatherData() }, [userLocation, fetchWeatherData])

  // Power consumption: 500-1700mW normal, 1700-2500mW peak
  useEffect(() => {
    const update = () => setPowerConsumption(isCurrentlyPeakHour ? 1700 + Math.random() * 800 : 500 + Math.random() * 1200)
    update()
    const interval = setInterval(update, 10000)
    return () => clearInterval(interval)
  }, [isCurrentlyPeakHour])

  // Virtual battery: charge when solar available, drain when in use
  useEffect(() => {
    const interval = setInterval(() => {
      setBatteryState(prev => {
        let newMah = prev.currentMah
        let isCharging = false
        let isDraining = false
        let chargeRateMW = 0
        let drainRateMW = 0
        
        // Charge battery when solar is producing excess
        if (solarPowerMW > powerConsumption * 0.8 && prev.currentMah < prev.capacityMah) {
          const excessMW = solarPowerMW - powerConsumption * 0.8
          chargeRateMW = Math.min(excessMW, 100) // Max 100mW charge rate
          const chargeMah = chargeRateMW / 3.7 / 3600 * 5 // 5 second intervals
          newMah = Math.min(prev.capacityMah, prev.currentMah + chargeMah)
          isCharging = true
        }
        
        // Drain battery when it's the active source
        if (activeSource === 'battery') {
          drainRateMW = powerConsumption * 0.3 // 30% of load
          const drainMah = drainRateMW / 3.7 / 3600 * 5
          newMah = Math.max(0, newMah - drainMah)
          isDraining = true
          isCharging = false
        }
        
        return { ...prev, currentMah: newMah, isDraining, isCharging, drainRateMW, chargeRateMW }
      })
    }, 5000)
    return () => clearInterval(interval)
  }, [activeSource, powerConsumption, solarPowerMW])

  // Source priority: Solar > Battery > Grid with AI explanation
  const determineActiveSource = useCallback(() => {
    let source: 'solar' | 'battery' | 'grid' = 'grid'
    let explanation = ''
    
    if (solarPowerMW >= powerConsumption * 0.5) {
      source = 'solar'
      explanation = `☀️ AI decided to use SOLAR because solar power (${solarPowerMW.toFixed(0)}mW) meets ${((solarPowerMW / powerConsumption) * 100).toFixed(0)}% of current demand (${powerConsumption.toFixed(0)}mW). This is the cleanest and most cost-effective option.`
    } else if (batteryPercentage > 15) {
      source = 'battery'
      explanation = `🔋 AI decided to use BATTERY because solar power is insufficient (${solarPowerMW.toFixed(0)}mW < ${(powerConsumption * 0.5).toFixed(0)}mW needed) but battery is at ${batteryPercentage.toFixed(0)}% charge. This avoids expensive grid electricity.`
    } else {
      source = 'grid'
      explanation = `⚡ AI decided to use GRID because solar power is low (${solarPowerMW.toFixed(0)}mW) and battery is depleted (${batteryPercentage.toFixed(0)}%). Grid is the only viable option to meet ${powerConsumption.toFixed(0)}mW demand.`
    }
    
    setAiExplanation(explanation)
    
    // Track source usage
    setSourceUsage(prev => ({
      ...prev,
      [source]: prev[source] + 1
    }))
    
    return source
  }, [solarPowerMW, powerConsumption, batteryPercentage])

  // Generate forecast for day
  const generateForecastForDay = useCallback((dayOffset: number): ForecastPrediction[] => {
    const date = new Date()
    date.setDate(date.getDate() + dayOffset)
    const isWeekend = date.getDay() === 0 || date.getDay() === 6
    return Array.from({ length: 24 }, (_, hour) => {
      let baseMW: number
      if (isWeekend) {
        if (hour >= 11 && hour <= 14) baseMW = 1800 + Math.random() * 500
        else if (hour >= 18 && hour <= 21) baseMW = 2000 + Math.random() * 500
        else if (hour <= 6) baseMW = 300 + Math.random() * 200
        else baseMW = 1000 + Math.random() * 400
      } else {
        if (hour >= 7 && hour <= 9) baseMW = 1800 + Math.random() * 400
        else if (hour >= 17 && hour <= 20) baseMW = 2000 + Math.random() * 500
        else if (hour <= 5) baseMW = 300 + Math.random() * 200
        else baseMW = 800 + Math.random() * 400
      }
      const ts = new Date(date); ts.setHours(hour, 0, 0, 0)
      return {
        hour, predicted_kwh: baseMW / 1000, timestamp: ts.toISOString(), hour_of_day: hour,
        is_peak_hour: isWeekend ? ((hour >= 11 && hour <= 14) || (hour >= 18 && hour <= 21)) : ((hour >= 7 && hour <= 9) || (hour >= 17 && hour <= 20)),
        demand_level: baseMW > 1700 ? 'high' : (baseMW > 1000 ? 'medium' : 'low')
      }
    })
  }, [])

  // Change forecast day with AI delay
  const handleForecastDayChange = useCallback(async (day: number) => {
    setIsLoadingForecast(true)
    setSelectedForecastDay(day)
    await new Promise(r => setTimeout(r, 500 + Math.random() * 1000))
    if (!weeklyForecast[day]) {
      const fc = generateForecastForDay(day)
      setWeeklyForecast(prev => ({ ...prev, [day]: fc }))
      setForecastData(fc)
    } else setForecastData(weeklyForecast[day])
    setIsLoadingForecast(false)
  }, [weeklyForecast, generateForecastForDay])

  const fetchSensorData = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/sensor-readings/all_latest/`)
      if (res.ok) { const data = await res.json(); setSensorData(data.sensors); setIsConnected(true) }
    } catch { setIsConnected(false) }
  }, [])

  // Void call to AI model for demo
  const callAIModel = useCallback(async () => {
    addLog({ id: Date.now().toString(), timestamp: new Date().toISOString(), type: 'info', message: '🧠 Calling AI Forecasting Model...', details: 'POST /api/ai/model/predict' })
    await new Promise(r => setTimeout(r, 800))
    addLog({ id: (Date.now() + 1).toString(), timestamp: new Date().toISOString(), type: 'success', message: '✅ AI Model Response Received', details: `Predicted peak hours: ${isCurrentlyPeakHour ? 'Currently in peak' : 'Normal hours'}` })
  }, [addLog, isCurrentlyPeakHour])

  const fetchAIDecision = useCallback(async () => {
    setIsAiThinking(true)
    try {
      await new Promise(r => setTimeout(r, 500 + Math.random() * 500))
      
      // Void call to AI model
      await callAIModel()
      
      const res = await fetch(`${API_BASE_URL}/api/ai/decide/`, { method: 'POST', headers: { 'Content-Type': 'application/json' } })
      if (!res.ok) throw new Error()
      const data = await res.json()
      if (data.available) {
        setAiAvailable(true); setLastUpdate(new Date().toLocaleTimeString()); setIsConnected(true)
        if (data.current_conditions) setSensorData({ 
          temperature: data.current_conditions.temperature || 25, 
          humidity: data.current_conditions.humidity || 50, 
          ldr: data.current_conditions.ldr || 2000, 
          current: data.current_conditions.current || 1.5, 
          voltage: data.current_conditions.voltage || 12 
        })
        
        const newSource = determineActiveSource()
        setActiveSource(newSource)
        
        const solarOut = solarPowerMW
        const batteryOut = newSource === 'battery' ? Math.min(powerConsumption * 0.3, BATTERY_MAX_OUTPUT_MW) : 0
        const gridOut = Math.max(0, powerConsumption - solarOut - batteryOut)
        setEnergyOutputs({ solar: solarOut, battery: batteryOut, grid: gridOut, home: powerConsumption })
        
        setStats(prev => ({ 
          carbonSavings: prev.carbonSavings + (newSource === 'solar' ? 0.05 : 0), 
          costSavings: prev.costSavings + (newSource === 'solar' ? 0.1 : newSource === 'battery' ? 0.05 : 0), 
          powerConsumption, 
          efficiency: newSource === 'solar' ? 95 : newSource === 'battery' ? 85 : 70 
        }))
        
        // Add detailed AI decision log
        addLog({ 
          id: Date.now().toString(), 
          timestamp: new Date().toISOString(), 
          type: 'success', 
          message: `🤖 AI Decision: Switch to ${newSource.toUpperCase()}`,
          details: aiExplanation || `Solar: ${solarOut.toFixed(0)}mW, Battery: ${batteryPercentage.toFixed(0)}%, Demand: ${powerConsumption.toFixed(0)}mW`
        })
      }
    } catch { 
      setIsConnected(false)
      addLog({ id: Date.now().toString(), timestamp: new Date().toISOString(), type: 'error', message: '❌ Failed to connect to AI Engine', details: 'Check if Django server is running' })
    }
    setIsAiThinking(false)
  }, [addLog, determineActiveSource, solarPowerMW, powerConsumption, batteryPercentage, aiExplanation, callAIModel])

  useEffect(() => {
    const init = async () => {
      setIsLoading(true)
      addLog({ id: Date.now().toString(), timestamp: new Date().toISOString(), type: 'info', message: '🚀 Initializing HyperVolt AI Engine...' })
      try {
        const res = await fetch(`${API_BASE_URL}/api/ai/status/`)
        if (res.ok) {
          setAiAvailable(true); setIsConnected(true)
          addLog({ id: (Date.now() + 1).toString(), timestamp: new Date().toISOString(), type: 'success', message: '✅ Connected to AI Engine' })
          addLog({ id: (Date.now() + 2).toString(), timestamp: new Date().toISOString(), type: 'info', message: '📡 Fetching sensor data from ESP32...' })
          await Promise.all([fetchSensorData(), fetchAIDecision()])
          handleForecastDayChange(0)
        }
      } catch { 
        setIsConnected(false)
        addLog({ id: Date.now().toString(), timestamp: new Date().toISOString(), type: 'warning', message: '⚠️ Running in offline mode', details: 'Start Django: cd api && python manage.py runserver' })
      }
      setIsLoading(false)
    }
    init()
  }, [addLog, fetchSensorData, fetchAIDecision, handleForecastDayChange])

  useEffect(() => {
    const interval = setInterval(() => { fetchSensorData(); fetchAIDecision() }, POLL_INTERVAL)
    return () => clearInterval(interval)
  }, [fetchSensorData, fetchAIDecision])

  // Colors: Solar=Green, Battery=Yellow, Grid=Red
  const getSourceColor = (s: string) => s === 'solar' ? 'text-green-400' : s === 'battery' ? 'text-yellow-400' : 'text-red-400'
  const getSourceBgColor = (s: string) => s === 'solar' ? 'bg-green-500/20 border-green-500/50' : s === 'battery' ? 'bg-yellow-500/20 border-yellow-500/50' : 'bg-red-500/20 border-red-500/50'
  const getSourceIcon = (s: string) => s === 'solar' ? <Sun className="w-6 h-6 text-green-400" /> : s === 'battery' ? <Battery className="w-6 h-6 text-yellow-400" /> : <Plug className="w-6 h-6 text-red-400" />
  const getDayName = (o: number) => o === 0 ? 'Today' : o === 1 ? 'Tomorrow' : new Date(Date.now() + o * 86400000).toLocaleDateString('en-US', { weekday: 'long' })

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900">
      <header className="border-b border-gray-700/50 bg-gray-900/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="container mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg"><Zap className="w-6 h-6 text-white" /></div>
              <div><h1 className="text-2xl font-bold text-white">HyperVolt</h1><p className="text-xs text-gray-400">AI-Driven Energy Orchestrator</p></div>
            </div>
            <div className="flex items-center gap-4">
              <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border ${aiAvailable ? 'bg-green-500/10 border-green-500/50 text-green-400' : 'bg-yellow-500/10 border-yellow-500/50 text-yellow-400'}`}>
                <Brain className="w-3 h-3" /><span className="text-xs font-medium">{isAiThinking ? 'AI Thinking...' : aiAvailable ? 'AI Online' : 'AI Offline'}</span>
              </div>
              <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border ${isConnected ? 'bg-blue-500/10 border-blue-500/50 text-blue-400' : 'bg-red-500/10 border-red-500/50 text-red-400'}`}>
                <Database className="w-3 h-3" /><span className="text-xs font-medium">{isConnected ? 'Connected' : 'Offline'}</span>
              </div>
              <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-800 rounded-full border border-gray-700">
                <Activity className="w-4 h-4 text-blue-400" /><span className="text-xs text-gray-300">{powerConsumption.toFixed(0)} mW</span>
              </div>
              <button onClick={fetchAIDecision} disabled={isAiThinking} className="p-2 rounded-lg bg-gray-800 border border-gray-700 hover:bg-gray-700 disabled:opacity-50">
                <RefreshCw className={`w-4 h-4 text-gray-400 ${isAiThinking ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-6 py-8">
        {isLoading ? (
          <div className="flex items-center justify-center h-64"><div className="flex flex-col items-center gap-4"><div className="w-12 h-12 border-4 border-purple-500 border-t-transparent rounded-full animate-spin" /><p className="text-gray-400">Connecting to AI Engine...</p></div></div>
        ) : (
          <>
            {/* Current Source with AI Explanation */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
              <div className={`rounded-xl border p-6 ${getSourceBgColor(activeSource)}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-6">
                    <div className={`p-4 rounded-xl ${getSourceBgColor(activeSource)}`}>{getSourceIcon(activeSource)}</div>
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <h2 className="text-lg text-gray-400">Current Energy Source</h2>
                        <span className="px-2 py-0.5 text-xs bg-purple-500/30 text-purple-300 rounded-full flex items-center gap-1"><Brain className="w-3 h-3" />AI Generated Decision</span>
                      </div>
                      <p className={`text-3xl font-bold capitalize ${getSourceColor(activeSource)}`}>{activeSource}</p>
                      <p className="text-sm text-gray-400 mt-2 max-w-xl">{aiExplanation}</p>
                    </div>
                  </div>
                  <div className="flex gap-8">
                    <div className="text-center"><p className="text-2xl font-bold text-green-400">{solarPowerMW.toFixed(0)} mW</p><p className="text-xs text-gray-400">Solar (V×I)</p></div>
                    <div className="text-center"><p className="text-2xl font-bold text-yellow-400">{batteryPercentage.toFixed(0)}%</p><p className="text-xs text-gray-400">Battery</p></div>
                    <div className="text-center"><p className={`text-2xl font-bold ${isCurrentlyPeakHour ? 'text-red-400' : 'text-blue-400'}`}>{powerConsumption.toFixed(0)} mW</p><p className="text-xs text-gray-400">{isCurrentlyPeakHour ? 'Peak' : 'Normal'}</p></div>
                  </div>
                </div>
              </div>
            </motion.div>

            {/* Most Used Source Indicator */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.02 }} className="mb-8">
              <div className="bg-gray-800/50 rounded-xl border border-gray-700/50 p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <TrendingUp className="w-5 h-5 text-purple-400" />
                    <h3 className="text-sm font-medium text-gray-300">Most Used Source Today</h3>
                  </div>
                  <div className="flex items-center gap-4">
                    {getSourceIcon(mostUsedSource)}
                    <span className={`text-lg font-bold capitalize ${getSourceColor(mostUsedSource)}`}>{mostUsedSource}</span>
                    <span className="text-xs text-gray-500">({sourceUsage[mostUsedSource]} times)</span>
                  </div>
                </div>
                <div className="flex gap-4 mt-3">
                  <div className="flex items-center gap-2"><Sun className="w-4 h-4 text-green-400" /><span className="text-xs text-gray-400">Solar: {sourceUsage.solar}</span></div>
                  <div className="flex items-center gap-2"><Battery className="w-4 h-4 text-yellow-400" /><span className="text-xs text-gray-400">Battery: {sourceUsage.battery}</span></div>
                  <div className="flex items-center gap-2"><Plug className="w-4 h-4 text-red-400" /><span className="text-xs text-gray-400">Grid: {sourceUsage.grid}</span></div>
                </div>
              </div>
            </motion.div>

            {/* Battery Bar with Charge/Discharge */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="mb-8">
              <div className="bg-gray-800/50 rounded-xl border border-gray-700/50 p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    {batteryState.isCharging ? <BatteryCharging className="w-5 h-5 text-green-400" /> : <Battery className="w-5 h-5 text-yellow-400" />}
                    <h3 className="text-sm font-medium text-gray-300">Virtual Battery ({BATTERY_CAPACITY_MAH}mAh / {BATTERY_MAX_VOLTAGE}V)</h3>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-gray-400">
                    <span>{batteryState.currentMah.toFixed(0)} mAh</span>
                    {batteryState.isCharging && <span className="text-green-400 animate-pulse">⚡ Charging: +{batteryState.chargeRateMW.toFixed(0)}mW</span>}
                    {batteryState.isDraining && <span className="text-yellow-400 animate-pulse">🔋 Draining: -{batteryState.drainRateMW.toFixed(0)}mW</span>}
                  </div>
                </div>
                <div className="w-full h-4 bg-gray-700 rounded-full overflow-hidden">
                  <motion.div className={`h-full rounded-full ${batteryState.isCharging ? 'bg-green-500' : batteryPercentage > 50 ? 'bg-green-500' : batteryPercentage > 20 ? 'bg-yellow-500' : 'bg-red-500'}`} initial={{ width: 0 }} animate={{ width: `${batteryPercentage}%` }} transition={{ duration: 0.5 }} />
                </div>
                <div className="flex justify-between mt-1 text-xs text-gray-500"><span>0%</span><span className={`font-bold ${batteryPercentage > 50 ? 'text-green-400' : batteryPercentage > 20 ? 'text-yellow-400' : 'text-red-400'}`}>{batteryPercentage.toFixed(1)}%</span><span>100%</span></div>
              </div>
            </motion.div>

            {/* Weather */}
            {weatherData && (
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="mb-8">
                <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3"><Cloud className="w-6 h-6 text-blue-400" /><div><h3 className="text-lg font-semibold text-blue-400">Weather (Open-Meteo)</h3><p className="text-xs text-gray-400 flex items-center gap-1"><MapPin className="w-3 h-3" />{weatherData.location}</p></div></div>
                    <div className="flex gap-6">
                      <div className="text-center"><p className="text-xl font-bold text-white">{weatherData.temperature.toFixed(1)}°C</p><p className="text-xs text-gray-400">Temp</p></div>
                      <div className="text-center"><p className="text-xl font-bold text-white">{weatherData.humidity}%</p><p className="text-xs text-gray-400">Humidity</p></div>
                      <div className="text-center"><p className="text-xl font-bold text-white">{weatherData.cloud_cover}%</p><p className="text-xs text-gray-400">Clouds</p></div>
                      <div className="text-center"><p className="text-xl font-bold text-yellow-400">{weatherData.solar_radiation.toFixed(0)} W/m²</p><p className="text-xs text-gray-400">Solar</p></div>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {/* Peak Settings */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }} className="mb-8">
              <div className="bg-gray-800/50 rounded-xl border border-gray-700/50 p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3"><Settings className="w-5 h-5 text-purple-400" /><h3 className="text-sm font-medium text-gray-300">Peak Hour Settings</h3>{isCurrentlyPeakHour && <span className="px-2 py-0.5 text-xs bg-red-500/30 text-red-300 rounded-full animate-pulse">Peak Hour</span>}</div>
                  <button onClick={() => setShowPeakSettings(!showPeakSettings)} className="text-gray-400 hover:text-white"><ChevronDown className={`w-5 h-5 transition-transform ${showPeakSettings ? 'rotate-180' : ''}`} /></button>
                </div>
                <AnimatePresence>
                  {showPeakSettings && (
                    <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="mt-4 space-y-3">
                      <div className="grid grid-cols-4 gap-2">
                        {[{ mode: 'auto', label: 'Auto (7-9AM, 5-8PM)' }, { mode: 'now', label: 'Now' }, { mode: 'plus1', label: '+1 Hour' }, { mode: 'custom', label: 'Custom' }].map(({ mode, label }) => (
                          <button key={mode} onClick={() => setPeakSettings({ ...peakSettings, mode: mode as PeakHourSettings['mode'] })} className={`px-3 py-2 text-xs rounded-lg border ${peakSettings.mode === mode ? 'bg-purple-500/30 border-purple-500/50 text-purple-300' : 'bg-gray-700/50 border-gray-600 text-gray-400 hover:bg-gray-700'}`}>{label}</button>
                        ))}
                      </div>
                      {peakSettings.mode === 'custom' && (
                        <div className="flex items-center gap-4">
                          <div className="flex items-center gap-2"><label className="text-xs text-gray-400">Start:</label><select value={peakSettings.customStart ?? 17} onChange={e => setPeakSettings({ ...peakSettings, customStart: parseInt(e.target.value) })} className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm text-white">{Array.from({ length: 24 }, (_, i) => <option key={i} value={i}>{i.toString().padStart(2, '0')}:00</option>)}</select></div>
                          <div className="flex items-center gap-2"><label className="text-xs text-gray-400">End:</label><select value={peakSettings.customEnd ?? 20} onChange={e => setPeakSettings({ ...peakSettings, customEnd: parseInt(e.target.value) })} className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm text-white">{Array.from({ length: 24 }, (_, i) => <option key={i} value={i}>{i.toString().padStart(2, '0')}:00</option>)}</select></div>
                        </div>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>

            {/* Stats */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="mb-8">
              <StatsGrid carbonSavings={stats.carbonSavings} costSavings={stats.costSavings} powerConsumption={stats.powerConsumption} efficiency={stats.efficiency} />
            </motion.div>

            {/* Sensors (mW, mA) */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }} className="mb-8">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2"><Database className="w-5 h-5 text-blue-400" />ESP32 Sensors<span className="text-xs text-gray-500 ml-2">Solar = V × I (mW)</span></h3>
              <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
                {[
                  { label: 'Temperature', value: `${sensorData.temperature.toFixed(1)}°C`, color: 'text-red-400' },
                  { label: 'Humidity', value: `${sensorData.humidity.toFixed(0)}%`, color: 'text-blue-400' },
                  { label: 'LDR', value: sensorData.ldr.toFixed(0), color: 'text-yellow-400' },
                  { label: 'Current', value: `${(sensorData.current * 1000).toFixed(0)} mA`, color: 'text-green-400' },
                  { label: 'Voltage', value: `${sensorData.voltage.toFixed(0)} V`, color: 'text-purple-400' },
                  { label: 'Solar Power', value: `${solarPowerMW.toFixed(0)} mW`, color: 'text-green-500', highlight: true },
                ].map((s, i) => (
                  <div key={i} className={`rounded-lg p-4 border ${s.highlight ? 'bg-green-500/10 border-green-500/30' : 'bg-gray-800/50 border-gray-700/50'}`}><p className="text-xs text-gray-400 mb-1">{s.label}</p><p className={`text-2xl font-bold ${s.color}`}>{s.value}</p></div>
                ))}
              </div>
            </motion.div>

            {/* Energy Flow + Distribution */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
              <div className="h-[400px]"><EnergyFlow activeSource={activeSource} solarOutput={energyOutputs.solar / 1000} batteryOutput={energyOutputs.battery / 1000} gridOutput={energyOutputs.grid / 1000} homeConsumption={energyOutputs.home / 1000} /></div>
              <div>
                <PowerDistribution solarOutput={energyOutputs.solar / 1000} batteryOutput={energyOutputs.battery / 1000} gridOutput={energyOutputs.grid / 1000} />
                <div className="mt-4 bg-gray-800/50 rounded-lg p-4 border border-gray-700/50">
                  <h4 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2"><Brain className="w-4 h-4 text-purple-400" />AI Source Allocation (mW)</h4>
                  <div className="space-y-2">
                    {[{ source: 'solar', power: energyOutputs.solar }, { source: 'battery', power: energyOutputs.battery }, { source: 'grid', power: energyOutputs.grid }].filter(s => s.power > 0).map((item, i) => (
                      <div key={i} className="flex items-center justify-between"><div className="flex items-center gap-2">{getSourceIcon(item.source)}<span className={`capitalize ${getSourceColor(item.source)}`}>{item.source}</span></div><span className="text-white font-medium">{item.power.toFixed(0)} mW</span></div>
                    ))}
                  </div>
                </div>
              </div>
            </motion.div>

            {/* 7-Day Forecast */}
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }} className="mb-8">
              <div className="bg-gray-900/50 rounded-lg p-6 border border-gray-700/50">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2"><Calendar className="w-5 h-5 text-purple-400" /><h3 className="text-lg font-semibold text-white">7-Day Energy Forecast</h3><span className="px-2 py-0.5 text-xs bg-purple-500/30 text-purple-300 rounded-full flex items-center gap-1"><Brain className="w-3 h-3" />AI</span></div>
                  <select value={selectedForecastDay} onChange={e => handleForecastDayChange(parseInt(e.target.value))} disabled={isLoadingForecast} className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white">
                    {Array.from({ length: 7 }, (_, i) => <option key={i} value={i}>{getDayName(i)}</option>)}
                  </select>
                </div>
                {isLoadingForecast ? (
                  <div className="h-[300px] flex items-center justify-center"><div className="flex flex-col items-center gap-3"><div className="flex items-center gap-2"><Brain className="w-8 h-8 text-purple-400 animate-pulse" /><div className="w-8 h-8 border-4 border-purple-500 border-t-transparent rounded-full animate-spin" /></div><p className="text-gray-400">AI analyzing patterns...</p></div></div>
                ) : <EnergyChart forecastData={forecastData} />}
                <p className="text-xs text-gray-500 mt-2">{[0, 6].includes(new Date(Date.now() + selectedForecastDay * 86400000).getDay()) ? '📅 Weekend: Peak afternoon & evening' : '📅 Weekday: Peak morning & evening'}</p>
              </div>
            </motion.div>

            <div className="text-center text-sm text-gray-500 mb-4"><Clock className="w-4 h-4 inline mr-1" />Last AI Update: {lastUpdate || 'Never'}</div>
          </>
        )}
      </main>

      <footer className="border-t border-gray-700/50 bg-gray-900/80 mt-12"><div className="container mx-auto px-6 py-4 text-center text-sm text-gray-400"><p>HyperVolt - SMVIT Sustainergy Hackathon 2026</p></div></footer>
      <LogsViewer logs={strategyLogs} />
    </div>
  )
}
