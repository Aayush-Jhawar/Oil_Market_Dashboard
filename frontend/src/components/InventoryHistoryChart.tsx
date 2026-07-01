import { useEffect, useState } from 'react'
import axios from 'axios'
import {
  ResponsiveContainer, ComposedChart, Area, Line, CartesianGrid, XAxis, YAxis, Tooltip, Legend,
} from 'recharts'
import Card from './shared/Card'

// Weekly EIA stock series with a 5-year seasonal band. This is the classic
// storage read: is the current year rich or cheap vs the seasonal norm?
const SERIES: { key: string; label: string }[] = [
  { key: 'crude', label: 'Crude' },
  { key: 'cushing', label: 'Cushing' },
  { key: 'gasoline', label: 'Gasoline' },
  { key: 'distillate', label: 'Distillate' },
]

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

interface BandPoint { week: number; min: number; max: number; avg: number; current: number | null }

export default function InventoryHistoryChart() {
  const [series, setSeries] = useState('crude')
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true)
    axios.get(`${API_BASE}/api/eia/history?series=${series}`)
      .then(res => { if (alive && res.data?.data) setData(res.data.data) })
      .catch(() => { if (alive) setData(null) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [series])

  const band: BandPoint[] = data?.seasonal_band || []
  const chart = band.map(p => ({
    week: p.week,
    range: [p.min, p.max] as [number, number],
    avg: p.avg,
    current: p.current,
  }))

  const latest = data?.latest_value ?? null
  const avg5 = data?.five_year_avg ?? null
  const delta = latest != null && avg5 != null ? latest - avg5 : null
  const deltaPct = delta != null && avg5 ? (delta / avg5) * 100 : null
  const unit = data?.unit || ''

  return (
    <Card title="EIA Inventory vs 5-Year Seasonal Band">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div className="flex gap-1.5">
          {SERIES.map(s => (
            <button
              key={s.key}
              onClick={() => setSeries(s.key)}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium transition ${
                series === s.key ? 'bg-sky-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
              }`}
            >{s.label}</button>
          ))}
        </div>
        {latest != null && (
          <div className="text-right text-xs">
            <span className="text-slate-400">Latest </span>
            <span className="font-mono text-slate-100">{latest.toLocaleString()} {unit}</span>
            {delta != null && (
              <span className={`ml-2 font-medium ${delta < 0 ? 'text-emerald-400' : 'text-amber-400'}`}>
                {delta > 0 ? '+' : ''}{delta.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                {deltaPct != null && ` (${deltaPct > 0 ? '+' : ''}${deltaPct.toFixed(1)}%)`} vs 5yr
              </span>
            )}
          </div>
        )}
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center text-slate-500 text-sm">Loading…</div>
      ) : chart.length === 0 ? (
        <div className="h-64 flex items-center justify-center text-slate-500 text-sm">No history available.</div>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={chart} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="week" tick={{ fill: '#94a3b8', fontSize: 11 }}
                   label={{ value: 'Week of year', position: 'insideBottom', offset: -2, fill: '#64748b', fontSize: 11 }} />
            <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} width={54}
                   domain={['auto', 'auto']} tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : `${v}`} />
            <Tooltip
              contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
              labelFormatter={(w) => `Week ${w}`}
              formatter={(val: any, name: string) => {
                if (name === '5yr range' && Array.isArray(val)) return [`${val[0].toLocaleString()} – ${val[1].toLocaleString()}`, name]
                return [typeof val === 'number' ? val.toLocaleString() : val, name]
              }}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Area type="monotone" dataKey="range" name="5yr range" stroke="none" fill="#334155" fillOpacity={0.5} />
            <Line type="monotone" dataKey="avg" name="5yr avg" stroke="#eab308" strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
            <Line type="monotone" dataKey="current" name="Current year" stroke="#38bdf8" strokeWidth={2.2} dot={false} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      )}
      <div className="text-[11px] text-slate-500 mt-2">
        Shaded band = 5-year weekly min–max · dashed = 5-year average · blue = current year. Below the band = tight (bullish), above = ample (bearish).
      </div>
    </Card>
  )
}
