import { useEffect, useState } from 'react'
import axios from 'axios'
import { useDashboardStore } from './store/useStore'
import type { DashboardTab } from './types'
import HeaderBar from './components/Header/HeaderBar'
import AlertStrip from './components/AlertStrip'
import SettingsPanel from './components/Settings/SettingsPanel'
import OverviewTab from './tabs/OverviewTab'
import PricesTab from './tabs/PricesTab'
import { PredictionTab } from './tabs/PredictionTab'
import NewsTab from './tabs/NewsTab'
import AnchorDataTab from './tabs/AnchorDataTab'
import SpreadsPanel from './components/SpreadsPanel'
import PortfolioTab from './tabs/PortfolioTab'
// import BacktestTab from './tabs/BacktestTab' // re-enable alongside the commented backtest tab below

// In dev, use relative URLs so Vite's proxy forwards /api/* to localhost:8000.
// In production (when VITE_API_BASE is set), use the full base URL.
const API_BASE = import.meta.env.VITE_API_BASE ?? ''
const api = axios.create({ baseURL: API_BASE, timeout: 90000 })

function App() {
  // Single-value selectors: only re-render when activeTab actually changes.
  // Object selectors without `shallow` always return a new reference → App would
  // re-render on every store update (WebSocket prices every 5s, historical fetches,
  // snapshotMapper updates) → OverviewTab re-renders constantly → clicks swallowed.
  const activeTab = useDashboardStore((state) => state.activeTab)
  const setActiveTab = useDashboardStore((state) => state.setActiveTab)
  const [showSettings, setShowSettings] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    // Dynamically import and connect WebSocket to avoid top-level side effects
    import('./store/dashboardStore').then(({ connectWebSocket }) => {
      connectWebSocket(API_BASE)
    })
  }, [])

  useEffect(() => {
    const fetchDashboard = async () => {
      // Read store actions once via getState() — they're stable and never change,
      // so we don't need to subscribe (which would cause App to re-render on
      // every store update and swallow clicks).
      const store = useDashboardStore.getState()

      try {
        // Fast endpoints only — composite is slow (8s cold) and fetched separately
        // below so it never blocks the isLoading gate.
        const [pricesRes, enhancedRes, macroRes, eiaRes, cftcRes, rigsRes, forwardRes, analyticsRes, newsRes, indicatorsRes] = await Promise.allSettled([
          api.get(`/api/prices/all`),
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

        if (pricesRes.status === 'fulfilled' && pricesRes.value.data?.data) {
          store.setPrices(pricesRes.value.data.data)
        }

        if (enhancedRes.status === 'fulfilled' && enhancedRes.value.data?.data) {
          store.setEnhancedSignals(enhancedRes.value.data.data)
          store.setCracks({
            crack_321: enhancedRes.value.data.data.market_state.crack_321,
            crack_532: enhancedRes.value.data.data.market_state.crack_532,
            cl_brent_spread: enhancedRes.value.data.data.market_state.cl_brent_spread,
            timestamp: enhancedRes.value.data.data.timestamp,
          })
        }

        if (macroRes.status === 'fulfilled' && macroRes.value.data?.data) {
          store.setMacro(macroRes.value.data.data)
        }

        if (eiaRes.status === 'fulfilled' && eiaRes.value.data?.data && Object.keys(eiaRes.value.data.data).length > 0) {
          store.setEIAData(eiaRes.value.data.data)
          store.setEIAStatus('ready')
        } else {
          store.setEIAStatus('unavailable')
        }

        if (cftcRes.status === 'fulfilled' && cftcRes.value.data?.data && cftcRes.value.data.data.WTI) {
          store.setCFTC(cftcRes.value.data.data)
          store.setCFTCStatus('ready')
        } else {
          store.setCFTCStatus('unavailable')
        }

        if (rigsRes.status === 'fulfilled' && rigsRes.value.data?.data) {
          store.setRigs(rigsRes.value.data.data)
        }

        if (forwardRes.status === 'fulfilled' && forwardRes.value.data?.data?.forward_curve) {
          store.setForwardCurve(forwardRes.value.data.data.forward_curve)
        }

        if (analyticsRes.status === 'fulfilled' && analyticsRes.value.data?.data) {
          store.setAnalytics(analyticsRes.value.data.data)
        }

        if (newsRes.status === 'fulfilled' && newsRes.value.data?.data) {
          store.setNews(newsRes.value.data.data)
        }

        if (indicatorsRes.status === 'fulfilled' && indicatorsRes.value.data?.data) {
          store.setIndicators(indicatorsRes.value.data.data)
        }
      } catch (error) {
        console.warn('Dashboard load failed:', error)
      } finally {
        // Page is interactive now — composite and historical load in background.
        setIsLoading(false)
      }

      // Background: fetch composite (slow on cold start, instant when cached).
      api.get(`/api/signals/composite`).then((res) => {
        if (res.data?.data) useDashboardStore.getState().setSignals(res.data.data)
      }).catch(() => {})

      // Background: fetch per-symbol historical prices.
      const historySymbols = ['WTI', 'Brent', 'RBOB', 'HO', 'GO', 'NG', '3-2-1CRACK', 'GASCRACK', 'DIESELCRACK', 'GASOILCRACK', 'WTI-Brent', 'WTI_CAL_SPREAD', 'BRENT_CAL_SPREAD', 'WTI_FLY', 'BRENT_FLY', 'HO_FLY']
      Promise.allSettled(
        historySymbols.map(async (symbol) => {
          try {
            const response = await api.get(`/api/prices/${symbol}/historical?period=1mo`)
            if (response.data?.data) {
              useDashboardStore.getState().setHistoricalPrices(symbol, response.data.data)
            }
          } catch (error) {
            console.warn(`Failed historical data for ${symbol}:`, error)
          }
        }),
      )
    }

    fetchDashboard()
  }, [])

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
              { id: 'spreads' as DashboardTab, label: 'Spreads' },
              { id: 'news' as DashboardTab, label: 'News & Forecast' },
              { id: 'anchor' as DashboardTab, label: 'EIA Anchors' },
              { id: 'prediction' as DashboardTab, label: 'Predictions' },
              // { id: 'backtest' as DashboardTab, label: 'Backtest' },
              { id: 'portfolio' as DashboardTab, label: 'Risk & Portfolio' },
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

            {activeTab === 'prediction' && (
              <div className="space-y-6">
                <PredictionTab />
              </div>
            )}



            {/* activeTab === 'backtest' && (
              <div className="space-y-6">
                <BacktestTab />
              </div>
            ) */}

            {activeTab === 'portfolio' && (
              <div className="space-y-6">
                <PortfolioTab />
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
