import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import axios from 'axios'
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
} from 'recharts'

const API_BASE = (import.meta as any).env?.VITE_API_BASE || 'http://localhost:8000'

// ─── Commodity config ────────────────────────────────────────────────────────

const COMMODITIES = [
  { symbol: 'WTI',   label: 'WTI Crude Oil',     unit: '$/bbl',  color: '#38BDF8' },
  { symbol: 'Brent', label: 'Brent Crude',        unit: '$/bbl',  color: '#60A5FA' },
  { symbol: 'RBOB',  label: 'RBOB Gasoline',      unit: '$/gal',  color: '#34D399' },
  { symbol: 'HO',    label: 'Heating Oil',         unit: '$/gal',  color: '#F97316' },
  { symbol: 'HH',    label: 'Henry Hub (Nat Gas)', unit: '$/MMBtu',color: '#A78BFA' },
  { symbol: 'GO',    label: 'ICE Gasoil',          unit: '$/MT',   color: '#FB923C' },
  { symbol: 'GC',    label: 'Gold',                unit: '$/oz',   color: '#FCD34D' },
  { symbol: 'DXY',   label: 'US Dollar Index',     unit: '',       color: '#94A3B8' },
  { symbol: 'SPX',   label: 'S&P 500',             unit: '',       color: '#10B981' },
  { symbol: 'VIX',   label: 'VIX (Volatility)',    unit: '',       color: '#EF4444' },
]

const TIME_RANGES = [
  { label: '1M',  period: '1mo' },
  { label: '3M',  period: '3mo' },
  { label: '6M',  period: '6mo' },
  { label: '1Y',  period: '1y'  },
  { label: '2Y',  period: '2y'  },
  { label: '5Y',  period: '5y'  },
  { label: 'Max', period: 'max' },
]

// Rolling indicators (BB/EMA) need a warmup buffer, otherwise a 20-day band only
// appears at the right edge of a 1-month chart. So we FETCH a longer series than
// the selected window, compute indicators across the whole thing, then trim to
// `visibleDays` for display — bands render edge-to-edge. `visibleDays` is trading
// days (~21/mo). 'max' shows everything.
const PERIOD_META: Record<string, { fetch: string; visibleDays: number }> = {
  '1mo': { fetch: '6mo', visibleDays: 23 },
  '3mo': { fetch: '1y',  visibleDays: 66 },
  '6mo': { fetch: '2y',  visibleDays: 131 },
  '1y':  { fetch: '2y',  visibleDays: 262 },
  '2y':  { fetch: '5y',  visibleDays: 523 },
  '5y':  { fetch: 'max', visibleDays: 1305 },
  'max': { fetch: 'max', visibleDays: Number.MAX_SAFE_INTEGER },
}

// ─── EMA calculation (client-side) ──────────────────────────────────────────

function calcEMA(prices: number[], period: number): (number | null)[] {
  if (prices.length < period) return prices.map(() => null)
  const k = 2 / (period + 1)
  const result: (number | null)[] = new Array(period - 1).fill(null)
  let ema = prices.slice(0, period).reduce((s, v) => s + v, 0) / period
  result.push(ema)
  for (let i = period; i < prices.length; i++) {
    ema = prices[i] * k + ema * (1 - k)
    result.push(ema)
  }
  return result
}

// ─── Custom tooltip ──────────────────────────────────────────────────────────

function CustomTooltip({ active, payload, label, unit }: any) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'rgba(5,11,20,0.97)',
      border: '1px solid rgba(56,189,248,0.3)',
      borderRadius: 8,
      padding: '10px 14px',
      fontSize: 12,
      minWidth: 160,
    }}>
      <div style={{ color: '#94A3B8', marginBottom: 6, fontSize: 11 }}>{label}</div>
      {payload
        .filter((entry: any) => entry.dataKey !== 'bbRange')
        .map((entry: any) => (
          <div key={entry.dataKey} style={{ display: 'flex', justifyContent: 'space-between', gap: 16, marginBottom: 3 }}>
            <span style={{ color: entry.color, fontWeight: 600 }}>{entry.name}</span>
            <span style={{ color: '#E2E8F0', fontFamily: 'monospace', fontWeight: 700 }}>
              {entry.value != null ? `${unit}${Number(entry.value).toFixed(2)}` : '—'}
            </span>
          </div>
        ))}
    </div>
  )
}

// ─── Loading skeleton ────────────────────────────────────────────────────────

function ChartSkeleton() {
  return (
    <div style={{ height: 320, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
        <div style={{
          width: 40, height: 40, borderRadius: '50%',
          border: '3px solid rgba(56,189,248,0.2)',
          borderTopColor: '#38BDF8',
          animation: 'spin 1s linear infinite',
        }} />
        <span style={{ color: '#4A6A96', fontSize: 13 }}>Loading price history…</span>
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}

// ─── Main component ──────────────────────────────────────────────────────────

interface BollingerBandsResult {
  upper: (number | null)[]
  middle: (number | null)[]
  lower: (number | null)[]
  bandwidth: (number | null)[]
  pct_b: (number | null)[]
}

function calcBollingerBands(prices: number[], period: number, multiplier: number): BollingerBandsResult {
  const upper: (number | null)[] = []
  const middle: (number | null)[] = []
  const lower: (number | null)[] = []
  const bandwidth: (number | null)[] = []
  const pct_b: (number | null)[] = []

  for (let i = 0; i < prices.length; i++) {
    if (i < period - 1) {
      upper.push(null)
      middle.push(null)
      lower.push(null)
      bandwidth.push(null)
      pct_b.push(null)
      continue
    }

    const slice = prices.slice(i - period + 1, i + 1)
    const sum = slice.reduce((acc, val) => acc + val, 0)
    const mean = sum / period

    const variance = slice.reduce((acc, val) => acc + Math.pow(val - mean, 2), 0) / period
    const stdDev = Math.sqrt(variance)

    const up = mean + multiplier * stdDev
    const dn = mean - multiplier * stdDev

    upper.push(up)
    middle.push(mean)
    lower.push(dn)
    bandwidth.push(mean !== 0 ? (up - dn) / mean : 0)
    pct_b.push(up !== dn ? (prices[i] - dn) / (up - dn) : 0.5)
  }

  return { upper, middle, lower, bandwidth, pct_b }
}

export default function PriceHistoryChart() {
  const [selectedSymbol, setSelectedSymbol] = useState('WTI')
  const [selectedPeriod, setSelectedPeriod] = useState('3mo')
  
  // Bollinger Band settings
  const [bbPeriod, setBbPeriod] = useState(20)
  const [bbMultiplier, setBbMultiplier] = useState(2)

  // Series visibility toggles
  const [showPrice, setShowPrice] = useState(true)
  const [showUpper, setShowUpper] = useState(true)
  const [showMiddle, setShowMiddle] = useState(true)
  const [showLower, setShowLower] = useState(true)
  const [showFill, setShowFill] = useState(true)

  // EMA overlays
  const [showEMA20, setShowEMA20] = useState(false)
  const [showEMA50, setShowEMA50] = useState(false)

  const [chartData, setChartData] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const commodity = COMMODITIES.find(c => c.symbol === selectedSymbol) ?? COMMODITIES[0]

  const fetchHistory = useCallback(async (symbol: string, period: string) => {
    // Cancel previous in-flight request
    if (abortRef.current) abortRef.current.abort()
    abortRef.current = new AbortController()

    setLoading(true)
    setError(null)

    try {
      // Fetch a longer window than requested so rolling indicators have warmup.
      const fetchPeriod = PERIOD_META[period]?.fetch ?? period
      const res = await axios.get(`${API_BASE}/api/prices/${symbol}/historical`, {
        params: { period: fetchPeriod },
        signal: abortRef.current.signal,
        timeout: 30000,
      })

      const raw: Array<{ timestamp: string; close: number; open: number; high: number; low: number; volume: number }>
        = res.data?.data ?? []

      if (!raw.length) {
        setError('No data available for this commodity and time range.')
        setChartData([])
        return
      }

      const closes = raw.map(r => r.close)
      const ema20s = calcEMA(closes, 20)
      const ema50s = calcEMA(closes, 50)

      const data = raw.map((r, i) => ({
        date: r.timestamp,
        label: new Date(r.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: raw.length > 252 ? '2-digit' : undefined }),
        price: r.close,
        high: r.high,
        low: r.low,
        ema20: ema20s[i],
        ema50: ema50s[i],
        volume: r.volume,
      }))

      setChartData(data)
    } catch (err: any) {
      if (err?.code === 'ERR_CANCELED') return
      setError('Failed to load price history. Please try again.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchHistory(selectedSymbol, selectedPeriod)
  }, [selectedSymbol, selectedPeriod, fetchHistory])

  // Compute EMA + Bollinger Bands over the FULL fetched series (warmup included),
  // then trim to the selected visible window so bands are populated edge-to-edge.
  const computedData = useMemo(() => {
    if (!chartData.length) return []
    const prices = chartData.map((d: any) => d.price)
    const bb = calcBollingerBands(prices, bbPeriod, bbMultiplier)
    const full = chartData.map((d: any, i: number) => {
      const lowerVal = bb.lower[i]
      const upperVal = bb.upper[i]
      return {
        ...d,
        bbUpper: upperVal,
        bbMiddle: bb.middle[i],
        bbLower: lowerVal,
        bbBandwidth: bb.bandwidth[i],
        bbPctB: bb.pct_b[i],
        bbRange: lowerVal != null && upperVal != null ? [lowerVal, upperVal] : null,
      }
    })
    const visible = PERIOD_META[selectedPeriod]?.visibleDays ?? full.length
    return full.length > visible ? full.slice(full.length - visible) : full
  }, [chartData, bbPeriod, bbMultiplier, selectedPeriod])

  // Price and BB range metrics
  const firstPrice = computedData[0]?.price
  const lastPrice  = computedData[computedData.length - 1]?.price
  const priceChange = firstPrice && lastPrice ? lastPrice - firstPrice : null
  const changePct   = firstPrice && priceChange != null ? (priceChange / firstPrice) * 100 : null
  const isPositive  = (changePct ?? 0) >= 0

  // Live indicators for insights panel
  const latestPoint = computedData[computedData.length - 1]
  const currentPrice = latestPoint?.price
  const currentMiddle = latestPoint?.bbMiddle
  const currentUpper = latestPoint?.bbUpper
  const currentLower = latestPoint?.bbLower
  const currentBandwidth = latestPoint?.bbBandwidth != null ? latestPoint.bbBandwidth * 100 : null
  const currentPctB = latestPoint?.bbPctB != null ? latestPoint.bbPctB * 100 : null

  // Calculate dynamic Y domain including BB values, EMA overlays to avoid clipping
  const yDomain = useMemo(() => {
    if (!computedData.length) return [0, 100]
    const vals: number[] = []
    computedData.forEach((d: any) => {
      if (d.price != null) vals.push(d.price)
      if (d.high != null) vals.push(d.high)
      if (d.low != null) vals.push(d.low)
      if (showUpper && d.bbUpper != null) vals.push(d.bbUpper)
      if (showLower && d.bbLower != null) vals.push(d.bbLower)
      // Always include middle band and EMA overlays in domain so they stay in bounds
      if (showMiddle && d.bbMiddle != null) vals.push(d.bbMiddle)
      if (showEMA20 && d.ema20 != null) vals.push(d.ema20)
      if (showEMA50 && d.ema50 != null) vals.push(d.ema50)
    })
    const minVal = vals.length ? Math.min(...vals) : 0
    const maxVal = vals.length ? Math.max(...vals) : 0
    const pad = (maxVal - minVal) * 0.06 || 1
    return [minVal - pad, maxVal + pad] as [number, number]
  }, [computedData, showUpper, showLower, showMiddle, showEMA20, showEMA50])

  const minPrice = computedData.length ? Math.min(...computedData.map((d: any) => d.low ?? d.price)) : 0
  const maxPrice = computedData.length ? Math.max(...computedData.map((d: any) => d.high ?? d.price)) : 0

  return (
    <article style={{
      background: 'linear-gradient(135deg, #0D1829 0%, #091222 100%)',
      borderRadius: 12,
      border: '1px solid #1E3050',
      overflow: 'hidden',
    }}>
      {/* ── Header ─────────────────────────────────────────── */}
      <header style={{
        padding: '14px 18px',
        borderBottom: '1px solid #1E3050',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 12,
      }}>
        <div>
          <h3 style={{ color: '#E8EEF7', fontSize: 14, fontWeight: 700, marginBottom: 2 }}>
            Commodity Price History
          </h3>
          <p style={{ color: '#4A6A96', fontSize: 11 }}>Interactive price history with Bollinger Bands ({bbPeriod}-day window) &amp; EMA (20/50-day window) overlays</p>
        </div>

        {/* Stats strip */}
        {!loading && !error && computedData.length > 0 && (
          <div style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
            <div style={{ textAlign: 'right' }}>
              <div style={{ color: '#4A6A96', fontSize: 10, marginBottom: 2 }}>LATEST</div>
              <div style={{ color: '#E8EEF7', fontFamily: 'monospace', fontSize: 15, fontWeight: 700 }}>
                {commodity.unit}{lastPrice?.toFixed(2) ?? '—'}
              </div>
            </div>
            {changePct != null && (
              <div style={{ textAlign: 'right' }}>
                <div style={{ color: '#4A6A96', fontSize: 10, marginBottom: 2 }}>CHANGE</div>
                <div style={{
                  color: isPositive ? '#10B981' : '#EF4444',
                  fontFamily: 'monospace', fontSize: 13, fontWeight: 700
                }}>
                  {isPositive ? '▲' : '▼'} {Math.abs(changePct).toFixed(2)}%
                </div>
              </div>
            )}
          </div>
        )}
      </header>

      {/* ── Controls Toolbar ────────────────────────────────── */}
      <div style={{
        padding: '10px 18px',
        borderBottom: '1px solid rgba(30,48,80,0.6)',
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        flexWrap: 'wrap',
      }}>
        {/* Commodity Dropdown */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ color: '#4A6A96', fontSize: 11, fontWeight: 600, whiteSpace: 'nowrap' }}>
            COMMODITY
          </label>
          <select
            value={selectedSymbol}
            onChange={e => setSelectedSymbol(e.target.value)}
            style={{
              background: '#0A1628',
              border: '1px solid #1E3050',
              borderRadius: 6,
              color: '#E8EEF7',
              fontSize: 12,
              padding: '5px 10px',
              cursor: 'pointer',
              outline: 'none',
            }}
          >
            {COMMODITIES.map(c => (
              <option key={c.symbol} value={c.symbol}>
                {c.label} ({c.unit || c.symbol})
              </option>
            ))}
          </select>
        </div>

        {/* Time Range Tabs */}
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <span style={{ color: '#4A6A96', fontSize: 11, fontWeight: 600, marginRight: 4 }}>RANGE</span>
          {TIME_RANGES.map(r => (
            <button
              key={r.period}
              onClick={() => setSelectedPeriod(r.period)}
              style={{
                background: selectedPeriod === r.period ? '#1E3A5F' : 'transparent',
                border: selectedPeriod === r.period ? '1px solid #38BDF8' : '1px solid #1E3050',
                borderRadius: 5,
                color: selectedPeriod === r.period ? '#38BDF8' : '#4A6A96',
                fontSize: 11,
                fontWeight: 700,
                padding: '4px 10px',
                cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              {r.label}
            </button>
          ))}
        </div>

        {/* Bollinger Band Config */}
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ color: '#4A6A96', fontSize: 11, fontWeight: 600 }}>BB PARAMETERS</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: '#4A6A96', fontSize: 10 }}>Period</span>
            <input
              type="number"
              min={5}
              max={100}
              value={bbPeriod}
              onChange={e => setBbPeriod(Math.max(5, parseInt(e.target.value) || 20))}
              style={{
                width: 48,
                background: '#0A1628',
                border: '1px solid #1E3050',
                borderRadius: 4,
                color: '#E8EEF7',
                fontSize: 11,
                padding: '2px 4px',
                textAlign: 'center',
                outline: 'none',
              }}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ color: '#4A6A96', fontSize: 10 }}>StdDev</span>
            <input
              type="number"
              min={0.5}
              max={10}
              step={0.1}
              value={bbMultiplier}
              onChange={e => setBbMultiplier(Math.max(0.1, parseFloat(e.target.value) || 2))}
              style={{
                width: 48,
                background: '#0A1628',
                border: '1px solid #1E3050',
                borderRadius: 4,
                color: '#E8EEF7',
                fontSize: 11,
                padding: '2px 4px',
                textAlign: 'center',
                outline: 'none',
              }}
            />
          </div>
          <button
            onClick={() => {
              setBbPeriod(20)
              setBbMultiplier(2)
            }}
            style={{
              background: 'transparent',
              border: '1px solid #1E3050',
              borderRadius: 4,
              color: '#4A6A96',
              fontSize: 10,
              padding: '2px 8px',
              cursor: 'pointer',
              transition: 'all 0.15s',
            }}
            onMouseEnter={e => (e.currentTarget.style.color = '#38BDF8')}
            onMouseLeave={e => (e.currentTarget.style.color = '#4A6A96')}
          >
            Reset
          </button>
        </div>

        {/* EMA overlay toggles */}
        <div style={{ display: 'flex', gap: 8, marginLeft: 'auto', alignItems: 'center' }}>
          <span style={{ color: '#4A6A96', fontSize: 11, fontWeight: 600 }}>OVERLAY</span>
          <ToggleBtn
            active={showEMA20}
            color="#FCD34D"
            label="EMA 20"
            onClick={() => setShowEMA20(v => !v)}
          />
          <ToggleBtn
            active={showEMA50}
            color="#F97316"
            label="EMA 50"
            onClick={() => setShowEMA50(v => !v)}
          />
        </div>
      </div>

      {/* ── Custom Legend Toggle Strip ───────────────────────── */}
      <div style={{
        display: 'flex',
        gap: 12,
        padding: '10px 18px',
        borderBottom: '1px solid rgba(30,48,80,0.6)',
        background: 'rgba(10, 22, 40, 0.4)',
        flexWrap: 'wrap',
        alignItems: 'center',
        fontSize: 11,
      }}>
        <span style={{ color: '#4A6A96', fontWeight: 600, marginRight: 6 }}>TOGGLE SERIES:</span>
        <LegendToggle active={showPrice} color={commodity.color} label="Price" onClick={() => setShowPrice(!showPrice)} />
        <LegendToggle active={showUpper} color="#3b82f6" label="Upper Band" onClick={() => setShowUpper(!showUpper)} isDashed />
        <LegendToggle active={showMiddle} color="#fbbf24" label="Middle Band (MA)" onClick={() => setShowMiddle(!showMiddle)} />
        <LegendToggle active={showLower} color="#f97316" label="Lower Band" onClick={() => setShowLower(!showLower)} isDashed />
        <LegendToggle active={showFill} color="rgba(59, 130, 246, 0.15)" label="Band Fill Area" onClick={() => setShowFill(!showFill)} isArea />
      </div>

      {/* ── Main Layout (Chart + Insights Panel) ─────────────── */}
      <div style={{ display: 'flex', flexWrap: 'wrap', width: '100%' }}>
        {/* Chart Column */}
        <div style={{ flex: '1 1 500px', padding: '16px 8px 8px 8px', minWidth: 320 }}>
          {loading ? (
            <ChartSkeleton />
          ) : error ? (
            <div style={{ height: 320, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{ textAlign: 'center' }}>
                <div style={{ color: '#EF4444', fontSize: 13, marginBottom: 8 }}>⚠ {error}</div>
                <button
                  onClick={() => fetchHistory(selectedSymbol, selectedPeriod)}
                  style={{
                    background: 'rgba(56,189,248,0.1)', border: '1px solid #38BDF8',
                    borderRadius: 6, color: '#38BDF8', fontSize: 12, padding: '6px 14px', cursor: 'pointer',
                  }}
                >
                  Retry
                </button>
              </div>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={computedData} margin={{ top: 8, right: 16, left: -8, bottom: 0 }}>
                <defs>
                  <linearGradient id={`phFill_${selectedSymbol}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"   stopColor={commodity.color} stopOpacity={0.25} />
                    <stop offset="95%"  stopColor={commodity.color} stopOpacity={0.02} />
                  </linearGradient>
                </defs>

                <CartesianGrid strokeDasharray="3 3" stroke="rgba(30,48,80,0.7)" vertical={false} />

                <XAxis
                  dataKey="label"
                  tick={{ fill: '#4A6A96', fontSize: 10 }}
                  axisLine={false} tickLine={false}
                  interval="preserveStartEnd" minTickGap={40}
                />
                <YAxis
                  domain={yDomain}
                  tick={{ fill: '#4A6A96', fontSize: 10 }}
                  axisLine={false} tickLine={false}
                  tickFormatter={(v: number) => `${commodity.unit}${v.toFixed(v >= 100 ? 0 : 2)}`}
                  width={70}
                />

                <Tooltip
                  content={<CustomTooltip unit={commodity.unit} />}
                  cursor={{ stroke: 'rgba(148,163,184,0.3)', strokeWidth: 1 }}
                />

                {/* Bollinger Bands Fill Area (between lower & upper) */}
                {showFill && (
                  <Area
                    type="monotone"
                    dataKey="bbRange"
                    stroke="none"
                    fill="#3b82f6"
                    fillOpacity={0.08}
                    connectNulls
                    legendType="none"
                  />
                )}

                {/* Bollinger Bands Lines */}
                {showUpper && (
                  <Line
                    type="monotone"
                    dataKey="bbUpper"
                    stroke="#3b82f6"
                    strokeWidth={1.2}
                    strokeDasharray="4 2"
                    dot={false}
                    name="Upper Band"
                    connectNulls
                  />
                )}
                {showMiddle && (
                  <Line
                    type="monotone"
                    dataKey="bbMiddle"
                    stroke="#fbbf24"
                    strokeWidth={1.5}
                    dot={false}
                    name="Middle Band"
                    connectNulls
                  />
                )}
                {showLower && (
                  <Line
                    type="monotone"
                    dataKey="bbLower"
                    stroke="#f97316"
                    strokeWidth={1.2}
                    strokeDasharray="4 2"
                    dot={false}
                    name="Lower Band"
                    connectNulls
                  />
                )}

                {/* Price line / area */}
                <Area
                  type="monotone"
                  dataKey="price"
                  stroke={commodity.color}
                  strokeWidth={2}
                  fill={`url(#phFill_${selectedSymbol})`}
                  fillOpacity={showPrice ? 1 : 0}
                  strokeOpacity={showPrice ? 1 : 0}
                  dot={false}
                  name={commodity.label}
                />

                {/* EMA overlays */}
                {showEMA20 && (
                  <Line
                    type="monotone"
                    dataKey="ema20"
                    stroke="#FCD34D"
                    strokeWidth={1.5}
                    dot={false}
                    name="EMA 20"
                    strokeDasharray="5 3"
                    connectNulls
                  />
                )}
                {showEMA50 && (
                  <Line
                    type="monotone"
                    dataKey="ema50"
                    stroke="#F97316"
                    strokeWidth={1.5}
                    dot={false}
                    name="EMA 50"
                    strokeDasharray="5 3"
                    connectNulls
                  />
                )}

                {(showEMA20 || showEMA50) && (
                  <Legend
                    verticalAlign="top"
                    align="right"
                    wrapperStyle={{ color: '#94A3B8', fontSize: 11, paddingRight: 12 }}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Insights Panel Column */}
        {!loading && !error && computedData.length > 0 && (
          <div style={{
            flex: '1 1 240px',
            background: 'rgba(13,24,41,0.5)',
            borderLeft: '1px solid #1E3050',
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            minHeight: 320,
          }}>
            <div>
              <h4 style={{ color: '#E8EEF7', fontSize: 12, fontWeight: 700, marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Bollinger Band Insights ({bbPeriod}-day window)
              </h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <MetricRow label="Current Price" value={currentPrice != null ? `${commodity.unit}${currentPrice.toFixed(2)}` : '—'} />
                <MetricRow label="Moving Average" value={currentMiddle != null ? `${commodity.unit}${currentMiddle.toFixed(2)}` : '—'} color="#fbbf24" />
                <MetricRow label="Upper Band" value={currentUpper != null ? `${commodity.unit}${currentUpper.toFixed(2)}` : '—'} color="#3b82f6" />
                <MetricRow label="Lower Band" value={currentLower != null ? `${commodity.unit}${currentLower.toFixed(2)}` : '—'} color="#f97316" />
                <MetricRow label="Band Width" value={currentBandwidth != null ? `${currentBandwidth.toFixed(2)}%` : '—'} />
                <MetricRow label="Price Position (%B)" value={currentPctB != null ? `${currentPctB.toFixed(1)}%` : '—'}
                           color={currentPctB != null ? (currentPctB > 80 ? '#EF4444' : currentPctB < 20 ? '#38BDF8' : '#E8EEF7') : '#E8EEF7'} />
              </div>
            </div>
            
            <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid rgba(30,48,80,0.6)', fontSize: 10, color: '#4A6A96', lineHeight: 1.4 }}>
              {currentPctB != null && (
                <div>
                  {currentPctB > 100 ? (
                    <span style={{ color: '#EF4444', fontWeight: 600 }}>⚠️ Price is above Upper Band.</span>
                  ) : currentPctB < 0 ? (
                    <span style={{ color: '#38BDF8', fontWeight: 600 }}>⚠️ Price is below Lower Band.</span>
                  ) : (
                    <span>Price is consolidating within bands.</span>
                  )}
                  {currentBandwidth != null && currentBandwidth < 5 && (
                    <span style={{ color: '#fbbf24', marginLeft: 4, fontWeight: 600 }}>⚡ Squeeze detected. Potential breakout imminent.</span>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ── Footer range stats ──────────────────────────────── */}
      {!loading && !error && computedData.length > 0 && (
        <div style={{
          display: 'flex', gap: 0,
          borderTop: '1px solid #1E3050',
          marginTop: 4,
        }}>
          {[
            { label: 'RANGE LOW',  value: `${commodity.unit}${minPrice.toFixed(2)}`, color: '#EF4444' },
            { label: 'RANGE HIGH', value: `${commodity.unit}${maxPrice.toFixed(2)}`, color: '#10B981' },
            { label: 'OPEN',       value: `${commodity.unit}${firstPrice?.toFixed(2) ?? '—'}`, color: '#94A3B8' },
            { label: 'DATA PTS',   value: `${computedData.length}`,  color: '#94A3B8' },
          ].map((s, i) => (
            <div key={s.label} style={{
              flex: 1, padding: '7px 0', textAlign: 'center',
              borderRight: i < 3 ? '1px solid #1E3050' : 'none',
            }}>
              <div style={{ color: '#4A6A96', fontSize: 10, marginBottom: 2 }}>{s.label}</div>
              <div style={{ color: s.color, fontFamily: 'monospace', fontSize: 12, fontWeight: 700 }}>{s.value}</div>
            </div>
          ))}
        </div>
      )}
    </article>
  )
}

// ─── Small toggle button ────────────────────────────────────────────────────

function ToggleBtn({ active, color, label, onClick }: { active: boolean; color: string; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: active ? `${color}22` : 'transparent',
        border: `1px solid ${active ? color : '#1E3050'}`,
        borderRadius: 5,
        color: active ? color : '#4A6A96',
        fontSize: 11, fontWeight: 700,
        padding: '4px 10px',
        cursor: 'pointer',
        transition: 'all 0.15s',
      }}
    >
      {label}
    </button>
  )
}

// ─── Custom Legend Toggle Button ────────────────────────────────────────────

function LegendToggle({ active, color, label, onClick, isDashed, isArea }: { active: boolean; color: string; label: string; onClick: () => void; isDashed?: boolean; isArea?: boolean }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        background: active ? 'rgba(30,48,80,0.3)' : 'transparent',
        border: `1px solid ${active ? '#1E3050' : 'transparent'}`,
        borderRadius: 4,
        padding: '3px 8px',
        color: active ? '#E8EEF7' : '#4A6A96',
        cursor: 'pointer',
        fontSize: 11,
        transition: 'all 0.15s',
      }}
    >
      <span style={{
        display: 'inline-block',
        width: 12,
        height: isArea ? 8 : 2,
        background: isArea ? color : (isDashed ? 'transparent' : color),
        borderTop: isDashed ? `2px dashed ${color}` : 'none',
        borderRadius: isArea ? 2 : 0,
      }} />
      <span>{label}</span>
    </button>
  )
}

// ─── Insights Panel Metric Row ──────────────────────────────────────────────

function MetricRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 12 }}>
      <span style={{ color: '#4A6A96' }}>{label}</span>
      <span style={{ color: color || '#E8EEF7', fontFamily: 'monospace', fontWeight: 700 }}>{value}</span>
    </div>
  )
}
