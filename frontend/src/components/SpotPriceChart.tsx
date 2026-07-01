import { useEffect, useState } from 'react'
import axios from 'axios'
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

interface Bar { timestamp: string; close: number }

// Intraday / spot session line for one product. WTI/Brent stream from the live
// 15-min candle DB; RBOB/HO/NG from 5-min yfinance — see /api/prices/{sym}/intraday.
export default function SpotPriceChart({ symbol, unit = '$' }: { symbol: string; unit?: string }) {
  const [bars, setBars] = useState<Bar[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true)
    axios.get(`${API_BASE}/api/prices/${symbol}/intraday?limit=390`)
      .then(res => { if (alive) setBars(res.data?.data || []) })
      .catch(() => { if (alive) setBars([]) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [symbol])

  const first = bars.length ? bars[0].close : null
  const last = bars.length ? bars[bars.length - 1].close : null
  const chg = first != null && last != null ? last - first : null
  const chgPct = chg != null && first ? (chg / first) * 100 : null
  const up = (chg ?? 0) >= 0
  const color = up ? '#10b981' : '#ef4444'

  // Multi-session spans get date labels; a single session gets HH:MM.
  const multiDay = bars.length > 1 && bars[0].timestamp.slice(0, 10) !== bars[bars.length - 1].timestamp.slice(0, 10)
  const fmtTick = (t: string) => multiDay ? t.slice(5, 10) : t.slice(11, 16)

  return (
    <div className="bg-energy-bg-tertiary p-4 rounded-lg">
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="text-sm font-bold text-slate-300">{symbol} Spot</h3>
        <div className="text-right">
          <span className="font-mono text-slate-100 text-sm">{last != null ? `${unit}${last.toFixed(2)}` : '—'}</span>
          {chgPct != null && (
            <span className={`ml-2 text-xs font-medium ${up ? 'text-emerald-400' : 'text-red-400'}`}>
              {up ? '▲' : '▼'} {Math.abs(chgPct).toFixed(2)}%
            </span>
          )}
        </div>
      </div>
      {loading ? (
        <div className="h-[220px] flex items-center justify-center text-slate-500 text-sm">Loading…</div>
      ) : bars.length === 0 ? (
        <div className="h-[220px] flex items-center justify-center text-slate-500 text-sm">No intraday data.</div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={bars} margin={{ top: 6, right: 8, bottom: 0, left: -6 }}>
            <defs>
              <linearGradient id={`spot_${symbol}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.28} />
                <stop offset="95%" stopColor={color} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis dataKey="timestamp" tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false}
                   interval="preserveStartEnd" minTickGap={44} tickFormatter={fmtTick} />
            <YAxis domain={['auto', 'auto']} tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false}
                   width={52} tickFormatter={(v: number) => `${unit}${v.toFixed(v >= 100 ? 0 : 2)}`} />
            <Tooltip
              contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
              labelFormatter={(t: string) => t}
              formatter={(v: any) => [`${unit}${Number(v).toFixed(2)}`, 'Price']}
            />
            <Area type="monotone" dataKey="close" stroke={color} strokeWidth={2} fill={`url(#spot_${symbol})`} dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
