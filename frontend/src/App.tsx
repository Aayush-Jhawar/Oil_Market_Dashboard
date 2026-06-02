import { useEffect, useState } from 'react'
import axios from 'axios'
import { useDashboardStore } from './store/useStore'
import type { DashboardTab } from './types'
import { connectWebSocket } from './store/dashboardStore'
import HeaderBar from './components/Header/HeaderBar'
import AlertStrip from './components/AlertStrip'
import SettingsPanel from './components/Settings/SettingsPanel'
import SnapshotPreview from './components/SnapshotPreview'
import './store/snapshotMapper'
import OverviewTab from './tabs/OverviewTab'
import PricesTab from './tabs/PricesTab'
import MarketStructureTab from './tabs/MarketStructureTab'
import SeasonalityTab from './tabs/SeasonalityTab'
import NewsTab from './tabs/NewsTab'
import AnchorDataTab from './tabs/AnchorDataTab'
import ProToolsTab from './tabs/ProToolsTab'
import SpreadsPanel from './components/SpreadsPanel'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
const api = axios.create({ baseURL: API_BASE, timeout: 15000 })

function App() {
  const { activeTab, setActiveTab } = useDashboardStore((state) => ({
    activeTab: state.activeTab,
    setActiveTab: state.setActiveTab,
  }))
  const [showSettings, setShowSettings] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  const {
    setPrices,
    setHistoricalPrices,
    setSignals,
    setCracks,
    setNews,
    setMacro,
    setRigs,
    setCFTC,
    setEIAData,
    setForwardCurve,
    setAnalytics,
    setEnhancedSignals,
    setIndicators,
  } = useDashboardStore()

  // start websocket connection to populate `snapshot` (simulated backend)
  useEffect(() => {
    const ws = connectWebSocket()
    return () => ws.close()
  }, [])

  useEffect(() => {
    const fetchDashboard = async () => {
      try {
        const endpoints = await Promise.allSettled([
          api.get(`/api/prices/all`),
          api.get(`/api/signals/composite`),
          api.get(`/api/signals/enhanced`),
          api.get(`/api/macro/all`),
          api.get(`/api/eia/weekly`),
          api.get(`/api/cftc/latest`),
          api.get(`/api/rigs/latest`),
          api.get(`/api/analytics/forward-curve`),
          api.get(`/api/analytics/correlations`),
          api.get(`/api/news/enhanced`),
          api.get(`/api/analytics/indicators?symbol=WTI&period=3mo&ema_periods=20,50&atr_period=14`),
        ])

        const [pricesRes, compositeRes, enhancedRes, macroRes, eiaRes, cftcRes, rigsRes, forwardRes, analyticsRes, newsRes, indicatorsRes] = endpoints

        if (pricesRes.status === 'fulfilled' && pricesRes.value.data?.data) {
          setPrices(pricesRes.value.data.data)
        }

        if (compositeRes.status === 'fulfilled' && compositeRes.value.data?.data) {
          setSignals(compositeRes.value.data.data)
        }

        if (enhancedRes.status === 'fulfilled' && enhancedRes.value.data?.data) {
          setEnhancedSignals(enhancedRes.value.data.data)
          setCracks({
            crack_321: enhancedRes.value.data.data.market_state.crack_321,
            crack_532: enhancedRes.value.data.data.market_state.crack_532,
            cl_brent_spread: enhancedRes.value.data.data.market_state.cl_brent_spread,
            timestamp: enhancedRes.value.data.data.timestamp,
          })
        }

        if (macroRes.status === 'fulfilled' && macroRes.value.data?.data) {
          setMacro(macroRes.value.data.data)
        }

        if (eiaRes.status === 'fulfilled' && eiaRes.value.data?.data) {
          setEIAData(eiaRes.value.data.data)
        }

        if (cftcRes.status === 'fulfilled' && cftcRes.value.data?.data) {
          setCFTC(cftcRes.value.data.data)
        }

        if (rigsRes.status === 'fulfilled' && rigsRes.value.data?.data) {
          setRigs(rigsRes.value.data.data)
        }

        if (forwardRes.status === 'fulfilled' && forwardRes.value.data?.data?.forward_curve) {
          setForwardCurve(forwardRes.value.data.data.forward_curve)
        }

        if (analyticsRes.status === 'fulfilled' && analyticsRes.value.data?.data) {
          setAnalytics(analyticsRes.value.data.data)
        }

        if (newsRes.status === 'fulfilled' && newsRes.value.data?.data) {
          setNews(newsRes.value.data.data)
        }

        if (indicatorsRes.status === 'fulfilled' && indicatorsRes.value.data?.data) {
          setIndicators(indicatorsRes.value.data.data)
        }

        const historySymbols = ['WTI', 'Brent', 'RBOB', 'HO', 'GO', 'HH']
        await Promise.allSettled(
          historySymbols.map(async (symbol) => {
            try {
              const response = await api.get(`/api/prices/${symbol}/historical?period=1mo`)
              if (response.data?.data) {
                setHistoricalPrices(symbol, response.data.data)
              }
            } catch (error) {
              console.warn(`Failed historical data for ${symbol}:`, error)
            }
          }),
        )
      } catch (error) {
        console.warn('Dashboard load failed:', error)
      } finally {
        setIsLoading(false)
      }
    }

    fetchDashboard()
  }, [
    setPrices,
    setHistoricalPrices,
    setSignals,
    setCracks,
    setNews,
    setMacro,
    setRigs,
    setCFTC,
    setEIAData,
    setForwardCurve,
    setAnalytics,
    setEnhancedSignals,
    setIndicators,
  ])

  return (
    <div className="min-h-screen bg-slate-950 text-slate-50 pt-14">
      <HeaderBar onSettingsClick={() => setShowSettings(!showSettings)} />

      <div className="container mx-auto px-4 py-6">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3 mb-6">
          <div>
            <p className="text-sm uppercase tracking-[0.3em] text-slate-500">Energy Trading Desk</p>
            <h1 className="text-3xl font-semibold text-white">Oil Market Dashboard</h1>
          </div>
          <div className="flex flex-wrap gap-3">
            {([
              { id: 'overview' as DashboardTab, label: 'Overview' },
              { id: 'prices' as DashboardTab, label: 'Prices' },
              { id: 'market' as DashboardTab, label: 'Market' },
              { id: 'forward' as DashboardTab, label: 'Forward' },
              { id: 'spreads' as DashboardTab, label: 'Spreads' },
              { id: 'news' as DashboardTab, label: 'News' },
              { id: 'anchor' as DashboardTab, label: 'EIA Anchors' },
              { id: 'protools' as DashboardTab, label: 'Pro Tools' },
            ] as Array<{ id: DashboardTab; label: string }> ).map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-2 rounded-full text-sm font-semibold transition ${
                  activeTab === tab.id
                    ? 'bg-blue-500 text-slate-950 shadow-lg shadow-blue-500/20'
                    : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        <div className="mb-6">
          <AlertStrip />
        </div>

        <div className="mb-6">
          <SnapshotPreview />
        </div>

        {isLoading ? (
          <div className="flex h-96 items-center justify-center">
            <div className="text-slate-400">Loading dashboard...</div>
          </div>
        ) : (
          <>
            {activeTab === 'overview' && (
              <div className="space-y-6">
                <OverviewTab />
              </div>
            )}

            {activeTab === 'prices' && (
              <div className="space-y-6">
                <PricesTab />
              </div>
            )}

            {activeTab === 'market' && (
              <div className="space-y-6">
                <MarketStructureTab />
              </div>
            )}

            {activeTab === 'forward' && (
              <div className="space-y-6">
                <SeasonalityTab />
              </div>
            )}

            {activeTab === 'spreads' && (
              <div className="space-y-6">
                <SpreadsPanel />
              </div>
            )}

            {activeTab === 'news' && (
              <div className="space-y-6">
                <NewsTab />
              </div>
            )}

            {activeTab === 'anchor' && (
              <div className="space-y-6">
                <AnchorDataTab />
              </div>
            )}

            {activeTab === 'protools' && (
              <div className="space-y-6">
                <ProToolsTab />
              </div>
            )}
          </>
        )}
      </div>

      {showSettings && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <SettingsPanel onClose={() => setShowSettings(false)} />
        </div>
      )}
    </div>
  )
}

export default App
