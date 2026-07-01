import { useEffect, useState, useMemo } from 'react'
import axios from 'axios'
import { useDashboardStore as useLegacyStore } from '../store/useStore'
import { useDashboardStore as useSnapshotStore } from '../store/dashboardStore'
import Card from '../components/shared/Card'
import Badge from '../components/shared/Badge'
import Sparkline from '../components/shared/Sparkline'
import { MacroSignalPulseCard, RefineryCrackSignalsCard, WatchlistMomentumCard } from '../components/EnhancedSignalsPanel'
import PriceHistoryChart from '../components/PriceHistoryChart'
import PaperTrading from '../components/PaperTrading'
import UnifiedMarketStructurePanel from '../components/UnifiedMarketStructurePanel'

const API_BASE = (import.meta as any).env?.VITE_API_BASE || 'http://localhost:8000'

// ─── Factor metadata ─────────────────────────────────────────────────────────

const FACTOR_META: Record<string, { label: string; description: string; defaultWeight: number }> = {
  trend_ema: {
    label: 'EMA Trend',
    description: 'EMA20/50 crossover + slope magnitude. A bullish cross with rising slope scores near +1.0, bearish cross near -1.0. Includes magnitude of divergence.',
    defaultWeight: 18,
  },
  trend_macd: {
    label: 'MACD Histogram',
    description: 'MACD histogram (MACD line minus signal line), normalized by price. Positive and growing histogram = bullish momentum building.',
    defaultWeight: 12,
  },
  bb_pct_b: {
    label: 'Bollinger %B',
    description: 'Where price sits within the Bollinger Band. Price at upper band → bearish (overbought). Price at lower band → bullish (mean-reversion opportunity). Uses 20-period, 2σ bands.',
    defaultWeight: 10,
  },
  mean_rev_zscore: {
    label: 'Mean Reversion Z-Score',
    description: 'Price z-score vs 20D rolling mean, inverted. When price is 2+ sigma above mean (overbought) → bearish score. When 2+ sigma below → bullish.',
    defaultWeight: 10,
  },
  rsi_normalized: {
    label: 'RSI (14)',
    description: 'RSI normalized to [-1, +1]. RSI > 70 → overbought → bearish score (-1). RSI < 30 → oversold → bullish score (+1). RSI = 50 → neutral.',
    defaultWeight: 10,
  },
  momentum_roc: {
    label: 'Momentum ROC',
    description: '14-day Rate of Change, z-scored over 60-day window. Captures medium-term momentum direction and relative strength vs recent history.',
    defaultWeight: 10,
  },
  macro_dxy: {
    label: 'DXY (Dollar Index)',
    description: 'US Dollar Index direction, inverted. Strong dollar is bearish for oil (commodities priced in USD). A +1% DXY move → -0.8 score. Source: yfinance live.',
    defaultWeight: 8,
  },
  macro_risk: {
    label: 'Risk Appetite (SPX/VIX)',
    description: 'Equity risk proxy for oil demand. Rising S&P 500 = risk-on = bullish oil. High VIX = risk-off = bearish. Composite of SPX daily move and VIX level.',
    defaultWeight: 7,
  },
  fundamentals_eia: {
    label: 'EIA Surprise',
    description: 'Weekly EIA crude inventory vs 5-year average. A draw below 5yr norm is bullish. A build above is bearish. Requires EIA_API_KEY configuration.',
    defaultWeight: 5,
  },
  fundamentals_cftc: {
    label: 'CFTC Contrarian',
    description: 'CFTC Managed Money net position, inverted (contrarian). Extreme net long = crowded trade = bearish. Currently awaiting live CFTC data integration.',
    defaultWeight: 5,
  },
  news_sentiment: {
    label: 'News Sentiment',
    description: 'NLP-derived sentiment score from recent energy news headlines (−1 to +1). Captures market-moving narratives around supply, demand and geopolitics.',
    defaultWeight: 15,
  },
  ai_prediction: {
    label: 'AI Prediction',
    description: 'Machine learning derived intraday directional bias. Aggregates multiple timeframes and features to predict short-term direction.',
    defaultWeight: 15,
  },
}


interface FactorState {
  weight: number    // 0-100
  enabled: boolean
}


function buildDefaultFactors(): Record<string, FactorState> {
  const out: Record<string, FactorState> = {}
  for (const [key, meta] of Object.entries(FACTOR_META)) {
    out[key] = { weight: meta.defaultWeight, enabled: true }
  }
  return out
}

// ─── Interactive Composite Score Card ────────────────────────────────────────

function CompositeScoreCard({ signals, symbolSignal, selectedCommodity, className }: { signals: any, symbolSignal?: any, selectedCommodity: string, className?: string }) {
  const [factors, setFactors] = useState<Record<string, FactorState>>(buildDefaultFactors())
  const [expandedFactor, setExpandedFactor] = useState<string | null>(null)
  const [showDetails, setShowDetails] = useState(false)

  // Sync actual weights from the backend
  useEffect(() => {
    if (signals?.weights && Object.keys(signals.weights).length > 0) {
      setFactors(prev => {
        const next = { ...prev }
        let changed = false
        for (const key of Object.keys(FACTOR_META)) {
          let pct = 0
          if (key === 'news_sentiment') {
            pct = 15 // Hardcoded overlay in backend
          } else {
            const backendWeight = signals.weights[key]
            if (backendWeight !== undefined) {
              // The backend squashes the multi-factor weights to 85% to make room for 15% news
              pct = Math.round((backendWeight * 0.85) * 100)
            }
          }
          if (next[key] && next[key].weight !== pct) {
            next[key] = { ...next[key], weight: pct }
            changed = true
          }
        }
        return changed ? next : prev
      })
    }
  }, [signals?.weights])

  const subScores: Record<string, number> = {
    ...(signals?.sub_scores ?? {}),
    ...(signals?.factor_scores ?? {}),
  }
  const compositeScore = signals?.composite_score ?? 0

  // Recalculate composite live from enabled factors + local weights
  const liveScore = useMemo(() => {
    const enabled = Object.entries(factors).filter(([, v]) => v.enabled)
    // Only include factors that the backend successfully calculated (present in subScores)
    const validFactors = enabled.filter(([key]) => subScores[key] !== undefined && subScores[key] !== null)
    
    const total = validFactors.reduce((s, [, v]) => s + v.weight, 0)
    if (total === 0) return 0
    let score = 0
    for (const [key, fac] of validFactors) {
      const sub = subScores[key] ?? 0
      score += sub * (fac.weight / total)
    }
    return Math.round(score * 100 * 10) / 10
  }, [factors, subScores])

  const displayScore = showDetails ? liveScore : compositeScore
  // Regime here is DIRECTIONAL only (BULLISH/BEARISH/NEUTRAL) — curve structure is separate
  const regime = signals?.regime || (displayScore > 30 ? 'BULLISH' : displayScore < -30 ? 'BEARISH' : 'NEUTRAL')
  const regimeColor = regime.includes('BULLISH') ? '#10B981' : regime.includes('BEARISH') ? '#EF4444' : '#6B7280'
  const regimeType = signals?.regime_type   // 'TRENDING', 'RANGING', 'HIGH_VOL'
  const signal = signals?.signal ?? 'NEUTRAL'
  const confidence = signals?.confidence ?? 0

  const activeFactor = Object.entries(factors).filter(([, v]) => v.enabled)
  const totalWeight = activeFactor.reduce((s, [, v]) => s + v.weight, 0)

  const handleWeightChange = (key: string, newWeight: number) => {
    setFactors(prev => ({ ...prev, [key]: { ...prev[key], weight: newWeight } }))
  }

  const handleToggle = (key: string) => {
    setFactors(prev => {
      const updated = { ...prev, [key]: { ...prev[key], enabled: !prev[key].enabled } }
      return updated
    })
  }

  const handleReset = () => {
    setFactors(buildDefaultFactors())
    setExpandedFactor(null)
  }

  return (
    <Card title={`Composite Score (${selectedCommodity})`} className={className}>

      {/* Gauge */}
      <div className="flex flex-col items-center justify-center py-4">
        <div className="relative w-32 h-20 mb-2">
          <svg className="w-full h-full" viewBox="0 0 200 100">
            <path d="M 30 80 A 70 70 0 0 1 170 80" fill="none" stroke="rgba(148,163,184,0.15)" strokeWidth="6" />
            <path
              d="M 30 80 A 70 70 0 0 1 170 80"
              fill="none"
              stroke={regimeColor}
              strokeWidth="6"
              strokeDasharray={`${Math.min(220, Math.abs(displayScore) * 2.2)} 220`}
              strokeLinecap="round"
              style={{ transition: 'stroke-dasharray 0.5s ease, stroke 0.4s ease' }}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center pt-4">
            <span className="text-2xl font-bold font-mono" style={{ color: regimeColor }}>
              {displayScore.toFixed(0)}
            </span>
          </div>
        </div>
        <Badge variant={regime.includes('BULLISH') ? 'green' : regime.includes('BEARISH') ? 'red' : 'neutral'}>
          {regime.replace('_', ' ')}
        </Badge>
        {/* Regime type + signal row */}
        <div className="flex gap-2 mt-1">
          {regimeType && (
            <span style={{ fontSize: 10, color: '#4A6A96', background: 'rgba(30,48,80,0.6)', borderRadius: 4, padding: '2px 6px' }}>
              {regimeType}
            </span>
          )}
          {signal && signal !== 'NEUTRAL' && (
            <span style={{
              fontSize: 10, fontWeight: 700, borderRadius: 4, padding: '2px 6px',
              background: signal.includes('BUY') ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
              color: signal.includes('BUY') ? '#10B981' : '#EF4444',
            }}>
              {signal}
            </span>
          )}
          {confidence > 0 && (
            <span style={{ fontSize: 10, color: '#4A6A96' }}>conf {(confidence * 100).toFixed(0)}%</span>
          )}
        </div>

        {/* Commodity Technical Indicators */}
        {symbolSignal && (
          <div className="w-full px-4 mt-3 pt-3 border-t border-energy-border space-y-1">
            <div className="flex justify-between text-xs">
              <span className="text-energy-text-secondary">EMA Signal:</span>
              <span className="font-mono">{symbolSignal.ema_trend ?? '—'}</span>
            </div>
            <div className="flex justify-between text-xs">
              <span className="text-energy-text-secondary">ATR (14):</span>
              <span className="font-mono">{symbolSignal.atr14 != null ? symbolSignal.atr14.toFixed(2) : '—'}</span>
            </div>
          </div>
        )}

        {/* Toggle details */}
        <button
          onClick={() => setShowDetails(v => !v)}
          style={{
            marginTop: 10,
            background: showDetails ? 'rgba(56,189,248,0.12)' : 'transparent',
            border: '1px solid rgba(56,189,248,0.3)',
            borderRadius: 6,
            color: '#38BDF8',
            fontSize: 11,
            fontWeight: 600,
            padding: '4px 12px',
            cursor: 'pointer',
            transition: 'all 0.15s',
          }}
        >
          {showDetails ? '▲ Hide Factor Controls' : '▼ Show Factor Controls'}
        </button>
      </div>

      {/* Factor Controls */}
      {showDetails && (
        <div style={{ borderTop: '1px solid rgba(30,48,80,0.8)', paddingTop: 12, paddingBottom: 4 }}>
          {/* Summary row */}
          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '0 4px 8px', fontSize: 11, color: '#4A6A96',
          }}>
            <span>{activeFactor.length} active factor{activeFactor.length !== 1 ? 's' : ''}</span>
            <span style={{ color: totalWeight === 100 ? '#10B981' : '#EF4444', fontWeight: 700 }}>
              Total weight: {totalWeight}%
            </span>
            <button
              onClick={handleReset}
              style={{
                background: 'transparent', border: '1px solid #1E3050',
                borderRadius: 4, color: '#4A6A96', fontSize: 10, padding: '2px 8px', cursor: 'pointer',
              }}
            >
              Reset
            </button>
          </div>

          {/* Factor rows */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {Object.entries(FACTOR_META).map(([key, meta]) => {
              const fac = factors[key]
              if (!fac) return null // Guard against missing state during HMR or stale state

              const sub = subScores[key] ?? null
              const contribution = fac.enabled && totalWeight > 0
                ? (sub ?? 0) * (fac.weight / totalWeight) * 100
                : 0
              const isExpanded = expandedFactor === key

              return (
                <div key={key} style={{
                  background: 'rgba(13,24,41,0.8)',
                  border: `1px solid ${isExpanded ? 'rgba(56,189,248,0.4)' : 'rgba(30,48,80,0.6)'}`,
                  borderRadius: 6,
                  padding: '6px 8px',
                  opacity: fac.enabled ? 1 : 0.5,
                  transition: 'all 0.2s',
                }}>
                  {/* Row header */}
                  <div
                    style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}
                    onClick={() => setExpandedFactor(isExpanded ? null : key)}
                  >
                    {/* Enable toggle */}
                    <button
                      onClick={e => { e.stopPropagation(); handleToggle(key) }}
                      style={{
                        width: 18, height: 18, borderRadius: 4, flexShrink: 0,
                        background: fac.enabled ? '#10B981' : 'transparent',
                        border: `2px solid ${fac.enabled ? '#10B981' : '#1E3050'}`,
                        cursor: 'pointer',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        transition: 'all 0.15s',
                      }}
                    >
                      {fac.enabled && <span style={{ color: '#fff', fontSize: 9, fontWeight: 900 }}>✓</span>}
                    </button>

                    {/* Label + weight */}
                    <span style={{ fontSize: 11, fontWeight: 600, color: '#C7D5E8', flex: 1 }}>
                      {meta.label}
                    </span>
                    <span style={{ fontSize: 10, color: '#38BDF8', fontFamily: 'monospace', fontWeight: 700 }}>
                      {fac.enabled ? `${fac.weight}%` : '—'}
                    </span>
                    <span style={{
                      fontSize: 10, fontFamily: 'monospace', fontWeight: 700,
                      color: contribution >= 0 ? '#10B981' : '#EF4444',
                      minWidth: 36, textAlign: 'right',
                    }}>
                      {fac.enabled ? (contribution >= 0 ? '+' : '') + contribution.toFixed(1) : ''}
                    </span>
                    <span style={{ color: '#4A6A96', fontSize: 10 }}>{isExpanded ? '▲' : '▼'}</span>
                  </div>

                  {/* Expanded: weight slider + description */}
                  {isExpanded && (
                    <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid rgba(30,48,80,0.6)' }}>
                      <p style={{ fontSize: 10, color: '#4A6A96', lineHeight: 1.5, marginBottom: 8 }}>
                        {meta.description}
                      </p>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontSize: 10, color: '#4A6A96', whiteSpace: 'nowrap' }}>Weight</span>
                        <input
                          type="range"
                          min={1}
                          max={90}
                          value={fac.weight}
                          disabled={!fac.enabled}
                          onChange={e => handleWeightChange(key, Number(e.target.value))}
                          style={{ flex: 1, accentColor: '#38BDF8', cursor: fac.enabled ? 'pointer' : 'not-allowed' }}
                        />
                        <span style={{
                          fontSize: 11, fontFamily: 'monospace', fontWeight: 700,
                          color: '#38BDF8', minWidth: 30, textAlign: 'right',
                        }}>
                          {fac.weight}%
                        </span>
                      </div>
                      {sub != null && (
                        <div style={{ marginTop: 4, fontSize: 10, color: '#4A6A96' }}>
                          Sub-score: <span style={{ color: sub >= 0 ? '#10B981' : '#EF4444', fontFamily: 'monospace', fontWeight: 700 }}>
                            {sub.toFixed(2)}
                          </span>
                          {' '}→ weighted contribution:{' '}
                          <span style={{ color: contribution >= 0 ? '#10B981' : '#EF4444', fontFamily: 'monospace', fontWeight: 700 }}>
                            {(contribution >= 0 ? '+' : '')}{contribution.toFixed(1)}
                          </span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {/* Live score note */}
          {showDetails && (
            <div style={{ textAlign: 'center', marginTop: 8, fontSize: 10, color: '#4A6A96' }}>
              Live score (above) reflects your factor controls
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

// ─── Main OverviewTab component ───────────────────────────────────────────────

export default function OverviewTab() {
  const { prices, signals, macro: storeMacro, cracks, eiaData, cftc, eiaStatus, cftcStatus, historicalPrices, enhancedSignals, setEnhancedSignals } = useLegacyStore()
  const snapshot = useSnapshotStore((s) => s.snapshot)
  const [alerts, setAlerts] = useState<any[]>([])
  const [localMacro, setLocalMacro] = useState<any>(null)
  const [selectedCommodity, setSelectedCommodity] = useState<string>('WTI')

  // Fetch macro data locally with refresh so DXY always shows
  useEffect(() => {
    let cancelled = false
    async function fetchMacro() {
      try {
        const res = await axios.get(`${API_BASE}/api/macro/all`)
        if (!cancelled && res.data?.data) {
          setLocalMacro(res.data.data)
        }
      } catch (err) {
        console.error('Failed to fetch macro data', err)
      }
    }
    fetchMacro()
    const timer = setInterval(fetchMacro, 5 * 60 * 1000) // refresh every 5 min
    return () => { cancelled = true; clearInterval(timer) }
  }, [])

  // Poll enhanced signals so the Watchlist / symbol cards self-heal if the
  // one-shot load at app mount failed or the backend was still warming up.
  useEffect(() => {
    let cancelled = false
    async function fetchEnhanced() {
      try {
        const res = await axios.get(`${API_BASE}/api/signals/enhanced`)
        if (!cancelled && res.data?.data?.symbols?.length) {
          setEnhancedSignals(res.data.data)
        }
      } catch (err) {
        console.error('Failed to fetch enhanced signals', err)
      }
    }
    if (!enhancedSignals?.symbols?.length) fetchEnhanced()
    const timer = setInterval(fetchEnhanced, 2 * 60 * 1000) // refresh every 2 min
    return () => { cancelled = true; clearInterval(timer) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setEnhancedSignals])

  // Use local macro if available, fall back to store macro
  const macro = localMacro ?? storeMacro

  useEffect(() => {
    let cancelled = false
    async function fetchAlerts() {
      try {
        const res = await axios.get(`${API_BASE}/api/alerts/active`)
        if (!cancelled && res.data?.data) {
          setAlerts(res.data.data)
        }
      } catch (err) {
        console.error('Failed to fetch alerts', err)
      }
    }
    fetchAlerts()
    const timer = setInterval(fetchAlerts, 60000)
    return () => { cancelled = true; clearInterval(timer) }
  }, [])

  const getPriceData = (symbol: string) => {
    const basePrice = prices[symbol] || {} as any
    const snapshotPrices = snapshot?.price?.data ?? snapshot?.header?.prices
    const snapshotPrice = snapshotPrices?.[symbol]
    if (snapshotPrice) {
      return {
        symbol,
        open: snapshotPrice.open ?? basePrice?.open ?? snapshotPrice.price ?? 0,
        high: snapshotPrice.high ?? basePrice?.high ?? snapshotPrice.close ?? 0,
        low: snapshotPrice.low ?? basePrice?.low ?? snapshotPrice.close ?? 0,
        close: snapshotPrice.price ?? snapshotPrice.close ?? basePrice?.close ?? 0,
        volume: snapshotPrice.volume ?? basePrice?.volume ?? 0,
        change_pct: (snapshotPrice.change_pct && snapshotPrice.change_pct !== 0)
          ? snapshotPrice.change_pct
          : (basePrice?.change_pct ?? snapshotPrice.change ?? 0),
        timestamp: snapshot?.ts ?? basePrice?.timestamp ?? new Date().toISOString(),
      }
    }
    return basePrice
  }

  const rawSignals = snapshot?.signals || signals
  const bySymbolDict = (snapshot as any)?.signals_by_symbol || rawSignals?.by_symbol || {}
  const bySymbolData = bySymbolDict[selectedCommodity] || (selectedCommodity === 'WTI' ? rawSignals : null)
  const aiTradeSignal = (snapshot as any)?.signals?.ai_predictions?.[selectedCommodity]?.trade_signal
  
  const activeSignals = aiTradeSignal && Object.keys(aiTradeSignal).length > 0
    ? { ...bySymbolData, ...aiTradeSignal }
    : bySymbolData

  const products = [
    { name: 'WTI', symbol: 'WTI', exchange: 'CME', unit: '$' },
    { name: 'Brent', symbol: 'Brent', exchange: 'ICE', unit: '$' },
    { name: 'RBOB', symbol: 'RBOB', exchange: 'CME', unit: '$' },
    { name: 'HO', symbol: 'HO', exchange: 'CME', unit: '$' },
    { name: 'Gasoil', symbol: 'GO', exchange: 'ICE', unit: '$' },
  ]

  // Build a symbol→signal lookup for the combined card grid
  const symbolSignals: Record<string, any> = {}
    ; (enhancedSignals?.symbols || []).forEach((s: any) => { symbolSignals[s.symbol] = s })

  // Top Movers Calculation
  const topMovers = Object.keys(prices || {}).length > 0 
    ? Object.keys(prices).map(sym => getPriceData(sym))
        .filter(p => p && p.change_pct != null)
        .sort((a, b) => Math.abs(b.change_pct) - Math.abs(a.change_pct))
        .slice(0, 3)
    : []

  const compositeScore = activeSignals?.composite_score ?? 0
  const tradeBias = compositeScore > 20 ? 'Bullish' : compositeScore < -20 ? 'Bearish' : 'Neutral'

  return (
    <div className="space-y-6">

      {/* ── Commodity Selector ──────────────────────── */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-energy-text-secondary font-semibold uppercase tracking-wider mr-2">Viewing:</span>
        {products.map((product) => {
          const isSelected = selectedCommodity === product.symbol
          const priceData = getPriceData(product.symbol)
          const isUp = (priceData?.change_pct ?? 0) > 0
          return (
            <button
              key={product.symbol}
              onClick={() => setSelectedCommodity(product.symbol)}
              className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all duration-200 border ${
                isSelected
                  ? 'bg-energy-accent-blue/15 border-energy-accent-blue/40 text-energy-accent-blue shadow-lg shadow-energy-accent-blue/10'
                  : 'bg-energy-bg-secondary border-energy-border text-energy-text-secondary hover:bg-energy-bg-tertiary hover:border-energy-border-hover'
              }`}
            >
              <div className="flex items-center gap-2">
                <span>{product.name}</span>
                {priceData?.close != null && (
                  <span className={`text-xs font-mono ${isUp ? 'text-energy-bull' : 'text-energy-bear'}`}>
                    ${priceData.close.toFixed(2)}
                  </span>
                )}
              </div>
            </button>
          )
        })}
      </div>

      {/* ── Trader Action Center Layout: 3 columns ──────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-stretch">

        {/* Column 1: Composite Score & Top Movers */}
        <div className="xl:col-span-3 flex flex-col gap-4">
          <CompositeScoreCard signals={activeSignals} symbolSignal={symbolSignals[selectedCommodity]} selectedCommodity={selectedCommodity} />
          
          <Card title="Top Movers (24h)">
            <div className="space-y-1 text-sm">
              {topMovers.length ? (
                topMovers.map((m: any) => (
                  <div key={m.symbol} className="flex justify-between items-center">
                    <div className="font-semibold text-xs">{m.symbol}</div>
                    <div className={`font-mono text-xs ${m.change_pct > 0 ? 'text-energy-bull' : 'text-energy-bear'}`}>
                      {m.change_pct > 0 ? '+' : ''}{m.change_pct.toFixed(2)}%
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-energy-text-secondary text-xs">No price movement data</div>
              )}
            </div>
          </Card>
        </div>

        {/* Column 2: Watchlist Momentum & Market State */}
        <div className="xl:col-span-4">
          <WatchlistMomentumCard
            volRegime={activeSignals?.vol_regime}
            volatilityPct={activeSignals?.volatility_pct}
            tradeBias={tradeBias}
          />
        </div>

        {/* Column 3: Virtual Trading Book */}
        <div className="xl:col-span-5">
          <PaperTrading />
        </div>
      </div>

      {/* ── Market Structure & Curve (Moved from Structure Tab) ──────────────────────── */}
      <div className="w-full">
        <UnifiedMarketStructurePanel symbol={selectedCommodity} />
      </div>

      {/* ── Combined Symbol Snapshot + Signal Heatmap ──────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-4">
        {products.map((product) => {
          const priceData = getPriceData(product.symbol)
          const sig = symbolSignals[product.symbol]
          const isWTI = product.symbol === 'WTI'
          const spread = isWTI ? snapshot?.cracks?.cl_brent_spread ?? cracks?.cl_brent_spread : null
          const isUp = (priceData?.change_pct ?? 0) > 0

          return (
            <Card key={product.symbol} className="flex flex-col">
              <div className="space-y-3">
                {/* Header: name + exchange + trend badge */}
                <div className="flex justify-between items-start">
                  <div>
                    <div className="text-sm font-bold">{product.name}</div>
                    <Badge variant="blue" className="text-xs mt-1">{product.exchange}</Badge>
                  </div>
                  {sig && (
                    <Badge variant={sig.signal_label?.includes('Bullish') ? 'green' : sig.signal_label?.includes('Bearish') ? 'red' : 'amber'}>
                      {sig.signal_label}
                    </Badge>
                  )}
                </div>

                {/* Price */}
                <div>
                  <div className={`text-2xl font-bebas ${isUp ? 'text-energy-bull' : 'text-energy-bear'}`}>
                    {product.unit}{priceData?.close != null ? priceData.close.toFixed(2) : '—'}
                  </div>
                  <div className="text-xs text-energy-text-secondary">
                    {isUp ? '▲' : '▼'}{Math.abs(priceData?.change_pct || 0).toFixed(2)}%
                  </div>
                </div>

                {/* H/L */}
                <div className="space-y-1 text-xs text-energy-text-secondary">
                  <div>H: {product.unit}{priceData?.high != null ? priceData.high.toFixed(1) : '—'}</div>
                  <div>L: {product.unit}{priceData?.low != null ? priceData.low.toFixed(1) : '—'}</div>
                </div>

                {/* Sparkline */}
                {historicalPrices[product.symbol] && historicalPrices[product.symbol].length > 1 && (
                  <div className="pt-2 border-t border-energy-border">
                    <Sparkline
                      data={historicalPrices[product.symbol]}
                      width={140}
                      height={40}
                      color={isUp ? '#10B981' : '#EF4444'}
                    />
                  </div>
                )}

                {/* Signal metrics */}
                {sig && (
                  <div className="pt-2 border-t border-energy-border space-y-1 text-xs text-energy-text-secondary">
                    <div className="flex justify-between">
                      <span>EMA</span>
                      <span className="font-mono">{sig.ema_trend}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>ATR14</span>
                      <span className="font-mono">{sig.atr14 != null ? sig.atr14.toFixed(2) : '—'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Bollinger</span>
                      <span className="font-mono">{sig.bollinger?.position ?? '—'}</span>
                    </div>
                  </div>
                )}

                {/* CL-Brent spread (WTI only) */}
                {spread && (
                  <div className="pt-2 border-t border-energy-border">
                    <div className="text-xs text-energy-text-secondary">CL-Brent</div>
                    <div className="font-mono text-xs">{spread.toFixed(2)}</div>
                  </div>
                )}
              </div>
            </Card>
          )
        })}
      </div>

      {/* ── Section 3: Macro & Refinery Signals ─────────────────────────────── */}
      <div className="grid grid-cols-2 gap-4">
        <MacroSignalPulseCard />
        <RefineryCrackSignalsCard />
      </div>

      {/* ── Section 4: Alert Feed ─────────────────────────────── */}
      <Card title="Alerts & Signals">
        <div className="space-y-2 text-xs max-h-48 overflow-y-auto">
          {alerts && alerts.length > 0 ? (
            alerts.map((alert: any) => {
              const symbolText = alert.symbol ? `${alert.symbol} ` : ''
              const textToSearch = ((alert.symbol || '') + ' ' + (alert.type || '') + ' ' + (alert.message || '')).toUpperCase().replace(/-/g, '')
              
              let tooltip = ''
              if (textToSearch.includes('FRAC')) tooltip = 'Fractionation Spread: Tracks NGL margins vs Natural Gas'
              else if (textToSearch.includes('321')) tooltip = '3-2-1 Crack: 3 bbls Crude into 2 bbls Gasoline, 1 bbl Heating Oil'
              else if (textToSearch.includes('211')) tooltip = '2-1-1 Crack: 2 bbls Crude into 1 bbl Gasoline, 1 bbl Heating Oil'
              else if (textToSearch.includes('221')) tooltip = '2-2-1 Crack: 2 bbls Crude into 2 bbls Gasoline, 1 bbl Heating Oil'
              else if (textToSearch.includes('WTICRACK')) tooltip = 'General WTI Crude Crack Spread'
              else if (textToSearch.includes('CRACK')) tooltip = 'Refinery Margin Proxy'

              return (
              <div key={alert.id} className="flex items-start gap-2 p-2 bg-energy-bg-tertiary rounded border border-energy-border">
                <div className={
                  alert.severity === 'critical' ? 'text-energy-bear' :
                    alert.severity === 'warning' ? 'text-energy-amber' :
                      'text-energy-bull'
                }>
                  {alert.severity === 'critical' || alert.severity === 'warning' ? '⚠' : '✓'}
                </div>
                <div className="flex-1">
                  <div className="font-semibold">
                    {tooltip ? (
                      <span title={tooltip} className="cursor-help border-b border-dotted border-energy-text-secondary">
                        {symbolText}{alert.type.replace(/_/g, ' ').toUpperCase()}
                      </span>
                    ) : (
                      <span>{symbolText}{alert.type.replace(/_/g, ' ').toUpperCase()}</span>
                    )}
                  </div>
                  <div className="text-energy-text-secondary">{alert.message}</div>
                </div>
                <div className="text-energy-text-secondary text-[10px]">
                  {new Date(alert.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </div>
              </div>
            )})
          ) : (
            <div className="text-center text-energy-text-secondary py-4 italic">No active alerts</div>
          )}
        </div>
      </Card>
      {/* ── Section 5: Price History Chart ───────────────────── */}
      <PriceHistoryChart />

      {/* ── Section 6: Fundamentals & Macro ────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card title="EIA Fundamentals Snapshot">
          <div className="space-y-4 text-sm">
            {Object.keys(eiaData || {}).length > 0 ? (
              [
                { title: 'Crude Stocks', value: eiaData?.crude_level?.current_value, delta: eiaData?.crude_level?.wow_change, unit: 'mb' },
                { title: 'Cushing Hub', value: eiaData?.cushing_level?.current_value, delta: eiaData?.cushing_level?.wow_change, unit: 'mb' },
                { title: 'Refinery Utilization', value: eiaData?.refinery_utilization?.current_value, delta: eiaData?.refinery_utilization?.wow_change, unit: '%' },
                { title: 'US Crude Production', value: eiaData?.us_crude_production?.current_value, delta: eiaData?.us_crude_production?.wow_change, unit: 'mbd' },
              ].map((item) => (
                <div key={item.title} className="flex justify-between items-center">
                  <div>
                    <div className="text-xs text-energy-text-secondary">{item.title}</div>
                    <div className="font-mono">{item.value != null ? item.value.toFixed(2) : '—'} {item.unit}</div>
                  </div>
                  <div className={`text-xs ${item.delta != null ? (item.delta > 0 ? 'text-energy-bear' : 'text-energy-bull') : 'text-energy-text-secondary'}`}>
                    {item.delta != null ? `${item.delta > 0 ? '+' : ''}${item.delta.toFixed(1)}` : '—'}
                  </div>
                </div>
              ))
            ) : eiaStatus === 'unavailable' ? (
              <div className="text-energy-text-secondary italic">EIA fundamentals data unavailable</div>
            ) : (
              <div className="text-energy-text-secondary">EIA fundamentals loading...</div>
            )}
          </div>
        </Card>

        <Card title="CFTC Positioning (WTI)">
          <div className="space-y-4 text-sm">
            {cftc && cftc.WTI ? (
              <div className="p-3 bg-energy-bg-tertiary rounded">
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>MM net long</div>
                  <div className="font-mono">{cftc.WTI.mm_net_long ?? '—'}</div>
                  <div>MM change</div>
                  <div className={`font-mono ${cftc.WTI.mm_net_change > 0 ? 'text-energy-bull' : 'text-energy-bear'}`}>
                    {cftc.WTI.mm_net_change != null ? `${cftc.WTI.mm_net_change > 0 ? '+' : ''}${cftc.WTI.mm_net_change}` : '—'}
                  </div>
                  <div>Open interest</div>
                  <div className="font-mono">{cftc.WTI.open_interest ?? '—'}</div>
                  <div>Producer short</div>
                  <div className="font-mono">{cftc.WTI.producer_net_short ?? '—'}</div>
                </div>
              </div>
            ) : cftcStatus === 'unavailable' ? (
              <div className="text-energy-text-secondary italic">CFTC positioning data unavailable</div>
            ) : (
              <div className="text-energy-text-secondary">CFTC positioning loading...</div>
            )}
          </div>
        </Card>

        <Card title="Macro Context">
          <div className="space-y-2 text-xs">
            <div className="flex justify-between">
              <span>DXY</span>
              <span className="font-mono">{macro?.dxy?.toFixed(1) ?? '—'}</span>
            </div>
            <div className="flex justify-between">
              <span>10Y Yield</span>
              <span className="font-mono">{macro?.us_10y_yield != null ? `${macro.us_10y_yield.toFixed(2)}%` : '—'}</span>
            </div>
            <div className="flex justify-between">
              <span>PMI</span>
              <span className="font-mono">{macro?.global_pmi?.toFixed(1) ?? '—'}</span>
            </div>
            <div className="pt-4 border-t border-energy-border text-energy-text-secondary">
              <div className="font-semibold text-xs">Oil macro insights</div>
              <div className="mt-2 space-y-1 text-[11px]">
                <div>3:2:1 and 5:3:2 crack spreads reflect refining margins and product demand.</div>
                <div>Gasoil vs Brent is a leading European downstream signal for distillate tightness.</div>
                <div>Watch inventories, refinery utilization, and curve shape for momentum context.</div>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}
