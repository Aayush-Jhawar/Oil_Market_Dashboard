import { useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import { ResponsiveContainer, LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, ReferenceLine } from 'recharts'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''
const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1)
const PRODUCTS = ['WTI', 'Brent', 'RBOB', 'HO', 'GO']

// An interactive calendar-spread / butterfly curve chart. The legs (2 = spread,
// 3 = fly) and product are selectable from the card's TITLE row, and the chart +
// z-score update live from /api/analytics/curve-structure.
export default function CurveChartCard({
  initialSymbol = 'WTI', initialLegs = [1, 2],
}: { initialSymbol?: string; initialLegs?: number[] }) {
  const [symbol, setSymbol] = useState(initialSymbol)
  const [legs, setLegs] = useState<number[]>(initialLegs)
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const mode: 'spread' | 'fly' = legs.length === 2 ? 'spread' : 'fly'
  const setMode = (m: 'spread' | 'fly') => setLegs(m === 'spread' ? [1, 2] : [1, 2, 3])
  const setLeg = (i: number, v: number) => setLegs(prev => prev.map((l, idx) => (idx === i ? v : l)))

  const legsKey = legs.join(',')
  useEffect(() => {
    let alive = true
    setLoading(true)
    axios.get(`${API_BASE}/api/analytics/curve-structure`, { params: { symbol, legs: legsKey } })
      .then(res => { if (alive) setData(res.data?.data || null) })
      .catch(() => { if (alive) setData(null) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [symbol, legsKey])

  const formula = mode === 'spread' ? `M${legs[0]}−M${legs[1]}` : `M${legs[0]}−2·M${legs[1]}+M${legs[2]}`
  const z = data?.zscore
  const zColor = z == null ? '#94a3b8' : Math.abs(z) > 2 ? '#ef4444' : Math.abs(z) > 1 ? '#f59e0b' : '#10b981'
  const history = data?.history || []

  const yDomain = useMemo(() => {
    if (!history.length) return ['auto', 'auto'] as any
    const vals = history.map((h: any) => h.value)
    const lo = Math.min(...vals, data?.current ?? Infinity)
    const hi = Math.max(...vals, data?.current ?? -Infinity)
    const pad = (hi - lo) * 0.08 || 1
    return [lo - pad, hi + pad]
  }, [history, data])

  const selCls = 'bg-slate-900 border border-slate-700 rounded-md text-slate-100 text-xs px-1.5 py-1 outline-none'

  return (
    <div className="bg-energy-bg-tertiary p-4 rounded-lg">
      {/* Title row = the selectors */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-2 mb-3">
        <select value={symbol} onChange={e => setSymbol(e.target.value)} className={`${selCls} font-semibold`}>
          {PRODUCTS.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        <div className="flex gap-1">
          {(['spread', 'fly'] as const).map(m => (
            <button key={m} onClick={() => setMode(m)}
              className={`px-2 py-1 rounded-md text-xs font-medium capitalize transition ${
                mode === m ? 'bg-sky-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>
              {m}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          {legs.map((leg, i) => (
            <select key={i} value={leg} onChange={e => setLeg(i, Number(e.target.value))} className={selCls}>
              {MONTHS.map(m => <option key={m} value={m}>M{m}</option>)}
            </select>
          ))}
        </div>
        <div className="ml-auto text-right">
          <span className="font-mono text-slate-100 text-sm">{data?.current != null ? data.current.toFixed(3) : '—'}</span>
          {z != null && (
            <span className="ml-2 text-xs font-semibold" style={{ color: zColor }}>z {z.toFixed(2)}</span>
          )}
        </div>
      </div>

      {loading ? (
        <div className="h-[220px] flex items-center justify-center text-slate-500 text-sm">Loading…</div>
      ) : history.length === 0 ? (
        <div className="h-[220px] flex items-center justify-center text-slate-500 text-xs px-4 text-center">
          {data?.current != null ? 'Live value only — no curve history for this product.' : 'No data for this structure.'}
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={history} margin={{ top: 6, right: 8, bottom: 0, left: -6 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
            <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 10 }} minTickGap={44}
                   tickFormatter={(d: string) => d?.slice(2, 7)} />
            <YAxis domain={yDomain} tick={{ fill: '#64748b', fontSize: 10 }} width={46}
                   tickFormatter={(v: number) => v.toFixed(1)} />
            <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                     formatter={(v: any) => [Number(v).toFixed(3), formula]} />
            {data?.mean != null && <ReferenceLine y={data.mean} stroke="#eab308" strokeDasharray="4 3" strokeWidth={1} />}
            {data?.current != null && <ReferenceLine y={data.current} stroke="#38bdf8" strokeWidth={1} />}
            <Line type="monotone" dataKey="value" stroke="#94a3b8" strokeWidth={1.7} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      )}

      <div className="flex justify-between items-center text-[11px] text-slate-500 mt-2">
        <span className="font-mono">{formula}</span>
        <span>
          {data?.percentile != null && <>pctile {data.percentile.toFixed(0)}% · </>}
          {data?.mean != null && <>μ {data.mean.toFixed(2)} · </>}
          <span className="text-sky-400">blue = live</span> · <span className="text-yellow-500">dashed = mean</span>
        </span>
      </div>
    </div>
  )
}
